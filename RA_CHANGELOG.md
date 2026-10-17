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
   ("not whitelisted") even with a valid key. The seed script does it (and adds the
   Tutorial 5.5 questions), from `backend/`:
   ```
   ../.venv/bin/python scripts/seed_ra_local.py --admin-email <your Google email>
   ```
   Add `--student-email <another Google email>` to also sign in as a student. The
   script refuses to run against anything but a local SQLite database.
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
| `backend/app/models/__init__.py` | 4 lines appended: import the two RA models so their tables are created |

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

---

## Step 2: The grader (17 Oct 2026)

Commit: "Grade RA answers by proof or generated databases, with step feedback" (`git log --oneline` shows its hash).
No shared files were touched in this step.

**What was built** (all in `backend/app/core/ra/`)

| File | What it does |
|---|---|
| `compare.py` | Two results are the same answer when they have the same attribute names (any order) and the same tuples; sets by default, bags as an option |
| `generator.py` | Builds small test databases from the **schema alone**: a few values per attribute, shared between attributes with the same name, plus every constant in the answers and its neighbours (`< 50` → 49, 50, 51). Every tuple is checked against the schema in SQLite, so keys, NOT NULL, foreign keys and **CHECK constraints** hold — staff write a question's assumptions as CHECK constraints |
| `mutate.py` | Makes deliberately wrong versions of the model answer: MIN↔MAX, <↔≤, ÷ → "at least one", ∪↔∩, swapped −, dropped conditions, inner↔outer joins … |
| `suite.py` | Generates databases until every wrong version is caught, keeps those that catch something plus 60 random and 5 larger ones, and reports how many were caught ("test strength") |
| `conjunctive.py` | **Exact proof** for answers that only use σ (with =), π, ⋈, ×, ρ, ∪, ∩ (Chandra–Merlin): equivalent on every possible database, no testing needed |
| `shrink.py` | Shrinks a counterexample to the fewest tuples that still show the difference, with readable values |
| `grader.py` | Puts it together: errors → wrong attributes → question data → proof → test databases; and compares **every step** of the student's answer with the model answer's steps (✓ match / ◐ close / ○ no match), by content, not by name |
| `printer.py` | Writes an expression back in slide notation |

**Results on Tutorial 5.5 (schema only, no data):** every model answer from the
solution slides is accepted; correct alternatives are accepted (÷ as a double
difference, steps vs one expression, other step names, ∩ as a join, MIN without γ);
typical mistakes are rejected with a small counterexample, including the two the old
prototype accepted (MAX instead of MIN, "any" instead of "all"), a hard-coded GPA, and
a difference on names that can repeat. Test strength: every wrong version caught for
10 of 11 model answers; the one survivor (Q1 iii, ⋈ → ⟕ in R2) is provably equivalent.
Grading takes 2–5 ms per answer (Q5, with its triple ×, 45 ms).

**Found while testing, for the supervisor**
- `γ MAX(A) → A R` differs from Q4's model answer when R is empty (γ returns one NULL
  tuple, as SQL does). Does the course count that as wrong?
- Q1(iv) by counting (lecture 2 slide 28) is wrong here twice over: two sections of
  one course count twice, and with no Civil Engineering courses ÷ returns every
  enrolled student while counting returns nobody.
- The tutorial question says ‘Database System’, the solution slide ‘Database Systems’.
  The grader treats them as different constants.

**How to check it on localhost**
1. Open **Relational Algebra** in the top bar, then press **Check against a model answer**.
2. In the top-right menu choose **Tutorial 5.5 Q1 — schema only (no data)**. Every
   relation shows *0 tuples*: grading here uses generated databases only.
3. Click **Q1(ii) — MAX instead of MIN (wrong)**, then **Check**. Expected:
   *✗ Not correct in general*, a small STUDENT table (two students, different GPAs), and
   what each answer returns on it. Under **Your steps**, R1 is ◐ (close).
4. Click **Q1(iv) — R1 picks the wrong department**, then **Check**. Under **Your steps**,
   R1 is ◐ and R2 ✓. Press **Show structure** on R1: its tree, its output, and the
   **Direction** with a small database where it differs from the model's step.
5. Click **Q1(iv) — your own step names (correct)**, then **Check**. Expected: *✓ Correct*
   and every step ✓, although the steps are called `ce`, `took`, `all`.
6. Click **Q1(iv) — any CE course instead of all (wrong)**: rejected with a counterexample.
7. Open **Test strength** under the result: *caught 4 of 4 deliberately wrong versions*.
8. Choose **Tutorial 5.5 Q1 — university (made-up data)** and run *Q1(ii) — hard-coded GPA*:
   the message says it is right on the question's data but not in general.
9. Try your own: paste any tutorial model answer into *Model answer*, write an answer,
   press **Check** (or Ctrl/⌘+Enter). The first check of a new model answer takes up to
   a few seconds while its test databases are built.

---

## Step 3: RA questions in the database, and their API (17 Oct 2026)

Commit: "Store RA questions and attempts, with staff and student endpoints"
(`git log --oneline` shows its hash).

**What was built**
- Two new tables (no existing table changed):
  - `ra_questions` (`backend/app/models/ra_question.py`): title, description, difficulty,
    schema SQL, optional data SQL, model answer, optional checkpoints, the generated test
    databases and their self-test report, and the switches *show step direction*,
    *compare as bags*, *hide correctness*, *published*.
  - `ra_attempts` (`backend/app/models/ra_attempt.py`): every submission with its verdict
    and the grader's full result, plus columns for a later staff override.
- `backend/run_ra_tables_migration.py`: creates the two tables on PostgreSQL (only needed
  on a server; SQLite creates them at startup).
- `backend/app/services/ra/questions.py`: saving (validates everything first and builds the
  test databases once; editing only the title keeps them), what each role may see,
  grading and recording attempts, and the two feedback switches.
- `backend/app/api/v1/endpoints/ra_questions.py`, all under `/api/v1/ra/questions`:
  staff `validate`, create, edit, update, delete; everyone list, view, `check` (run
  without grading), `submit` (graded and recorded), own `attempts`.
- Students never receive the model answer, its steps or the test databases; drafts and
  deleted questions are invisible to them.
- `backend/app/services/ra/tutorial_5_5.py`: the ten Tutorial 5.5 questions (schema only,
  model answers from the solution slides) and one lecture example with data.
- `backend/scripts/seed_ra_local.py`: whitelists you and adds those questions locally.

**Noticed: the tutorial sheet and the solution slides disagree twice.** Q1(iii) says
‘Database System’ vs ‘Database Systems’; Q2's table is RESERVATIONS vs RESERVATION. The
seeded questions follow the question sheet.

**How to check it**
1. From `backend/`: `../.venv/bin/python scripts/seed_ra_local.py --admin-email <your Google email>`.
   Expected: eleven lines `created #… Tutorial 5.5 …`, each with *caught N/N wrong
   versions* (Q1(iii) shows 4/5: its one survivor is equivalent to the model answer).
2. Run it again: every line says `exists`, nothing is duplicated.
3. Run the tests: `cd backend && ../.venv/bin/python -m pytest tests/ra -q` (151 pass).
4. The pages that use these endpoints come in step 4.

---

## Step 4: RA pages for students and staff (17 Oct 2026)

Commit: "Add RA question pages for students and staff" (`git log --oneline` shows its hash).

**What was built** (frontend; the top-bar link now goes to `/ra`)

| Page | Who | What |
|---|---|---|
| `/ra` | everyone | The RA questions as cards: difficulty, *Schema only* when there is no data, *✓ Solved* or the number of attempts. Staff also see drafts (marked *Draft*), **New question**, **Edit** and **Delete**. A **Playground** button. |
| `/ra/questions/[id]` | everyone | The workspace: question text, schema (keys underlined), the editor with **Check (not graded)** and **Submit**; after Submit the verdict, the counterexample, **Your steps** with **Show structure**, and **Your attempts** (with **Load** to bring one back). The unsent answer is kept per browser. |
| `/ra/questions/new`, `/ra/questions/[id]/edit` | staff | The form: title, difficulty, question text (markdown), schema and data SQL, model answer. **Check the model answer** shows the test strength, the model's steps, and the **Checkpoints**: which model steps students' steps are compared with, and the label students see for each. Switches: show step direction, hide correctness, compare as bags, published. **Try an answer** grades any answer with these settings. |

Components are in `frontend/src/components/ra/` (`RaQuestionWorkspace`, `RaQuestionForm`,
`RaStepStructure`, `RaVerdict`, `RaCaseView`, …).

Backend change: the playground's grading endpoint also takes checkpoints and the
set/bag choice, so the staff test bench grades exactly like the saved question will.

**How to check it on localhost** (after the one-time setup and the seed script)
1. Sign in with your (admin) account and click **Relational Algebra** in the top bar. You
   see the 11 seeded questions, each with **Edit** and **Delete**, plus **New question**
   and **Playground**.
2. Open **Tutorial 5.5 Q1(ii) — lowest GPA**. Type
   ```
   R1 := γ MAX(GPA) → MinGPA (STUDENT)
   R2 := STUDENT ⋈ STUDENT.GPA = R1.MinGPA R1
   Answer := π Sname (R2)
   ```
   and press **Check (not graded)**: the result and every step on an example generated
   database. Then press **Submit**: *✗ Not correct in general*, a two-student
   counterexample, and under **Your steps** three ◐ steps. **Show structure** opens each.
3. Replace `MAX` with `MIN` and **Submit**: *✓ Correct … proved* or *… on all 66 test
   databases*, every step ✓. **Your attempts (2)** lists both; **Load** puts one back.
4. Go back to **Relational Algebra**: the card now says *✓ Solved*.
5. Click **Edit** on **Q1(iv)**, then **Check the model answer**: *catches 4 of 4
   deliberately wrong versions*, and the four checkpoints. Change R1's label to
   *the Civil Engineering courses*, untick R2, **Save changes**. Submit an answer whose R1
   uses `'Computer Science'`: R1 is ◐ with your label, R2 is no longer compared (○).
6. In the edit form, use **Try an answer** to grade any answer without saving anything.
7. **New question**: write a schema, a model answer, press **Check the model answer**,
   tick **Published**, **Create question**. It appears on `/ra`.
8. To see the student view, sign in with the `--student-email` account from the seed
   script: no Edit/Delete/New buttons, no drafts, and never the model answer.
