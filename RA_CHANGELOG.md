# Relational Algebra module: build log

What was built for the Relational Algebra (RA) module, when, in which commits, and how
to check each piece yourself on localhost. All work is on the `ra` branch; nothing here
is merged into `main` or deployed.

---

## One-time localhost setup

1. **Backend settings.** Add these lines to `backend/.env` (it is gitignored):
   ```
   RA_ENABLED=true
   GOOGLE_CLIENT_ID=<your Google OAuth client id>
   ```
   With `RA_ENABLED` missing or `false`, every RA page and link is hidden and the site
   behaves exactly as `main`.
2. **Frontend settings.** Create `frontend/.env.local` with:
   ```
   NEXT_PUBLIC_GOOGLE_CLIENT_ID=<the same client id>
   ```
   In Google Cloud Console, `http://localhost:3000` must be an *Authorised JavaScript origin*.
3. **Your email must be whitelisted** in your local database, or Google sign-in is refused
   ("not whitelisted") even with a valid key.
4. **Python packages.** From the repo root (the `.venv` was made with `uv`, so it has no
   `pip`): `uv pip install --python .venv/bin/python -r backend/requirements.txt`
   (the RA module needs `lark`; it is already installed in your `.venv`).
5. **Start both servers** (two terminals):
   ```
   cd backend  && ../.venv/bin/uvicorn app.main:app --reload --port 8000
   cd frontend && npm run dev
   ```
   Then open http://localhost:3000 and sign in with Google.

**Run the RA tests** (no servers needed): `cd backend && ../.venv/bin/python -m pytest tests/ra -q`

---

## Where the code is

| Part | Location |
|---|---|
| Engine: parser, grammar, evaluator, schema loader | `backend/app/core/ra/` |
| API | `backend/app/api/v1/endpoints/ra.py` |
| Request/response shapes | `backend/app/schemas/ra.py` |
| Services (playground examples, …) | `backend/app/services/ra/` |
| Tests | `backend/tests/ra/` |
| Pages | `frontend/src/app/ra/` |
| Components | `frontend/src/components/ra/` |
| Frontend service, types, hook | `frontend/src/services/ra.service.ts`, `frontend/src/types/ra.types.ts`, `frontend/src/hooks/use-ra-status.ts` |

**Edits to shared files** (the only places a merge with `main` can conflict):

| File | Change |
|---|---|
| `backend/app/main.py` | 2 lines at the end of the router list: import and mount the RA router |
| `backend/app/config.py` | `RA_ENABLED`, `RA_AGGREGATE_NULLS` appended to the settings |
| `backend/requirements.txt` | `lark==1.2.2` appended |
| `.gitignore` | `backend/tests/` → `backend/tests/*` + `!backend/tests/ra/`, so only the RA tests are tracked |
| `frontend/src/components/HeaderNav.tsx` | "Relational Algebra" link, shown only while RA is enabled |

---

## Step 1: RA engine and Playground (17 Oct 2026)

Commits: `10e5cbe` (engine + playground), `c7c5348` (top-bar link).

**What was built**
- The parser and evaluator from the earlier prototype, reviewed against the CZ2007
  Topic 5 slides and moved into `backend/app/core/ra/`. Fixes made during the review:
  - Conditions use three-valued logic: a comparison with NULL is *unknown*, so
    `σ NOT (Score > 60)` no longer keeps a student whose Score is NULL.
  - Symbols pasted from Word/PowerPoint/PDF (⨝, ∏, –, non-breaking spaces) are read as
    the real operators.
  - `ρ S (R)` now works (the brackets hold the relation, not attribute names).
  - Hyphenated schema names such as `teamid-one` (Tutorial 5.5 Q3) are one name, not
    "teamid minus one".
  - A careless `×` or θ-join on large relations is refused before it starts, so it
    cannot freeze the server.
  - `RA_AGGREGATE_NULLS=slides` makes COUNT/SUM treat NULL as lecture 3 slides 20–21 do;
    the default `sql` follows SQL. (Open question for the course coordinator.)
- Schemas are loaded from staff-written `CREATE TABLE`/`INSERT` SQL in a private,
  in-memory SQLite with file access and PRAGMAs blocked and a time limit.
- **RA Playground** page: run any RA expression on a lecture or tutorial schema and see
  every intermediate step. Nothing is graded or saved.
- All ten Tutorial 5.5 model answers run exactly as written on the solution slides.

**How to check it on localhost**
1. Sign in. The top bar shows **Relational Algebra** (after *SQL Labs* for students,
   after *Labs* for staff). Click it. You land on http://localhost:3000/ra/playground.
2. The example *Lecture 1 — Students, Grades, CrsSch* is loaded. The schema panel lists
   `Students(ID, Name, Age, School)` etc. with key attributes underlined. Click a relation
   to see its tuples.
3. Press **Run**. Expected result: `(1234, Alice)` and `(3742, Cathy)`, with the time taken.
   Scroll down to **Steps**: each operator (Π, σ, Students) with its tuple count; click one
   to see its table.
4. Click one of the *Try one of these* expressions, then Run. The last one gives `Alice`.
5. Type the lecture's classic mistake, then press Ctrl/⌘+Enter:
   ```
   R1 := Π ID, Name Students
   σ School = 'SCSE' R1
   ```
   Expected: line 2 underlined in red, and *"Attribute “School” is not in the input of σ
   (ID, Name)"* with the lecture's advice "select before you project".
6. Choose *Tutorial 5.5 Q1 — university (made-up data)* in the top-right menu and run the
   third suggestion (÷). Expected result: `(1, Ann, 3.6)`.
7. Click **Edit SQL** to change the schema or data, then **Load schema**.
8. Set `RA_ENABLED=false` in `backend/.env` and restart the backend: the top-bar link
   disappears and `/ra/playground` says the module is switched off.
