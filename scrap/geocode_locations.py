#!/usr/bin/env python3
"""
Geocode locations_list.csv using Nominatim.
Outputs scrap/data/geocoded_locations.csv with lat, lon, precision, matched_query columns.

Bounding boxes (west, south, east, north) verified against OSM / Wikidata extents:
  Gaza Strip:  34.20°E–34.56°E, 31.21°N–31.60°N
  West Bank:   34.85°E–35.58°E, 31.32°N–32.58°N
"""

import csv
import sys
from pathlib import Path

from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

INPUT_CSV = Path(__file__).parent / "locations_list.csv"
OUTPUT_CSV = Path(__file__).parent / "data" / "geocoded_locations.csv"

FRONT_MAP = {
    "Gaza Strip": {
        "country_codes": "ps",
        "bbox": (34.20, 31.21, 34.56, 31.60),  # (west, south, east, north)
    },
    "West Bank (Judea & Samaria)": {
        "country_codes": "ps",
        "bbox": (34.85, 31.32, 35.58, 32.58),
    },
    "Lebanon": {"country_codes": "lb"},
    "Syria":   {"country_codes": "sy"},
    "Yemen":   {"country_codes": "ye"},
    "Iran":    {"country_codes": "ir"},
}


def inside_bbox(lat, lon, bbox):
    west, south, east, north = bbox
    return south <= lat <= north and west <= lon <= east


def bbox_to_viewbox(bbox):
    """Convert (west, south, east, north) to geopy viewbox [(north_lat, west_lon), (south_lat, east_lon)]."""
    west, south, east, north = bbox
    return [(north, west), (south, east)]


def try_geocode(geocode_fn, query, *, country_codes=None, viewbox=None, bounded=False):
    """Single geocode attempt; returns location or None."""
    if not query or not query.strip():
        return None
    kwargs = {}
    if country_codes:
        kwargs["country_codes"] = country_codes
    if viewbox:
        kwargs["viewbox"] = viewbox
        kwargs["bounded"] = bounded
    try:
        return geocode_fn(query, **kwargs)
    except Exception as e:
        print(f"  [warn] geocode error for '{query}': {e}", file=sys.stderr)
        return None


def main():
    geolocator = Nominatim(user_agent="tzahal_mapper_geocoder_v1")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.0, error_wait_seconds=5.0)

    with open(INPUT_CSV, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    output_rows = []
    unresolved_names = []

    for i, row in enumerate(rows, 1):
        name_en = row["name_en"].strip()
        name_ar = row["name_ar"].strip()
        front = row["front"].strip()
        config = FRONT_MAP.get(front, {})
        cc = config.get("country_codes", "")
        bbox = config.get("bbox")
        has_bbox = bbox is not None
        viewbox = bbox_to_viewbox(bbox) if has_bbox else None

        result = None
        matched = ""
        precision = "unresolved"

        def valid(loc):
            """Return loc if it passes bbox validation (or no bbox needed), else None."""
            if loc is None:
                return None
            if has_bbox and not inside_bbox(loc.latitude, loc.longitude, bbox):
                return None
            return loc

        # Attempt 1: name_en, country_codes
        loc = valid(try_geocode(geocode, name_en, country_codes=cc))
        if loc:
            result, matched, precision = loc, "en", "exact"

        # Attempt 2: name_ar, country_codes
        if result is None:
            loc = valid(try_geocode(geocode, name_ar, country_codes=cc))
            if loc:
                result, matched, precision = loc, "ar", "exact"

        # Attempt 3: broader search
        #   Gaza/West Bank: name_en bounded to region viewbox (no cc filter)
        #   Other countries: name_en without country_codes restriction
        if result is None:
            if has_bbox:
                loc = valid(try_geocode(geocode, name_en, viewbox=viewbox, bounded=True))
            else:
                loc = try_geocode(geocode, name_en)
            if loc:
                result, matched, precision = loc, "en_broad", "fallback"

        if result is not None:
            row["lat"] = round(result.latitude, 6)
            row["lon"] = round(result.longitude, 6)
            row["precision"] = precision
            row["matched_query"] = matched
            print(f"[{i:3d}/{len(rows)}] [{precision:>10}] {name_en}: {row['lat']}, {row['lon']}")
        else:
            row["lat"] = ""
            row["lon"] = ""
            row["precision"] = "unresolved"
            row["matched_query"] = ""
            unresolved_names.append(name_en)
            print(f"[{i:3d}/{len(rows)}] [unresolved] {name_en}")

        output_rows.append(row)

    # Write output CSV
    OUTPUT_CSV.parent.mkdir(exist_ok=True)
    base_fields = list(rows[0].keys()) if rows else []
    added_fields = ["lat", "lon", "precision", "matched_query"]
    fieldnames = base_fields + [f for f in added_fields if f not in base_fields]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    total = len(output_rows)
    exact = sum(1 for r in output_rows if r["precision"] == "exact")
    fallback = sum(1 for r in output_rows if r["precision"] == "fallback")
    unres = sum(1 for r in output_rows if r["precision"] == "unresolved")

    print(f"\n=== Summary ===")
    print(f"Total rows:   {total}")
    print(f"  Exact:      {exact} ({exact/total*100:.1f}%)")
    print(f"  Fallback:   {fallback} ({fallback/total*100:.1f}%)")
    print(f"  Unresolved: {unres} ({unres/total*100:.1f}%)")
    if unresolved_names:
        print(f"\nUnresolved ({len(unresolved_names)}) — manual follow-up needed:")
        for name in unresolved_names:
            print(f"  - {name}")
    print(f"\nOutput: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
