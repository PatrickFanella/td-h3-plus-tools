#!/usr/bin/env python3
"""Validate and upload a licensed-ready TD-H3 Plus profile image."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from chirp.wxui import serialtrace

from h3plus_build_image import SETTINGS_RANGE, allowed_offset
from h3plus_build_profile_images import (
    actual_tx_frequency,
    decoded_memory,
    expected_memory,
    in_tx_band,
    validate_plan,
)
from h3plus_read_backup import ALLOWED_MODELS, load_test_driver


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def open_serial(port_path: Path, radio_class):
    pipe = serialtrace.SerialTrace(
        str(port_path),
        baudrate=radio_class.BAUD_RATE,
        timeout=0.5,
        rtscts=radio_class.HARDWARE_FLOW,
        exclusive=True,
    )
    pipe.rts = radio_class.WANTS_RTS
    pipe.dtr = radio_class.WANTS_DTR
    return pipe


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, type=Path)
    parser.add_argument("--driver", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--expected-raw-sha256", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument(
        "--acknowledge-no-transmit-until-licensed",
        required=True,
        action="store_true",
        help="Required acknowledgement that upload does not authorize transmission.",
    )
    args = parser.parse_args()

    port_path = args.port.resolve(strict=True)
    driver_path = args.driver.resolve(strict=True)
    factory_path = args.factory.resolve(strict=True)
    plan_path = args.plan.resolve(strict=True)
    image_path = args.image.resolve(strict=True)
    receipt_path = args.receipt.resolve()
    plan = json.loads(plan_path.read_text())
    validate_plan(plan)
    if args.profile not in plan["scan_profiles"]:
        raise ValueError(f"Unknown scan profile {args.profile!r}")

    module = load_test_driver(driver_path)
    offline = module.TDH3_Plus(None)
    offline.load_mmap(str(image_path))
    candidate = offline.get_mmap().get_byte_compatible().get_packed()
    factory_radio = module.TDH3_Plus(None)
    factory_radio.load_mmap(str(factory_path))
    factory = factory_radio.get_mmap().get_byte_compatible().get_packed()
    candidate_hash = sha256(candidate)
    if candidate_hash != args.expected_raw_sha256:
        raise RuntimeError(f"Candidate hash {candidate_hash} != authorized hash {args.expected_raw_sha256}")
    if len(candidate) != len(factory):
        raise RuntimeError("Candidate and factory raw images have different sizes")
    unexpected = [
        offset for offset, pair in enumerate(zip(factory, candidate))
        if pair[0] != pair[1] and not allowed_offset(offset)
    ]
    if unexpected:
        raise RuntimeError(f"Candidate changes disallowed offset 0x{unexpected[0]:04X}")
    settings_start, settings_stop = SETTINGS_RANGE
    if candidate[settings_start:settings_stop] != factory[settings_start:settings_stop]:
        raise RuntimeError("Candidate changes radio-wide settings")

    expected_numbers = {item["number"] for item in plan["channels"]}
    for item in plan["channels"]:
        memory = offline.get_memory(item["number"])
        actual = decoded_memory(memory)
        wanted = expected_memory(item, args.profile)
        if actual != wanted:
            raise RuntimeError(f"Memory {memory.number}: {actual!r} != {wanted!r}")
        tx_hz = actual_tx_frequency(memory)
        if item["service"] != "amateur" and tx_hz is not None:
            raise RuntimeError(f"Memory {memory.number}: non-amateur TX enabled")
        if tx_hz is not None and (not in_tx_band(memory.freq) or not in_tx_band(tx_hz)):
            raise RuntimeError(f"Memory {memory.number}: TX outside 2 m/70 cm")
        if str(memory.power) != "Low":
            raise RuntimeError(f"Memory {memory.number}: power is not Low")
    populated = [offline.get_memory(number) for number in range(1, 200)]
    populated_numbers = {memory.number for memory in populated if not memory.empty}
    if populated_numbers != expected_numbers:
        raise RuntimeError("Populated memories do not exactly match the plan")

    serial_port = open_serial(port_path, module.TDH3_Plus)
    try:
        detected_class = module.TDH3_Plus.detect_from_serial(serial_port)
        if detected_class.MODEL not in ALLOWED_MODELS:
            raise RuntimeError(f"Detected unsupported model {detected_class.MODEL!r}")
        module._exit_write_block(detected_class(serial_port))
        serial_port.close()
        serial_port = None
        time.sleep(1.0)
        serial_port = open_serial(port_path, detected_class)
        radio = detected_class(serial_port)
        radio.load_mmap(str(image_path))

        def status(update):
            percent = round(100 * update.cur / update.max) if update.max else 0
            print(f"\rWriting radio: {percent:3d}%", end="", flush=True)

        radio.status_fn = status
        radio.sync_out()
        print("\rWriting radio: 100%")
        receipt = {
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "operation": "licensed-ready profile upload completed",
            "license_gate": plan["license_gate"],
            "detected_model": detected_class.MODEL,
            "profile": args.profile,
            "profile_description": plan["scan_profiles"][args.profile],
            "port": str(args.port),
            "resolved_port": str(port_path),
            "driver": str(driver_path),
            "driver_sha256": sha256(driver_path.read_bytes()),
            "factory": str(factory_path),
            "plan": str(plan_path),
            "plan_sha256": sha256(plan_path.read_bytes()),
            "candidate_image": str(image_path),
            "candidate_raw_sha256": candidate_hash,
            "populated_channel_count": len(expected_numbers),
            "scan_included_count": sum(
                args.profile in item["scan_profiles"] for item in plan["channels"]
            ),
            "non_amateur_transmit_enabled_count": 0,
            "radio_wide_settings_unchanged": True,
        }
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        receipt_path.chmod(0o600)
        print(json.dumps(receipt, indent=2))
        return 0
    except Exception as error:
        error_path = receipt_path.with_suffix(".error.json")
        error_path.parent.mkdir(parents=True, exist_ok=True)
        error_path.write_text(json.dumps({
            "failed_at_utc": datetime.now(timezone.utc).isoformat(),
            "operation": "licensed-ready profile upload did not complete",
            "error_type": type(error).__name__,
            "error": str(error),
            "candidate_raw_sha256": candidate_hash,
            "profile": args.profile,
            "port": str(args.port),
        }, indent=2) + "\n")
        error_path.chmod(0o600)
        raise
    finally:
        if serial_port is not None:
            serial_port.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}", flush=True)
        raise SystemExit(1)
