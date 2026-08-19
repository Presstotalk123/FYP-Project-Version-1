"""
Registers the converted leetcode_questions.json data (see
frontend/scripts/convert-leetcode-questions.mjs) by calling the REAL, deployed
backend API -- POST /questions, PUT /lad/questions/{id}/concepts,
POST /questions/{id}/publish -- exactly as the admin "New Question" form does.

This deliberately does NOT write to the DB directly. The previous session's direct
Postgres writes bypassed the running app, so the per-question SQLite files were
generated on the wrong machine's disk (see the plan for the full diagnosis) and
every one of those questions failed with "unable to open database file" once
deployed. Going through the real API means the SERVER that will actually grade
these questions is the one generating (and keeping) its own db file.

Auth: set AKELA_ADMIN_TOKEN to a real access token from a logged-in staff/admin
browser session (dev tools -> Local Storage -> access_token). Never minted locally.

Run from the backend directory:
    set AKELA_ADMIN_TOKEN=...   (or export on non-Windows)
    python scripts/import_leetcode_questions_via_api.py --dry-run
    python scripts/import_leetcode_questions_via_api.py
"""
import argparse
import json
import os
import sys
import time

import requests

BASE_URL = os.environ.get(
    "AKELA_API_BASE_URL",
    "https://ntu-akela-backend-ggcpejb0evb3fbg5.southeastasia-01.azurewebsites.net/api/v1",
)

CONVERTED_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend", "scripts", "leetcode_questions.converted.json",
)


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


def _existing_titles(s: requests.Session) -> set:
    titles = set()
    skip = 0
    while True:
        resp = s.get(f"{BASE_URL}/questions", params={"skip": skip, "limit": 100}, timeout=30)
        resp.raise_for_status()
        page = resp.json()
        if not page:
            break
        titles.update(q["title"] for q in page)
        skip += len(page)
        if len(page) < 100:
            break
    return titles


def import_questions(dry_run: bool) -> None:
    token = os.environ.get("AKELA_ADMIN_TOKEN")
    if not token:
        raise SystemExit("Set AKELA_ADMIN_TOKEN to a real staff/admin access token first.")

    with open(CONVERTED_JSON_PATH, "r", encoding="utf-8") as f:
        entries = json.load(f)

    s = _session(token)
    _check_auth(s)

    print("Fetching existing question titles for idempotency...")
    existing = _existing_titles(s)
    print(f"  {len(existing)} existing titles found.")

    concepts_resp = s.get(f"{BASE_URL}/lad/concepts", timeout=30)
    concepts_resp.raise_for_status()
    slug_to_id = {c["slug"]: c["id"] for c in concepts_resp.json()}
    print(f"  {len(slug_to_id)} SQL concepts in taxonomy.")

    created = []
    skipped_duplicate = []
    failed = []
    order_sensitive_applied = []

    for entry in entries:
        title = entry["title"]

        if title in existing:
            skipped_duplicate.append((entry["id"], title))
            continue

        payload = {
            "title": title,
            "description": entry["description"],
            "difficulty": entry["difficulty"],
            "schema_sql": entry["schema_sql"],
            "sample_data_sql": entry["sample_data_sql"],
            "correct_answer_query": entry["correct_answer_query"],
            "advanced_sql_testing": False,
            "order_sensitive": entry["order_sensitive"],
            "hide_correctness": False,
            # entry["id"] is the LeetCode problem number — persist it so the bank keeps
            # DATABASE_README_EN.md ordering without a separate backfill for new imports.
            "leetcode_id": int(entry["id"]),
        }

        if dry_run:
            created.append((entry["id"], title))
            if entry["order_sensitive"]:
                order_sensitive_applied.append((entry["id"], title))
            continue

        try:
            resp = s.post(f"{BASE_URL}/questions", json=payload, timeout=60)
            if resp.status_code != 201:
                failed.append((entry["id"], title, f"create {resp.status_code}: {resp.text[:300]}"))
                continue
            question_id = resp.json()["id"]

            if entry["concepts"]:
                body_tags = [
                    {"concept_id": slug_to_id[c["slug"]], "weight": c["weight"]}
                    for c in entry["concepts"] if c["slug"] in slug_to_id
                ]
                if body_tags:
                    tag_resp = s.put(
                        f"{BASE_URL}/lad/questions/{question_id}/concepts",
                        json={"tags": body_tags},
                        timeout=30,
                    )
                    if tag_resp.status_code != 200:
                        print(f"  warning: concept tagging failed for #{entry['id']} {title}: "
                              f"{tag_resp.status_code} {tag_resp.text[:200]}")

            pub_resp = s.post(f"{BASE_URL}/questions/{question_id}/publish", timeout=30)
            if pub_resp.status_code != 200:
                failed.append((entry["id"], title, f"publish {pub_resp.status_code}: {pub_resp.text[:300]}"))
                continue

            created.append((entry["id"], title))
            if entry["order_sensitive"]:
                order_sensitive_applied.append((entry["id"], title))
            existing.add(title)

        except requests.RequestException as e:
            failed.append((entry["id"], title, f"request error: {e}"))

        time.sleep(0.05)  # be polite to the shared deployed instance

    mode = "DRY RUN — nothing written" if dry_run else "IMPORTED"
    print(f"\n=== {mode} ===")
    print(f"Created/validated: {len(created)}")
    print(f"Skipped (already exists): {len(skipped_duplicate)}")
    print(f"Failed: {len(failed)}")
    for qid, title, err in failed:
        print(f"  #{qid} {title}: {err}")
    print(f"\norder_sensitive = true for {len(order_sensitive_applied)} question(s):")
    for qid, title in order_sensitive_applied:
        print(f"  #{qid} {title}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Validate only; do not create/publish.")
    args = parser.parse_args()
    import_questions(dry_run=args.dry_run)
