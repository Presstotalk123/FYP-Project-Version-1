# Bulk-importing SQL practice questions

Two scripts turn a JSON file of LeetCode-style SQL problems into published
questions in the app. They go through the **real deployed API** (the same
`POST /questions` the admin "New Question" form uses), so each question's
per-question SQLite database is generated on the server that will actually
grade it. **Do not** write to the database directly — see "Why the API"
below.

For adding just one or two questions, use the admin **New Question** form in
the UI instead; it has the same "Convert to SQLite" and "Suggest concepts"
helpers built in. The scripts are for bulk.

## Input format

Add entries to `leetcode_questions.json` at the repo root. Each entry:

```json
{
  "id": "1234",
  "title": "Some Problem Title",
  "slug": "some-problem-title",
  "difficulty": "Easy",              // Easy | Medium | Hard
  "question_markdown": "Table: `X`\n\n```\n...ascii table...\n```\n\n...prose...",
  "sql_schema": "Create table ...; Truncate table ...; insert into ...;",  // MySQL/LeetCode dialect
  "answer": "select ...",            // the correct answer query
  "fetch_status": "success"
}
```

Notes:
- `sql_schema` may be raw MySQL (backticks, `varchar`, `int`, `TRUNCATE`, `ENUM`,
  `DATEDIFF`, `DATE_FORMAT`, ...) — the converter rewrites the common cases to SQLite.
- `question_markdown` is used verbatim as the description (already ```-fenced tables).
- The answer must be a **read-only** statement (SELECT / WITH-CTE / EXPLAIN / VALUES).
  Parameterized stored functions/procedures and bare DML (UPDATE/DELETE) are not supported.

## Steps

1. **Convert** (from `frontend/`):
   ```
   node --experimental-strip-types scripts/convert-leetcode-questions.mjs
   ```
   Regenerates `frontend/scripts/leetcode_questions.converted.json` (a generated,
   git-ignored artifact). Reuses the app's own `mysqlToSqlite` and `detectConcepts`.
   Prints which questions it skipped and which it marked order-sensitive.

2. **Import** (from `backend/`): get a fresh admin/staff access token from a
   logged-in browser session (dev tools → Local Storage → `access_token`), then:
   ```
   set AKELA_ADMIN_TOKEN=<token>      # PowerShell: $env:AKELA_ADMIN_TOKEN="<token>"
   python scripts/import_leetcode_questions_via_api.py --dry-run   # preview
   python scripts/import_leetcode_questions_via_api.py             # create + publish
   ```

The import is **idempotent**: it skips any question whose title already exists,
so re-running only creates the new ones — no duplicates. Cache invalidation and
the per-question SQLite file are handled automatically because everything goes
through the normal API request path.

## Why the API (and not a direct DB write)

An earlier version wrote straight to Postgres and called the DB-generation code
locally. That produced each question's SQLite file on the *local* machine, not on
the deployed server, so every imported question failed at runtime with
"unable to open database file". Postgres rows are shared; the per-question `.db`
files are **not** — they live on whichever machine's disk created them. Always
import through the deployed API so the files land where the app can open them.
