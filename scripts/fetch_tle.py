from __future__ import annotations

"""
OpenOrbitLink TLE Fetcher - Download TLE data from CelesTrak.

Usage:
    python scripts/fetch_tle.py
    python scripts/fetch_tle.py --group amateur --output data/amateur.tle
    python scripts/fetch_tle.py --norad 25544
    python scripts/fetch_tle.py --all-openorbitlink --include-fossa
"""

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request


CELESTRAK_BASE = "https://celestrak.org/NORAD/elements/gp.php"
WARNING_AGE_DAYS = 3.0
STALE_AGE_DAYS = 7.0
EXPIRED_AGE_DAYS = 14.0

TLE_GROUPS = {
    "amateur": "amateur",
    "noaa": "noaa",
    "stations": "stations",
    "cubesat": "cubesat",
    "tle-new": "tle-new",
    "active": "active",
    "weather": "weather",
    "resource": "resource",
    "sarsat": "sarsat",
    "science": "science",
}

OPENORBITLINK_SATELLITES = {
    25544: "ISS (ZARYA)",
    28654: "NOAA-18",
    33591: "NOAA-19",
    25338: "NOAA-15",
    39444: "FUNcube-1 (AO-73)",
    43017: "FalconSAT-3",
}

FOSSA_NAME_HINTS = ("FOSSA", "FOSSASAT", "FEROX")


@dataclass(frozen=True)
class TLERecord:
    name: str
    line1: str
    line2: str
    norad_id: int
    epoch: datetime
    age_days: float
    staleness: str


def _http_get(url: str) -> str:
    print(f"Fetching: {url}")
    if HAS_REQUESTS:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def fetch_tle_group(group: str, format_type: str = "tle") -> str:
    """Fetch TLE data for a satellite group from CelesTrak."""
    url = f"{CELESTRAK_BASE}?GROUP={group}&FORMAT={format_type.upper()}"
    return _http_get(url)


def fetch_tle_by_norad(norad_id: int, format_type: str = "tle") -> str:
    """Fetch TLE for a specific satellite by NORAD ID."""
    url = f"{CELESTRAK_BASE}?CATNR={norad_id}&FORMAT={format_type.upper()}"
    return _http_get(url)


def fetch_tle_by_name(name: str, format_type: str = "tle") -> str:
    """Fetch TLEs matching a satellite-name fragment."""
    url = f"{CELESTRAK_BASE}?NAME={quote_plus(name)}&FORMAT={format_type.upper()}"
    return _http_get(url)


def tle_epoch(line1: str) -> datetime:
    """Return the TLE epoch encoded in line 1."""
    if len(line1) < 32 or not line1.startswith("1 "):
        raise ValueError("invalid TLE line 1")
    raw = line1[18:32].strip()
    year = int(raw[:2])
    year += 1900 if year >= 57 else 2000
    day_of_year = float(raw[2:])
    return datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_of_year - 1)


def classify_tle_age(age_days: float) -> str:
    if age_days >= EXPIRED_AGE_DAYS:
        return "expired"
    if age_days >= STALE_AGE_DAYS:
        return "stale"
    if age_days >= WARNING_AGE_DAYS:
        return "warning"
    return "fresh"


def parse_tle_records(tle_data: str, now: datetime | None = None) -> list[TLERecord]:
    now = now or datetime.now(timezone.utc)
    lines = [line.strip() for line in tle_data.splitlines() if line.strip()]
    records: list[TLERecord] = []
    i = 0
    while i < len(lines):
        if i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            name, line1, line2 = lines[i], lines[i + 1], lines[i + 2]
            epoch = tle_epoch(line1)
            age_days = (now - epoch).total_seconds() / 86400.0
            records.append(
                TLERecord(
                    name=name,
                    line1=line1,
                    line2=line2,
                    norad_id=int(line1[2:7]),
                    epoch=epoch,
                    age_days=age_days,
                    staleness=classify_tle_age(age_days),
                )
            )
            i += 3
        else:
            i += 1
    return records


def unique_tle_records(tle_data: str) -> str:
    records = parse_tle_records(tle_data)
    seen: set[int] = set()
    output: list[str] = []
    for record in records:
        if record.norad_id in seen:
            continue
        seen.add(record.norad_id)
        output.extend([record.name, record.line1, record.line2])
    return "\n".join(output) + ("\n" if output else "")


def fetch_openorbitlink_satellites(include_fossa: bool = False) -> str:
    """Fetch TLE data for all OpenOrbitLink-relevant satellites."""
    all_tle = ""
    for norad_id, name in OPENORBITLINK_SATELLITES.items():
        try:
            tle = fetch_tle_by_norad(norad_id)
            if tle.strip():
                all_tle += tle.rstrip() + "\n"
                print(f"  OK: {name} (NORAD {norad_id})")
            else:
                print(f"  WARN: Empty TLE for {name}")
        except Exception as exc:
            print(f"  ERROR: {name}: {exc}")
        time.sleep(0.5)

    if include_fossa:
        all_tle += fetch_fossa_satellites()
    return unique_tle_records(all_tle)


def fetch_fossa_satellites() -> str:
    """Fetch known FOSSA/FOSSASAT/FEROX TLEs by CelesTrak name search."""
    all_tle = ""
    for name_hint in FOSSA_NAME_HINTS:
        try:
            tle = fetch_tle_by_name(name_hint)
            if tle.strip():
                all_tle += tle.rstrip() + "\n"
                print(f"  OK: FOSSA name search {name_hint}")
            else:
                print(f"  WARN: Empty FOSSA name search {name_hint}")
        except Exception as exc:
            print(f"  ERROR: FOSSA name search {name_hint}: {exc}")
        time.sleep(0.5)
    return unique_tle_records(all_tle)


def metadata_for_tle(tle_data: str, source: str, fetched_at: datetime | None = None) -> dict:
    fetched_at = fetched_at or datetime.now(timezone.utc)
    records = parse_tle_records(tle_data, now=fetched_at)
    worst = "fresh"
    rank = {"fresh": 0, "warning": 1, "stale": 2, "expired": 3}
    for record in records:
        if rank[record.staleness] > rank[worst]:
            worst = record.staleness
    return {
        "source": source,
        "fetched_at": fetched_at.isoformat(),
        "satellite_count": len(records),
        "worst_staleness": worst,
        "warning_age_days": WARNING_AGE_DAYS,
        "stale_age_days": STALE_AGE_DAYS,
        "expired_age_days": EXPIRED_AGE_DAYS,
        "satellites": [
            {
                **asdict(record),
                "epoch": record.epoch.isoformat(),
            }
            for record in records
        ],
    }


def write_tle_and_metadata(tle_data: str, output: str, source: str, metadata_output: str | None = None) -> None:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(tle_data, encoding="utf-8")
    metadata = metadata_for_tle(tle_data, source=source)
    metadata_path = Path(metadata_output) if metadata_output else output_path.with_suffix(output_path.suffix + ".json")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"\nSaved {metadata['satellite_count']} satellites to {output_path}")
    print(f"Metadata: {metadata_path}")
    print(f"Worst TLE age status: {metadata['worst_staleness']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenOrbitLink TLE Data Fetcher")
    parser.add_argument("--group", type=str, default=None, choices=list(TLE_GROUPS.keys()), help="CelesTrak group name")
    parser.add_argument("--norad", type=int, default=None, help="Specific NORAD catalog number")
    parser.add_argument("--name", type=str, default=None, help="CelesTrak satellite-name search")
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    parser.add_argument("--metadata-output", type=str, default=None, help="Metadata JSON output path")
    parser.add_argument(
        "--all-openorbitlink",
        "--all-OpenOrbitLink",
        dest="all_openorbitlink",
        action="store_true",
        help="Fetch all OpenOrbitLink-relevant satellites",
    )
    parser.add_argument("--include-fossa", action="store_true", help="Include FOSSA/FOSSASAT/FEROX name searches")
    parser.add_argument("--fossa", action="store_true", help="Fetch only FOSSA/FOSSASAT/FEROX name searches")
    args = parser.parse_args()

    if args.fossa:
        tle_data = fetch_fossa_satellites()
        output = args.output or "data/fossa_satellites.tle"
        source = "celestrak-name:fossa"
    elif args.all_openorbitlink:
        tle_data = fetch_openorbitlink_satellites(include_fossa=args.include_fossa)
        output = args.output or "data/openorbitlink_satellites.tle"
        source = "openorbitlink-satellite-set"
    elif args.norad:
        tle_data = fetch_tle_by_norad(args.norad)
        output = args.output or f"data/norad_{args.norad}.tle"
        source = f"celestrak-catnr:{args.norad}"
    elif args.name:
        tle_data = fetch_tle_by_name(args.name)
        output = args.output or f"data/name_{args.name.lower().replace(' ', '_')}.tle"
        source = f"celestrak-name:{args.name}"
    elif args.group:
        tle_data = fetch_tle_group(TLE_GROUPS[args.group])
        output = args.output or f"data/{args.group}.tle"
        source = f"celestrak-group:{args.group}"
    else:
        tle_data = fetch_tle_group("amateur")
        output = args.output or "data/amateur.tle"
        source = "celestrak-group:amateur"

    write_tle_and_metadata(tle_data, output, source=source, metadata_output=args.metadata_output)


if __name__ == "__main__":
    main()
