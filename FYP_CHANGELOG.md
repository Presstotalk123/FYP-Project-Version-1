# FYP changelog

Running log of FYP changes on top of the inherited Akela codebase (tag `baseline-inherited`).
Requirement IDs refer to the design documents in `fyp-docs/design/`.

## 2026-10-16 — branch `fyp/weeks-3-4-foundations`

- **Regression tests for labs** — `backend/tests/fyp/test_lab_regression.py` pins SQL and Graph lab
  behaviour before refactoring. `.gitignore` now tracks `backend/tests/fyp/` (other inherited tests stay ignored).
- **Lab-engine registry** — `backend/app/core/lab_engines.py`; `labs.py` dispatches through
  `get_lab_engine()` instead of eight `lab_type == "graph"` branches. Prepares FR-VEC-01.
- **Relational algebra parser + translator** — `backend/app/core/ra/` (FR-RA-02, -03, -04, -05;
  tree output for FR-RA-07). Not yet connected to the question endpoints.
- **Dependencies** — `lark` (RA grammar) and `hypothesis` (property tests) in `backend/requirements.txt`.
- **Prototypes** — `prototypes/ra_demo.py`, `prototypes/sqlite_vec_spike.py`.
- **Docs** — design documents 01–04 and the Weeks 3–4 progress report in `fyp-docs/`.

## 2026-09-25 — design phase (Weeks 1–2)

- Architecture, RA design, vector-lab design, timeline/risks documents (`fyp-docs/design/`).
