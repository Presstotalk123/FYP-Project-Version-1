# Mass-uploading SQL practice questions

This guide explains how to bulk-import many SQL questions at once. It converts a
JSON file of LeetCode-style problems into published questions on the live site.

> **For one or two questions**, don't use this — just use the admin **New Question**
> form in the UI. It already has the "Convert to SQLite" and "Suggest concepts"
> buttons. This guide is only worth it for uploading in bulk.

---

## How it works (in one sentence)

A **Node** script converts each problem (MySQL → SQLite, detects concept tags and
whether row-order matters), then a **Python** script creates each question by calling
the **real deployed API** — the exact same `POST /questions` the admin form uses — so
every question's practice database is built on the server that will grade it.

There are two files you run, in order:

| Step | File | Run from |
|------|------|----------|
| 1. Convert | `frontend/scripts/convert-leetcode-questions.mjs` | `frontend/` |
| 2. Import  | `backend/scripts/import_leetcode_questions_via_api.py` | `backend/` |

---

## Prerequisites (one-time)

- **Node.js 22+** and **Python 3.11+** installed.
- Python `requests` installed: `pip install requests` (already in `backend/requirements.txt`).
- You are logged into the deployed site as a **staff or admin** account.

---

## Step 0 — Prepare the questions

Edit **`leetcode_questions.json`** (at the repo root). It's a JSON array; add one
object per question. Fields:

```json
{
  "id": "1234",
  "title": "Some Problem Title",
  "slug": "some-problem-title",
  "difficulty": "Easy",
  "question_markdown": "Table: `Employees`\n\n```\n+----+------+\n| id | name |\n+----+------+\n```\n\nWrite a query that ...\n\n**Example 1:**\n\n```\nInput: ...\nOutput: ...\n```",
  "sql_schema": "Create table If Not Exists Employees (id int, name varchar(50)); Truncate table Employees; insert into Employees (id, name) values (1, 'Alice');",
  "answer": "select id, name from Employees order by id",
  "fetch_status": "success"
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `id` | yes | Any unique string. Only used for logging/skip-lists, not stored. |
| `title` | yes | Must be **unique** — the importer skips titles that already exist. |
| `slug` | no | Only used by helper scripts; not required for import. |
| `difficulty` | yes | `Easy`, `Medium`, or `Hard` (case-insensitive). |
| `question_markdown` | yes | The problem statement. Use ` ``` ` fences around ASCII tables — this is what students see. If empty, the description falls back to a raw schema dump (bad — avoid). |
| `sql_schema` | yes | MySQL/LeetCode dialect is fine. May mix `CREATE TABLE`, `TRUNCATE`, and `INSERT`. The converter splits and rewrites it. |
| `answer` | yes | The correct answer query. Must be **read-only** (see limits below). |
| `fetch_status` | yes | Set to `"success"`. Rows with `"failed"` are skipped. |

**Answer-query limits** (these fail and are reported, not guessed):
- Must be read-only: `SELECT`, `WITH ... SELECT` (CTE), `EXPLAIN`, or `VALUES`.
- **Not** supported: parameterized `CREATE FUNCTION` / `CREATE PROCEDURE`, or bare
  `UPDATE` / `DELETE` (those need the admin form's "Advanced SQL Testing" mode).
- The answer must return **at least one row** against the sample data.

---

## Step 1 — Convert

From the `frontend/` folder:

```bash
node --experimental-strip-types scripts/convert-leetcode-questions.mjs
```

This reads `leetcode_questions.json` and writes
`frontend/scripts/leetcode_questions.converted.json` (a generated file — you never
edit it). It prints:
- how many it converted / skipped,
- which questions it marked **order-sensitive** (row order graded) and why.

The conversion reuses the app's own `mysqlToSqlite` and `detectConcepts`, so the
result matches what the admin form's buttons produce. It also handles common MySQL
functions (`DATEDIFF`, `DATE_FORMAT`, `MONTH`, `YEAR`, `LEFT`, `ENUM` columns, etc.).

---

## Step 2 — Get an access token

The importer talks to the live API as you, so it needs your login token:

1. Log into the deployed site as staff/admin.
2. Open browser **DevTools** (F12) → **Application** (Chrome) / **Storage** (Firefox)
   → **Local Storage** → the site's origin.
3. Copy the value of the **`access_token`** key.

Tokens expire (typically hours). If a run stops mid-way with `401`, just grab a fresh
token and re-run — the import is idempotent (see below).

---

## Step 3 — Import

From the `backend/` folder, set the token, then dry-run before the real run:

**PowerShell:**
```powershell
$env:AKELA_ADMIN_TOKEN = "<paste token>"
python scripts/import_leetcode_questions_via_api.py --dry-run
python scripts/import_leetcode_questions_via_api.py
```

**bash / Git Bash:**
```bash
export AKELA_ADMIN_TOKEN="<paste token>"
python scripts/import_leetcode_questions_via_api.py --dry-run
python scripts/import_leetcode_questions_via_api.py
```

- `--dry-run` checks your token and connectivity and reports what *would* happen,
  without creating anything.
- The real run creates each question, tags its concepts, and **publishes** it.

At the end it prints a summary: created / skipped-as-duplicate / failed (with the
exact error per failed question).

---

## Idempotency — re-running is safe

The importer **skips any question whose title already exists**. So you can:
- Re-run after fixing a few failures — only the new/fixed ones get created.
- Re-run after a token expiry — it picks up where it left off.

You will **not** get duplicates as long as titles are unique.

---

## Troubleshooting the common failures

| Error in the report | Cause | Fix |
|---------------------|-------|-----|
| `Only SELECT/WITH (CTE)/EXPLAIN queries are allowed` | Answer starts with something else (e.g. a leading `(`, or DML). | Rewrite the answer as a plain `SELECT`/`WITH`, or use the admin form's Advanced mode. |
| `unable to open database file` (at runtime, not import) | A question was created by writing to the DB directly instead of via the API. | **Never** bypass the API. This script already uses the API — don't use any direct-DB import script. |
| `no such function: regexp` / `concat` / `sqrt` / `ceiling` | The deployed server's SQLite build lacks that function. | Rewrite the answer without it, or author the question manually. |
| `near "order": syntax error` | `ORDER BY` inside an aggregate (`GROUP_CONCAT(... ORDER BY ...)`) — deployed SQLite too old. | Rewrite without the in-aggregate ORDER BY. |
| `ambiguous column name: X` | The answer references a column present in two joined tables without qualifying it. | Qualify it (`t.X`) in the answer. |
| `must return at least one row` | The answer returns nothing against the sample data. | Fix the answer or the sample data. |
| `401 Unauthorized` | Token missing/expired. | Get a fresh `access_token` and re-run. |

Failed questions are simply **not created** — nothing half-broken is left behind. Fix
them and re-run, or author them by hand in the admin UI.

---

## After importing — verifying

- The list pages show **all** questions (they page through the full bank).
  Do a hard refresh (Ctrl+Shift+R) if a browser tab was already open.
- Open a couple of new questions and run their answer to confirm they execute and grade.

---

## Why this goes through the API (important)

Each question has its **own SQLite file** on disk, separate from the shared Postgres
database. Postgres rows are shared across machines; the per-question `.db` files are
**not** — they live only on the machine that created them. An earlier approach wrote
rows straight to Postgres and generated the `.db` files on a local laptop, so the
deployed server had rows pointing at files it never received → every such question
failed with *"unable to open database file."*

Always import through the deployed API (as these scripts do) so the files are created
on the same server that serves and grades them.
