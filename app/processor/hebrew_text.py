import re

# Geresh (marks a borrowed/foreign consonant, e.g. ג' for the "j" sound) and
# gershayim (marks an acronym, e.g. צה"ל) both appear in scraped text in
# several visually-similar Unicode forms. Canonicalizing them before matching
# means a gazetteer name and a message only need to agree on meaning, not on
# which of several apostrophe/quote characters was typed.
_GERESH_VARIANTS = "'’`׳"       # ' ’ ` ׳
_GERSHAYIM_VARIANTS = '"“”״'    # " “ ” ״

CANONICAL_GERESH = "׳"      # ׳
CANONICAL_GERSHAYIM = "״"   # ״

_GERESH_RE = re.compile(f"[{re.escape(_GERESH_VARIANTS)}]")
_GERSHAYIM_RE = re.compile(f"[{re.escape(_GERSHAYIM_VARIANTS)}]")


def normalize_hebrew_punctuation(text: str) -> str:
    """
    Canonicalizes geresh/gershayim variants so that a gazetteer name and a
    message text only need to agree on meaning, not on which visually-similar
    apostrophe/quote character was used. Applied to both sides of a match.
    """
    if not text:
        return text
    text = _GERSHAYIM_RE.sub(CANONICAL_GERSHAYIM, text)
    text = _GERESH_RE.sub(CANONICAL_GERESH, text)
    return text


# Geresh/gershayim play two unrelated roles in this corpus: marking an
# *internal* abbreviation (חמא"ס, gershayim before the last letter of a
# multi-letter word) versus wrapping a term in single/double "scare quotes"
# (ה'עבסנים', בשכונת "חמד" -- a single-letter word, usually one of the seven
# prefix letters, immediately touching an opening or closing quote mark, with
# no space). Python's built-in \b treats the mark as a non-word character in
# both cases: that's correct for the quote-wrapping case, but wrong for the
# acronym case -- it fires *inside* חמא"ס, splitting it into two
# falsely-bounded tokens ("חמא" + "ס") and letting an unrelated gazetteer
# entry match the fragment.
#
# The real Hebrew orthography rule distinguishes them: a gershayim/geresh
# used as an acronym marker always has *two or more* letters on the side
# being abbreviated (rarely just one, per standard usage), while a scare
# quote has exactly one single-letter word (ה/ו/ב/ל/כ/מ/ש) directly against
# it. So a mark only signals "still inside the same word" when two or more
# word characters sit directly on the same side of it.
_MARKS = re.escape(CANONICAL_GERESH) + re.escape(CANONICAL_GERSHAYIM)
BOUNDARY_START = rf"(?<!\w)(?<!\w\w[{_MARKS}])"
BOUNDARY_END = rf"(?!\w)(?![{_MARKS}]\w(?!\w))"
