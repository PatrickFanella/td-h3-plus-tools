#!/usr/bin/env python3
"""Build and verify a receive-only TD-H3 Plus image from a factory backup."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from chirp import chirp_common

from h3plus_read_backup import load_test_driver


ALLOWED_CHANGED_RANGES = (
    (0x0008, 0x0C88, "channel records"),
    (0x0D48, 0x1388, "channel names"),
    (0x1908, 0x1921, "used flags"),
    (0x1928, 0x1941, "scan flags"),
)
SETTINGS_RANGE = (0x0CA8, 0x0D48)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def allowed_offset(offset: int) -> bool:
    return any(start <= offset < stop for start, stop, _ in ALLOWED_CHANGED_RANGES)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--driver", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    driver_path = args.driver.resolve(strict=True)
    factory_path = args.factory.resolve(strict=True)
    plan_path = args.plan.resolve(strict=True)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    plan = json.loads(plan_path.read_text())
    channels = plan["channels"]
    numbers = [item["number"] for item in channels]
    names = [item["name"] for item in channels]
    if len(numbers) != len(set(numbers)) or len(names) != len(set(names)):
        raise ValueError("Channel numbers and names must be unique")
    if any(not 1 <= number <= 199 for number in numbers):
        raise ValueError("Channel numbers must be within 1..199")
    if any(len(name) > 8 for name in names):
        raise ValueError("Channel names must be at most eight characters")
    if any(item["mode"] not in {"FM", "AM"} for item in channels):
        raise ValueError("Only FM and AM modes are supported by this plan")

    module = load_test_driver(driver_path)
    radio = module.TDH3_Plus(None)
    radio.load_mmap(str(factory_path))
    original = radio.get_mmap().get_byte_compatible().get_packed()

    # Remove every factory memory, including stale channel names and scan flags.
    for number in range(1, 200):
        empty = chirp_common.Memory(number=number, empty=True)
        radio.set_memory(empty)
        radio._get_nam(number).fill_raw(b"\xFF")
        radio._memobj.scanadd[number - 1] = False

    low_power = module.TDH3_Plus._tx_power[0]
    for item in channels:
        memory = chirp_common.Memory()
        memory.number = item["number"]
        memory.name = item["name"]
        memory.freq = round(item["frequency_mhz"] * 1_000_000)
        memory.mode = item["mode"]
        memory.duplex = "off"
        memory.offset = 0
        memory.tmode = ""
        memory.power = low_power
        memory.skip = "" if item["scan"] else "S"
        memory.empty = False
        radio.set_memory(memory)

    candidate = radio.get_mmap().get_byte_compatible().get_packed()
    if len(candidate) != len(original):
        raise RuntimeError("Candidate size differs from the factory image")

    changed = [index for index, pair in enumerate(zip(original, candidate)) if pair[0] != pair[1]]
    unexpected = [offset for offset in changed if not allowed_offset(offset)]
    settings_start, settings_stop = SETTINGS_RANGE
    if original[settings_start:settings_stop] != candidate[settings_start:settings_stop]:
        raise RuntimeError("Radio-wide settings bytes changed")
    if unexpected:
        sample = ", ".join(f"0x{x:04X}" for x in unexpected[:20])
        raise RuntimeError(f"Unexpected changed byte offsets: {sample}")

    # Decode every requested memory again and enforce the receive-only invariant.
    decoded = []
    for expected in channels:
        memory = radio.get_memory(expected["number"])
        actual = {
            "number": memory.number,
            "name": memory.name,
            "frequency_hz": memory.freq,
            "mode": memory.mode,
            "duplex": memory.duplex,
            "offset_hz": memory.offset,
            "tone_mode": memory.tmode,
            "power": str(memory.power),
            "skip": memory.skip,
        }
        wanted = {
            "number": expected["number"],
            "name": expected["name"],
            "frequency_hz": round(expected["frequency_mhz"] * 1_000_000),
            "mode": expected["mode"],
            "duplex": "off",
            "offset_hz": 0,
            "tone_mode": "",
            "power": "Low",
            "skip": "" if expected["scan"] else "S",
        }
        if actual != wanted:
            raise RuntimeError(f"Memory {memory.number} failed validation: {actual!r} != {wanted!r}")
        decoded.append(actual)

    populated = [radio.get_memory(number) for number in range(1, 200)]
    populated = [memory for memory in populated if not memory.empty]
    if len(populated) != len(channels):
        raise RuntimeError(f"Expected {len(channels)} populated memories; found {len(populated)}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = f"td_h3_plus-60515-receive-only-{timestamp}"
    raw_path = output_dir / f"{base}.raw.bin"
    image_path = output_dir / f"{base}.img"
    manifest_path = output_dir / f"{base}.json"
    raw_path.write_bytes(candidate)
    radio.save_mmap(str(image_path))

    by_range = {}
    for start, stop, label in ALLOWED_CHANGED_RANGES:
        by_range[label] = sum(start <= offset < stop for offset in changed)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "receive-only starter image; transmit disabled on every populated memory",
        "driver_path": str(driver_path),
        "driver_sha256": sha256(driver_path.read_bytes()),
        "factory_image": str(factory_path),
        "factory_raw_sha256": sha256(original),
        "plan": str(plan_path),
        "plan_sha256": sha256(plan_path.read_bytes()),
        "candidate_raw_file": raw_path.name,
        "candidate_raw_size_bytes": len(candidate),
        "candidate_raw_sha256": sha256(candidate),
        "candidate_image_file": image_path.name,
        "candidate_image_sha256": sha256(image_path.read_bytes()),
        "populated_channel_count": len(decoded),
        "receive_only_validation": {
            "all_duplex_off": all(item["duplex"] == "off" for item in decoded),
            "all_tone_modes_empty": all(item["tone_mode"] == "" for item in decoded),
            "all_power_low": all(item["power"] == "Low" for item in decoded)
        },
        "binary_diff_validation": {
            "changed_byte_count": len(changed),
            "changed_bytes_by_allowed_range": by_range,
            "unexpected_changed_byte_count": len(unexpected),
            "radio_wide_settings_0x0ca8_0x0d47_unchanged": True
        },
        "channels": decoded
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    for path in (raw_path, image_path, manifest_path):
        os.chmod(path, 0o600)

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
