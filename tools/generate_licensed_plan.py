#!/usr/bin/env python3
"""Generate the source-backed 60515 licensed-ready TD-H3 Plus channel plan."""

from __future__ import annotations

import json
from pathlib import Path


OUTPUT = Path(__file__).resolve().parent.parent / "channel-plan-60515-licensed-ready.json"


SOURCES = {
    "local_note": {
        "title": "Chicagoland Amateur Radio Repeater Table",
        "url": "/home/onnwee/Documents/ars-malefica/003 Resources/Reference/Chicagoland Amateur Radio Repeater Table.md",
        "note": "2026-08-05 discovery snapshot; current entries cross-checked where practical."
    },
    "ilra": {
        "title": "Illinois Repeater Association directory",
        "url": "https://www.ilra.net/DirByRegByCity.html"
    },
    "darc": {
        "title": "DuPage Amateur Radio Club repeaters",
        "url": "https://www.w9dup.org/repeaters.html"
    },
    "w9ccu": {
        "title": "Wheaton Community Radio Amateurs repeaters",
        "url": "https://www.w9ccu.org/wordpressLimitless/?page_id=104"
    },
    "faa": {
        "title": "FAA Chicago Terminal Area Chart",
        "url": "https://aeronav.faa.gov/visual/09-03-2026/PDFs/Chicago_TAC.pdf"
    },
    "noaa": {
        "title": "NWS Chicago NOAA Weather Radio",
        "url": "https://www.weather.gov/lot/NWR"
    },
    "noaa_apt": {
        "title": "NOAA Polar Operational Environmental Satellites user guide",
        "url": "https://www.ospo.noaa.gov/resources/documents/POES_TIP.pdf"
    },
    "rail": {
        "title": "Illinois BNSF Railway frequencies",
        "url": "https://www.railroad-frequencies.com/state/illinois/bnsf-railway/",
        "note": "Community-maintained scanner directory corroborated against Chicago rail references."
    },
    "amsat": {
        "title": "AMSAT live FM satellites",
        "url": "https://www.amsat.org/live-fm-satellites/"
    },
    "ariss": {
        "title": "ARISS frequencies in use",
        "url": "https://www.ariss.org/contact-the-iss.html"
    },
    "uscg": {
        "title": "US Coast Guard US VHF channel information",
        "url": "https://navcen.uscg.gov/us-vhf-channel-information"
    },
    "fcc_frs": {
        "title": "FCC FRS channel table",
        "url": "https://docs.fcc.gov/public/attachments/FCC-17-57A1_Rcd.pdf"
    },
    "fcc_murs": {
        "title": "FCC MURS frequency allocation",
        "url": "https://docs.fcc.gov/public/attachments/FCC-00-235A1_Rcd.pdf"
    },
    "ecfr": {
        "title": "47 CFR 97.301 amateur frequency bands",
        "url": "https://www.ecfr.gov/current/title-47/chapter-I/subchapter-D/part-97/subpart-D/section-97.301"
    }
}


def rx(number, name, frequency, mode, category, profiles, sources):
    return {
        "number": number,
        "name": name,
        "frequency_mhz": frequency,
        "mode": mode,
        "category": category,
        "service": "receive-only",
        "duplex": "off",
        "tone_mode": "",
        "power": "Low",
        "scan_profiles": profiles,
        "sources": sources,
    }


def amateur_repeater(number, name, frequency, offset, tone, location, sources, profiles=None):
    transmit_enabled = 144.0 <= frequency <= 148.0 or 420.0 <= frequency <= 450.0
    item = {
        "number": number,
        "name": name,
        "frequency_mhz": frequency,
        "mode": "FM",
        "category": "amateur repeater",
        "service": "amateur",
        "location": location,
        "duplex": "+" if offset > 0 else "-" if transmit_enabled else "off",
        "offset_mhz": abs(offset) if transmit_enabled else 0,
        "tone_mode": "Tone" if transmit_enabled else "",
        "tone_hz": tone if transmit_enabled else None,
        "power": "Low",
        "scan_profiles": profiles or ["daily", "ham", "all_voice"],
        "sources": sources,
    }
    if not transmit_enabled:
        item["note"] = "Receive-only: TX220 radio-wide control is intentionally unchanged."
    return item


def amateur_simplex(number, name, frequency, profiles):
    return {
        "number": number,
        "name": name,
        "frequency_mhz": frequency,
        "mode": "FM",
        "category": "amateur simplex",
        "service": "amateur",
        "duplex": "",
        "offset_mhz": 0,
        "tone_mode": "",
        "power": "Low",
        "scan_profiles": profiles,
        "sources": ["ecfr"],
    }


def amateur_split(number, name, receive, transmit, tone, sources):
    return {
        "number": number,
        "name": name,
        "frequency_mhz": receive,
        "tx_frequency_mhz": transmit,
        "mode": "FM",
        "category": "amateur satellite",
        "service": "amateur",
        "duplex": "split",
        "tone_mode": "Tone" if tone is not None else "",
        "tone_hz": tone,
        "power": "Low",
        "scan_profiles": ["satellite"],
        "sources": sources,
    }


channels = [
    amateur_repeater(1, "DARC2M", 145.430, -0.600, 107.2, "Downers Grove", ["darc", "ilra", "local_note"]),
    amateur_repeater(2, "DARC70", 442.550, 5.000, 114.8, "Downers Grove", ["darc", "ilra", "local_note"]),
    amateur_repeater(3, "WCRA70", 444.475, 5.000, 114.8, "Wheaton/Downers Grove", ["w9ccu", "ilra", "local_note"]),
    amateur_repeater(4, "YORK70", 442.875, 5.000, 114.8, "Downers Grove", ["ilra", "local_note"]),
    amateur_repeater(5, "WESTMNT", 145.490, -0.600, 107.2, "Westmont", ["ilra", "local_note"], ["daily", "ham", "weather", "all_voice"]),
    amateur_repeater(6, "LISLE2M", 146.655, -0.600, 107.2, "Lisle", ["ilra", "local_note"], ["daily", "ham", "weather", "all_voice"]),
    amateur_repeater(7, "LISLE70", 442.050, 5.000, 114.8, "Lisle", ["ilra", "local_note"], ["daily", "ham", "weather", "all_voice"]),
    amateur_repeater(8, "ANL2M", 145.190, -0.600, 114.8, "Argonne", ["ilra", "local_note"]),
    amateur_repeater(9, "DARC220", 224.680, -1.600, 110.9, "Downers Grove", ["darc", "ilra", "local_note"]),
    amateur_repeater(10, "WCRA2M", 145.310, -0.600, 107.2, "Wheaton", ["w9ccu", "ilra", "local_note"]),
    amateur_repeater(11, "WCRA220", 224.140, -1.600, 110.9, "Wheaton", ["w9ccu", "ilra", "local_note"]),
    amateur_repeater(12, "HINS2M", 146.970, -0.600, 107.2, "Hinsdale", ["ilra", "local_note"]),
    amateur_repeater(13, "HINS70", 443.300, 5.000, 114.8, "Hinsdale", ["ilra", "local_note"]),
    amateur_repeater(14, "NAPR70", 443.050, 5.000, 114.8, "Naperville", ["ilra", "local_note"], ["daily", "ham", "weather", "all_voice"]),
    amateur_repeater(15, "BOL2M", 147.330, 0.600, 107.2, "Bolingbrook", ["ilra", "local_note"]),
    amateur_repeater(16, "BOL70", 443.525, 5.000, 114.8, "Bolingbrook", ["ilra", "local_note"]),
    amateur_repeater(17, "WHEAT70", 442.225, 5.000, 114.8, "Wheaton", ["ilra", "local_note"]),
    amateur_repeater(18, "WHEAT22", 224.360, -1.600, 110.9, "Wheaton", ["ilra", "local_note"]),
    amateur_repeater(19, "GLEN2M", 146.850, -0.600, 100.0, "Glendale Heights", ["ilra", "local_note"]),
    amateur_repeater(20, "GLEN70", 444.875, 5.000, 114.8, "Glendale Heights", ["ilra", "local_note"]),

    amateur_simplex(21, "CALL2M", 146.520, ["daily", "ham", "all_voice"]),
    amateur_simplex(22, "CALL70", 446.000, ["daily", "ham", "all_voice"]),
    amateur_simplex(23, "YORKSMP", 147.420, ["ham", "all_voice"]),
    rx(24, "APRS", 144.390, "FM", "amateur packet", [], ["ecfr"]),

    rx(30, "ISSVCE", 145.800, "FM", "ISS voice downlink", ["satellite"], ["ariss"]),
    rx(31, "ISSPKT", 145.825, "FM", "ISS packet", [], ["ariss"]),
    amateur_split(32, "ISSRPT", 437.800, 145.990, 67.0, ["ariss", "amsat"]),
    amateur_split(33, "SO-50", 436.795, 145.850, 67.0, ["amsat"]),
    amateur_split(34, "AO-91", 145.960, 435.250, None, ["amsat"]),
    amateur_split(35, "AO-123", 435.400, 145.850, 67.0, ["amsat"]),
    rx(36, "APT1371", 137.100, "FM", "weather satellite APT", [], ["noaa_apt"]),
    rx(37, "APT1376", 137.620, "FM", "weather satellite APT", [], ["noaa_apt"]),
    rx(38, "APT1379", 137.9125, "FM", "weather satellite APT", [], ["noaa_apt"]),

    rx(40, "WX-LOCK", 162.425, "FM", "NOAA Weather Radio", [], ["noaa"]),
    rx(41, "WX-CHI", 162.550, "FM", "NOAA Weather Radio", [], ["noaa"]),
    rx(42, "WX-PLNO", 162.400, "FM", "NOAA Weather Radio", [], ["noaa"]),
    rx(43, "WX-RKFD", 162.475, "FM", "NOAA Weather Radio", [], ["noaa"]),
    rx(44, "WX-CRYS", 162.500, "FM", "NOAA Weather Radio", [], ["noaa"]),
    rx(45, "WX-DIXN", 162.525, "FM", "NOAA Weather Radio", [], ["noaa"]),
    rx(46, "WX-HEBR", 162.450, "FM", "NOAA Weather Radio", [], ["noaa"]),

    rx(50, "BNSF66", 161.100, "NFM", "railroad", ["daily", "rail", "all_voice"], ["rail"]),
    rx(51, "BNSF70", 161.160, "NFM", "railroad", ["daily", "rail", "all_voice"], ["rail"]),
    rx(52, "BNSF85", 161.385, "NFM", "railroad", ["rail", "all_voice"], ["rail"]),
    rx(53, "BNSF60", 161.010, "NFM", "railroad maintenance", ["rail", "all_voice"], ["rail"]),
    rx(54, "EOLAYRD", 160.875, "NFM", "railroad yard", ["rail", "all_voice"], ["rail"]),
    rx(55, "EOLA77", 161.265, "NFM", "railroad yard", ["rail", "all_voice"], ["rail"]),
    rx(56, "UPWEST1", 160.890, "NFM", "railroad", ["rail", "all_voice"], ["rail"]),
    rx(57, "UPWEST2", 161.040, "NFM", "railroad", ["rail", "all_voice"], ["rail"]),
    rx(58, "CNLEITH", 161.475, "NFM", "railroad", ["rail", "all_voice"], ["rail"]),

    rx(70, "DPA-TWR", 120.900, "AM", "aviation", ["daily", "air", "all_voice"], ["faa"]),
    rx(71, "DPA-GND", 121.800, "AM", "aviation", ["air", "all_voice"], ["faa"]),
    rx(72, "DPA-ATIS", 132.075, "AM", "aviation automated", [], ["faa"]),
    rx(73, "LOT-TWR", 134.800, "AM", "aviation", ["daily", "air", "all_voice"], ["faa"]),
    rx(74, "LOT-GND", 120.425, "AM", "aviation", ["air", "all_voice"], ["faa"]),
    rx(75, "LOT-ATIS", 126.675, "AM", "aviation automated", [], ["faa"]),
    rx(76, "ARR-TWR", 119.900, "AM", "aviation", ["daily", "air", "all_voice"], ["faa"]),
    rx(77, "ARR-GND", 121.700, "AM", "aviation", ["air", "all_voice"], ["faa"]),
    rx(78, "ARR-ATIS", 125.850, "AM", "aviation automated", [], ["faa"]),
    rx(79, "AIRGUARD", 121.500, "AM", "aviation emergency", ["air", "all_voice"], ["faa"]),
    rx(80, "CHIAPP1", 120.550, "AM", "aviation approach", ["daily", "air", "all_voice"], ["faa"]),
    rx(81, "CHIAPP2", 133.500, "AM", "aviation approach", ["daily", "air", "all_voice"], ["faa"]),
    rx(82, "CHIAPP3", 128.200, "AM", "aviation approach", ["air", "all_voice"], ["faa"]),

    rx(90, "MAR16", 156.800, "FM", "marine safety/calling", ["general", "all_voice"], ["uscg"]),
    rx(91, "MAR13", 156.650, "FM", "marine bridge-to-bridge", ["general", "all_voice"], ["uscg"]),
    rx(92, "MAR09", 156.450, "FM", "marine calling", ["general", "all_voice"], ["uscg"]),
    rx(93, "MAR22A", 157.100, "FM", "marine safety information", ["general", "all_voice"], ["uscg"]),
    rx(94, "MAR06", 156.300, "FM", "marine intership safety", ["general", "all_voice"], ["uscg"]),
]

for index, frequency in enumerate([151.820, 151.880, 151.940, 154.570, 154.600], start=1):
    channels.append(rx(99 + index, f"MURS{index}", frequency, "NFM", "MURS receive", ["general", "all_voice"], ["fcc_murs"]))

frs_frequencies = [
    462.5625, 462.5875, 462.6125, 462.6375, 462.6625, 462.6875, 462.7125,
    467.5625, 467.5875, 467.6125, 467.6375, 467.6625, 467.6875, 467.7125,
    462.5500, 462.5750, 462.6000, 462.6250, 462.6500, 462.6750, 462.7000, 462.7250,
]
for index, frequency in enumerate(frs_frequencies, start=1):
    channels.append(rx(109 + index, f"FRGM{index:02d}", frequency, "NFM", "FRS/GMRS receive", ["general", "all_voice"], ["fcc_frs"]))

plan = {
    "title": "60515 licensed-ready master plan for TIDRADIO TD-H3 Plus",
    "created": "2026-09-20",
    "license_gate": "Do not transmit until an FCC amateur license grant appears in the ULS database.",
    "policy": {
        "amateur_transmit": "Enabled only on selected 2 m and 70 cm amateur channels at Low power.",
        "non_amateur_transmit": "Disabled, regardless of scan profile.",
        "one_scan_list": "The radio has no banks; profile images differ only in scan inclusion flags.",
        "global_settings": "Preserved byte-for-byte because the beta driver's settings parser fails on this radio.",
        "tone_squelch": "Transmit access tones only; receive carrier squelch remains open."
    },
    "scan_profiles": {
        "daily": "Nearby analog repeaters, calling channels, primary BNSF, and high-value aviation.",
        "ham": "Local analog amateur repeaters and simplex.",
        "weather": "ARES/weather-capable local amateur repeaters; NOAA is direct-select because it is continuous.",
        "rail": "Railroad channels.",
        "air": "Voice aviation channels; continuous ATIS excluded.",
        "satellite": "Current FM amateur-satellite and ISS voice/downlink channels.",
        "general": "Marine, MURS, and FRS/GMRS receive-only channels.",
        "all_voice": "Every non-continuous voice channel; slowest scan cycle."
    },
    "sources": SOURCES,
    "channels": sorted(channels, key=lambda item: item["number"]),
}

OUTPUT.write_text(json.dumps(plan, indent=2) + "\n")
print(OUTPUT)
