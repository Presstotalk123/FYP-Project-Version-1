"""Backfill questions.leetcode_id from DATABASE_README_EN.md.

DATABASE_README_EN.md lists the LeetCode database problems in ascending problem-number
order — the ordering we want the bank to follow. That number was never stored when the
questions were imported (see backend/scripts/import_leetcode_questions_via_api.py), so this
one-off backfill parses the README table for its `number -> title` rows and writes the
number onto the matching stored question (matched by normalized title).

Unlike the import script, this writes the DB directly (like the run_*_migration.py runners,
via settings.DATABASE_URL). That is safe here because it only sets a scalar column — no
per-question SQLite file is generated, which was the reason imports had to go through the API.

Idempotent: only rows with leetcode_id IS NULL are touched. Run from the backend directory:
    python scripts/backfill_leetcode_ids.py --dry-run   # report matches, write nothing
    python scripts/backfill_leetcode_ids.py             # apply
"""
import argparse
import os
import re
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
README_PATH = os.path.join(REPO_ROOT, "DATABASE_README_EN.md")

# A README solutions row: | 0175 | [Combine Two Tables](/solution/...) | `Database` | Easy | |
ROW_RE = re.compile(r"^\|\s*(\d{3,4})\s*\|\s*\[([^\]]+)\]")


def _normalize(title: str) -> str:
    """Lowercase and strip every non-alphanumeric char, so encoding quirks in the README
    ("Capital GainLoss", "Apples & Oranges") still match the stored titles ("Capital
    Gain/Loss", "Apples & Oranges")."""
    return re.sub(r"[^a-z0-9]", "", title.lower())


def parse_readme() -> dict:
    """Return {normalized_title: leetcode_number} from the README solutions table."""
    mapping = {}
    with open(README_PATH, "r", encoding="utf-8") as f:
        for line in f:
            m = ROW_RE.match(line)
            if not m:
                continue
            number = int(m.group(1))
            title = m.group(2).strip()
            mapping[_normalize(title)] = number
    return mapping


def _fetch_unset_rows(conn, is_sqlite: bool):
    """Return [(id, title)] for questions with leetcode_id still NULL."""
    if is_sqlite:
        cur = conn.execute("SELECT id, title FROM questions WHERE leetcode_id IS NULL")
        return cur.fetchall()
    with conn.cursor() as cur:
        cur.execute("SELECT id, title FROM questions WHERE leetcode_id IS NULL")
        return cur.fetchall()


def _update(conn, is_sqlite: bool, question_id: int, leetcode_id: int):
    if is_sqlite:
        conn.execute(
            "UPDATE questions SET leetcode_id = ? WHERE id = ?", (leetcode_id, question_id)
        )
    else:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE questions SET leetcode_id = %s WHERE id = %s",
                (leetcode_id, question_id),
            )


def backfill(dry_run: bool) -> None:
    title_to_number = parse_readme()
    print(f"Parsed {len(title_to_number)} numbered titles from DATABASE_README_EN.md.")

    is_sqlite = settings.DATABASE_URL.startswith("sqlite")
    if is_sqlite:
        import sqlite3
        conn = sqlite3.connect(settings.DATABASE_URL.replace("sqlite:///", ""))
    else:
        import psycopg2
        conn = psycopg2.connect(settings.DATABASE_URL)

    matched = []
    unmatched = []
    try:
        rows = _fetch_unset_rows(conn, is_sqlite)
        print(f"{len(rows)} question(s) have leetcode_id unset.")
        for question_id, title in rows:
            number = title_to_number.get(_normalize(title))
            if number is None:
                unmatched.append((question_id, title))
                continue
            matched.append((question_id, title, number))
            if not dry_run:
                _update(conn, is_sqlite, question_id, number)
        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    mode = "DRY RUN — nothing written" if dry_run else "APPLIED"
    print(f"\n=== {mode} ===")
    print(f"Matched: {len(matched)}")
    print(f"Unmatched (left NULL — fix by hand if these should be numbered): {len(unmatched)}")
    for question_id, title in unmatched:
        print(f"  #{question_id} {title}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report matches; write nothing.")
    args = parser.parse_args()
    print("=" * 60)
    print("Backfill questions.leetcode_id from DATABASE_README_EN.md")
    print("=" * 60)
    backfill(dry_run=args.dry_run)
