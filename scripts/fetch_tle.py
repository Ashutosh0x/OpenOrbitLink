from __future__ import annotations

"""
OpenOrbitLink TLE Fetcher — Download latest TLE data from CelesTrak

Usage:
    python scripts/fetch_tle.py
    python scripts/fetch_tle.py --group amateur --output data/amateur.tle
    python scripts/fetch_tle.py --norad 25544  # ISS only
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request

CELESTRAK_BASE = "https://celestrak.org/NORAD/elements/gp.php"

# Satellite groups relevant to OpenOrbitLink
TLE_GROUPS = {
    "amateur": "amateur",
    "noaa": "noaa",
    "stations": "stations",       # ISS, Tiangong
    "cubesat": "cubesat",
    "tle-new": "tle-new",         # Recently launched
    "active": "active",           # All active satellites
    "weather": "weather",
    "resource": "resource",
    "sarsat": "sarsat",
    "science": "science",
}

# Key satellites for OpenOrbitLink
OpenOrbitLink_SATELLITES = {
    25544: "ISS (ZARYA)",
    28654: "NOAA-18",
    33591: "NOAA-19",
    25338: "NOAA-15",
    39444: "FUNcube-1 (AO-73)",
    43017: "FalconSAT-3",
}


def fetch_tle_group(group: str, format_type: str = "tle") -> str:
    """Fetch TLE data for a satellite group from CelesTrak."""
    url = f"{CELESTRAK_BASE}?GROUP={group}&FORMAT={format_type}"
    print(f"Fetching: {url}")

    if HAS_REQUESTS:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text
    else:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode('utf-8')


def fetch_tle_by_norad(norad_id: int, format_type: str = "tle") -> str:
    """Fetch TLE for a specific satellite by NORAD ID."""
    url = f"{CELESTRAK_BASE}?CATNR={norad_id}&FORMAT={format_type}"
    print(f"Fetching NORAD {norad_id}: {url}")

    if HAS_REQUESTS:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text
    else:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode('utf-8')


def fetch_OpenOrbitLink_satellites(output_dir: str = "data") -> str:
    """Fetch TLE data for all OpenOrbitLink-relevant satellites."""
    os.makedirs(output_dir, exist_ok=True)
    all_tle = ""

    for norad_id, name in OpenOrbitLink_SATELLITES.items():
        try:
            tle = fetch_tle_by_norad(norad_id)
            if tle.strip():
                all_tle += tle + "\n"
                print(f"  OK: {name} (NORAD {norad_id})")
            else:
                print(f"  WARN: Empty TLE for {name}")
        except Exception as e:
            print(f"  ERROR: {name}: {e}")
        time.sleep(0.5)  # Rate limiting

    return all_tle


def main():
    parser = argparse.ArgumentParser(description="OpenOrbitLink TLE Data Fetcher")
    parser.add_argument("--group", type=str, default=None,
                        choices=list(TLE_GROUPS.keys()),
                        help="CelesTrak group name")
    parser.add_argument("--norad", type=int, default=None,
                        help="Specific NORAD catalog number")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file path")
    parser.add_argument("--all-OpenOrbitLink", action="store_true",
                        help="Fetch all OpenOrbitLink-relevant satellites")
    args = parser.parse_args()

    if args.all_OpenOrbitLink:
        tle_data = fetch_OpenOrbitLink_satellites()
        output = args.output or "data/OpenOrbitLink_satellites.tle"
    elif args.norad:
        tle_data = fetch_tle_by_norad(args.norad)
        output = args.output or f"data/norad_{args.norad}.tle"
    elif args.group:
        tle_data = fetch_tle_group(args.group)
        output = args.output or f"data/{args.group}.tle"
    else:
        # Default: fetch amateur satellites
        tle_data = fetch_tle_group("amateur")
        output = args.output or "data/amateur.tle"

    # Save to file
    os.makedirs(os.path.dirname(output) if os.path.dirname(output) else ".", exist_ok=True)
    with open(output, 'w') as f:
        f.write(tle_data)

    lines = [l for l in tle_data.strip().split('\n') if l.strip()]
    n_sats = len(lines) // 3
    print(f"\nSaved {n_sats} satellites to {output}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
