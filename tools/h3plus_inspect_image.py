#!/usr/bin/env python3
"""Decode a saved TIDRADIO TD-H3 Plus image without connecting a radio."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from chirp.settings import RadioSetting, RadioSettingGroup

from h3plus_read_backup import load_test_driver


def flatten_settings(group, prefix=""):
    result = []
    for element in group:
        name = element.get_name()
        qualified_name = f"{prefix}.{name}" if prefix else name
        if isinstance(element, RadioSettingGroup):
            result.extend(flatten_settings(element, qualified_name))
        elif isinstance(element, RadioSetting):
            result.append({"name": qualified_name, "value": str(element.value)})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--driver", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    module = load_test_driver(args.driver.resolve(strict=True))
    radio = module.TDH3_Plus(None)
    radio.load_mmap(str(args.image.resolve(strict=True)))

    channels = []
    for number in range(1, 200):
        memory = radio.get_memory(number)
        if memory.empty:
            continue
        channels.append(
            {
                "number": number,
                "name": memory.name,
                "frequency_hz": memory.freq,
                "duplex": memory.duplex,
                "offset_hz": memory.offset,
                "tone_mode": memory.tmode,
                "mode": memory.mode,
                "power": str(memory.power) if memory.power else "",
                "skip": memory.skip,
            }
        )

    try:
        decoded_settings = flatten_settings(radio.get_settings())
        settings_error = None
    except Exception as error:
        decoded_settings = []
        settings_error = f"{type(error).__name__}: {error}"

    result = {
        "decoded_as": module.TDH3_Plus.MODEL,
        "memory_bounds": [1, 199],
        "populated_channel_count": len(channels),
        "channels": channels,
        "settings": decoded_settings,
        "settings_error": settings_error,
    }
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.resolve().write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
