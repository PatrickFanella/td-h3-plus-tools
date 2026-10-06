# Native TD-H3 Plus firmware tool

`h3plus_firmware.py` implements the application-update protocol from
<https://web.odmaster.net/ruoyi/firmwareUpgrade.js>. The source snapshot is saved
at `backups/firmware-1.0.50/official-firmwareUpgrade.js`.

This is an experimental Linux tool, not a successful hardware-qualified flasher.
It uses the CH340 cable at 1,000,000 baud, 8 data bits, no parity, 2 stop bits,
and no flow control. It requires Python, pyserial, and `fuser`. It does not
implement the radio's USB-C update protocol or a Windows compatibility layer.

## Current evidence: September 24, 2026

Eleven offline tests passed, including command comparisons against the saved
vendor JavaScript, fragmented frames, malformed-frame recovery, real deadlines,
image/geometry checks, simulated sector updates, and write-failure behavior.
The simulator validates the implementation's sequencing; it does not demonstrate
that the physical radio accepts a flash.

The first native hardware probe received 21 bytes beginning `aa551200`. The
header declares an 18-byte payload, which requires a 24-byte complete frame.
The read stopped after three seconds without a valid packet. Only DEVICE_INIT
was sent. No erase, firmware write, or reboot command was sent. The port closed.

Capture: `backups/firmware-1.0.50/native-updater-probe-20260924.jsonl`.
Firmware upgrade, SDK response, flash geometry, and CRC reads remain unverified
on the physical update target.

## Commands

Place the original update target in the vendor-specified update mode, close
other applications holding its serial port, and use a new log filename each run.
The script refuses to overwrite logs.

```sh
rtk proxy python3 tools/h3plus_firmware.py probe --log backups/firmware-1.0.50/probe-new.jsonl
```

`probe` sends DEVICE_INIT for `app_dir_head` and, only after a valid reply,
DEVICE_CHECK. It sends no flash erase/write commands.

`plan` also validates the firmware SHA-256 and reported application geometry,
reads application-sector CRCs, and logs which sectors differ. It does not erase,
write, or reboot:

```sh
rtk proxy python3 tools/h3plus_firmware.py plan \
  --firmware 'H3 Plus 1.0.50-Update-Kendwood/TD-H3-PlusV1.0.50.bin' \
  --log backups/firmware-1.0.50/plan-new.jsonl
```

`flash` is implemented but has not been run against hardware. Before using it,
obtain and review a successful probe and plan for this physical TD-H3 Plus.
It repeats initialization and device checks before erasing. It accepts only the
reviewed V1.0.50 image with SHA-256
`0dd16ac8a26b58ef62c4681ac8ee018cfd6a276b81eb2049b33f834da016b40e`.
It requires 4096-byte erase sectors and a nonzero application region outside
the first 64 KiB. Unknown geometry stops the operation rather than guessing.

The writer follows the vendor order: erase application sector zero, update
changed later sectors, then write sector zero last. Writes use 1024-byte chunks.
Each written sector and the entire application are checked through the radio's
CRC command before a reboot is requested. A sent reboot does not prove a normal
boot or firmware version; those require a separate check.

There is no U-Boot update, checksum bypass, automatic destructive retry, or
automatic recovery after an interrupted flash. The protocol lacks sequence IDs;
on an ambiguous response the tool stops rather than accepting a late reply to a
different command. A failure after an erase may leave the application incomplete.
The existing CHIRP configuration backup is not a firmware recovery image.

## Offline validation

```sh
rtk proxy python3 -m unittest discover -s tools -p test_h3plus_firmware.py -v
```

The tests use the saved vendor JavaScript and firmware package, Node.js for
command comparison, and simulated transports. They never open a serial device.
