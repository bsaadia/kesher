"""
Audits what the gazetteer matcher (app/processor/processing.py) currently
tags, or would tag, across the full message table -- without writing
anything. For each gazetteer entry, samples the matched message contexts so a
human (or an LLM given the output) can judge whether the matches plausibly
refer to the named place.

This is the tool meant to catch the *next* false-positive collision, instead
of waiting for someone to notice a bad map pin in production: re-run it
whenever the gazetteer grows or a new batch of messages comes in, and review
entries whose samples look wrong.

Uses iter_location_matches() from app.processor.processing directly, so this
can never drift from what the production matcher actually does.

Usage:
    python scripts/sweep_gazetteer_matches.py [--samples-per-entry N] [--out PATH]

Reads DATABASE_URL from the environment/.env like the rest of the app (see
models/base.py); defaults to whatever local DB that resolves to. Read-only:
issues SELECTs only, never writes to the database.
"""
import argparse
import json
import os
import random
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.base import engine
from models.location import Location
from models.message import Message
from app.processor.processing import iter_location_matches, normalize_hebrew_punctuation, _load_exclusions

CONTEXT_CHARS = 30  # characters of context on each side of a match, for the sample


def sweep(session: Session, samples_per_entry: int, seed: int = 42):
    random.seed(seed)
    exclusions = _load_exclusions()

    locations = session.execute(select(Location)).scalars().all()
    messages = session.execute(select(Message.id, Message.text)).all()

    normalized = [(msg_id, normalize_hebrew_punctuation(text)) for msg_id, text in messages if text]

    results = []
    for loc in locations:
        if not loc.name_he:
            continue

        matches = []  # (msg_id, surface_form, context)
        for msg_id, text in normalized:
            for m in iter_location_matches(loc, text, exclusions=exclusions):
                start, end = m.span()
                ctx = text[max(0, start - CONTEXT_CHARS):min(len(text), end + CONTEXT_CHARS)].replace("\n", " ")
                matches.append((msg_id, m.group(), ctx))
                break  # one match per message is enough signal for a sweep

        if not matches:
            continue

        surface_forms = {}
        for mid, sf, ctx in matches:
            surface_forms.setdefault(sf, []).append((mid, sf, ctx))

        sample = []
        for sf, items in surface_forms.items():
            sample.extend(items[:2])
        if len(sample) > samples_per_entry:
            sample = random.sample(sample, samples_per_entry)
        elif len(matches) > len(sample):
            remaining = [x for x in matches if x not in sample]
            extra_n = min(samples_per_entry - len(sample), len(remaining))
            sample.extend(random.sample(remaining, extra_n))

        results.append({
            "name_he": loc.name_he,
            "name_en": loc.name_en,
            "front": loc.front,
            "total_count": len(matches),
            "surface_forms": {sf: len(v) for sf, v in surface_forms.items()},
            "sample": [{"msg_id": mid, "surface": sf, "context": ctx} for mid, sf, ctx in sample],
        })

    results.sort(key=lambda r: -r["total_count"])
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples-per-entry", type=int, default=10,
                         help="Max sample messages to include per gazetteer entry (default: 10)")
    parser.add_argument("--out", default=None,
                         help="Write JSON results to this path instead of stdout")
    args = parser.parse_args()

    with Session(engine) as session:
        results = sweep(session, samples_per_entry=args.samples_per_entry)

    output = json.dumps(results, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Wrote {len(results)} entries with >=1 match to {args.out}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
