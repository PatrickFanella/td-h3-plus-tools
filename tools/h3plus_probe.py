#!/usr/bin/env python3
"""Perform a read-only TD-H3 Plus identity handshake and leave clone mode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from chirp.wxui import serialtrace

from h3plus_read_backup import ALLOWED_MODELS, load_test_driver


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, type=Path)
    parser.add_argument("--driver", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    result_path = args.result.resolve()
    result_path.parent.mkdir(parents=True, exist_ok=True)

    port = args.port.resolve(strict=True)
    module = load_test_driver(args.driver.resolve(strict=True))
    pipe = serialtrace.SerialTrace(
        str(port),
        baudrate=module.TDH3_Plus.BAUD_RATE,
        timeout=0.5,
        rtscts=module.TDH3_Plus.HARDWARE_FLOW,
        exclusive=True,
    )
    pipe.rts = module.TDH3_Plus.WANTS_RTS
    pipe.dtr = module.TDH3_Plus.WANTS_DTR
    entered_clone_mode = False
    try:
        detected = module.TDH3_Plus.detect_from_serial(pipe)
        entered_clone_mode = True
        if detected.MODEL not in ALLOWED_MODELS:
            raise RuntimeError(f"Unexpected model: {detected.MODEL}")
        result_path.write_text(json.dumps({
            "status": "pass",
            "detected_model": detected.MODEL,
            "port": str(port)
        }, indent=2) + "\n")
        print(f"PASS: detected {detected.MODEL} on {port}")
        return 0
    except Exception as error:
        result_path.write_text(json.dumps({
            "status": "fail",
            "error_type": type(error).__name__,
            "error": str(error),
            "port": str(port)
        }, indent=2) + "\n")
        print(f"FAIL: {type(error).__name__}: {error}")
        return 1
    finally:
        if entered_clone_mode:
            module._exit_write_block(module.TDH3_Plus(pipe))
        pipe.close()


if __name__ == "__main__":
    raise SystemExit(main())
