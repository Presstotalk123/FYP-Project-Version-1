"""Import authorised local source files through the *serving* staff API.

No source is published. Use --dry-run for local diagnostics; actual writes require
--authorised. API tokens are read from AKELA_ADMIN_TOKEN, never printed.
"""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--authorised", action="store_true")
    parser.add_argument("--api", default=os.environ.get("AKELA_API_BASE_URL", "http://localhost:8000/api/v1"))
    args = parser.parse_args()
    entries = [row for path in args.sources for row in json.loads(path.read_text(encoding="utf-8"))]
    if args.dry_run:
        from app.services.incident_authoring import normalise_source
        for row in entries:
            snapshot, errors = normalise_source(row)
            print(json.dumps({"id": row.get("id"), "eligible": snapshot["eligible"], "diagnostics": errors}))
        return
    if not args.authorised:
        parser.error("Confirm permission to use the sources with --authorised, or inspect with --dry-run.")
    token = os.environ.get("AKELA_ADMIN_TOKEN")
    if not token:
        parser.error("Set AKELA_ADMIN_TOKEN to your signed-in staff/admin access token.")
    import httpx
    with httpx.Client(base_url=args.api.rstrip("/") + "/", headers={"Authorization": "Bearer " + token}, timeout=180) as client:
        for offset in range(0, len(entries), 10):
            response = client.post("admin/competition-sources/import", json={"entries": entries[offset:offset + 10], "authorised": True})
            response.raise_for_status()
            print(json.dumps([{k: row[k] for k in ("id", "external_id", "eligible", "diagnostics")} for row in response.json()]))


if __name__ == "__main__":
    main()
