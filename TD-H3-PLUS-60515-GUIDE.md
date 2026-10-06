# TD-H3 Plus 60515 licensed-ready guide

## Installed state

The `ham` profile was uploaded on 2026-09-20 at 17:57 UTC and independently downloaded from the radio afterward. The retained 8,200-byte image matched the built candidate byte-for-byte with SHA-256 `77946f342fc626d345711284b77d8c3383d43e402b777757fb264246430e9a50`. Upload receipt: `backups/uploads/td_h3_plus-licensed-ready-ham-20260920.json`. Readback manifest: `backups/readbacks/licensed-ready-ham/td_h3_plus-factory-20260920T175735Z.json`. Saving this profile in ODmaster remains a manual step.

## Current configuration design

The master plan contains 94 memories. Every profile contains the same memories; a profile changes only which memories participate in channel scan.

| Profile | Scanned memories | Intended use |
| --- | ---: | --- |
| `daily` | 29 | Nearby repeaters and calling channels, primary BNSF channels, and useful tower/approach channels |
| `ham` | 23 | Local 2 m/70 cm repeaters and simplex, plus receive-only 1.25 m repeaters |
| `weather` | 4 | Selected local weather/ARES-capable repeaters |
| `rail` | 9 | BNSF, Eola yard, UP West, and CN railroad channels |
| `air` | 10 | DPA, Lewis, Aurora, guard, and Chicago approach voice channels |
| `satellite` | 5 | ISS and current FM amateur-satellite voice channels |
| `general` | 32 | Marine, MURS, and FRS/GMRS reception |
| `all_voice` | 74 | All non-continuous voice channels; slowest scan cycle |

The `daily` profile is the recommended default. NOAA Weather Radio and continuous ATIS channels remain directly selectable but are intentionally skipped during scans because a continuous carrier would stop the scanner every cycle.

## Transmit policy

- Do not transmit until the FCC has granted your amateur license and the grant appears in ULS.
- Transmit is enabled only on selected 144–148 MHz and 420–450 MHz amateur memories.
- Every transmit-capable memory is set to Low power.
- Repeaters use transmit CTCSS only; receive tone squelch is left open so a tone mismatch cannot hide traffic.
- The 1.25 m/220 MHz repeaters are receive-only because the beta driver cannot safely change the radio-wide 220 MHz transmit control.
- Aviation, railroad, NOAA, marine, MURS, and FRS/GMRS memories are hard receive-only in every profile.
- Satellite memories 32–35 contain the published cross-band uplink/downlink pairs, but should not be transmitted on until licensed and after learning satellite operating procedure and Doppler correction.

## Scanning on the radio

1. Press `VFO/MR` until the radio is in channel/MR mode.
2. Hold the `3 / SCAN` key for more than two seconds.
3. Use the up/down keys to change scan direction.
4. Press `EXIT` to stop.

The TD-H3 Plus driver exposes one scan-inclusion flag per memory and no banks or zones. Therefore, the active scan group is selected by loading one of the profile images over USB. Direct channel selection still works for all 94 memories regardless of the loaded scan profile.

## Channel blocks

| Memories | Contents |
| --- | --- |
| 1–20 | Local repeaters |
| 21–24 | Amateur calling/simplex and APRS receive |
| 30–38 | ISS, amateur satellites, and NOAA APT receive |
| 40–46 | NOAA Weather Radio |
| 50–58 | Railroad |
| 70–82 | Aviation |
| 90–94 | Marine receive |
| 100–104 | MURS receive |
| 110–131 | FRS/GMRS receive |

The authoritative machine-readable plan, including frequencies, offsets, tones, categories, profile membership, and sources, is `channel-plan-60515-licensed-ready.json`.

## Profile artifacts

The byte-verified images and their individual JSON manifests are in `builds/licensed-ready/`. The aggregate build manifest records every image hash and validation result.

To load a different profile, use `tools/h3plus_upload_licensed_image.py` with that profile's image and raw SHA-256 from the aggregate manifest. The uploader refuses an image that does not exactly match the plan, changes radio-wide settings, enables non-amateur transmit, uses power above Low, or permits transmit outside the configured 2 m/70 cm limits.

After every upload, read the radio back and compare its raw SHA-256 with the selected profile's expected hash. An upload receipt alone proves that the write command completed; the readback proves what the radio retained.

## Expanded vault documentation

The maintained operating guide is `/home/onnwee/Documents/ars-malefica/003 Resources/Systems/TD-H3 Plus Programming and ODmaster Guide.md`. The complete channel table, scan memberships, source register, and verified hashes are in `/home/onnwee/Documents/ars-malefica/003 Resources/Reference/TD-H3 Plus 60515 Channel and Profile Reference.md`. Both were reconciled against these artifacts on 2026-09-20.
