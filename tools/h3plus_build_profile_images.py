#!/usr/bin/env python3
"""Build byte-verified TD-H3 Plus images for every scan profile in a plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from chirp import chirp_common

from h3plus_build_image import ALLOWED_CHANGED_RANGES, SETTINGS_RANGE, allowed_offset
from h3plus_read_backup import load_test_driver


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def in_tx_band(frequency_hz: int) -> bool:
    return 144_000_000 <= frequency_hz <= 148_000_000 or 420_000_000 <= frequency_hz <= 450_000_000


def actual_tx_frequency(memory) -> int | None:
    if memory.duplex == "off":
        return None
    if memory.duplex == "+":
        return memory.freq + memory.offset
    if memory.duplex == "-":
        return memory.freq - memory.offset
    if memory.duplex == "split":
        return memory.offset
    if memory.duplex == "":
        return memory.freq
    raise ValueError(f"Unsupported duplex value {memory.duplex!r}")


def expected_memory(item: dict, profile: str) -> dict:
    duplex = item["duplex"]
    if duplex == "split":
        offset_hz = round(item["tx_frequency_mhz"] * 1_000_000)
    else:
        offset_hz = round(item.get("offset_mhz", 0) * 1_000_000)
    return {
        "number": item["number"],
        "name": item["name"],
        "frequency_hz": round(item["frequency_mhz"] * 1_000_000),
        "mode": item["mode"],
        "duplex": duplex,
        "offset_hz": offset_hz,
        "tone_mode": item.get("tone_mode", ""),
        "tone_hz": float(item["tone_hz"]) if item.get("tone_mode") == "Tone" else None,
        "power": "Low",
        "skip": "" if profile in item["scan_profiles"] else "S",
    }


def decoded_memory(memory) -> dict:
    return {
        "number": memory.number,
        "name": memory.name,
        "frequency_hz": memory.freq,
        "mode": memory.mode,
        "duplex": memory.duplex,
        "offset_hz": memory.offset,
        "tone_mode": memory.tmode,
        "tone_hz": float(memory.rtone) if memory.tmode == "Tone" else None,
        "power": str(memory.power),
        "skip": memory.skip,
    }


def validate_plan(plan: dict) -> None:
    channels = plan["channels"]
    profiles = set(plan["scan_profiles"])
    numbers = [item["number"] for item in channels]
    names = [item["name"] for item in channels]
    if len(numbers) != len(set(numbers)) or len(names) != len(set(names)):
        raise ValueError("Channel numbers and names must be unique")
    if any(not 1 <= number <= 199 for number in numbers):
        raise ValueError("Channel numbers must be within 1..199")
    if any(len(name) > 8 for name in names):
        raise ValueError("Channel names must be at most eight characters")
    if any(item["mode"] not in {"FM", "NFM", "AM", "NAM"} for item in channels):
        raise ValueError("Unsupported channel mode")
    for item in channels:
        unknown_profiles = set(item["scan_profiles"]) - profiles
        if unknown_profiles:
            raise ValueError(f"Channel {item['number']} names unknown profiles {sorted(unknown_profiles)}")
        if item["service"] != "amateur" and item["duplex"] != "off":
            raise ValueError(f"Non-amateur channel {item['number']} permits transmit")
        if item["duplex"] != "off":
            rx_hz = round(item["frequency_mhz"] * 1_000_000)
            if item["duplex"] == "split":
                tx_hz = round(item["tx_frequency_mhz"] * 1_000_000)
            elif item["duplex"] == "+":
                tx_hz = rx_hz + round(item["offset_mhz"] * 1_000_000)
            elif item["duplex"] == "-":
                tx_hz = rx_hz - round(item["offset_mhz"] * 1_000_000)
            elif item["duplex"] == "":
                tx_hz = rx_hz
            else:
                raise ValueError(f"Unsupported duplex on channel {item['number']}")
            if not in_tx_band(rx_hz) or not in_tx_band(tx_hz):
                raise ValueError(f"Channel {item['number']} transmits outside configured 2 m/70 cm limits")


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
    validate_plan(plan)

    module = load_test_driver(driver_path)
    factory_radio = module.TDH3_Plus(None)
    factory_radio.load_mmap(str(factory_path))
    original = factory_radio.get_mmap().get_byte_compatible().get_packed()
    low_power = module.TDH3_Plus._tx_power[0]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    build_manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "driver": str(driver_path),
        "driver_sha256": sha256(driver_path.read_bytes()),
        "factory": str(factory_path),
        "factory_raw_sha256": sha256(original),
        "plan": str(plan_path),
        "plan_sha256": sha256(plan_path.read_bytes()),
        "profiles": {},
    }

    for profile in plan["scan_profiles"]:
        radio = module.TDH3_Plus(None)
        radio.load_mmap(str(factory_path))
        for number in range(1, 200):
            radio.set_memory(chirp_common.Memory(number=number, empty=True))
            radio._get_nam(number).fill_raw(b"\xFF")
            radio._memobj.scanadd[number - 1] = False

        for item in plan["channels"]:
            memory = chirp_common.Memory()
            memory.number = item["number"]
            memory.name = item["name"]
            memory.freq = round(item["frequency_mhz"] * 1_000_000)
            memory.mode = item["mode"]
            memory.duplex = item["duplex"]
            if item["duplex"] == "split":
                memory.offset = round(item["tx_frequency_mhz"] * 1_000_000)
            else:
                memory.offset = round(item.get("offset_mhz", 0) * 1_000_000)
            memory.tmode = item.get("tone_mode", "")
            if memory.tmode == "Tone":
                memory.rtone = float(item["tone_hz"])
            memory.power = low_power
            memory.skip = "" if profile in item["scan_profiles"] else "S"
            memory.empty = False
            radio.set_memory(memory)

        candidate = radio.get_mmap().get_byte_compatible().get_packed()
        changed = [index for index, pair in enumerate(zip(original, candidate)) if pair[0] != pair[1]]
        unexpected = [offset for offset in changed if not allowed_offset(offset)]
        settings_start, settings_stop = SETTINGS_RANGE
        if candidate[settings_start:settings_stop] != original[settings_start:settings_stop]:
            raise RuntimeError(f"{profile}: radio-wide settings changed")
        if unexpected:
            raise RuntimeError(f"{profile}: unexpected changed byte 0x{unexpected[0]:04X}")

        decoded = []
        by_number = {item["number"]: item for item in plan["channels"]}
        for item in plan["channels"]:
            memory = radio.get_memory(item["number"])
            actual = decoded_memory(memory)
            wanted = expected_memory(item, profile)
            if actual != wanted:
                raise RuntimeError(f"{profile} memory {memory.number}: {actual!r} != {wanted!r}")
            tx_hz = actual_tx_frequency(memory)
            if item["service"] != "amateur" and tx_hz is not None:
                raise RuntimeError(f"{profile} memory {memory.number}: non-amateur TX enabled")
            if tx_hz is not None and (not in_tx_band(memory.freq) or not in_tx_band(tx_hz)):
                raise RuntimeError(f"{profile} memory {memory.number}: TX outside 2 m/70 cm")
            decoded.append(actual)

        populated = [radio.get_memory(number) for number in range(1, 200)]
        populated = [memory for memory in populated if not memory.empty]
        if len(populated) != len(by_number):
            raise RuntimeError(f"{profile}: expected {len(by_number)} channels, found {len(populated)}")

        base = f"td_h3_plus-60515-licensed-ready-{profile}-{timestamp}"
        raw_path = output_dir / f"{base}.raw.bin"
        image_path = output_dir / f"{base}.img"
        manifest_path = output_dir / f"{base}.json"
        raw_path.write_bytes(candidate)
        radio.save_mmap(str(image_path))
        by_range = {
            label: sum(start <= offset < stop for offset in changed)
            for start, stop, label in ALLOWED_CHANGED_RANGES
        }
        profile_manifest = {
            "profile": profile,
            "description": plan["scan_profiles"][profile],
            "candidate_image": image_path.name,
            "candidate_image_sha256": sha256(image_path.read_bytes()),
            "candidate_raw": raw_path.name,
            "candidate_raw_sha256": sha256(candidate),
            "populated_channel_count": len(decoded),
            "scan_included_count": sum(item["skip"] == "" for item in decoded),
            "transmit_enabled_count": sum(item["duplex"] != "off" for item in decoded),
            "non_amateur_transmit_enabled_count": sum(
                item["duplex"] != "off" and by_number[item["number"]]["service"] != "amateur"
                for item in decoded
            ),
            "all_power_low": all(item["power"] == "Low" for item in decoded),
            "radio_wide_settings_unchanged": True,
            "unexpected_changed_byte_count": len(unexpected),
            "changed_byte_count": len(changed),
            "changed_bytes_by_allowed_range": by_range,
            "channels": decoded,
        }
        manifest_path.write_text(json.dumps(profile_manifest, indent=2) + "\n")
        for path in (raw_path, image_path, manifest_path):
            os.chmod(path, 0o600)
        build_manifest["profiles"][profile] = profile_manifest | {"manifest": manifest_path.name}

    manifest_path = output_dir / f"td_h3_plus-60515-licensed-ready-profiles-{timestamp}.json"
    manifest_path.write_text(json.dumps(build_manifest, indent=2) + "\n")
    os.chmod(manifest_path, 0o600)
    print(json.dumps({"manifest": str(manifest_path), "profiles": build_manifest["profiles"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
