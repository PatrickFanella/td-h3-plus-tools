#!/usr/bin/env python3
"""Read and back up a TIDRADIO TD-H3 Plus HAM without uploading to it."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

from chirp import directory
from chirp import CHIRP_VERSION as chirp_version
from chirp.wxui import serialtrace


ALLOWED_MODELS = {"TD-H3-Plus", "TD-H3-Plus-HAM"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_test_driver(path: Path):
    directory.import_drivers()
    directory.enable_reregistrations()

    module_name = "chirp.drivers.tdh8_issue12216"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load driver module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, type=Path)
    parser.add_argument("--driver", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    port_path = args.port.resolve(strict=True)
    driver_path = args.driver.resolve(strict=True)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    driver_data = driver_path.read_bytes()
    driver_hash = sha256(driver_data)
    module = load_test_driver(driver_path)

    serial_port = serialtrace.SerialTrace(
        str(port_path),
        baudrate=module.TDH3_Plus.BAUD_RATE,
        timeout=0.5,
        rtscts=module.TDH3_Plus.HARDWARE_FLOW,
        exclusive=True,
    )
    serial_port.rts = module.TDH3_Plus.WANTS_RTS
    serial_port.dtr = module.TDH3_Plus.WANTS_DTR
    try:
        detected_class = module.TDH3_Plus.detect_from_serial(serial_port)
        if detected_class.MODEL not in ALLOWED_MODELS:
            raise RuntimeError(
                f"Refusing to continue: detected {detected_class.MODEL!r}, "
                f"expected one of {sorted(ALLOWED_MODELS)!r}"
            )

        radio = detected_class(serial_port)

        def status(update):
            percent = round(100 * update.cur / update.max) if update.max else 0
            print(f"\rReading radio: {percent:3d}%", end="", flush=True)

        radio.status_fn = status
        radio.sync_in()
        print("\rReading radio: 100%")

        raw_data = radio.get_mmap().get_byte_compatible().get_packed()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        model_slug = detected_class.MODEL.lower().replace("-", "_")
        base_name = f"{model_slug}-factory-{timestamp}"
        raw_path = output_dir / f"{base_name}.raw.bin"
        image_path = output_dir / f"{base_name}.img"
        manifest_path = output_dir / f"{base_name}.json"

        raw_path.write_bytes(raw_data)
        radio.save_mmap(str(image_path))

        manifest = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "operation": "radio-to-computer download only; no upload performed",
            "detected_model": detected_class.MODEL,
            "port": str(args.port),
            "resolved_port": str(port_path),
            "chirp_version": chirp_version,
            "driver_source": "CHIRP issue 12216 attachment 15686, beta 081726.05",
            "driver_path": str(driver_path),
            "driver_sha256": driver_hash,
            "raw_file": raw_path.name,
            "raw_size_bytes": len(raw_data),
            "raw_sha256": sha256(raw_data),
            "chirp_image_file": image_path.name,
            "chirp_image_size_bytes": image_path.stat().st_size,
            "chirp_image_sha256": sha256(image_path.read_bytes()),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        os.chmod(raw_path, 0o600)
        os.chmod(image_path, 0o600)
        os.chmod(manifest_path, 0o600)

        print(json.dumps(manifest, indent=2))
        return 0
    finally:
        serial_port.close()


if __name__ == "__main__":
    raise SystemExit(main())
