"""Clean up an answer before parsing, without moving any character.

Students paste answers from Word, PowerPoint and PDFs, which bring look-alike symbols
(⨝ for ⋈, ∏ for Π, an en dash for −) and invisible spaces. The lexer only knows the
canonical symbols, so these are swapped one-for-one here. Every replacement is a
single character for a single character, so the line/column of every error still
points at the right place in the student's editor.

Schema names can also contain "-" (Tutorial 5.5 Q3 uses teamid-one), which would
otherwise read as "teamid minus one". When the caller passes the schema's names, the
"-" inside each of them is swapped for U+2010 (‐), which the grammar accepts inside a
NAME; the parser turns it back into "-" (see ``restore_name``).
"""
import re
from typing import Iterable

INTERNAL_HYPHEN = "‐"

_LOOKALIKES = {
    "⨝": "⋈",   # ⨝ JOIN (Word's equation editor)
    "∏": "Π",   # ∏ n-ary product, often used for projection
    "П": "Π",   # П Cyrillic Pe
    "ϱ": "ρ",   # ϱ rho symbol
    "ς": "σ",   # ς final sigma
    "⨯": "×",   # ⨯ vector cross product
    "∖": "−",   # ∖ set minus
    "–": "−",   # – en dash (Word auto-corrects " - ")
    "—": "−",   # — em dash
    "⋃": "∪",   # ⋃ n-ary union
    "⋂": "∩",   # ⋂ n-ary intersection
    "≦": "≤",   # ≦
    "≧": "≥",   # ≧
    "⩽": "≤",   # ⩽
    "⩾": "≥",   # ⩾
    "⟶": "→",   # ⟶ long arrow
    "⟵": "←",   # ⟵ long arrow
    INTERNAL_HYPHEN: "-",  # a typed ‐ is just a hyphen; only we may insert U+2010
    "‑": "-",   # non-breaking hyphen
}
# Invisible or unusual spaces become a plain space (not removed, to keep columns).
for _space in (" ", " ", " ", " ", " ", " ", " ",
               " ", " ", " ", "​", " ", " ", "　", "﻿"):
    _LOOKALIKES[_space] = " "
_TABLE = str.maketrans(_LOOKALIKES)

_STRING = re.compile(r"'(?:[^']|'')*'|‘[^’]*’|\"[^\"]*\"|“[^”]*”")


def normalize(text: str, names: Iterable[str] = ()) -> str:
    """Return ``text`` with look-alike symbols replaced; same length as the input."""
    text = text.translate(_TABLE)
    hyphenated = sorted({n for n in names if "-" in n}, key=len, reverse=True)
    if not hyphenated:
        return text
    pattern = re.compile(r"(?<![\w‐])(" + "|".join(re.escape(n) for n in hyphenated)
                         + r")(?![\w‐])", re.IGNORECASE)
    # Leave string literals alone: 'teamid-one' in quotes is data, not a name.
    out, last = [], 0
    for m in _STRING.finditer(text):
        out.append(pattern.sub(_protect, text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(pattern.sub(_protect, text[last:]))
    return "".join(out)


def _protect(m: re.Match) -> str:
    return m.group(0).replace("-", INTERNAL_HYPHEN)


def restore_name(name: str) -> str:
    return name.replace(INTERNAL_HYPHEN, "-")
