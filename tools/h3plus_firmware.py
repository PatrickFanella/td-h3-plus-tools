#!/usr/bin/env python3
"""Native TD-H3 Plus application updater; probe is the default.

Protocol source: https://web.odmaster.net/ruoyi/firmwareUpgrade.js
Reference snapshot: backups/firmware-1.0.50/official-firmwareUpgrade.js
Requires pyserial. No U-Boot update, automatic retry, or checksum bypass.
"""
from __future__ import annotations

import argparse
import binascii
from dataclasses import asdict, dataclass
import datetime
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time

KEY = 12345678
SDK_ID = 0x12345678
INIT, CHECK, ERASE, WRITE, CRC, REBOOT = 0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xCA
FIRMWARE_SHA = "0dd16ac8a26b58ef62c4681ac8ee018cfd6a276b81eb2049b33f834da016b40e"
PORT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"


def crc16(data: bytes) -> int:
    return binascii.crc_hqx(data, 0)


def crypt(data: bytes) -> bytes:
    key = struct.pack("<I", KEY)
    return bytes(value ^ key[i % 4] for i, value in enumerate(data))


def frame(opcode: int, body: bytes = b"", status: int = 0) -> bytes:
    payload = crypt(bytes((opcode, status)) + body)
    packet = b"\xaa\x55" + struct.pack("<H", len(payload)) + payload
    return packet + struct.pack("<H", crc16(packet))


class PacketParser:
    """Resynchronize only on a complete frame with a valid CRC; never repair bytes."""

    def __init__(self):
        self.buffer = bytearray()
        self.bad_crc = 0

    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        packets = []
        while True:
            found = False
            start = self.buffer.find(b"\xaa\x55")
            while start >= 0:
                if len(self.buffer) - start < 4:
                    break
                length = struct.unpack_from("<H", self.buffer, start + 2)[0]
                end = start + length + 6
                # Largest response used here is 16 CRCs plus opcode/status.
                if 2 <= length <= 34 and end <= len(self.buffer):
                    packet = self.buffer[start:end]
                    if crc16(packet[:-2]) == struct.unpack("<H", packet[-2:])[0]:
                        packets.append(crypt(packet[4:-2]))
                        del self.buffer[:end]
                        found = True
                        break
                    self.bad_crc += 1
                start = self.buffer.find(b"\xaa\x55", start + 1)
            if not found:
                # Bounded even under endless malformed input. A frame is <=40 bytes.
                if len(self.buffer) > 4096:
                    del self.buffer[:-40]
                return packets


class Link:
    def __init__(self, port, record):
        self.port = port
        self.record = record
        self.destructive_sent = False

    def request(self, opcode, body=b"", *, timeout=3.0, response_size=2):
        packet = frame(opcode, body)
        parser = PacketParser()
        self.port.reset_input_buffer()
        time.sleep(0.28 if len(packet) > 400 else 0.08)
        self.record("tx", opcode=opcode, hex=packet.hex())
        if opcode in (ERASE, WRITE):
            self.destructive_sent = True
        if self.port.write(packet) != len(packet):
            raise RuntimeError("Incomplete serial write; stopping without retry")
        if opcode == REBOOT:
            return b""
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            self.port.timeout = min(0.05, remaining)
            raw = self.port.read(256)
            if not raw:
                continue
            self.record("rx", hex=raw.hex())
            for payload in parser.feed(raw):
                if payload[0] != opcode:
                    raise RuntimeError(f"Unexpected response opcode {payload[0]:02x}")
                if payload[1] != 0:
                    raise RuntimeError(f"Radio rejected opcode {opcode:02x}: status {payload[1]}")
                if len(payload) != response_size:
                    raise RuntimeError(f"Unexpected response length {len(payload)} for {opcode:02x}")
                return payload[2:]
        self.record("timeout", opcode=opcode, retained_hex=parser.buffer.hex(),
                    bad_crc_observations=parser.bad_crc)
        raise TimeoutError(f"No valid response to {opcode:02x} within {timeout:g}s")


@dataclass(frozen=True)
class Geometry:
    file_offset: int
    capacity: int
    flash_offset: int
    erase_size: int


def initialize(link) -> Geometry:
    response = link.request(INIT, b"app_dir_head".ljust(16, b"\0") + b"\0",
                            response_size=18)
    return Geometry(*struct.unpack("<IIII", response))


def check_device(link) -> dict:
    response = link.request(CHECK, struct.pack("<I", SDK_ID), response_size=26)
    vid, pid, sdk = struct.unpack("<4s16sI", response)
    if sdk != SDK_ID:
        raise RuntimeError(f"Unrecognized SDK ID {sdk:08x}; no flash permitted")
    return {"vendor_hex": vid.hex(), "product_hex": pid.hex(), "sdk_id": sdk}


def prepare(image: bytes, geometry: Geometry) -> bytes:
    if hashlib.sha256(image).hexdigest() != FIRMWARE_SHA:
        raise ValueError("Only the reviewed TD-H3-Plus V1.0.50 image is accepted")
    g = geometry
    # Conservative admission until another geometry has independent evidence.
    if g.erase_size != 4096:
        raise ValueError("Unreviewed erase geometry; require 4096-byte sectors")
    if not 65536 <= g.file_offset < len(image) or g.file_offset % g.erase_size:
        raise ValueError("Invalid application file offset; U-Boot must be excluded")
    if g.flash_offset < 65536 or g.flash_offset % g.erase_size:
        raise ValueError("Invalid application flash offset; U-Boot must be excluded")
    data = image[g.file_offset:]
    data += b"\xff" * (-len(data) % g.erase_size)
    if len(data) > g.capacity or g.flash_offset + len(data) > 2**32:
        raise ValueError("Application exceeds radio-reported capacity or address range")
    return data


def chip_crcs(link, address: int, count: int, size: int) -> list[int]:
    result = []
    for start in range(0, count, 16):
        n = min(16, count - start)
        body = struct.pack("<III", address + start * size, n * size, size)
        raw = link.request(CRC, body, response_size=2 + 2 * n)
        result.extend(struct.unpack(f"<{n}H", raw))
    return result


def apply_application(link, geometry, data, expected, before, record):
    """Vendor order: erase sector zero, update later sectors, commit zero last."""
    g = geometry
    if len(expected) != len(before) or len(data) != len(expected) * g.erase_size:
        raise ValueError("Inconsistent application plan")
    if before == expected:
        record("already_matches")
        return

    def erase(i):
        record("erase", sector=i)
        link.request(ERASE, struct.pack("<II", g.flash_offset + i * g.erase_size, 2),
                     timeout=8.0)

    def write(i):
        record("write", sector=i)
        offset = i * g.erase_size
        for chunk_offset in range(0, g.erase_size, 1024):
            chunk = data[offset + chunk_offset:offset + chunk_offset + 1024]
            body = struct.pack("<II", g.flash_offset + offset + chunk_offset, len(chunk)) + chunk
            link.request(WRITE, body, timeout=5.0)
        actual = chip_crcs(link, g.flash_offset + offset, 1, g.erase_size)
        if actual != [expected[i]]:
            raise RuntimeError(f"Sector {i} failed CRC verification; stopped, no reboot")

    erase(0)
    for i in range(1, len(expected)):
        if expected[i] != before[i]:
            erase(i)
            write(i)
    write(0)
    if chip_crcs(link, g.flash_offset, len(expected), g.erase_size) != expected:
        raise RuntimeError("Final application CRC mismatch; stopped, no reboot")
    record("verified_application_crcs")


def open_serial(path):
    import fcntl
    import serial
    import termios

    path = str(Path(path).resolve(strict=True))
    # flock alone does not exclude browsers, which do not participate in it.
    holders = subprocess.run(["fuser", path], capture_output=True, text=True)
    if holders.returncode == 0:
        raise RuntimeError("Serial port is already open; close the other updater first")
    if holders.returncode != 1 or holders.stderr.strip():
        raise RuntimeError("Could not establish that the serial port is free")
    port = serial.Serial(port=None, baudrate=1000000, bytesize=8, parity="N",
                         stopbits=2, timeout=0.05, write_timeout=2,
                         xonxoff=False, rtscts=False, dsrdtr=False, exclusive=True)
    port.dtr = False
    port.rts = False
    port.port = path
    try:
        port.open()
        fcntl.ioctl(port.fileno(), termios.TIOCEXCL)
    except BaseException:
        port.close()
        raise
    return port


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("probe", "plan", "flash"), nargs="?", default="probe")
    parser.add_argument("--port", default=PORT)
    parser.add_argument("--firmware", type=Path)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    if args.mode != "probe" and args.firmware is None:
        parser.error("plan and flash require --firmware")
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("x", encoding="utf-8") as output:
        def record(event, **fields):
            output.write(json.dumps({"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                     "event": event, **fields}) + "\n")
            output.flush()
            if event not in ("tx", "rx"):
                print(event, json.dumps(fields), flush=True)

        link = None
        try:
            image = args.firmware.read_bytes() if args.firmware else None
            if image is not None and hashlib.sha256(image).hexdigest() != FIRMWARE_SHA:
                raise ValueError("Firmware SHA-256 does not match reviewed V1.0.50 package")
            record("start", mode=args.mode, port=args.port, baud=1000000, format="8N2",
                   dtr=False, rts=False, firmware_sha256=FIRMWARE_SHA if image else None)
            with open_serial(args.port) as port:
                link = Link(port, record)
                geometry = initialize(link)
                record("geometry", **asdict(geometry))
                identity = check_device(link)
                record("device_check", **identity)
                if args.mode != "probe":
                    data = prepare(image, geometry)
                    expected = [crc16(data[i:i + geometry.erase_size])
                                for i in range(0, len(data), geometry.erase_size)]
                    before = chip_crcs(link, geometry.flash_offset, len(expected), geometry.erase_size)
                    record("plan", sectors=len(expected), bytes=len(data),
                           changed=[i for i, pair in enumerate(zip(expected, before)) if pair[0] != pair[1]],
                           file_crcs=expected, chip_crcs=before)
                    if args.mode == "flash":
                        # Recheck geometry before any erase; abort any inconsistency.
                        if initialize(link) != geometry:
                            raise RuntimeError("Application geometry changed; refusing erase")
                        check_device(link)
                        apply_application(link, geometry, data, expected, before, record)
                        link.request(REBOOT)
                        record("reboot_sent", normal_boot_verified=False)
            record("complete", mode=args.mode)
            return 0
        except (Exception, KeyboardInterrupt) as error:
            record("stopped", error_type=type(error).__name__, error=str(error),
                   destructive_command_sent=bool(link and link.destructive_sent))
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
