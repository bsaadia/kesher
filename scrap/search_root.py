"""
Search all messages for words derived from a Hebrew root.
Uses a consonant-skeleton regex — no external stemmer required.

Usage (from project root):
    python scrap/search_root.py          # defaults to root תקף
    python scrap/search_root.py --root ירה
"""

import sys
import os
import re
import argparse
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from sqlalchemy import select
from models.base import engine
from models.message import Message
from bidi.algorithm import get_display


def rtl(text: str) -> str:
    return get_display(str(text))


# Root-specific patterns ──────────────────────────────────────────────────────
# Each pattern matches the consonant skeleton of the root inside a Hebrew word.
# Common Hebrew prefix letters (ב ל ה מ כ ו ש) are stripped before matching.
# The dictionary maps a root string to a compiled pattern; any root not listed
# falls back to a naive consonant-sequence pattern.

ROOT_PATTERNS = {
    # תקף: ת(ו?)ק(י?)פ — excludes תקופה (period) where ו sits between ק and פ
    "תקף": re.compile(r"ת[ו]?ק[י]?פ"),
}

PREFIX_STRIP = re.compile(r"^[בלהמכוש]+")
HEBREW_WORD  = re.compile(r"[א-ת]+")


def pattern_for_root(root: str) -> re.Pattern:
    if root in ROOT_PATTERNS:
        return ROOT_PATTERNS[root]
    # Fallback: consonants in sequence, optional single vowel letter between each pair
    consonants = list(root)
    parts = [consonants[0]]
    for c in consonants[1:]:
        parts.append(r"[ויא]?")
        parts.append(c)
    return re.compile("".join(parts))


def word_matches(word: str, pattern: re.Pattern) -> bool:
    stripped = PREFIX_STRIP.sub("", word)
    return bool(pattern.search(stripped)) or bool(pattern.search(word))


def search(texts, ids, channels, pattern):
    results = []
    for msg_id, text, channel in zip(ids, texts, channels):
        words = HEBREW_WORD.findall(text)
        matched = [w for w in words if word_matches(w, pattern)]
        if matched:
            results.append({"id": msg_id, "text": text, "channel": channel, "matched": matched})
    return results


def print_results(results, root, sample):
    word_counts = Counter(w for r in results for w in r["matched"])

    WIDTH = 80
    bar = "═" * WIDTH

    print()
    print(bar)
    print(f"  root: {rtl(root)}")
    print(f"  messages matched: {len(results)}")
    print(bar)

    print()
    print("  WORD FORMS FOUND:")
    for word, count in word_counts.most_common():
        print(f"    {count:>4}  {rtl(word)}")

    print()
    print(f"  SAMPLE MESSAGES (first {min(sample, len(results))}):")
    print("  " + "─" * (WIDTH - 2))
    for r in results[:sample]:
        print(f"  [{r['id']:>5}]  channel: {rtl(r['channel'])}")
        # Print message line by line, bidi-corrected, indented
        for line in r["text"].splitlines():
            line = line.strip()
            if line:
                print(f"           {rtl(line)}")
        print()

    print(bar)
    print()


def main():
    parser = argparse.ArgumentParser(description="Search Hebrew messages by root consonants")
    parser.add_argument("--root",   default="תקף", help="Three-letter root (default: תקף)")
    parser.add_argument("--sample", type=int, default=20, help="Messages to print (default: 20)")
    args = parser.parse_args()

    pattern = pattern_for_root(args.root)

    print(f"Loading messages ...", flush=True)
    with Session(engine) as session:
        rows = session.execute(select(Message.id, Message.text, Message.channel)).all()

    ids      = [r.id      for r in rows if r.text and r.text.strip()]
    texts    = [r.text    for r in rows if r.text and r.text.strip()]
    channels = [r.channel for r in rows if r.text and r.text.strip()]

    print(f"Searching {len(texts)} messages for root {args.root} ...", flush=True)
    results = search(texts, ids, channels, pattern)

    print_results(results, args.root, args.sample)


if __name__ == "__main__":
    main()
