"""Offline tests only; no real serial devices are opened."""
import json
from pathlib import Path
import struct
import subprocess
import time
import unittest
from unittest.mock import patch

import h3plus_firmware as fw

ROOT = Path(__file__).resolve().parents[1]


class FakePort:
    def __init__(self, response=b""):
        self.response = response
        self.timeout = 0.01
        self.sent = []

    def reset_input_buffer(self):
        pass

    def write(self, data):
        self.sent.append(data)
        return len(data)

    def read(self, count):
        if self.response:
            value, self.response = self.response[:3], self.response[3:]
            return value
        time.sleep(self.timeout)
        return b""


class SimulatedRadio:
    def __init__(self, data, base=65536, fail_write=False):
        self.flash = bytearray(data)
        self.base = base
        self.commands = []
        self.fail_write = fail_write

    def request(self, opcode, body=b"", **kwargs):
        self.commands.append((opcode, body))
        if opcode == fw.CRC:
            address, length, size = struct.unpack("<III", body)
            offset = address - self.base
            values = [fw.crc16(self.flash[i:i + size]) for i in range(offset, offset + length, size)]
            return struct.pack(f"<{len(values)}H", *values)
        address, n = struct.unpack("<II", body[:8])
        offset = address - self.base
        if opcode == fw.ERASE:
            assert n == 2 and offset >= 0 and offset % 4096 == 0
            self.flash[offset:offset + 4096] = b"\xff" * 4096
        elif opcode == fw.WRITE:
            if self.fail_write:
                raise TimeoutError("Simulated write acknowledgement lost")
            assert 0 <= offset <= len(self.flash) - n and n <= 1024
            # NOR writes can only clear bits without an erase.
            self.flash[offset:offset + n] = bytes(a & b for a, b in zip(self.flash[offset:offset+n], body[8:]))
        else:
            raise AssertionError(f"Unexpected command {opcode}")
        return b""


class FirmwareTests(unittest.TestCase):
    def test_frames_match_vendor_javascript(self):
        source = (ROOT / "backups/firmware-1.0.50/official-firmwareUpgrade.js").read_text()
        names = ("crc16", "makeCommand", "makeDeviceInitCmd", "makeDeviceCheckCmd",
                 "makeEraseCmd", "makeWriteCmd", "makeFlashCRCCmd", "makeRebootCmd")
        functions = []
        for name in names:
            start = source.index("function " + name + "(")
            # Vendor top-level function closing braces start in column zero.
            end = source.index("\n}", start) + 2
            functions.append(source[start:end])
        js = "const JL_SU_RSP={SUCC:0}; const JL_SU_CMD={DEVICE_INIT:192,DEVICE_CHECK:193,ERASE:194,WRITE:195,FLASH_CRC:196,REBOOT:202};\n"
        js += "\n".join(functions)
        js += "\nconsole.log(JSON.stringify([makeDeviceInitCmd(12345678,'app_dir_head',0),makeDeviceCheckCmd(12345678,0x12345678),makeEraseCmd(12345678,65536,2),makeWriteCmd(12345678,65536,new Uint8Array([1,2,3])),makeFlashCRCCmd(12345678,65536,65536,4096),makeRebootCmd(12345678)].map(x=>Buffer.from(x).toString('hex'))));"
        actual = json.loads(subprocess.check_output(["node", "-e", js], text=True))
        expected = [fw.frame(fw.INIT, b"app_dir_head".ljust(16, b"\0") + b"\0"),
                    fw.frame(fw.CHECK, struct.pack("<I", fw.SDK_ID)),
                    fw.frame(fw.ERASE, struct.pack("<II", 65536, 2)),
                    fw.frame(fw.WRITE, struct.pack("<II", 65536, 3) + bytes((1, 2, 3))),
                    fw.frame(fw.CRC, struct.pack("<III", 65536, 65536, 4096)), fw.frame(fw.REBOOT)]
        self.assertEqual(actual, [x.hex() for x in expected])

    def test_parser_fragmentation(self):
        raw = fw.frame(fw.INIT, bytes(16))
        for split in range(1, len(raw)):
            parser = fw.PacketParser()
            self.assertEqual(parser.feed(raw[:split]), [])
            self.assertEqual(parser.feed(raw[split:]), [bytes((fw.INIT, 0)) + bytes(16)])

    def test_bad_packet_followed_by_valid_packet(self):
        good = fw.frame(fw.CHECK, bytes(24))
        bad = bytearray(good)
        bad[8] ^= 1
        for prefix in (bad, b"\xaa\x55\xff\xff", b"\xaa\x55\x22\x00", b"noise"):
            self.assertEqual(fw.PacketParser().feed(prefix + good), [bytes((fw.CHECK, 0)) + bytes(24)])

    def test_saved_invalid_replies_never_accepted(self):
        directory = ROOT / "backups/firmware-1.0.50"
        captures = [json.loads((directory / "native-handshake.json").read_text())]
        captures += json.loads((directory / "native-rts-comparison.json").read_text())
        for capture in captures:
            self.assertEqual(fw.PacketParser().feed(bytes.fromhex(capture["response_hex"])), [])

    def test_empty_read_has_real_deadline(self):
        port = FakePort()
        start = time.monotonic()
        with self.assertRaises(TimeoutError):
            fw.Link(port, lambda *a, **k: None).request(fw.INIT, timeout=0.06)
        self.assertLess(time.monotonic() - start, 0.5)
        self.assertEqual(len(port.sent), 1)

    def test_fragmented_reply_through_transport(self):
        geometry = struct.pack("<IIII", 65536, 1048576, 65536, 4096)
        port = FakePort(fw.frame(fw.INIT, geometry))
        self.assertEqual(fw.initialize(fw.Link(port, lambda *a, **k: None)), fw.Geometry(65536,1048576,65536,4096))

    def test_error_status_and_wrong_opcode_stop(self):
        for packet in (fw.frame(fw.CHECK), fw.frame(fw.INIT, status=1), fw.frame(fw.INIT, b"x")):
            with self.assertRaises(RuntimeError):
                fw.Link(FakePort(packet), lambda *a, **k: None).request(fw.INIT)

    def test_geometry_and_image_admission(self):
        image = (ROOT / "H3 Plus 1.0.50-Update-Kendwood/TD-H3-PlusV1.0.50.bin").read_bytes()
        g = fw.Geometry(65536, 1048576, 65536, 4096)
        self.assertEqual(fw.prepare(image, g), image[65536:])
        for invalid in (fw.Geometry(0,1048576,65536,4096),fw.Geometry(65536,1048576,0,4096),
                        fw.Geometry(65536,1,65536,4096),fw.Geometry(65536,1048576,65536,256)):
            with self.assertRaises(ValueError):
                fw.prepare(image, invalid)
        with self.assertRaises(ValueError):
            fw.prepare(image[:-1], g)

    def test_simulated_flash_skips_matching_sectors_and_commits_zero_last(self):
        data = b"A" * 4096 + b"B" * 4096 + b"C" * 4096
        original = b"a" * 4096 + b"B" * 4096 + b"c" * 4096
        radio = SimulatedRadio(original)
        expected = [fw.crc16(data[i:i+4096]) for i in range(0,len(data),4096)]
        before = [fw.crc16(original[i:i+4096]) for i in range(0,len(data),4096)]
        fw.apply_application(radio, fw.Geometry(65536,1048576,65536,4096), data, expected, before, lambda *a, **k: None)
        self.assertEqual(radio.flash, data)
        writes = [struct.unpack_from("<I", b)[0] for op,b in radio.commands if op==fw.WRITE]
        self.assertEqual(writes[-4:], [65536+i*1024 for i in range(4)])
        self.assertFalse(any(65536+4096 <= x < 65536+8192 for x in writes))
        self.assertEqual(radio.commands[0][0], fw.ERASE)

    def test_write_failure_stops_without_retry_commit_or_reboot(self):
        radio = SimulatedRadio(bytes(8192), fail_write=True)
        data = b"a"*8192
        with self.assertRaises(TimeoutError):
            fw.apply_application(radio, fw.Geometry(65536,1048576,65536,4096), data,
                                 [fw.crc16(data[:4096])]*2, [0,0], lambda *a, **k: None)
        writes=[b for op,b in radio.commands if op==fw.WRITE]
        self.assertEqual(len(writes),1)
        self.assertGreaterEqual(struct.unpack_from("<I",writes[0])[0],65536+4096)
        self.assertNotIn(fw.REBOOT,[op for op,b in radio.commands])

    def test_matching_image_never_erased(self):
        radio=SimulatedRadio(bytes(4096))
        fw.apply_application(radio, fw.Geometry(65536,1048576,65536,4096), bytes(4096), [1], [1], lambda *a, **k: None)
        self.assertEqual(radio.commands,[])


if __name__ == "__main__":
    unittest.main()
