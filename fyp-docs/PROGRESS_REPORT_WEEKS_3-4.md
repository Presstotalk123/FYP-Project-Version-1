# FYP Progress Report — Weeks 3–4

**Project:** Extending Akela with Relational Algebra and Vector Database modules
**Branch:** `fyp/weeks-3-4-foundations` (from `main` at the hand-over commit, tagged `baseline-inherited`)
**Plan reference:** Document 04, §6 “Plan for the next two weeks (W3–W4)”

`git diff baseline-inherited..fyp/weeks-3-4-foundations` shows everything added for the FYP on this branch.

> **AI assistance:** the code on this branch was written with Claude Code (an AI coding assistant).
> Each commit carries a `Co-Authored-By` line saying so.

---

## 1. Summary

| Planned task (Doc 04 §6) | Status | Evidence |
|---|---|---|
| Tag the baseline; set up changelog and a committed docs folder | ✔ Done | tag `baseline-inherited`; `FYP_CHANGELOG.md`; `fyp-docs/` |
| Regression tests for the current SQL and Graph lab flows | ✔ Done | `backend/tests/fyp/test_lab_regression.py` (5 tests) |
| Lab-engine registry; switch `labs.py` to it | ✔ Done | `backend/app/core/lab_engines.py`; `labs.py` −95 lines; 5 registry unit tests |
| RA grammar and parser, both notations | ✔ Done | `backend/app/core/ra/grammar.lark`, `parser.py` |
| RA → SQL translator *(planned for W5–W7)* | ✔ Done early | `backend/app/core/ra/translator.py`; 45 RA tests |
| sqlite-vec check | ✔ Done | `prototypes/sqlite_vec_spike.py` — 9/9 checks |
| Draft ethics application | ☐ Not started | Waiting on supervisor answer O-8 |

**Test suite:** 55 tests, all passing (`cd backend && python -m pytest tests/fyp`).

## 2. What was built

### 2.1 Lab-engine registry (shared foundation for Vector Labs)
- `labs.py` used to branch on `lab_type == "graph"` in **eight** places. Each one now calls
  `get_lab_engine(lab.lab_type)`, which returns that type's template builder, query executor,
  schema reader and database-state reader (`app/core/lab_engines.py`).
- Adding Vector Labs is now one entry in `LAB_ENGINES` instead of eight edits.
- **How I know nothing broke:** the regression suite was committed *first*, against the inherited code
  (commit “Pin SQL and Graph lab behaviour…”). It passes unchanged after the refactor. It drives both
  lab types through create → schema preview → task + reference answer → order-sensitivity toggle →
  session → execute (including a data change) → database view → validate (right and wrong) → schema update.
- `student_report.py` still checks for `"graph"`, but only to *count* completed labs by type. It
  doesn't dispatch to an engine, so I left it alone. It will need a `vector` counter later.

### 2.2 Relational algebra module (`backend/app/core/ra/`)
- **Language:** σ, π, ρ (relation and attribute renaming), ×, natural ⋈, θ-⋈, ∪, ∩, −, ÷, and assignment
  `T ← expr;`. Each operator has a Unicode form and an ASCII form (`\select_{…}`, `\project_{…}`,
  `\join`, …) that produce identical results. Conditions support `= ≠ < ≤ > ≥`, `and/or/not`
  (or `∧ ∨ ¬`), numbers and quoted strings.
- **Translation:** one bottom-up pass checks names against the question database and produces nested
  `SELECT DISTINCT` sub-queries (set semantics). Output column names are deterministic, because the
  inherited grader hashes column names.
- **Errors in RA terms:** RA001–RA012 with line/column and “did you mean” hints, e.g.
  `RA003: Attribute “nme” is not in the input of π (sid, name, age, major). Did you mean “name”?`
- **Outputs for the next phase:** a JSON tree for the expression-tree view, the list of operators used
  (for concept tagging), and non-blocking warnings (RA008: text compared with a number).
- **Change from Design Doc 02:** the checker and SQL generator are one module (`translator.py`)
  instead of two, because each node needs its children's output schema for both jobs.

### 2.3 Test strategy (45 RA tests)
- **Equivalence (14 cases):** each RA query and a hand-written SQL query give the **same grading hash**,
  run through the platform's own read-only executor. Cases include a three-way join, division, a
  self-join, “oldest student without aggregation” and assignments.
- **Errors (15 cases):** every error code fires on a minimal example.
- **Security:** an injection attempt in a string literal stays one escaped literal (layer 1), and the
  inherited executor refuses it anyway (layer 2). Only names that exist in the schema can be used.
- **Property-based (hypothesis, 80 random cases):** π/σ matches SQL; σ distributes over ∪; ⋈ is commutative.

## 3. Findings worth discussing

1. **Risk R1 (sqlite-vec on Azure) is much lower than I thought.** `graphqlite`, which Graph Labs use,
   is *itself a SQLite extension* loaded through `enable_load_extension`. Graph Labs already work in
   production, so production's Python must allow extension loading, and sqlite-vec loads the same way.
   Still to confirm on Azure itself.
2. **The default Python on this Mac (python.org build) cannot run Graph Labs or sqlite-vec.** It was
   compiled without extension loading. A uv-managed Python works:
   `uv python install 3.11`. This setup step was missing from the README.
3. **sqlite-vec really does return `-0.0`.** The spike shows it for cosine distance on Achar, exactly as
   predicted in Design Doc 03 §4.3. The planned normalisation (`round(v, 4) + 0.0`) fixes it. All
   expected answers in Design Doc 03 §5.2 match sqlite-vec v0.1.9 and the pure-Python fallback.
4. **Extension lock-down works:** after loading sqlite-vec and switching extension loading off,
   `SELECT load_extension(…)` from SQL is refused (“not authorized”).
5. **The inherited executor's keyword blacklist has false positives:** any query containing DROP,
   UPDATE, REPLACE … is rejected, even inside a string literal. This is harmless for security, but an RA
   question whose data contains such a word (e.g. a course titled 'Update Policies') can't be queried.
   To raise with the supervisor before authoring the question bank.

## 4. How to run it

```bash
uv python install 3.11                          # Python with SQLite extension loading
uv venv --python 3.11 .venv && source .venv/bin/activate
pip install -r backend/requirements.txt sqlite-vec
cd backend
python -m pytest tests/fyp -q                   # 55 tests
python ../prototypes/ra_demo.py                 # RA → tree → SQL → result, plus error examples
python ../prototypes/ra_demo.py "π[name](σ[age > 20](Student))"
python ../prototypes/sqlite_vec_spike.py        # vector feasibility checks
```

## 5. Next two weeks (W5–W6)

1. `query_language` column + migration; translate RA reference answers in `questions.py`.
2. RA branch in `execute.py` and the `/ra/parse` preview endpoint.
3. Start the RA editor (Monaco language + operator palette).
4. Confirm sqlite-vec on an Azure staging slot (needs O-7).
5. Decisions needed: O-1 (RA notation), O-7 (staging access), O-8 (ethics), plus finding 5 above.
