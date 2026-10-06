#!/usr/bin/python
"""Read a radio on Soyuz using the existing local CHIRP driver over SSH."""
import hashlib
import json
import os
from pathlib import Path
import select
import shlex
import subprocess
import time
from datetime import datetime, timezone

from h3plus_read_backup import ALLOWED_MODELS, load_test_driver

REMOTE = r'''
import os, sys, select, termios, tty, fcntl
fd = os.open('/dev/cu.usbserial-120', os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
old = termios.tcgetattr(fd)
try:
    fcntl.ioctl(fd, termios.TIOCEXCL)
    tty.setraw(fd)
    attrs = termios.tcgetattr(fd)
    attrs[2] |= termios.CLOCAL | termios.CREAD
    attrs[4] = attrs[5] = termios.B38400
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)
    print('READY', file=sys.stderr, flush=True)
    while True:
        ready, _, _ = select.select([fd, 0], [], [], 60)
        if not ready:
            break
        if 0 in ready:
            data = os.read(0, 4096)
            if not data:
                break
            while data:
                _, writable, _ = select.select([], [fd], [], 5)
                if not writable:
                    raise TimeoutError('serial write timeout')
                data = data[os.write(fd, data):]
        if fd in ready:
            data = os.read(fd, 4096)
            if data:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
finally:
    termios.tcsetattr(fd, termios.TCSANOW, old)
    os.close(fd)
'''


class ReadOnlyPipe:
    timeout = 1
    port = '/dev/cu.usbserial-120'

    def __init__(self):
        self.proc = subprocess.Popen(
            ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
             'soyuz', 'python3 -u -c ' + shlex.quote(REMOTE)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0)
        ready, _, _ = select.select([self.proc.stderr], [], [], 15)
        if not ready or self.proc.stderr.readline().strip() != b'READY':
            self.proc.terminate()
            raise RuntimeError('Remote serial bridge did not become ready')

    def write(self, data):
        allowed = data in (b'PVOJH\\\x14', b'\x02', b'\x06', b'E')
        allowed |= (len(data) == 4 and data[:1] == b'R'
                    and data[3] == 32
                    and int.from_bytes(data[1:3], 'big') < 8192
                    and int.from_bytes(data[1:3], 'big') % 32 == 0)
        if not allowed:
            raise RuntimeError('Blocked non-read command: ' + data.hex())
        self.proc.stdin.write(data)
        self.proc.stdin.flush()
        return len(data)

    def read(self, count):
        result = b''
        deadline = time.monotonic() + self.timeout
        while len(result) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            ready, _, _ = select.select([self.proc.stdout], [], [], remaining)
            if not ready:
                break
            chunk = os.read(self.proc.stdout.fileno(), count - len(result))
            if not chunk:
                raise RuntimeError('Remote serial bridge closed')
            result += chunk
        return result

    def log(self, message):
        pass

    def close(self):
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.terminate()


def main():
    root = Path(__file__).resolve().parent.parent
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = root / 'backups' / ('soyuz-programmed-radio-' + stamp)
    out.mkdir(mode=0o700, parents=True)
    driver = root / 'tools/vendor/tdh8_issue12216_attachment15686_beta08172605.py'
    module = load_test_driver(driver)
    pipe = ReadOnlyPipe()
    radio = None
    try:
        detected = module.TDH3_Plus.detect_from_serial(pipe)
        if detected.MODEL not in ALLOWED_MODELS:
            raise RuntimeError('Unexpected model: ' + detected.MODEL)
        radio = detected(pipe)
        radio.status_fn = lambda status: None
        radio.sync_in()
        raw = radio.get_mmap().get_byte_compatible().get_packed()
        (out / 'radio.raw.bin').write_bytes(raw)
        radio.save_mmap(str(out / 'radio.img'))
        memories = [radio.get_memory(n) for n in range(1, 200)]
        active = [m for m in memories if not m.empty]
        result = dict(status='pass', model=detected.MODEL, host='soyuz',
                      port='/dev/cu.usbserial-120', operation='configuration download only',
                      raw_bytes=len(raw), raw_sha256=hashlib.sha256(raw).hexdigest(),
                      image_sha256=hashlib.sha256((out/'radio.img').read_bytes()).hexdigest(),
                      driver_sha256=hashlib.sha256(driver.read_bytes()).hexdigest(),
                      programmed_memories=len(active),
                      channels=[dict(number=m.number, name=m.name, frequency=m.freq,
                                     duplex=m.duplex, skip=m.skip) for m in active])
        (out / 'manifest.json').write_text(json.dumps(result, indent=2)+'\n')
        for p in out.iterdir():
            p.chmod(0o600)
        print(json.dumps({k:v for k,v in result.items() if k != 'channels'}, indent=2))
        print('Backup: ' + str(out))
    except Exception as error:
        (out / 'failure.json').write_text(json.dumps(dict(error=str(error)))+'\n')
        raise
    finally:
        try:
            if radio is not None:
                module._exit_write_block(radio)
        finally:
            pipe.close()


if __name__ == '__main__':
    main()
