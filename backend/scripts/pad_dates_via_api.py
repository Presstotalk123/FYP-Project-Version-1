"""
Zero-pads unpadded date literals (e.g. '2020-7-16' -> '2020-07-16') in already-published
SQL questions, by calling the REAL, deployed backend API -- GET /questions,
GET /questions/{id}, PUT /questions/{id} -- exactly as the admin "Edit Question" form does.

Why this is needed
------------------
MySQL/LeetCode setup scripts accept unpadded dates, and the import pipeline
(mysqlToSqlite / applyImportFixups) never padded them. SQLite's date/time functions
(strftime, julianday, date()) and lexical date comparisons require ISO YYYY-MM-DD; given
'2020-7-16' they return NULL or sort wrong, so any question that groups/filters by
month/date grades against wrong results.

The fix goes through PUT /questions/{id} so the SERVER regenerates the question's SQLite
db file (on the same machine that grades it), re-executes the answer, and recomputes the
grading hash. This deliberately does NOT touch the DB directly (see
import_leetcode_questions_via_api.py for the full rationale).

Only the fields that actually change are sent. The padded correct_answer_query is sent
only when the answer itself contained an unpadded date, so data and answer stay consistent
for the server's hash recompute.

Auth: set AKELA_ADMIN_TOKEN to a real access token from a logged-in staff/admin browser
session (dev tools -> Local Storage -> access_token). Never minted locally.

Run from the backend directory:
    set AKELA_ADMIN_TOKEN=...   (or export on non-Windows)
    python scripts/pad_dates_via_api.py --dry-run
    python scripts/pad_dates_via_api.py
"""
import argparse
import os
import re
import time

import requests

BASE_URL = os.environ.get(
    "AKELA_API_BASE_URL",
    "https://ntu-akela-backend-ggcpejb0evb3fbg5.southeastasia-01.azurewebsites.net/api/v1",
)

# A date token (with an optional time part). Anchored on a 4-digit year so non-date
# hyphenated tokens are not matched. The month/day (and h/m/s if a time part is present)
# may be 1 or 2 digits; we zero-fill them to 2. Applied only to string-literal *content*
# (see pad_dates), so numbers/identifiers outside quotes are never touched.
_DATE_TOKEN = re.compile(
    r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"             # Y-M-D
    r"(?:([ T])(\d{1,2}):(\d{1,2}):(\d{1,2}))?"    # optional  HH:MM:SS
)


def _pad_token(m: re.Match) -> str:
    y, mo, d, sep, hh, mi, ss = m.groups()
    out = f"{y}-{int(mo):02d}-{int(d):02d}"
    if sep is not None:
        out += f"{sep}{int(hh):02d}:{int(mi):02d}:{int(ss):02d}"
    return out


def pad_dates(sql: str) -> str:
    """Zero-pad every date/datetime literal that appears inside a single-quoted string.
    Quote-aware: walks the SQL, and within each '...' literal pads every date token (so a
    range with two dates in one literal is fully handled), honoring '' as an escaped quote.
    Content outside quotes -- identifiers, keywords, numbers -- is never altered. Idempotent:
    an already-padded date rewrites to the identical string."""
    if not sql:
        return sql
    out = []
    i = 0
    n = len(sql)
    while i < n:
        c = sql[i]
        if c == "'":
            j = i + 1
            buf = []
            closed = False
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":  # doubled '' = escaped quote
                        buf.append("''")
                        j += 2
                        continue
                    closed = True
                    break
                buf.append(sql[j])
                j += 1
            padded = _DATE_TOKEN.sub(_pad_token, "".join(buf))
            out.append("'" + padded + ("'" if closed else ""))
            i = j + 1 if closed else n
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _sample_changes(before: str, after: str, limit: int = 4) -> list:
    """A few before->after date tokens, for the dry-run report."""
    b = re.findall(r"\d{4}-\d{1,2}-\d{1,2}", before or "")
    a = re.findall(r"\d{4}-\d{1,2}-\d{1,2}", after or "")
    diffs = [f"{x}->{y}" for x, y in zip(b, a) if x != y]
    return diffs[:limit]


def _session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _check_auth(s: requests.Session) -> dict:
    resp = s.get(f"{BASE_URL}/auth/me", timeout=30)
    if resp.status_code != 200:
        raise SystemExit(
            f"Auth check failed: GET /auth/me -> {resp.status_code} {resp.text}\n"
            "Get a fresh AKELA_ADMIN_TOKEN from a logged-in staff/admin browser session."
        )
    me = resp.json()
    if me.get("role") not in ("staff", "admin"):
        raise SystemExit(f"Token belongs to role={me.get('role')!r}, need staff or admin.")
    print(f"Authenticated as {me.get('email')} (role={me.get('role')}).")
    return me


def _all_question_ids(s: requests.Session) -> list:
    ids = []
    skip = 0
    while True:
        resp = s.get(f"{BASE_URL}/questions", params={"skip": skip, "limit": 100}, timeout=30)
        resp.raise_for_status()
        page = resp.json()
        if not page:
            break
        ids.extend((q["id"], q["title"]) for q in page)
        skip += len(page)
        if len(page) < 100:
            break
    return ids


# Fields the padder scans/fixes, in the order they'd be sent to PUT.
_SQL_FIELDS = ("schema_sql", "sample_data_sql", "correct_answer_query")


def pad_dates_in_questions(dry_run: bool) -> None:
    token = os.environ.get("AKELA_ADMIN_TOKEN")
    if not token:
        raise SystemExit("Set AKELA_ADMIN_TOKEN to a real staff/admin access token first.")

    s = _session(token)
    _check_auth(s)

    print("Listing all questions...")
    ids = _all_question_ids(s)
    print(f"  {len(ids)} questions in the bank.")

    updated = []
    skipped_no_change = []
    failed = []

    for qid, title in ids:
        try:
            resp = s.get(f"{BASE_URL}/questions/{qid}", timeout=30)
            if resp.status_code != 200:
                failed.append((qid, title, f"get {resp.status_code}: {resp.text[:200]}"))
                continue
            q = resp.json()

            payload = {}
            samples = []
            for f in _SQL_FIELDS:
                before = q.get(f)
                if not before:
                    continue
                after = pad_dates(before)
                if after != before:
                    payload[f] = after
                    samples += [f"{f}: {x}" for x in _sample_changes(before, after)]

            if not payload:
                skipped_no_change.append((qid, title))
                continue

            print(f"  #{qid} {title} -> fields {list(payload)}; {', '.join(samples[:4])}")

            if dry_run:
                updated.append((qid, title))
                continue

            put = s.put(f"{BASE_URL}/questions/{qid}", json=payload, timeout=60)
            if put.status_code != 200:
                failed.append((qid, title, f"put {put.status_code}: {put.text[:300]}"))
                continue
            updated.append((qid, title))
            time.sleep(0.05)  # be polite to the shared deployed instance

        except requests.RequestException as e:
            failed.append((qid, title, f"request error: {e}"))

    mode = "DRY RUN - nothing written" if dry_run else "UPDATED"
    print(f"\n=== {mode} ===")
    print(f"{'Would update' if dry_run else 'Updated'}: {len(updated)}")
    print(f"Skipped (already padded / no dates): {len(skipped_no_change)}")
    print(f"Failed: {len(failed)}")
    for qid, title, err in failed:
        print(f"  #{qid} {title}: {err}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not PUT.")
    args = parser.parse_args()
    pad_dates_in_questions(dry_run=args.dry_run)
