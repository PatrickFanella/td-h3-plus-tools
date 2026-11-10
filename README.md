# TD-H3 Plus Tools

Python scripts and channel plans for programming a TIDRADIO TD-H3 Plus
handheld radio from Linux. They read and back up the radio, build one image
per scan profile from a channel plan, check each image against the plan before
upload, and include an experimental application-firmware updater.

These are experimental tools made for one radio. The channel plans list
repeaters and services around ZIP code 60515 (the western Chicago suburbs), so
they are useful elsewhere only as examples. The firmware updater has never
completed a flash on real hardware.

## Before you transmit

Do not transmit until the FCC has granted your amateur licence and it appears
in ULS. The licensed-ready plan enables transmit only on selected 2 m and 70 cm
amateur memories, all at Low power. Aviation, railroad, NOAA, marine, MURS and
FRS/GMRS memories are receive-only in every profile, and the 1.25 m repeaters
are receive-only too.

## Features

- **Read-only probe and backup** of the radio over its programming cable,
  using CHIRP and the bundled beta TD-H3 Plus driver.
- **Channel plan**: [channel-plan-60515-licensed-ready.json](channel-plan-60515-licensed-ready.json)
  holds 94 memories with frequencies, offsets, tones, categories, scan-profile
  membership and sources. `tools/generate_licensed_plan.py` regenerates it.
- **Scan profiles**: the radio has one scan list and no banks, so each profile
  is a separate image that changes only which memories are scanned. Profiles:
  `daily`, `ham`, `weather`, `rail`, `air`, `satellite`, `general` and
  `all_voice`. Continuous channels (NOAA Weather Radio, ATIS) stay directly
  selectable but are left out of scans.
- **Image builder** that starts from your factory backup, keeps radio-wide
  settings byte for byte, and checks every memory against the plan.
- **Guarded upload**: the licensed-ready uploader refuses an image that does
  not match the plan or the expected SHA-256, changes radio-wide settings,
  enables non-amateur transmit, uses more than Low power, or transmits outside
  the 2 m and 70 cm limits.
- **Image inspector** that decodes a saved image without a radio attached.
- **Experimental firmware updater** (`tools/h3plus_firmware.py`) that
  implements the vendor's application-update protocol over the CH340 cable.
  See [tools/H3PLUS-FIRMWARE.md](tools/H3PLUS-FIRMWARE.md) before using it.

The memory layout and profile table are in the
[60515 guide](TD-H3-PLUS-60515-GUIDE.md).

## Requirements

- Python 3
- [CHIRP](https://chirpmyradio.com/) installed so that `import chirp` works
- The programming cable on a serial port such as `/dev/ttyUSB0`
- `pyserial` and `fuser` for the firmware updater

Every script that talks to the radio takes the driver with
`--driver tools/vendor/tdh8_issue12216_attachment15686_beta08172605.py`.

## Usage

Run the scripts from the repository root. Each one prints its options with
`--help`.

```sh
DRIVER=tools/vendor/tdh8_issue12216_attachment15686_beta08172605.py

# Identify the radio without changing it
python3 tools/h3plus_probe.py --port /dev/ttyUSB0 --driver "$DRIVER" --result probe.json

# Back up the radio; this factory image is the base for every build
python3 tools/h3plus_read_backup.py --port /dev/ttyUSB0 --driver "$DRIVER" --output-dir backups/

# Build one image per scan profile and a manifest with each image's SHA-256
python3 tools/h3plus_build_profile_images.py --driver "$DRIVER" \
  --factory backups/<backup>.img --plan channel-plan-60515-licensed-ready.json \
  --output-dir builds/licensed-ready

# Decode an image without a radio
python3 tools/h3plus_inspect_image.py --driver "$DRIVER" --image builds/licensed-ready/<profile>.img

# Upload one profile
python3 tools/h3plus_upload_licensed_image.py --port /dev/ttyUSB0 --driver "$DRIVER" \
  --factory backups/<backup>.img --plan channel-plan-60515-licensed-ready.json \
  --profile daily --image builds/licensed-ready/<profile>.img \
  --expected-raw-sha256 <sha256 from the build manifest> \
  --receipt upload-receipt.json --acknowledge-no-transmit-until-licensed
```

After an upload, read the radio back with `h3plus_read_backup.py` and compare
its SHA-256 with the profile's expected hash. A finished upload only shows the
write completed; the readback shows what the radio kept.

To scan on the radio, press `VFO/MR` until it is in channel mode, hold
`3 / SCAN` for more than two seconds, and press `EXIT` to stop.

Backups, built images and receipts are not committed to the repository.

## Project layout

```text
channel-plan-60515-licensed-ready.json   current 94-memory plan with profiles
channel-plan-60515.json                  earlier receive-only starter plan
TD-H3-PLUS-60515-GUIDE.md                profiles, memory blocks and transmit policy
tools/                                   probe, backup, build, inspect, upload and firmware scripts
tools/vendor/                            beta CHIRP driver for the TD-H3 Plus
```

## Contributing

Report bugs and request features in
[GitHub issues](https://github.com/subculture-collective/td-h3-plus-tools/issues).
For code, open a pull request on GitHub against `main`. There is no CI on this
repository.

## License

Original contributions are licensed under the GNU General Public License,
version 3 or any later version (`GPL-3.0-or-later`). See [LICENSE](LICENSE).
The CHIRP driver in `tools/vendor/` is GPL-2.0-or-later and keeps its
upstream attribution and licence header.
