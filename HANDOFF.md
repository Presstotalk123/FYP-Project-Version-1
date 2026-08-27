# Akela — Technical Handoff

> **Purpose of this document.** A from-scratch technical brief for whoever inherits
> this codebase — most likely after the current maintainer graduates and stops being
> reachable. It explains *what the system is*, *why it's built the way it is*
> (design philosophy, not just file layout), and *where the sharp edges are*. Read
> this once end-to-end before making changes; it should save you from re-deriving
> decisions that were made deliberately.
>
> This file is **not** in `docs/`, which is gitignored on this repo (see
> [Known gaps & gotchas](#known-gaps--gotchas)). It lives at the repo root
> specifically so it travels with `git clone` and is the first thing a new
> maintainer sees. Keep it there — or if you move it, remove the `docs/` line
> from `.gitignore` first.

---

## 1. What Akela is

**Akela** is a web platform for teaching and practising SQL and database design,
built for a university course (NTU). Production: **ntuakela.net**.

Teachers ("staff") author SQL practice questions, hands-on SQL labs, ER-diagram
(entity-relationship) exercises, and timed assessments. Students solve them
interactively with instant grading, an AI tutor, and (behind feature flags) a
personal learning-analytics dashboard. There are three flat user roles:
`student`, `staff`, `admin` (`backend/app/models/user.py`).

The names "Akela" (the platform) and "Bagheera" (the AI tutor persona) are Jungle
Book references — cosmetic branding only, not an architectural concept. Don't read
meaning into them beyond "the platform" and "the chatbot."

### Feature inventory (what a user can actually do)

| Area | Student-facing | Staff-facing |
|---|---|---|
| SQL Questions | Solve against a per-question SQLite DB, get instant correctness + AI query review | Author questions, bulk-import (LeetCode-style bank), publish/unpublish |
| SQL Labs | Multi-task sessions against a shared schema, session-scoped | Author lab tasks, view lab analytics |
| ER Diagrams | Draw ER diagrams in an embedded draw.io canvas, get LLM-graded feedback + an interactive Socratic tutor | Author ER questions, set rubrics, override grades, add submissions on a student's behalf |
| Assessments | Timed (optionally password-gated, optionally class-scheduled) sets of the above item types | Author assessments, clone them, view analytics, reset a student's attempt |
| AI Tutor ("Bagheera") | Streaming chat while working a question/lab; optionally "adaptive" (mastery-aware) | — |
| Learning Analytics Dashboard (LAD) | Per-concept mastery map, SOLO-taxonomy level, anonymized peer benchmarking (**dark by default**, see §5) | Tag questions with concepts |
| Admin | — | User/whitelist management, login-activity & live-presence tracking, cohort analytics, anonymized research CSV export |
| Auth | Email/password, Google SSO, Microsoft (Azure Entra ID) SSO | same |

---

## 2. Technology stack

**Backend** — `backend/`
- FastAPI (Python), synchronous `def` endpoints run in a threadpool (see §5.4)
- SQLAlchemy 2.0 (declarative models under `app/models/`); **no Alembic in practice**
  — schema changes ship as hand-written `run_*.py` scripts (§8)
- PostgreSQL in production, SQLite for local dev — both must work from the same
  ORM code, which shapes a lot of the query/timestamp handling (§5.7)
- LangGraph + LangChain for the ERD tutor/rubric engines and (planned pattern for)
  future agentic features
- OpenAI / Azure OpenAI for LLM calls (query review, ERD grading/tutoring, SOLO
  classification)
- JWT sessions (`python-jose` + `bcrypt`), Google SSO, Microsoft SSO via `PyJWKClient`

**Frontend** — `frontend/`
- Next.js 16 + React 19 + TypeScript, deployed to Azure Static Web Apps via its
  Next.js **hybrid-rendering** support — a real server, not a static export
  (this matters — see §9)
- Mantine 8 (component library), Monaco Editor (SQL editing), an embedded draw.io
  board (ER diagrams)
- TanStack Query for server-state/data-fetching + caching
- CASL for permission checks (`@casl/ability`), `dnd-kit` for drag-and-drop,
  `dagre` for auto-layout of the concept-mastery graph
- MSAL (`@azure/msal-browser`/`msal-react`) for Microsoft SSO, `@react-oauth/google`
  for Google SSO

---

## 3. Repository map

```
.
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/   # one router module per feature area
│   │   ├── core/               # grading, query execution, security, in-process cache
│   │   ├── models/             # SQLAlchemy ORM models (one file per table, mostly)
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── services/            # business logic — grading engines, analytics, tutors
│   │   ├── utils/                # DB provisioning helpers, storage adapters
│   │   ├── middleware/           # (currently just __init__; middleware lives inline in main.py)
│   │   ├── config.py             # Settings — the single source of truth for env-driven behavior
│   │   ├── database.py           # SQLAlchemy engine/session setup (SQLite vs Postgres branch)
│   │   └── main.py               # app assembly: middleware, startup DDL, router wiring
│   ├── migrations/               # reference Postgres DDL (*.sql) — NOT auto-applied
│   ├── run_*.py                  # the migrations that actually get run (§8)
│   ├── tests/                    # pytest suite
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── app/                  # Next.js App Router — routes below mirror roles: student/, admin/, plus shared er-diagram/, login/, register/
│       ├── components/           # feature-grouped: admin/, assessment/, auth/, common/, course/, lad/, nav/, workspace/, plus top-level (ChatPanel, DrawioBoard, ...)
│       ├── services/              # one *.service.ts per backend feature area — the only place that calls the API
│       ├── contexts/              # AuthContext, AssessmentTimerContext, AssessmentProgressContext
│       ├── permissions/           # CASL ability definitions (currently just ER questions)
│       ├── hooks/, types/, utils/, config/
├── docs/                          # gitignored (see §11) — local design docs, migration handoffs, plans
├── .github/workflows/             # two independent CI/CD pipelines, backend and frontend (§9)
└── README.md                      # quick-start / setup instructions (complements this doc, doesn't replace it)
```

Two loose top-level files (`leetcode_questions.json/xlsx`, `DATABASE_README_EN.md`,
`uncovered_leetcode_questions.*`) are **not part of the app** — they're the seed
data / reference material used to bulk-import the SQL question bank from LeetCode's
public database-problem set (see `MASS_UPLOAD_QUESTIONS.md` and
`frontend/scripts/convert-leetcode-questions.mjs`). Safe to ignore unless you're
importing more questions.

---

## 4. Data model overview

All models live in `backend/app/models/`, one class per file, registered on a
shared `Base` (`app/database.py`). Grouped by domain:

- **Identity**: `user.py` (role enum: student/staff/admin, `class_group` free-text
  string — see §5.9), `whitelist.py`, `login_activity.py`, `platform_session.py`
  (live-presence tracking), `user_preference.py`.
- **SQL Questions**: `question.py`, `attempt.py`, `progress.py`, `query_review.py`
  (AI review history).
- **SQL Labs**: `lab.py`, `lab_task.py`, `lab_session.py`, `lab_attempt.py`,
  `lab_task_submission.py`.
- **ER Diagrams**: `er_diagram_question.py`, `er_submission.py`,
  `er_diagram_draft.py` / `er_diagram_image_draft.py` (autosave), `erd_prompt_version.py`
  (rubric-generation prompt history), `erd_tutor_conversation.py` /
  `erd_tutor_message.py` (LangGraph engine's conversation state — §6.3).
- **Assessments**: `assessment.py`, `assessment_item.py`, `assessment_session.py`,
  `assessment_item_visit.py`, `assessment_class_window.py` (Timing Gateway — §6.4),
  `assessment_analytics.py` (materialized cohort aggregates).
- **AI Tutor**: `tutor_chat_conversation.py` / `tutor_chat_message.py` (the
  non-adaptive "Bagheera" chat history), `sql_tutor_conversation.py` /
  `sql_tutor_message.py` (Akela adaptive-mode chat — separate table set, §6.5).
- **Learning Analytics (Akela agents, dark by default — §6.5)**: `sql_concept.py`,
  `sql_concept_prerequisite.py`, `question_concept.py` (tagging), `learning_event.py`
  (append-only telemetry log), `concept_mastery.py`, `solo_classification.py`.
- **Platform config**: `app_setting.py`, `course_info.py`.

**No ORM relationships are load-bearing across domains in a way that would block a
partial deploy** — e.g. the LAD tables can exist and be empty with zero effect on
the rest of the app, which is exactly the point (§5.1).

---

## 5. Design philosophy

This section is the part most worth reading carefully — it's the accumulated set
of decisions that aren't obvious from any single file, extracted from design notes
left in the code (`config.py`, `main.py`, `core/cache.py`,
`services/assessment_gateway.py`, etc.). Recognizing these patterns will make
future changes consistent with the rest of the codebase instead of fighting it.

### 5.1 Ship dark behind paired feature flags, not branches

Large or risky features (the Akela multi-agent learning-analytics platform, the
ERD LangGraph tutor engine) are built **on `main`**, guarded by env-var flags that
default to the old/off behavior, and validated in production before flipping the
switch. There are no long-lived feature branches for this kind of work.

- `AKELA_AGENTS_ENABLED` (default `False`) — master switch for learning-event
  logging and the background Learner Profiling / SOLO Classifier agents. Off means
  the new tables exist but nothing writes to or reads from them; the app behaves
  exactly as before.
- `SQL_TUTOR_ADAPTIVE` (default `False`) — switches the SQL chatbot's prompt
  construction from stateless single-shot to mastery/scaffolding-aware. Independent
  of the flag above so telemetry can be collected and validated *before* it's
  allowed to change what students see.
- `ERD_TUTOR_ENGINE` / `ERD_RUBRIC_ENGINE` (`"dify"` legacy vs `"langgraph"` new) —
  same pattern one generation earlier: the new local LangGraph engine ships next to
  the old hosted-Dify path, selectable per-environment, with the old path kept
  byte-for-byte unchanged as an instant rollback.

**When you build the next big feature, follow this pattern**: a settings flag that
defaults to "off"/"legacy", full implementation merged to `main` behind it, and a
migration that's safe to skip until the flag is flipped.

### 5.2 Deterministic logic and LLM logic are kept in separate modules

The mastery model (`services/learner_profiling.py`) is **pure arithmetic** — fixed
additive deltas (`CONCEPT_MASTERY_SUCCESS_DELTA` / `_FAILURE_DELTA`) on a 0–1
`mastery_level`, no LLM call. The SOLO-taxonomy classifier
(`services/solo_classifier.py`) *is* an LLM call, and it's the only piece of the
LAD that is — and it has an explicit confidence gate
(`SOLO_CONFIDENCE_THRESHOLD`, default 0.6) that falls back to a generic prompt
when the model isn't confident. This separation means the deterministic 80% of the
system is unit-testable without mocking an LLM, and the one LLM-dependent piece
fails safe.

Apply this split to any new "intelligent" feature: put the parts that can be
computed with certainty in a plain-Python service, and isolate the LLM call behind
a narrow interface with an explicit fallback.

### 5.3 No queue infrastructure until it's actually needed

Background work (the Learner Profiling and SOLO Classifier agents) runs via
FastAPI's `BackgroundTasks` — in-process, fire-and-forget, no Celery/RQ/Redis. This
is a **documented, deliberate tripwire**: the memory of this decision explicitly
says *"scaling tripwire: move to RQ if class sizes grow."* Likewise, the read cache
(`core/cache.py`) is in-process with cross-worker consistency via a DB-stored
version counter — not Redis — because the deployment is small enough (Azure App
Service, a couple of gunicorn workers) that it isn't needed yet.

**If you're adding infrastructure (a queue, Redis, a scheduler), first check
whether the existing lazy/in-process pattern still holds** — it was chosen on
purpose to avoid running services nobody is paid to operate. Don't add new infra
speculatively; add it when a specific scaling number is hit (see the note in
`services/erd_grading` about `ERD_GRADE_MAX_CONCURRENCY` and Azure TPM budgets, and
in `config.py` about `DB_POOL_SIZE` and Azure Postgres Burstable-tier limits — both
already describe the ceiling and what to do when you hit it).

### 5.4 Lazy enforcement, no polling, no schedulers

This is one of the most consistent patterns in the codebase, and it's worth
stating plainly: **nothing in this backend polls anything, on any interval, ever.**
No cron job, no `setInterval`-equivalent background loop, no scheduler process,
no message queue consumer sitting there checking "has this expired yet?" Every
piece of time-based or state-based enforcement is instead **resolved on demand,
the next time a relevant request happens to arrive** — a pattern usually called
lazy (or "pull-based") evaluation/expiration, as opposed to active/"push-based"
enforcement.

Concretely:

- **The assessment timer** (`services/assessment_timer.py`). The backend stores
  exactly one fact: `AssessmentSession.end_time`, a plain timestamp. There is no
  server-side countdown counting down in real time. When a student's browser
  shows a ticking countdown, that's a **frontend-only display timer**
  (`AssessmentTimerContext.tsx`, a client-side `setInterval` purely for the UI) —
  it has no authority and enforces nothing. The backend never "notices" a session
  has expired on its own; it only finds out when `enforce_not_expired` runs
  inside the next mutating request that session makes (submitting an answer,
  running a query, etc.), compares `now()` to the stored `end_time`, and if it's
  passed, finalizes the session right there and rejects that request. A student
  who closes their laptop with 2 minutes left and never sends another request
  will have a session that looks "active" in the database indefinitely — nobody
  is watching the clock for them. This is an accepted tradeoff (see §11), not an
  oversight: it means zero infrastructure to keep alive or monitor, at the cost of
  expiration being *discovered late* rather than enforced *on time*.
- **The Timing Gateway** (`services/assessment_gateway.py`) is the same shape one
  level up: whether "now" falls inside a class group's scheduled window is
  recomputed **from scratch on every call** to `resolve_state` (a handful of
  timestamp comparisons) — there's no job that opens/closes assessments at the
  scheduled instant. A window that opened five minutes ago behaves identically to
  one checked one millisecond after opening; the system has no notion of "an
  event just fired," only "what does the math say about right now."
- **Lab and assessment `is_running`/`is_published` flags** (§6.2, §6.4) are
  plain columns flipped by an explicit staff action (`POST .../start`,
  `.../stop`, `.../publish`). Nothing watches these either — a lab doesn't
  auto-stop at some deadline (there isn't one), it stops when staff calls the
  `/stop` endpoint, full stop.
- Query execution time is the one place the clock moves the *other* way: it's
  **credited back** to the student's deadline (`credit_query_time`) so a slow
  query doesn't silently eat into their allotted time. This still isn't polling —
  it's another lazy adjustment made synchronously inside the request that ran the
  query.

**Why this matters for you as a future maintainer**: if you're tempted to add a
background loop, a cron job, or a "check every N seconds" mechanism for some new
time-based feature, that would be a first for this codebase — everything else
achieves the same effect by making the *next real request* do the check. Prefer
that pattern unless you have a concrete reason a student's own next action can't
be relied on to trigger the check (e.g. something that must happen even if no
one ever visits the page again — that's the one case lazy evaluation can't cover,
and none of the current features need it).

### 5.4.1 No polling on the frontend either

The same philosophy holds one layer up: the frontend does not poll the backend
"is it still open / has it expired / did the state change" on a timer. The
countdown UI is a local display computed from the `end_time`/deadline the backend
returned when the session started (`AssessmentTimerContext.tsx`,
`AssessmentProgressContext.tsx`) — it ticks visually in the browser but doesn't
re-ask the server "how much time is left?" on every tick. The server is only
consulted again when the student actually does something (submits, navigates), at
which point that request's response carries the authoritative state. The one
exception is presence — `use-presence-heartbeat.ts` genuinely does poll on an
interval (`PRESENCE_BEAT_SECONDS`/10 min on the frontend), because "is this user
still here" has no natural request to piggyback on for a tab that's open but
idle; it's a deliberate, narrow exception to the otherwise request-driven design,
not a precedent to generalize from. Even this one poller is careful not to
degrade into a thundering herd: each tab's next beat is scheduled at
`BEAT_MS ± a fresh random jitter` rather than a fixed interval, specifically so
that many tabs starting together (a whole class joining an assessment at the same
moment) drift apart over time instead of hammering the server in lockstep every
10 minutes.

### 5.5 Config that must move in lockstep across a boundary is documented, not hidden

Two examples worth knowing before you touch either side:

- **`ER_MAX_XML_CHARS`** (`config.py`) caps accepted draw.io XML size on the
  server. The frontend has its own copy of the same cap as a plain constant in
  `frontend/src/hooks/use-er-draft.ts` — deliberately **not** an env var,
  because `NEXT_PUBLIC_*` values bake into the client bundle at build time
  regardless of how the frontend is hosted (see §9's correction — this project
  is not a static export, but that part would be true even if it were). Raise
  one without the other and you get a client that silently rejects diagrams
  the server would have accepted.
- **`THREADPOOL_MAX_THREADS`** (backend, sync-endpoint concurrency) and
  `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` (Postgres connection pool) must be sized
  together against the number of gunicorn workers — `workers × (pool + overflow)`
  has to stay under Postgres's connection ceiling, and the threadpool cap should
  be bounded by CPU headroom, not left at FastAPI's default of 40. The comments in
  `config.py` and `database.py` spell out the actual numbers for the current Azure
  tier — re-derive them if you ever change the worker count or the DB tier.

The general rule this reflects: **when a value has to agree between two
independently-deployed halves of the system, say so loudly in a comment next to
both copies.** Follow that convention for anything new in this category.

### 5.6 Anonymization is a config-level guarantee, not an afterthought

`RESEARCH_EXPORT_SALT` is required — the raw research-CSV export endpoint
(`api/v1/endpoints/research_export.py`) returns 503 if it's unset, specifically so
a forgotten env var can't accidentally ship a weakly (or non-) anonymized export.
`PEER_BENCHMARK_MIN_COHORT` (default 5) suppresses any class-average shown to a
student if the cohort is too small to be anonymous. `ANALYTICS_EXCLUDED_CLASS_GROUPS`
(`TEST`/`TA`/`PROF`) is filtered out of both the numerator and denominator of every
analytics ratio, so a staff member testing the platform doesn't skew a real class's
numbers. If you add a new aggregate/export, thread it through the same three
mechanisms rather than inventing a new anonymization scheme per feature.

### 5.7 SQLite (dev) and PostgreSQL (prod) must both work from one codebase

This shows up everywhere:
- `database.py` branches engine construction on the URL scheme (Postgres gets a
  tuned connection pool + keepalives; SQLite gets `check_same_thread=False`).
- `main.py` auto-creates tables via `Base.metadata.create_all` **only for
  SQLite**; Postgres requires running `create_tables.py` and the relevant
  `run_*.py` migration(s) manually, because concurrent gunicorn workers racing to
  `create_all` against Postgres causes `UniqueViolation` on the implicit composite
  types.
- Timestamps: SQLite hands back naive `datetime`s even for
  `DateTime(timezone=True)` columns; helpers like `assessment_gateway._as_utc`
  explicitly coerce naive → UTC-aware before comparison. **Never compare a raw DB
  timestamp to `datetime.now(timezone.utc)` without going through a helper like
  this**, or the code will work locally (SQLite) and misbehave in prod (Postgres),
  or vice versa.
- Partial/filtered unique indexes: SQLite ignores `postgresql_where`, so
  `main.py` explicitly drops and lets `create_all` recreate one such index so
  local dev doesn't silently diverge from the Postgres DDL.

### 5.8 Migrations are hand-written, idempotent scripts — not Alembic

Despite `alembic`-adjacent tooling being available, this project's actual
migration mechanism is `backend/run_*.py` — one script per schema change, run
manually against Postgres, each wrapping its `ALTER TABLE` / `CREATE TABLE` in a
try/except so re-running it is harmless. `backend/migrations/*.sql` are **reference
DDL only**, not auto-applied — they exist so the SQL is reviewable, but the `.py`
script is what actually gets executed. See §8 for the workflow. If you add a
column, add both: the model change and a new `run_add_<thing>_migration.py` (copy
an existing one, e.g. `run_add_leetcode_id_question_migration.py`, as a template).

### 5.9 Authorization is flat roles + one ownership check, not a general ACL system

Only three roles exist (`student`/`staff`/`admin`), checked mostly with plain
`if user.role == ...` in endpoints. The one place a real permission library shows
up is `frontend/src/permissions/er-ability.ts` (CASL), which encodes exactly one
rule beyond role: a student can delete only the ER questions *they* created, staff
and admin can delete any. There's no generalized policy engine — don't build one
unless a second ownership-style rule actually appears; extend the CASL ability the
same narrow way if it does.

`class_group` is a free-text string on `User`, not a normalized `ClassGroup`
entity — the Timing Gateway (`AssessmentClassWindow`) keys windows by
`(assessment_id, class_group)` string match. This is a known simplification: it's
fragile to typos and can't validate that a class group "exists," but it avoided
building a whole class-management subsystem for a single scheduling feature.

### 5.10 Identity is anchored on email address, not a provider ID

A user can sign in three ways — local email/password, Google SSO, or Microsoft
SSO — and all three converge on the **same join key: the email address**, not a
provider-specific ID (Google's `sub`, Microsoft's `oid`/`tid`). This is the
mechanism, in `api/v1/endpoints/auth.py`:

1. Staff pre-provision a `WhitelistEntry` (`models/whitelist.py`) — keyed by
   **unique email** — with the role, display name, and `class_group` that
   account should have, *before the person has ever logged in*.
2. On first successful sign-in (any of the three methods), the backend takes
   whatever email the login proved ownership of, lower-cases it, and looks it up
   against the whitelist. No entry → 403, login refused, regardless of how
   convincingly the person authenticated. This is the actual access-control
   gate — it, not the role system, decides who is allowed onto the platform at
   all.
3. If whitelisted, a `User` row is created (or found) for that email, and its
   `role`/`name`/`class_group` are synced from the whitelist entry.

**Why email and not a provider ID**: a teacher needs to be able to grant a
student access *before* that student has ever touched the platform — a Google
`sub` or Microsoft `oid` doesn't exist yet at that point, but the student's
university email address does, and it's the one identifier that's stable and
knowable in advance across every login method they might use. This is also why
the Google/Microsoft login handlers explicitly validate that the token actually
carries an `@`-containing email (Microsoft's `preferred_username` fallback is
only used when it's email-shaped) rather than trusting any other subject claim.
`RESTRICTED_USER_EMAILS` (§5.9) and `ANALYTICS_EXCLUDED_CLASS_GROUPS` reuse the
same idea: email is the one identity string every part of this system agrees on,
so every access-control and analytics carve-out is expressed in terms of it.

`RESTRICTED_USER_EMAILS` (`main.py`'s `restrict_limited_users` middleware) is a
narrow, explicit carve-out — specific accounts (by email) are confined to a fixed
path-prefix allowlist regardless of their DB role. This exists for one or two
known non-standard accounts (e.g. a TA account that should only see SQL
Questions/Labs); it is not a general-purpose feature and shouldn't be extended
into one — if you need per-user path restrictions more broadly, this is a sign to
build a real permission model instead of adding more emails to the set.

---

## 6. Subsystem walkthroughs

### 6.1 SQL Questions — one shared database per question, never copied

When staff author a question, `utils/db_generator.py::create_sqlite_from_sql`
runs their `CREATE TABLE` (schema) and `INSERT` (data) SQL **once**, producing a
single `<uuid>.db` file under `question_databases/`. That one file is the
question's permanent "template" — and, unlike labs (§6.2), it is **never copied
per student**. Every student who opens that question runs their query against
the exact same file.

This is safe only because of a second, independent decision:
`core/query_executor.py` (used by `api/v1/endpoints/execute.py`) enforces that a
submitted query is **read-only** — it must start with `SELECT`/`WITH`/`EXPLAIN`/
`VALUES`, and a keyword blacklist (`DROP`, `INSERT`, `UPDATE`, `ALTER`, `CREATE`,
etc., matched on word boundaries) rejects anything else before it ever reaches
SQLite. Since no student query can mutate the file, there's nothing to isolate —
sharing one file per question is simpler than templating and cheaper than
per-student copies, and it's only possible *because* mutation is blocked at the
executor level. (Advanced SQL Testing questions relax the *authoring-time*
validation on the reference/correct-answer query via
`core/advanced_sql_grader.is_permissive_but_safe`, but the *student's submitted*
query still goes through the same read-only executor.)

- Correctness grading: `core/answer_validator.py` (hash-based comparison of the
  student's result set against the stored correct-answer hash) plus
  `core/advanced_sql_grader.py` for the more permissive "Advanced SQL Testing"
  pipeline.
- AI query review is a separate, optional feature (`AI_PROVIDER`/`AI_API_KEY` in
  config) — it explains *why* a query is right/wrong, it doesn't do the grading.
- Cancellation: `core/query_deadline.py`'s module docstring explains *why* a
  plain `thread.join(timeout=)` isn't enough on its own — the abandoned thread
  keeps burning CPU on the SQLite statement until a SQLite progress-handler
  callback kills it.

### 6.2 SQL Labs and Graph Labs — template + per-student copy, because labs allow mutation

Labs are the mirror image of Questions: a lab's schema is designed to be
**mutated** (`INSERT`/`UPDATE`/`DELETE`/DDL are all allowed — `LabQueryExecutor`
places no restriction on statement type, unlike the read-only Questions
executor), so one shared file per lab would let students corrupt each other's
data or see each other's changes. The fix is a **template + copy-on-session-start**
pattern, entirely in `utils/lab_db_manager.py`:

1. **Authoring** (`create_lab_template`) runs the staff-authored schema/seed SQL
   once into `<LAB_DB_PATH>/templates/lab_<id>_template.db` — this file is never
   touched by students, only regenerated when staff edit the lab.
2. **Session start** (`copy_template_to_session`, called from
   `POST /labs/{lab_id}/session/start`) file-copies (`shutil.copy2`) the template
   into `<LAB_DB_PATH>/sessions/lab_<id>_student_<user_id>.db` the first time a
   given student opens that lab. From then on, every query that student runs
   mutates *only their own copy*. `start_session` is idempotent — calling it
   again while a session is already active just returns the existing one rather
   than re-copying (which would wipe the student's progress).
3. **Reset** (`POST /labs/{lab_id}/session/reset`) re-runs the same copy step to
   discard a student's changes and hand them a fresh copy of the template — the
   template itself is the reset point.
4. **Stop** (`POST /labs/{lab_id}/stop`, staff-only) calls
   `terminate_all_lab_sessions`, which ends every active `LabSession` and deletes
   every student's session `.db` file — the template is untouched, so starting
   the lab again later regenerates clean sessions from it.

**Graph Labs** (`Lab.lab_type = "graph"`) are the same template/session pattern
applied to a different backend: `utils/graph_db_manager.py` builds the template
by running Cypher (not SQL) through the `graphqlite` library
(`create_graph_template`), and `core/graph_query_executor.py` executes student
Cypher queries against the per-student copy with the *same threading-timeout,
cancellation, and result shape* as `LabQueryExecutor` — deliberately built as a
drop-in replacement so the rest of the lab machinery (session creation, task
grading, hashing/comparison via `generate_hash`) doesn't need to know or care
whether it's talking to a relational or graph backend. If you're adding a third
lab flavor, follow this same shape: a `create_<type>_template` +
`<Type>QueryExecutor` pair that plugs into the existing template/session/task
scaffolding rather than a parallel lab system.

**Two independent flags control a lab's lifecycle** (`Lab.is_published`,
`Lab.is_running` — see §5.4 for why neither is scheduler-driven): `is_published`
controls whether the lab is visible/listed at all; `is_running` controls whether
students can currently start a session. A lab can be published (visible in a
list, editable metadata locked down) without being running (not yet
session-joinable), and staff can always access any lab for testing regardless of
either flag.

Task-level progress: `LabTask`s within a lab are graded per-submission
(`lab_task_submission.py`), and `chatbot.py`'s `/lab-chat` path lets the AI tutor
see the student's live schema state via `utils/lab_db_manager.get_schema_info`.
`utils/lab_cleanup.py` reaps orphaned session files (e.g. from a crashed
mid-copy) and handles Windows file-locking retries when replacing a session file.

### 6.3 ER Diagrams and the ERD Tutor

Unlike Questions and Labs, ER-diagram exercises have **no per-question database
template at all** — there's no schema to run queries against. Grading is
stateless-per-submission: the student's draw.io XML (or an uploaded image) is
sent to the grading engine each time, evaluated against the question's stored
rubric (`rubric_md`/`rubric_json`, LLM-generated at authoring time — see
`services/erd_rubric/`), and scored. "Isolation" here isn't a database-file
problem the way it is for Labs; it's handled instead by each `ERSubmission` row
being its own independent record and (for the LangGraph engine) a per-student
conversation row, described below — there's no shared mutable state between
students to protect against in the first place.

Students draw entity-relationship diagrams in an embedded draw.io canvas
(`frontend/src/components/DrawioBoard.tsx`, `ERDiagramWorkspace.tsx`). Submission
grading and the interactive Socratic tutor both run through
`services/er_grading.py`, which dispatches to one of two engines selected by
`ERD_TUTOR_ENGINE`:

- **`dify`** (legacy, default) — calls a hosted Dify chatflow.
- **`langgraph`** (new) — a local LangGraph engine under `services/erd_tutor/`:
  `submit_graph.py` (observe → normalize → grade → score) and `query_graph.py`
  (tutor → state_update), with conversation state persisted in
  `erd_tutor_conversation`/`erd_tutor_message`. Scoring is deterministic
  (`erd_tutor/scoring.py`, a port of the original Dify code node), not LLM-judged.

**Full migration history, gotchas, and a production checklist for this engine
live in `docs/erd-langgraph-migration-handoff.md`** — read it before touching
anything under `services/erd_tutor/`. Key points repeated here because that file
is gitignored (§11) and could be lost:
- The Azure OpenAI resource this project uses only supports the **unified v1 API
  surface** (`ChatOpenAI` against `{endpoint}/openai/v1`, no `api-version`,
  Bearer auth) — `AzureChatOpenAI` with a dated api-version does **not** work
  against it. If ERD/SOLO Azure calls start failing with "API version not
  supported," this is why — don't "fix" it by adding an api-version back.
  `services/erd_tutor/llm.py` and `services/solo_classifier.py` both encode this.
- Run `python backend/run_erd_tutor_migration.py` on Postgres **before** flipping
  `ERD_TUTOR_ENGINE=langgraph` in production; SQLite auto-creates the tables.
- `get_or_create_conversation` (`services/erd_tutor/persistence.py`) has a known,
  benign multi-worker create race (no unique constraint yet).

Staff also author ER rubrics — a separate engine pair, `services/erd_rubric/`,
governed by `ERD_RUBRIC_ENGINE`.

### 6.3.1 The draw.io integration: an iframe and a `postMessage` protocol

`DrawioBoard.tsx` embeds `embed.diagrams.net` (draw.io's official embed
endpoint — configurable via `NEXT_PUBLIC_DRAWIO_ORIGIN`, default
`https://embed.diagrams.net/?embed=1&spin=1&ui=min&libs=er;general&proto=json`)
as a plain `<iframe>`. There is no npm package or SDK — the entire integration
is a hand-rolled `window.postMessage` protocol, JSON-encoded (`proto=json` in
the URL), with five message types the component listens for and reacts to:

- **`init`** — draw.io has finished loading inside the iframe and is ready to
  receive content. The handler stops the retry loop (below) and immediately
  posts back `{action: "load", autosave: 1, xml: initialXml}`. **`autosave: 1`
  belongs on this `load` message, not as a URL parameter** — without it, draw.io
  never emits `autosave` events at all and no draft is ever captured; this is
  called out explicitly in the code as an easy thing to get wrong.
- **`autosave`** — draw.io fires this on essentially every canvas change
  (including some that don't actually change content, e.g. a selection or
  viewport change — the autosave hook downstream de-duplicates that, §6.3.2).
  Forwarded to the parent via `onAutosave(xml)`.
- **`save`** — a different signal from an explicit in-editor save action;
  forwarded via `onSaveRequest(xml)`, and the handler replies
  `{action: "status", modified: false}` to clear draw.io's own "unsaved
  changes" indicator now that the host has taken responsibility for the
  content.
- **`exit`** — the user clicked draw.io's own exit control; forwarded via
  `onExitRequest()`.
- **`export`** — the reply to an `{action: "export", format: "png"|"xml"}`
  request the host sent. PNG is used for the actual submission image, XML for
  reading the current diagram source (draft saves, and the pre-submit XML
  capture). **A PNG export reply also carries the XML alongside it** (verified
  empirically against embed.diagrams.net, noted in a comment) — so a submit
  only needs one export round-trip, not two, to get both the image and the
  source.

**Message origin is checked twice** before any payload is trusted:
`event.origin !== DRAWIO_ORIGIN` is rejected outright, and — because more than
one iframe could theoretically be listening — `event.source !== iframeRef.current
?.contentWindow` is checked too, so a message actually has to have come from
*this* embed instance.

**Handshake retry loop**: `onLoad` on the `<iframe>` element itself doesn't
guarantee draw.io's internal app has finished initializing and is listening —
so the component starts a `setInterval` that re-sends the `load` message every
250ms, up to 8 times, until an `init` reply is actually received (which cancels
the retry). This is a pure client-side handshake retry, unrelated to the
no-polling design principle in §5.4 — nothing here talks to the backend.

**PNG export post-processing**: draw.io's raw PNG export can have a transparent
background; `toWhiteBackgroundPngFile` decodes it onto an off-screen `<canvas>`
painted white first, then re-encodes, so every submission (student-drawn or
staff-added on a student's behalf) renders consistently regardless of the
diagram's own background setting. This function is exported specifically so a
staff "add a submission for a student" flow and a real student submission
produce byte-for-byte comparable images.

**XML export has a hard 4-second timeout** (`XML_EXPORT_TIMEOUT_MS`): a caller
awaiting `exportXml()` gets a rejected promise if draw.io doesn't reply in
time, and the submit flow is written to treat that as "no XML available" and
still submit on the image alone rather than hang indefinitely waiting for a
reply that may never come (e.g. the iframe navigated away, or crashed).

### 6.3.2 Autosave: the draw.io XML draft, two tiers with server-side reconciliation

`hooks/use-er-draft.ts` (~700 lines, one of the densest files in the frontend —
worth reading directly if you're touching this feature) owns a student's
in-progress bank-question canvas. The design rests on one observation stated in
its own top comment: **localStorage and the server fail differently**, so one
tier alone can't cover both a crashed tab and a different machine:

- **localStorage (synchronous, instant, per-device)** — every single
  `autosave` event from draw.io writes to `localStorage` immediately
  (`persistLocal`), keyed `er-draft-u{userId}-bank-{questionId}`. This is what
  makes leaving and re-entering "focus mode" (which unmounts/remounts the
  `DrawioBoard`) feel instant, and what survives a crashed browser or an
  accidental tab close before anything reached the server.
- **Server (debounced, coalesced, cross-device)** — a `PUT /er-diagram/draft`
  upsert, gated behind real scheduling logic rather than firing on every
  keystroke-equivalent change:
  - **`MIN_CHANGES_BEFORE_SAVE = 10`** — a hard floor: the automatic-save
    timers don't even arm until 10 distinct canvas changes have accumulated
    since the last successful sync. Below that floor, the edit lives only in
    localStorage.
  - **`IDLE_MS = 300_000` (5 min)** — once the floor is crossed, a flush fires
    5 minutes after the *last* edit (the idle timer is reset on every new
    change), giving a natural desync across students since everyone pauses at
    different moments.
  - **`MAX_WAIT_MS = 600_000` (10 min), jittered ±20%** — a hard ceiling so a
    student who never pauses still syncs periodically. Unlike the idle timer,
    a ceiling armed at the same moment for a whole class (everyone starting an
    assessment together) would *not* desync naturally — so it's deliberately
    randomized (`MAX_WAIT_MS * (0.8 + Math.random() * 0.4)`) to spread a
    cohort's writes instead of stacking them at the same instant on top of
    already-peaky assessment-start traffic.
  - **Retry ladder**: `[2s, 6s, 15s]` backoff on a failed PUT, but only for
    genuinely transient failures (`isRetryableStatus`: no response at all,
    `408`, `429`, or any `5xx`). A `4xx` other than those is treated as
    permanent — most commonly a `400` from the client/server `MAX_XML_CHARS`
    mismatch described in §5.5 — and surfaces as a `too-large` state instead of
    burning through retries re-sending the same rejected payload.
  - **Single-flight with joining**: a second `flush()` call while one is
    already in-flight doesn't start a competing request — it `await`s the live
    one via a shared promise, then re-checks whether anything newer landed in
    the meantime before returning, so a caller awaiting `flushNow()` (the exit
    button) never resolves before *their* content specifically has actually
    reached the server.
  - **Multiple independent exit paths, all funneling into the same `flush()`**:
    `visibilitychange → hidden` (tab switched/minimized/closed), `pagehide`
    (fires right after, specifically because a plain request can be cancelled
    mid-flight once the document starts actually unloading — this path uses
    `fetch(..., keepalive: true)` instead, gated under a 60KB body-size cap
    because the browser hard-caps keepalive request bodies at 64KB, which a
    real diagram's XML can exceed), `online` (connectivity returning after an
    outage resets the retry ladder and retries immediately), and component
    unmount (client-side navigation via Next.js routing tears down the React
    tree without firing either browser event, so the hook's own cleanup
    function fires one last best-effort flush). The comments note that on a
    real tab close, **both** the `visibilitychange` flush and the `pagehide`
    keepalive fetch typically fire — considered a harmless redundancy (an
    idempotent upsert just bumps the revision an extra time) rather than
    something worth deduplicating, because skipping the keepalive whenever an
    ordinary flush happens to already be in-flight would remove the one path
    actually built to survive teardown, at exactly the moment it matters.

**Conflict resolution is lineage-based, never clock-based** — both timestamps
involved are client-generated and a second device's clock could be skewed, so
trusting "newest timestamp wins" could silently discard real work. On mount,
the hook fetches the server's draft (conditionally, via `known_revision` so an
unchanged draft skips re-sending its XML — mirroring the cache-read pattern in
§7.2) and reconciles by comparing the **revision** the local copy last
synced against the server's current revision:
- No server draft at all → the local copy (if any) is the truth; schedule a
  sync.
- Server unchanged from what this device already has → nothing to do.
- Local copy's `syncedRevision` matches the server's current revision (this
  device is on the current lineage) → just push local edits if any.
- No local draft, or the local copy isn't dirty → adopt the server's copy.
- **Both a different lineage on the server AND unsaved local work** — the only
  case where a silent choice in either direction could destroy real work — a
  conflict modal is raised (`conflict: {localXml, serverXml}`) and the student
  explicitly picks "local" or "server" (`resolve()`).

### 6.3.3 Autosave: image drafts (IndexedDB cache + server-authoritative upload)

A student can answer an ER question by uploading an image instead of drawing
one, and this path is architected differently on purpose: **the server, not the
browser, is the source of truth**, because the image needs to survive to a
different device and be gradable at finalize time regardless of what the
uploading browser still has cached. `utils/er-image-idb.ts` (IndexedDB) is
explicitly documented as **only a cache** for instant local preview — never the
thing grading reads from.

- **Why IndexedDB and not localStorage** (mirroring the XML draft's choice):
  localStorage is string-only with a small (~5MB) origin-wide quota and
  synchronous writes that would jank the UI for a multi-MB image; IndexedDB
  stores a `Blob` natively (no base64 inflation), has a much larger quota, and
  is asynchronous. Every IndexedDB call in this module is wrapped to resolve to
  "no cache" rather than throw — IndexedDB disabled, a private-mode zero quota,
  or an eviction all just fall through to fetching the image from the server
  instead, never surface as an error.
- **Upload flow**: the moment a student drops a file, the workspace calls
  `PUT /er-diagram/image-draft` (multipart form) — *not* debounced, unlike the
  XML autosave, because a discrete drop event is already the natural unit of
  work (there's no equivalent of draw.io's continuous `autosave` firing for a
  file drop). The backend (`save_er_image_draft`, `er_diagram.py`) validates
  the file, enforces `ER_MAX_IMAGE_BYTES` by actually reading the body (since
  `UploadFile.size` isn't reliably populated by every ASGI server) *before*
  handing it to storage, offloads the actual write to a thread
  (`asyncio.to_thread(provider.save, ...)` — local disk or Azure Blob, so
  synchronous I/O never blocks the event loop), upserts the
  `ErDiagramImageDraft` row (same one-statement upsert pattern as the XML
  draft, §6.1's data-model conventions), and **deletes the blob it just
  replaced** — `save_image_draft` reads the *previous* `storage_key` before
  the upsert overwrites the column, so the caller can clean up the now-orphaned
  file and nothing accumulates unbounded on disk/blob storage across repeated
  re-uploads of the same question.
- **Reading it back**: `GET /image-draft` returns only metadata (revision,
  filename, content-type — never the bytes) so the client can compare against
  its IndexedDB cache's `syncedRevision` and decide whether it needs the actual
  content; `GET /image-draft/content` streams the bytes themselves, used when
  the cache is missing or stale (a different browser, or an evicted cache).

### 6.3.4 Auto-submit at end of assessment, and the LLM-grading semaphore

**Auto-submit is a real client-triggered action, not a fiction** — it's worth
being precise about this against §5.4's "nothing polls" claim: the visible
countdown (`AssessmentTimerContext.tsx`) runs a plain `setInterval` ticking
once per second purely to *update the on-screen number*, but when that local
countdown reaches zero, it actually calls `autoSubmit()` — a genuine action, not
just a display change. The backend's own enforcement is still lazy (§5.4) —
nothing here is the backend "noticing" the deadline — but the frontend is where
the timer expiring turns into a real submission being sent, since otherwise a
student who leaves their laptop running past their deadline would never
actually finalize anything.

`autoSubmit()` calls `finalizeWithSave()`, which does three things in order,
all best-effort (a failure in one step never blocks the next — the assessment
must end regardless of what state anything else is in):

1. **Runs every registered "pre-finalize hook"** — `AssessmentTimerContext`
   exposes `registerPreFinalizeHook(fn)`, a plain `Set` any workspace component
   can add itself to (and must remove itself from on unmount). The ER diagram
   workspace is the one real user of this today: it registers a hook that hands
   over whatever image the student has staged **in memory but hasn't finished
   uploading yet** — a genuine race the design accounts for explicitly (a drop
   just before the buzzer, upload still in flight).
2. **`POST /er-diagram/finalize-pending`** — the actual grading trigger,
   described below.
3. **`POST` to the student-assessment submit endpoint** — closes the session
   server-side; if the backend already auto-finalized it via its own lazy
   expiration check on some other request, this just no-ops rather than
   erroring.

**`finalize-pending` is a deliberately trusted, unguarded path**: unlike the
regular `/submission` endpoint, it does **not** call `enforce_not_expired` —
its entire purpose is to still work when fired *at* the buzzer, after the
deadline has technically already passed, so the assessment's actual expiration
check must not be the thing that blocks it. It grades, for every ER question in
the assessment, **both** the student's XML draft **and** their autosaved image
draft as independent attempts (best-attempt scoring, §6.4, keeps whichever
scores higher — so a student who both drew something and uploaded an image
loses neither), skipping any draft that hasn't changed since it was already
graded (a genuine no-op costs zero LLM calls).

**The grading semaphore** (`_erd_grade_semaphore()`, `er_diagram.py`) is the
mechanism that keeps a mass end-of-assessment sweep — a whole class's worth of
diagrams needing grading in the same few seconds — from flooding the LLM
provider:

- It's a plain `asyncio.Semaphore(settings.ERD_GRADE_MAX_CONCURRENCY)`
  (default 5), created lazily on first use so it binds to the actual running
  event loop rather than import time. It is **per-worker**, exactly like the
  connection-pool sizing discussed in §5.5 — an `asyncio.Semaphore` can't
  coordinate across separate gunicorn worker processes, so the true
  deployment-wide concurrency ceiling is `ERD_GRADE_MAX_CONCURRENCY ×
  worker_count`, sized against the LLM provider's actual tokens/minute budget
  (a ~50k-token grade × the target ceiling of ~10 concurrent grades ≈ the
  ~500k tokens/min the account allows). Changing the worker count without
  re-deriving this value is the same kind of tripwire as the DB pool sizing.
- **The semaphore is acquired *before* the per-pair DB session is even opened**
  — `async with _erd_grade_semaphore(): task_db = SessionLocal(); ...` — so a
  task queued waiting for a free slot holds zero pooled connections while it
  waits, and each grade runs on its **own** fresh `SessionLocal()`, never the
  original request's session (which is a synchronous object, unsafe to share
  across genuinely concurrent tasks). The DB work for one pair commits and
  releases its connection *before* the 30–90-second LLM stream begins, so the
  actual bottleneck resource (DB connections) is never held for anything close
  to the duration of an LLM call — only `ERD_GRADE_MAX_CONCURRENCY` connections
  are ever briefly live per worker, and none of them for the slow part.
- **A whole class's sweep is `asyncio.gather`'d** over every `(student,
  question)` pair at once (`grade_pending_er_for_assessment`), with the
  semaphore as the only thing actually throttling how many run concurrently —
  the code doesn't chunk the list into batches itself, it just lets every
  pair's own `async with semaphore` block until a slot frees. Each pair is
  wrapped in its own `try/except` so one student's grading failure (a bad
  image, a timeout) is logged and skipped rather than aborting the whole
  `gather()` and leaving the rest of the class ungraded.
- This exact function (`grade_pending_er_for_assessment`) is **shared** between
  the student's own auto-submit-triggered finalize and a staff "bulk sweep /
  refresh scores" action — one code path, so a student's own submission and a
  staff-triggered re-grade capture ER work identically.

### 6.4 Assessments: authoring, publish/clone, start/stop, and the Timing Gateway

An `Assessment` bundles SQL questions, labs, and/or ER questions as
`AssessmentItem`s, each independently `weight`ed. Its lifecycle has four states
worth distinguishing, none of them scheduler-driven (§5.4):

1. **Draft** (`is_published = 0`) — staff can freely edit the item list; each
   `AssessmentItem.item_id` still points at a **master bank** question/lab/ER
   question (the same rows students see and practice on for free elsewhere in
   the app).
2. **Publish** (`POST /assessments/{id}/publish`, staff-only, see
   `services/assessment_clone.py`) — this is the step that **deep-copies every
   referenced item into an assessment-owned clone** and repoints each
   `AssessmentItem.item_id` at the clone (keeping the original id in
   `source_item_id` as a backreference). Concretely:
   - A SQL question clone is a **file copy** of its SQLite database
     (`generate_unique_filename` + file copy, *not* re-running the schema/data
     SQL) — this preserves the exact `correct_answer_hash` without re-validating
     it.
   - A lab clone deep-copies the lab's **template** file the same way labs are
     already templated (§6.2) — the clone gets its own `template_db_path`, so
     student sessions against it copy *that* template, never the master bank
     lab's.
   - An ER-question clone copies the row (rubric, model answer reference, etc.)
     under a new id.
   - Every clone is marked `owner_assessment_id = <this assessment>` and
     excluded from bank listings/pickers so it never shows up as something a
     staff member can pick for a *different* assessment.
   - The whole operation is transactional (flush-not-commit inside the service,
     the endpoint commits or rolls back the lot) and **idempotent** — items that
     already have `source_item_id` set are skipped, so re-publishing (e.g. after
     a transient failure) never double-clones.
3. **Running** (`is_running = 1`, via `/start`, requires already-published) *or*,
   for assessments with `gateway_enabled = 1`, access is governed by the Timing
   Gateway's per-class-group windows instead (see below) — the two are mutually
   exclusive gates on whether a student may `join`, not two timers stacked on
   each other.
4. **Unpublish — deliberately dead as of `e363358` ("stop unpublish and edit
   capability").** The endpoint (`POST /assessments/{id}/unpublish`) and the
   would-be-reversing logic (`assessment_clone.delete_cloned_content` deleting
   the clone SQLite files and soft-deleting the clone rows, each
   `AssessmentItem.item_id` pointed back at the master) **still exist in the
   code**, but a guard added ahead of it —
   ```python
   if assessment.is_published:
       raise HTTPException(400, "Published assessments cannot be unpublished.")
   ```
   — fires unconditionally on every assessment that has anything real to
   unpublish, so that logic is unreachable in practice. This is intentional,
   not an inverted-condition bug: publishing an assessment's clones is a
   one-way door because nothing merges a clone's grade history (`Attempt`/
   `LabAttempt`/`LabTaskSubmission`/`ErSubmission`, all permanently keyed to
   the *clone's* id, never the master's) back anywhere once the clone is
   deleted and the `AssessmentItem` stops pointing at it — the grades still
   exist as orphaned rows, but nothing in the app can reach them anymore. The
   frontend removes the Unpublish (and Edit) buttons entirely once
   `is_published` is true, and shows an explicit warning in the Publish
   confirmation modal itself: *"Once published, this assessment can no longer
   be edited or unpublished. Its items are frozen for students."* Same
   one-way-door pattern as `unpublish_lab`/`unpublish_er_question`? **No** —
   labs and standalone ER questions have no analogous block; this restriction
   is specific to assessments, because only assessment content has grade rows
   irreversibly keyed to a clone the way described above.

**Why clone at all, instead of letting assessments reference the bank directly?**
Three reasons, stated directly in `assessment_clone.py`'s module docstring and
worth internalizing since they'll shape any future change to this area:

- **A published assessment must be frozen.** If staff tweak a bank question's
  wording or correct answer *after* publishing an assessment that uses it,
  students mid-assessment (or grading afterward) must not be affected. Cloning
  at publish time — rather than at grading time, or via some "pin to a version"
  scheme — means the assessment simply points at content that literally cannot
  change underneath it, because nothing else references that clone.
- **Practice progress must never leak into (or out of) a graded attempt, and vice
  versa.** A student who practiced a question in the free bank has `Attempt` rows
  keyed to the *master* question's id. Once that question is cloned for an
  assessment, the assessment attempt is keyed to the *clone's* id — a completely
  different primary key. There is no shared row for "prior practice" and "this
  graded attempt" to collide on, so a student's practice history can never
  accidentally count toward (or be confused with) their assessment score, and
  resetting/regrading one never touches the other. This is a deliberate
  isolation-by-construction choice: rather than adding an `is_practice` flag or a
  `context` column to every attempt/grading/analytics table and auditing every
  query to respect it, giving assessment content its own distinct rows means
  **all existing grading, progress, attempt-history, cleanup, and aggregation
  code keeps working completely unmodified** — it's automatically scoped to one
  assessment just by virtue of operating on ids that only that assessment's items
  point to. That's the "easier and better to implement" part: a whole class of
  potential practice/assessment cross-contamination bugs is structurally
  impossible rather than something every future feature has to remember to guard
  against.
- **Soft-delete, not hard-delete, on unpublish** exists so that a student's
  historical attempt record (which foreign-keys to the clone's id) still resolves
  when a staff member looks at past analytics for an assessment that has since
  been unpublished — hard-deleting the clone row would orphan that history.

There are two independent timing mechanisms layered on top of the above — read
both docstrings (`services/assessment_timer.py`, `services/assessment_gateway.py`)
before changing either:

1. **Per-attempt timer** (`AssessmentSession.end_time`) — a personal countdown
   that moves forward as query time is credited back (§5.4).
2. **Timing Gateway** (`AssessmentClassWindow`, gated by
   `Assessment.gateway_enabled`) — a per-`class_group` scheduled access window
   (`start_at`/`end_at`). When enabled, it supersedes the manual
   start/stop flag entirely.

The two compose: a session's *effective* deadline is `min(personal end_time,
window end_at)` — the window's `end_at` is stamped onto the session as an
immovable `hard_deadline` at join time.

**Scoring** (`services/assessment_scoring.py`) always uses the student's **best
attempt**, not the latest one, per item — this was a deliberate correction (see
git history: "Score ERD assessment items on the best attempt, not the latest").
Per-item-type correctness fractions (binary for SQL questions, task-completion
ratio for labs, best percent for ER questions) combine into a single weighted
0–100 score via `Σ(weight_i × fraction_i)`, normalized so weights don't need to
sum to exactly 100. Returns `None` (shown as "N/A") for unweighted/legacy
assessments rather than a misleading 0.

### 6.5 AI Tutor ("Bagheera") and the Akela Learning Analytics pipeline, end-to-end

Two tutor code paths coexist, on purpose:

- **`services/tutor_chat/`** — the original, stateless-ish streaming chatbot
  (`api/v1/endpoints/chatbot.py`, `/send` and `/lab-chat`). Always available,
  regardless of any flag.
- **Adaptive mode** (`services/sql_tutor_adaptive.py` + `sql_tutor_prompts.py`),
  gated by `SQL_TUTOR_ADAPTIVE`. Explicitly **not** a LangGraph engine — the
  module docstring says so — because the flow is "a couple of DB lookups plus
  prompt assembly," not a multi-step agent graph.

Everything below this point is gated by `AKELA_AGENTS_ENABLED`
(mastery/telemetry/SOLO) and/or `SQL_TUTOR_ADAPTIVE` (the prompt actually
changing what the student sees) — with both off, `send_chatbot_message` builds
its original hardcoded system prompt (still inline in `chatbot.py`, never
deleted) and none of the machinery below runs at all.

**The pipeline has two separate triggers, on two separate cadences, that only
meet inside the *next* chat turn's prompt:**

1. **Mastery updates, triggered by grading, not by chat.** Every time a
   student's query is graded — `execute.py::execute_query` for SQL Questions
   (§6.7) — and `AKELA_AGENTS_ENABLED` is on, a `BackgroundTasks` job calls
   `learner_profiling.process_query_submitted(user_id, question_id, is_correct)`.
   This looks up every `(concept_id, weight)` tag the question carries
   (`question_concepts` — a question can exercise more than one concept, each
   independently weighted) and, for **each** tagged concept, applies one fixed
   deterministic rule to that student's `ConceptMastery` row (creating it at
   `mastery_level=0.0` on first touch):
   ```
   correct:    consecutive_successes += 1, consecutive_failures = 0
               mastery_level += CONCEPT_MASTERY_SUCCESS_DELTA * weight   (clamped to [0,1])
   incorrect:  consecutive_failures += 1, consecutive_successes = 0
               mastery_level -= CONCEPT_MASTERY_FAILURE_DELTA * weight   (clamped to [0,1])
   ```
   `total_attempts` and `last_attempt_at` are bumped either way. Nothing here
   calls an LLM (§5.2) — `apply_attempt()` is pure arithmetic over the DB, which
   is exactly what makes `backend/tests/test_akela_agents.py` able to assert
   exact mastery values without mocking anything.
2. **Scaffolding level, recomputed at the *start* of every adaptive chat turn**
   — not by the mastery update above, and not on a schedule. Every call to
   `sql_tutor_adaptive.prepare_turn()` (i.e. every message sent while
   `SQL_TUTOR_ADAPTIVE` is on) re-derives the level from whatever the student's
   `ConceptMastery` streaks currently say, via
   `scaffolding_engine.compute_next_level(current_level, consecutive_successes,
   consecutive_failures)`: failures take precedence over successes (a
   `SCAFFOLDING_DOWNGRADE_STREAK`-length failure streak drops support one level,
   checked first), and a `SCAFFOLDING_UPGRADE_STREAK`-length success streak
   fades support one level, over the four ordered levels `full → guided →
   minimal → independent`. The **active concept** for a question is simply its
   highest-weight tag (`resolve_active_concept` — untagged questions never
   move off the default `full` level, since there's no mastery to key off of).
   The level itself is persisted on `SqlTutorConversation.scaffolding_level`
   (one row per `(user, question)`, created lazily on first adaptive turn) so
   it survives across turns without being recomputed from scratch — but the
   *computation itself* re-runs every turn against live streak data, it isn't
   just read back unchanged. A transition logs an `EVENT_SCAFFOLDING_CHANGED`
   telemetry event carrying `{from_level, to_level}`.

**SOLO classification runs asynchronously per message and is deliberately
consumed one turn late.** When a student sends a chat message,
`chatbot.py::send_chatbot_message` schedules
`solo_classifier.classify_message(...)` as a `BackgroundTasks` job — it does
**not** block the response, and does not affect the reply the student is about
to receive. It makes its own synchronous LLM call (the *sync* provider SDK, not
the async one used for the streaming reply, because a `BackgroundTasks` job
runs in the threadpool, not the event loop) with a fixed prompt asking for
exactly one of five SOLO Taxonomy levels
(`prestructural`/`unistructural`/`multistructural`/`relational`/`extended_abstract`)
plus a self-reported `confidence` 0–1, and persists a `SoloClassification` row
(also logging `EVENT_SOLO_CLASSIFIED`). Very short messages ("ok", "thanks") are
skipped before ever reaching the LLM. **The result of classifying message N is
only read when building the prompt for message N+1** — `prepare_turn()` calls
`latest_solo()` to fetch whichever `SoloClassification` is newest for that
conversation *before* the current message is classified, and unparseable model
output is simply discarded (logged, not retried). This one-turn lag is the
price of never making the student wait on an extra LLM round-trip before their
tutor reply starts streaming; there is no synchronous SOLO path.

**The confidence gate is enforced twice, independently, for defense in depth**:
once when the classification is created (`used_fallback` is stored `True` on
the row itself if `confidence < SOLO_CONFIDENCE_THRESHOLD`), and again when it's
*read back* in `prepare_turn()` (`used_generic = fallback OR confidence <
threshold` — re-checked against the live setting rather than trusting the
stored flag alone, so lowering `SOLO_CONFIDENCE_THRESHOLD` after the fact
doesn't retroactively "unlock" old low-confidence rows). **SOLO level is never
shown to the student anywhere in the UI** — there's no "your SOLO level is X"
display; it exists purely as a hidden signal that tailors the tutor's tone
(§ below) and as raw telemetry for staff/research analysis.

**Prompt assembly** (`sql_tutor_prompts.build_system_prompt`) is a hardcoded,
non-DB-editable template (`services/sql_tutor_prompts.py` — no admin UI to edit
these, unlike the ERD tutor's Dify-authored prompts) built from three stacked
blocks: a common base (question/schema/sample-data/student's-latest-query,
always the same "never give away the answer" rules), a `LEVEL_GUIDANCE` block
selected by the current scaffolding level (from concrete hints at `full`, down
through progressively more Socratic/question-only phrasing at `independent`,
where the tutor is instructed to give *no* hints or fixes at all — only
metacognitive questions), and a `SOLO_GUIDANCE` block — but only when a
confident, non-fallback classification exists; otherwise a neutral
`GENERIC_SOLO_NUDGE` is used instead, so an unclassified or low-confidence
student still gets a coherent, level-appropriate prompt, just without the
SOLO-specific tone.

**Two separate "conversation" record types exist for the same (student,
question) pair, and it's worth being clear on why**, since it looks like
duplication otherwise: `tutor_chat_conversation`/`tutor_chat_message` is the
**actual chat transcript** — the messages fed back to the LLM as memory
(`TUTOR_CHAT_MEMORY_TURNS`, capped at 10) and what a page reload restores —
and exists regardless of `SQL_TUTOR_ADAPTIVE`. `sql_tutor_conversation`/
`sql_tutor_message` is a **separate state record**, created only when adaptive
mode is on, that carries `scaffolding_level`, `active_concept_id`, and the link
`SoloClassification` rows key off of (`conversation_id`) — it is not itself
where the visible chat text lives. If you're debugging "the adaptive tutor
seems to have amnesia about scaffolding but remembers the conversation fine"
(or vice versa), check which of the two tables actually holds the state you're
looking at.

If `prepare_turn()` raises for any reason, it's caught in `chatbot.py` and the
original hardcoded (non-adaptive) system prompt is used instead — the adaptive
layer can degrade but can never break the chat.

### 6.5.1 The LAD read side: what the student dashboard actually shows

The **Learning Analytics Dashboard** (student-facing: "My Learning",
`frontend/src/app/student/analytics/page.tsx`, backed by `services/lad_service.py`
+ `api/v1/endpoints/lad.py`) is a **read-only aggregation** over the data the
pipeline above produces — it computes nothing new, no LLM calls happen on this
path at all:

- **`GET /lad/concept-graph`** — every active `SqlConcept` plus this student's
  own `ConceptMastery.mastery_level` (raw `0..1` float, rounded to 4dp) and a
  coarse display band derived from it (`mastery_band`: `<0.25` novice, `<0.5`
  developing, `<0.8` proficient, else mastered; `None` → "untouched," a concept
  never attempted), plus the prerequisite edges — rendered client-side as a DAG
  with `dagre` + hand-rolled SVG in `frontend/src/components/lad/ConceptGraph.tsx`
  (no new graphing library added for this). A 26-concept, 17-prerequisite-edge
  taxonomy is seeded by `services/concept_taxonomy_seed.py`
  (`run_akela_agents_migration.py --seed`).
- **`GET /lad/peer-benchmark`** — the anonymized class-average mastery per
  concept described in §5.6/§7.4: cached under a date-stamped key
  (`(class_group, today's date)`), so it's at most a day stale by design, and
  suppressed entirely (`{"suppressed": true, "reason": "cohort_too_small" |
  "no_class_group"}`) below `PEER_BENCHMARK_MIN_COHORT`, rather than ever
  showing a computed average for a cohort small enough to identify a specific
  classmate.
- **`GET /lad/scaffolding/{question_id}`** — the current scaffolding level for
  that (student, question) pair, read straight off `SqlTutorConversation`
  (defaulting to `"full"` if no adaptive conversation has started yet, and
  never creating one just to answer this read) — this is what drives
  `components/workspace/ScaffoldingIndicator.tsx` in the chat tab, the one
  place a student sees any signal from this system while actually working a
  question.
- Concept **tagging** itself (`GET`/`PUT /lad/questions/{id}/concepts`) is a
  staff-only CRUD surface (`components/admin/QuestionForm.tsx`) — mastery and
  scaffolding are only ever computed for concepts a question has been
  explicitly tagged with; an untagged question contributes nothing to any
  student's mastery map no matter how many times it's attempted.

**Rollout note**: the "My Learning" nav link is always visible in the UI even
while the flags are off — it just shows an empty/"not started" state (every
concept renders "untouched," no mastery rows exist yet). To hide it entirely
pre-launch, remove the nav line or simply don't run the seed migration.

### 6.6 Admin, analytics, and auth

- **Auth** (`api/v1/endpoints/auth.py`, `core/security.py`): JWT (HS256,
  `python-jose`), bcrypt password hashing, Google SSO (`google-auth`) and
  Microsoft SSO (`PyJWKClient` against Azure Entra ID's JWKS endpoint, tenant
  `"common"` so both work/school and personal Microsoft accounts work). On the
  frontend, Microsoft sign-in uses a **full-page redirect**, not a popup — see the
  comments in `AuthContext.tsx` for why (`navigateToLoginRequestUrl: false` avoids
  a visible flash back to `/login` before the role-based redirect fires). All
  three login paths converge on the whitelist-by-email gate described in §5.10 —
  that's the actual "can this person get in at all" check, done before a `User`
  row is even created.
- **Live presence**: `platform_session.py` + a heartbeat
  (`frontend/src/hooks/use-presence-heartbeat.ts`) — `PRESENCE_BEAT_SECONDS` /
  `PRESENCE_WINDOW_SECONDS` in `config.py` control how often a tab checks in and
  how stale a check-in can be before the user is shown offline; the window must
  stay `≥ 2×beat + 60s` or presence flickers (documented in `config.py`). The
  underlying session-time-tracking model this rides on is described fully in
  §6.6.2.
- **Whitelist**: `whitelist.py` model + endpoint — an allowlist of emails
  permitted to self-register *and* the source of truth for their role,
  display name, and class group, synced onto the `User` row at first login
  (§5.10). Not separate from the role system — it's how role is assigned in
  the first place, before a `User` row exists. Bulk-loading a class roster into
  it is covered in §6.6.7.

### 6.6.1 Staff analytics: computed live, not from rollup tables

`services/sql_analytics.py`, `er_analytics.py`, and `lab_analytics.py` are
**deliberately parallel implementations**, one per content type, each following
the same shape (their own docstrings say so explicitly: *"mirrors
er_analytics.py"*) rather than one generic analytics engine parameterized by
content type. **Nothing here is a maintained rollup/summary table** — every
number is computed from the raw `Attempt`/`LabAttempt`/`LabTaskSubmission`/
`ErSubmission` rows on each request, wrapped only in the ordinary
version-counter cache from §7 (so a fresh number is at most one request behind
the last write, not a nightly batch job). The stated reasoning is simply that
class sizes are small (tens of students, not thousands) — this is a legitimate
scaling tripwire: if cohort sizes grow by an order of magnitude, this is the
first place to consider a real materialized rollup, and `Ns.ASSESSMENT_ANALYTICS`
(§7.3) already shows what that would look like (write-triggered instead of
computed-per-read).

Each of the three computes, per question/lab: a roster of students who
attempted it (email/name/class_group joined in once, not per-row — the same
"fetch identity once, not N times" discipline seen in `platform_usage.py`,
§6.6.2), a completion signal specific to that content type (SQL Questions:
"queries run up to and including the first correct one," preferring the exact
count from full attempt history but falling back to `UserProgress.attempts_count`
for students whose correct attempt predates an older pruning behavior that's
since been removed; Labs: the same idea per task, "submissions to first
correct," which is always exact because lab submissions are never pruned), and
**whether the student ever used the AI tutor on that specific item** — computed
by checking for at least one message in a `TutorChatConversation`/`Message`
pair scoped to that `(user, content_type, content_id)`. A `student_detail`
function per module returns one student's full query/attempt history, chat
transcript, and AI-review history for that item — this is what backs the
per-student drill-down staff sees when they click into an item's analytics.

### 6.6.2 Platform-time tracking and presence

`services/platform_usage.py` answers two different questions from the same
`platform_sessions` table, and it's worth keeping them distinct:

- **"How much time has this student spent on the platform"** (`daily_usage`,
  `usage_summary`, `usage_overview`, `lifetime_total`) — a `PlatformSession` row
  is opened once per login (`start_session`), and its duration is simply
  `last_action_at − login_at`. `touch_session` advances `last_action_at` on
  meaningful authenticated actions, but is **throttled server-side to once per
  `THROTTLE_SECONDS` (120s)** via a single conditional `UPDATE` (no prior
  `SELECT`) — so a burst of rapid actions costs one write, not one per action,
  and the resulting duration is granular to about two minutes, not exact to the
  second. A day's total is the *sum* of that day's session durations (a student
  can log in more than once in a day); a month's total sums across days; the
  all-time total is a live sum over **every session ever recorded** — there is
  no way to bound that scan to a date range, so it necessarily grows with the
  school year, and the code says outright what the real fix would be if it ever
  becomes the bottleneck: a per-student rollup maintained incrementally inside
  `touch_session`, not a query-time full scan. Duration arithmetic is
  deliberately done in **Python, not SQL** in every one of these functions —
  the comment is explicit that SQLite and Postgres don't agree on
  datetime-subtraction semantics, so keeping it in Python guarantees identical
  output on both backends (the same dev/prod-parity concern as §5.7).
- **"Who is online right now"** (`count_online`, `list_online`, behind the
  `/admin` active-user count) — a *different* read over the same table: a
  session counts as "online" when its `last_action_at` is inside
  `PRESENCE_WINDOW_SECONDS` **and** it hasn't been explicitly marked left
  (`left_at`) since that action. `mark_left` (fired by a `pagehide`-style signal
  on the frontend) sets *only* `left_at`, never touching `last_action_at` —
  doing otherwise would retroactively shrink the recorded time-on-task duration
  above, conflating "presence" with "usage time," which are genuinely different
  numbers computed from the same rows. A user who left and came back has
  `left_at` cleared by the *next* `touch_session` call (specifically exempted
  from the 120s throttle, so a quick return isn't stuck "away" for up to two
  minutes).

Every write in this module is wrapped in `try/except`, logged, and swallowed —
the module docstring states the principle directly: *tracking must never break
a login or an authenticated request; a lost heartbeat is far better than a
failed action.* This is the same fail-open instinct as the cache layer (§7.1)
applied to telemetry instead of reads.

### 6.6.3 The research-export pipeline

`services/research_export.py` (~550 lines) is a genuinely separate subsystem
from the staff analytics in §6.6.1 — it exists specifically to produce data for
**research use** (this being an academic FYP project, this is very plausibly
feeding the actual research writeup), not day-to-day teaching decisions, and
its numbers are shaped accordingly: cohort-level and anonymized rather than
"which student needs help." It has two outputs, both staff-only:

- **`GET /admin/export/summary`** (`compute_summary`) — seven cohort-level
  aggregates assembled into one JSON payload, cached under `Ns.RESEARCH_EXPORT`
  with the same date-stamped-key strategy as `CONCEPT_MASTERY_AGGREGATE` (§7.4
  — refreshes once/day, no write-triggered invalidation, because it spans a
  half-dozen high-write tables): `system_scale` (distinct students, lab
  sessions, total graded submissions — SQL question attempts + lab task
  submissions specifically, with raw exploratory lab query *runs* excluded so
  they don't double-count against the graded submissions), `adaptive_efficacy`,
  `solo_articulation` (a SOLO-level transition matrix — how students move
  between the five levels over time), `ai_performance`, `productive_friction`,
  `learning_curves` (bucketed by "opportunity index," capped at
  `MAX_OPPORTUNITY = 10` attempts so one outlier student's hundreds of attempts
  on one concept doesn't blow out the bucket range), and
  `misconception_taxonomy` — a **first-match-wins pattern classifier** over raw
  SQL error messages (`_classify_error`), ordered most-specific-first (e.g. an
  "ambiguous column" error must classify as `wrong_join` before the more
  generic `unknown_column` pattern gets a chance to match it). The taxonomy's
  own comment is honest about its limits: it's "a first pass written against
  generic SQLite/Postgres phrasing" and should be validated against a real
  sample of this deployment's actual `error_message` values before anyone
  relies on it for a research conclusion.
- **`GET /admin/export/raw-csv`** (`stream_raw_csv_rows`) — one row per
  student, streamed (all DB aggregation batched up front via
  `_prefetch_all_student_metrics`; only the CSV text serialization is a
  generator, so the response starts immediately rather than after the full
  cohort is computed). Columns: `anon_id, class_group, final_weighted_score,
  total_time_on_task_min, num_ai_interactions, hint_dependency_ratio,
  avg_solo_level_numeric, scaffolding_level_at_end, error_category_counts_json`
  — no name, no email, nothing directly identifying beyond `class_group` (which
  is why `PEER_BENCHMARK_MIN_COHORT`-style cohort-size floors matter elsewhere,
  though this particular export doesn't itself suppress small groups — treat
  `class_group` in a downloaded CSV as sensitive on its own).

**The anonymization mechanism** (`anon_id`) is exactly what §5.6 promised but
didn't spell out the mechanics of: `HMAC-SHA256(RESEARCH_EXPORT_SALT,
str(user_id))`, truncated to 16 hex characters. This is a keyed one-way hash,
not an encoding — there is no stored mapping anywhere from `anon_id` back to
`user_id`, and it cannot be reversed without the salt. Because the *same*
`user_id` always hashes to the *same* `anon_id` (as long as the salt doesn't
change), a researcher can still track one anonymized student's data across
multiple export runs or across the summary and the CSV — the anonymity is
against an outside reader identifying *who* a row is, not against the dataset
losing per-student consistency. **Rotating `RESEARCH_EXPORT_SALT` permanently
breaks that consistency** — every `anon_id` changes at once, which is a one-way
door (§5.6 already flags this; it's restated here because it's the concrete
mechanism behind that warning). Every population query in this module funnels
through `_student_ids`, which applies
`assessment_registration.exclude_test_groups` — the same
`ANALYTICS_EXCLUDED_CLASS_GROUPS` filter used everywhere else (§5.6) — so a
staff/TA test account can never appear as a row in research data, anonymized
or not.

### 6.6.4 Grading-integrity tooling: staff score overrides and submit-on-behalf

Two related but distinct staff powers exist over ER-diagram grades, both
reached through `api/v1/endpoints/er_analytics.py`:

**Score override** (`services/er_score_override.py`) lets staff hand-correct an
LLM-graded ER submission, check by check. The LLM grader can only ever award a
check `pass`/`partial`/`fail` — which `compute_grade` (§6.7) turns into `100%`,
`50%`, or `0%` of that check's points — but a human marking by hand often needs
a number in between (13 of 18 points, say), which no status can express. Staff
therefore set **points earned per check directly**; the code derives a
`status` back out of that number for display (`_status_from_earned`: `0` →
`fail`, full value → `pass`, anything between → `partial`, the "everything in
between" status the rest of the system already understands) — the override is
the one place points come first and status is derived, the reverse of how the
grader itself works. A few integrity rules worth knowing if you touch this:
- **Weights come from the submission's own stored `checks_json`, never the
  question's current `rubric_json`.** A rubric can be edited after a student's
  attempt was graded; re-scoring against today's version would silently mark
  the student against criteria they were never shown.
- **The grader's original result is snapshotted exactly once**, on the *first*
  correction only (`original_grade_json`), specifically so "what did the AI
  originally say" has one stable answer even across several rounds of
  corrections — and so a correction can be reverted (`revert_override`) back to
  that frozen original at any time.
- **A correction only ever touches the student's assessment mark if it's their
  *latest* attempt** (`is_latest_attempt`) — correcting a superseded attempt
  updates that historical row for the record, but deliberately does not move
  the conversation state (`last_submit_score`) that the student currently sees
  and that scoring reads, since that would be marking them on work they'd
  already replaced.
- **Propagation is two hops, both required**: syncing the conversation alone
  isn't enough, because the assessment roster reads a value cached at
  finalization (`assessment_scoring.refresh_frozen_weighted_score`) and the
  cached `Ns.ASSESSMENT_ANALYTICS` payload isn't touched by an ordinary
  conversation write (§7.3's deliberate non-invalidation for that namespace
  during a live exam) — so an override explicitly calls `bump_version` *and*
  `refresh_frozen_weighted_score` itself, or a correction would show up in ER
  analytics and nowhere else a staff member is actually looking.

**Submit-on-behalf** (`services/er_staff_submission.py`) is for the opposite
situation: a student who never submitted anything at all (per git history:
*"Let staff add an ER submission for a student who never submitted one"*).
`grade_and_record` runs the exact same LangGraph grading pipeline a live
student submission runs, and is **shared code** between the staff-facing
endpoint and `scripts/grade_saved_draft.py`, a standalone maintenance script
for bulk-cleanup — the module docstring states the reason explicitly: *a
submission written by either route must be indistinguishable from a student's
own, or the assessment mark and the analytics disagree about what happened.*
It's async specifically because the 30–90s spent awaiting the LLM would
otherwise pin a threadpool worker for that entire duration; the actual
SQLAlchemy writes are pushed to a worker thread instead
(`asyncio.to_thread(_persist)`), keeping the event loop free in both
directions — the same discipline as the ERD grading semaphore's session
handling in §6.3.4. It refuses to run over an existing grade unless
`regrade=True` is explicitly passed (`AlreadyGraded`), and every written row
carries `added_by_staff_id`/`added_reason` so a staff-added submission is
auditable as such even though it's otherwise identical to a student's own.

### 6.6.5 Assessment reset: what "clean slate" actually deletes

`services/assessment_reset.py::reset_student_attempt` is the staff action that
lets one student retake an assessment from scratch. It's worth understanding
precisely because of what it *doesn't* touch: since assessment content is
cloned at publish time (§6.4) and every clone's `owner_assessment_id` points
back to exactly one assessment, a reset can delete a student's `Attempt` /
`LabAttempt` / `LabTaskSubmission` / `ErdTutorConversation` rows keyed to those
clone ids **without any risk of touching the student's standalone practice
attempts or their attempts on any other assessment** — there's no shared row to
accidentally delete, by the same clone-isolation construction described in
§6.4's "why clone" rationale. As a second safety belt beyond that structural
guarantee, `_owns()` explicitly re-verifies each content row's
`owner_assessment_id` actually matches the assessment being reset before
deleting anything against it, even though the calling contract (only ever
called against a published assessment) should already guarantee that. The
student's `AssessmentSession` row(s) are deleted outright, not soft-reset —
which is also what clears the single-attempt completion lock (§6.4) so the
student can rejoin. Every delete here is a bulk `.delete()` that bypasses the
ORM unit of work, so (per §7.3) it can't trigger the automatic cache
invalidation — the function ends with an explicit `bump_version(db,
Ns.ASSESSMENT_ANALYTICS)` for exactly that reason.

### 6.6.6 Platform config, per-user preferences, and the ER storage abstraction

Three small, deliberately narrow key/value-shaped subsystems, easy to miss
because none has its own endpoint file worth reading in isolation:

- **App settings** (`services/app_settings.py`, `AppSetting` model) — a generic
  `key → string value` table for **admin-tunable, boolean, platform-wide**
  toggles, with defaults living in code (`DEFAULTS: dict[str, bool]`) so a
  missing row is a well-defined default rather than an error — callers of
  `get_bool` never see `None`. Today it has exactly one entry
  (`erd.student_authoring_enabled` — whether students may author their own ER
  questions, off unless staff turn it on). Add a new admin toggle by adding a
  key here, not a new table.
- **User preferences** (`services/user_preferences.py`, `UserPreference`
  model) — the same shape, but per-user and for **UI state**, not platform
  config (currently: whether a student dismissed the ERD guide modal). The
  vocabulary is a closed `ALLOWED_KEYS` frozenset checked on every write
  (`set_value` raises `ValueError` for anything outside it) — a deliberate
  guard, per its own comment, against the table quietly becoming a
  general-purpose dumping ground for arbitrary client state. Adding a new
  "don't show again" flag for a future guide is one new constant here plus a
  matching frontend key, no schema change either way.
- **ER storage provider** (`utils/er_storage.py`) — a small `Protocol`
  (`save`/`delete`) with two implementations,
  `LocalERStorageProvider` (writes to `ER_DIAGRAM_UPLOAD_PATH` on local disk)
  and `AzureBlobERStorageProvider` (uploads to `ER_AZURE_CONTAINER`, accepting
  either a connection string or an account URL + key), selected once at
  request time by `get_er_storage_provider()` reading `ER_STORAGE_PROVIDER`.
  This is the same "engine flag" shape as `ERD_TUTOR_ENGINE` (§5.1) applied to
  a storage backend instead of an LLM pipeline — every caller (image drafts
  §6.3.3, submission images, model answers) codes against the `Protocol`, never
  against either concrete class, so switching a deployment from local disk to
  Azure Blob is a one-line env var change with no code change anywhere that
  calls it.

### 6.6.7 Bulk import: student rosters and the SQL question bank

Two independent bulk-loading paths, neither of which shares code with the
other (they load fundamentally different things), and neither of which has a
bespoke bulk-insert code path on the backend — both are designed to go through
the *same* validated write path a single manual entry would use:

- **Student roster upload** (`services/excel_parser.py` +
  `api/v1/endpoints/whitelist.py`'s `/upload`/`/upload/confirm` pair) — parses
  a school-exported attendance-list file (`.xlsx`, `.xls`, or a `.xls` that's
  actually tab-separated text, which the parser detects and handles — a
  documented real-world quirk of the exported files this targets) into
  `{name, email, class_group}` rows: rows are ragged (a "Class Group: X"
  metadata row has far fewer columns than a real student row), which the
  parser works around by naming a fixed, generously-wide column set so pandas
  pads short rows with `NaN` instead of raising a `ParserError`. Student emails
  aren't in the source file directly — they're derived from a username column
  (`f"{username.lower()}@e.ntu.edu.sg"`), a hardcoded institution-specific
  assumption worth knowing about if this is ever adapted for a different
  school's export format. **The endpoint is a preview-then-confirm pattern,
  never a direct write**: `POST /whitelist/upload` is a dry run
  (`preview_student_upload`) that diffs the parsed sheet against the existing
  `WhitelistEntry` table and returns `{to_add, to_update, to_remove}` without
  writing anything; the frontend shows this diff for staff to review, and only
  a subsequent `POST /whitelist/upload/confirm` actually commits it. A
  zero-valid-row parse is explicitly rejected rather than silently proposing
  to remove every existing student — the code treats an all-empty parse as
  much more likely to be a wrong/corrupt file than a genuinely empty roster.
- **SQL question bank bulk import** (`MASS_UPLOAD_QUESTIONS.md`,
  `frontend/scripts/convert-leetcode-questions.mjs` +
  `backend/scripts/import_leetcode_questions_via_api.py`) — this is **not** a
  database-loading script in the usual sense. It's a two-stage *local* pipeline
  where a Node script converts a JSON file of LeetCode-style problems (MySQL →
  SQLite dialect, detects concept tags and whether row order matters) and a
  Python script then calls `POST /questions` **against the real deployed API**
  — the exact same endpoint the admin "New Question" form itself calls — once
  per question. The doc is explicit about why: *"every question's practice
  database is built on the server that will grade it,"* so a bulk-imported
  question's SQLite file (§6.1) is generated by the identical code path as a
  manually authored one, with no separate bulk-creation logic anywhere on the
  backend to keep in sync or accidentally diverge from. Titles must be unique
  and re-running the importer against already-imported questions is a no-op
  skip (matched by title), so the script is safe to re-run after a partial
  failure.

### 6.7 Grading pipelines end-to-end

Four different grading pipelines exist, one per content type, and they're built
differently on purpose because each has different trust/isolation needs.

**SQL Questions** (`POST /api/v1/execute`, `api/v1/endpoints/execute.py::execute_query`).
Request: `ExecuteRequest{question_id, query}`. The handler runs in three
deliberately separated phases (this pattern — release the DB connection before
the slow/untrusted part, re-acquire it only for the final write — recurs
throughout the codebase and is worth copying for any new grading endpoint):

1. **Read phase** (short Postgres transaction): loads the `Question`, snapshots
   every field the rest of the function needs into plain locals (not ORM
   attributes — see the comment in the code about attribute-expiry-after-commit
   triggering surprise reload queries), resolves whether this is assessment
   content (checks `owner_assessment_id`) and, if so, enforces the assessment
   timer (§6.4) and the per-question `max_queries` cap. Ends with `db.commit()`
   to hand the Postgres connection back to the pool.
2. **Query phase** (no Postgres connection held): the student's query runs
   against the question's SQLite file (§6.1) for up to several seconds. Two
   grading modes branch here:
   - **Standard**: `core.query_executor.execute_student_query` runs the
     (read-only-enforced) query, then `core.answer_validator.validate_answer`
     hashes the result set and compares it to the question's stored
     `correct_answer_hash` (order-sensitive or not, per `question.order_sensitive`).
   - **Advanced SQL Testing** (`question.advanced_sql_testing`, for
     trigger/DML-style questions where the submission itself returns no rows —
     `core/advanced_sql_grader.py`): a 3-stage pipeline runs entirely against a
     single **isolated in-memory clone** of the question's database, never the
     canonical on-disk file — (1) apply the student's submitted SQL (e.g. a
     `CREATE TRIGGER`), (2) run a hidden **Test Script** that exercises its
     effect (e.g. an `INSERT` that should fire the trigger), (3) run a hidden
     **Check Query** that captures the resulting state, then hash *that* output
     the same way standard grading does. Error messages are handled per stage:
     a failure in the student's own SQL is safe to show verbatim; a failure in
     the hidden Test Script or Check Query is replaced with a fixed generic
     message, because the raw SQLite error could leak hidden table/column
     names the question is designed to keep secret.
3. **Write phase** (short Postgres transaction, in a `try`/`finally` so it still
   runs on a timeout): persists the `Attempt` row (always, correct or not) and
   updates/creates the `UserProgress` row (marks `completed=1` on first correct
   answer). The `finally` credits the query's wall-clock time back to the
   assessment deadline (§5.4) regardless of outcome.

Response: `ExecuteResponse{is_correct, execution_time_ms, results, columns,
error_message, row_count, assessment_end_time, max_queries, attempts_used}` —
see §14 for the full schema and the reasoning behind its `Optional` fields.
Background, fire-and-forget (`BackgroundTasks`, after the response is already
constructed): a `learning_event` telemetry write and the deterministic Learner
Profiling mastery update (§6.5), both gated by `AKELA_AGENTS_ENABLED` and unable
to affect the response the student already received.

**SQL Labs and Graph Labs** split grading across **two separate endpoints**,
which is a meaningfully different shape from Questions:

- `POST /labs/session/{id}/execute` runs *any* statement the student typed
  against their session-scoped database copy (§6.2), dispatching to
  `LabQueryExecutor` or `GraphQueryExecutor` by `lab.lab_type`, and logs a
  `LabAttempt` row. This is exploratory — it's how a student runs a query at
  all, correct or not, task-related or not.
- `POST /labs/tasks/submit` is the actual grading step, and it is **not** a
  second query execution**: it takes the `columns`/`results` the *client already
  received* from a prior `/execute` call, hashes them
  (`generate_hash(results_tuples, columns, order_sensitive=task.order_sensitive)`),
  and compares against the task's stored `correct_answer_hash`. **The server
  does not re-run the query for the submit step — it trusts the result set the
  client reports.** This is a real, structural difference from SQL Questions
  (where `execute.py` always re-executes and hashes server-side) and is called
  out again in §11 as something to be aware of if you're ever asked to harden
  grading integrity for labs.

**ER Diagrams** dispatch on `settings.ERD_TUTOR_ENGINE` inside
`services/er_grading.py` / `services/erd_tutor/runner.py` (§6.3). The legacy
`dify` path proxies the submission (XML or image) to a hosted Dify workflow over
HTTP/SSE, with purpose-built error translation for common failure shapes (e.g.
detecting a Cloudflare/WAF block and returning an actionable message instead of
raw HTML). The `langgraph` path runs `submit_graph` (observe → normalize → grade
→ score) and produces a **deterministic points-based score**
(`services/erd_tutor/scoring.py::compute_grade`) from two independent JSON
documents: the question's **rubric** (a list of checks, each with an `id`, a
`requirement_level` of `must`/`should`/`optional`, and a `points` value) and the
LLM **judge's** verdict on each check (`pass`/`fail`/`partial`/`not_applicable`
+ a short reason). The two are joined by check `id`. Notably fail-safe: if the
judge's response is missing a verdict for some check, that's treated as a
*grader* failure, not evidence the student got it wrong — a zero-point/optional
check becomes `not_applicable` ("not evaluated"), while a `must`/`should` check
with real points still fails conservatively (silently passing an unverified
check would be the worse failure mode). A rubric check can also declare a
binding `decision_policy` that forces a strictly binary pass/fail even if the
judge hedges with `"partial"` — because it's an LLM, it sometimes returns
`"partial"` on checks the rubric explicitly doesn't allow partial credit for,
and the rubric's own policy overrides that.

### 6.8 The AI-assist helpers for SQL ("Bagheera's toolkit")

Beyond the always-on streaming tutor chat (§6.5), `api/v1/endpoints/chatbot.py`
implements several **narrow, single-purpose LLM-backed endpoints** that power
specific UI affordances on the SQL Questions workspace, all sharing one
provider-agnostic helper:

**`call_ai_for_review(system_prompt, context)`** — the one function every helper
below goes through. Branches on `settings.AI_PROVIDER` (`azure_openai` |
`openai` | `gemini`), builds the right async client, sends the given system
prompt plus `context` (an arbitrary dict) JSON-dumped as the user message,
strips a markdown code fence if the model wrapped its answer in one, and
`json.loads`s the result — callers get back a plain dict, never a raw model
response object. Retries **once** on any exception (a bare `try: ... except:
return await _once()` — no backoff, no logging of the first failure) before
letting the error propagate. Temperature defaults to `0.2` unless
`AI_TEMPERATURE` is set or `AI_ENABLE_TEMPERATURE=False` (needed for
reasoning-style models that reject the parameter entirely). Every system prompt
in this file ends with an explicit "respond ONLY with valid JSON in this exact
shape" instruction — the contract between prompt and parser is enforced by
prompt text, not by the provider's structured-output/function-calling features.

The six endpoints, in increasing order of how much they actually execute versus
just ask the LLM:

- **`POST /chatbot/query-review`** — pure LLM call. Given the question, its
  schema/sample data, and the student's wrong query, returns
  `{problem_token, explanation, hint}` — the single clause/column that's wrong,
  why, and a hint that deliberately never states the correct SQL. Nothing is
  executed to verify this; it's the LLM's read of the query alone.
- **`POST /chatbot/counterexample`** — the most distinctive helper: the LLM
  proposes up to 3 candidate small `INSERT` statements designed to make the
  student's query and the reference query diverge, but **the backend actually
  runs both queries against an isolated in-memory clone of the real database
  with each candidate's rows injected, hashes both result sets, and only
  returns the first candidate that provably causes a real divergence** — never
  one that just sounds plausible. This is "proven, not asserted": one LLM call
  proposes several ideas cheaply, and local execution (each check is
  millisecond-scale) is the actual verifier. Candidates are re-validated through
  `is_permissive_but_safe` before ever being executed, since they're
  LLM-authored SQL running against real infrastructure.
- **`POST /chatbot/contrast`** — asks the LLM for the *minimal single-concept
  edit* to the student's own query (not a rewrite into the reference query) that
  would make it correct, e.g. "swap `WHERE` for `HAVING`". Both the student's
  query and the LLM's corrected variant are then actually executed against the
  real question data, and the response includes a per-row `diff` flag (computed
  locally, not by the LLM) so the frontend can visually highlight exactly which
  rows differ between the two result sets.
- **`POST /chatbot/worked-example`** — not really an LLM-authoring feature at
  all; it's retrieval + rerank. The candidate pool is the student's own
  already-completed questions (via `UserProgress`, most recent 25). The LLM's
  only job is to pick which one of those is conceptually closest to the current
  problem and write a short mapping note — the actual reference material
  returned to the student is **their own past correct query**
  (`Attempt.query`), never anything AI-generated, and never anything about the
  question they're currently stuck on.
- **`POST /chatbot/lab-query-review`** — the lab-context version of
  query-review, but its prompt gives the model one extra job: compare the lab's
  template schema against the student's *current live* (possibly
  self-mutated) schema and the recent query history, and flag if the student
  broke their own environment (dropped a needed table, wiped data) in a way
  that would block the current task — distinct from the review of the query
  itself.
- **Streaming chat** (`POST /chatbot/send`, `/lab-chat`, `/course-chat`) — the
  actual "Bagheera" conversational tutor, `StreamingResponse` token-by-token
  from whichever provider is configured, with persisted history
  (`tutor_chat_conversation`/`_message`) capped to the last
  `TUTOR_CHAT_MEMORY_TURNS` (10) messages fed back as context per turn — not
  the whole conversation, to bound prompt size.

**Every one of these is gated the same two ways**, checked at the top of each
endpoint before any LLM call happens: `question.owner_assessment_id is not None`
(this is assessment content, not bank content) disables *all* AI assistance for
students outright, and `question.hide_correctness` disables specifically the
helpers that would leak correctness (query-review, counterexample, contrast,
worked-example — anything that implies "your query is wrong" or shows a correct
one). Every successful call from the four non-streaming helpers is persisted via
`_persist_query_review` (one shared table, tagged by `problem_token` —
`"counterexample"`/`"contrast"` are used as the token for those two, reusing the
same column rather than adding new ones) so staff analytics can see a student's
full AI-assistance history alongside their query attempts.

---

## 7. Caching layer

`backend/app/core/cache.py` (~380 lines, worth reading in full — it's dense but
short) is an in-process, per-worker read cache for payloads that are identical
across every user of a role: the Problems/Manage Labs/Assessments list pages,
question/lab/ER-question detail views, dashboard counts, course info, the
whitelist lookup on login, and several analytics aggregates. It is explicitly
**not a general-purpose cache** — it is never used for per-user mutable data
(a student's own attempt history, their own progress), which stays live-fetched
everywhere in the app (the frontend mirrors this exact split, §15 point 5). And
it is **not Redis or any external cache** — there is no separate cache process;
each gunicorn worker holds its own in-memory store, and the mechanism described
below exists specifically to keep those independent, unsynchronized in-memory
stores from ever serving data older than the last committed write.

### 7.1 The core mechanism: a DB-stored version counter, not a TTL

Every cacheable payload lives in a per-namespace `OrderedDict[key -> (version,
payload)]` inside the worker process (`_store`, capped at `_LRU_MAXSIZE = 1024`
entries per namespace, evicted LRU). Freshness is decided not by *how long ago*
something was cached (there is no TTL anywhere in this module) but by comparing
its stamped **version number** against a **generation counter stored in the
database**, one row per namespace in a `cache_versions` table:

- **Read** (`cache_read`): look up the namespace's current version with one
  trivial single-row primary-key `SELECT` on the request's *existing* DB session
  (`get_version` — no extra connection-pool checkout). If the cached entry's
  stamped version equals that number, serve it straight from memory, skipping
  the real query and serialization entirely. If it doesn't match (or nothing is
  cached yet), call the caller-supplied `producer()` to compute the real
  payload, store it stamped with the version just read, and return it.
- **Write**: any mutation bumps that namespace's DB row by 1
  (`bump_version`, an atomic `INSERT ... ON CONFLICT DO UPDATE version = version
  + 1`, executed **inside the same transaction as the mutation itself**, before
  `db.commit()`).

Because the version lives in the shared database rather than in any one
worker's memory, **every worker sees the bump on its very next read** — there
is no propagation delay, no pub/sub, no TTL staleness window to reason about.
A worker that served a page a millisecond before a mutation committed elsewhere
will correctly recompute on its very next request after that commit, because
the version number it reads has already moved. This is the entire trick that
lets a cache work correctly across multiple independent worker processes
without Redis: **the source of truth for "is my cached copy still current" is
one cheap read against the same database everything else already talks to.**

A few implementation details worth knowing if you ever touch this file:

- **Read-before-produce ordering matters.** `cache_read` reads the version
  *before* calling `producer()`, not after. If a mutation commits while
  `producer()` is still running, the freshly-computed payload gets stamped with
  the now-stale version it read at the start — so on the *next* read it will
  correctly be treated as stale and recomputed again. It's never served as
  current, it's just briefly wasted work; correctness never depends on timing.
- **Monotonic-version guard against write reordering** (`_put_cached`): if a
  slower thread finishes computing an *older*-versioned payload after a faster
  thread already stored a newer one, the older result is silently dropped
  rather than overwriting the newer entry (`if existing[0] > version: return`).
  Without this, two concurrent requests racing after a mutation could
  leave the cache holding the stale one.
- **Single-flight per (namespace, key)** (`_key_lock`): concurrent misses on
  the exact same key collapse into one `producer()` call instead of a thundering
  herd all recomputing the same expensive query at once — relevant the moment a
  bump invalidates a namespace a whole class is about to hit simultaneously
  (e.g. everyone loading the Problems list right after a staff member publishes
  a question).
- **Fail-open, never fail-closed.** `get_version` returns a sentinel `-1` (not
  0) if the `cache_versions` table doesn't exist yet or the read raises for any
  reason, and `cache_read` treats `version < 0` as "cache subsystem
  unavailable — always run live." The cache can only ever make a correct
  request faster; it can never be the reason a request fails. The same
  philosophy shows up in `bootstrap()`'s `_cache_ready` flag (§7.4): until the
  table is confirmed to exist, the automatic invalidation listener is a no-op
  rather than raising inside a real mutation's flush.

### 7.2 Cache keys: composite tuples, one per distinct payload shape

`key` is a plain tuple the caller builds to uniquely identify *which* variant of
a namespace's data is being requested — the namespace scopes invalidation
(one version counter), the key scopes storage (many independent cached
entries can share that one counter). Real examples from the codebase:

```python
# Question list — one entry per (role × difficulty filter × page), free-text
# search explicitly opts OUT of caching entirely (see below):
cache_read(db, Ns.QUESTIONS,
           key=(f"role={role}", f"diff={difficulty}", f"skip={skip}", f"limit={limit}"),
           producer=producer, cacheable=(search is None))

# Dashboard count — a much smaller key space, same namespace:
cache_read(db, Ns.QUESTIONS, key=("count", role), producer=producer)

# Whitelist lookup on login — keyed by the actual email being checked:
cache_read(db, Ns.WHITELIST, key=("email", email), producer=_lookup_whitelist_entry)

# ER question detail — keyed by id:
cache_read(db, Ns.ER_QUESTIONS, key=("detail", question_id), producer=producer)
```

Two conventions to follow when adding a new cached endpoint:

- **Free-text search bypasses the cache entirely** via the `cacheable=` kwarg
  (`cache_read(..., cacheable=(search is None))`) rather than being included in
  the key. Putting an arbitrary user-typed string into a cache key would let
  the entry count grow unboundedly (and mostly never hit again, since search
  strings are rarely repeated) — cheaper to just skip the cache for that one
  request shape than to cache it badly. Do the same for any future filter whose
  value space is effectively unbounded free text.
- **A namespace can be created lazily, per-id, at runtime** — `assessment_body_ns(id)`
  returns `f"assessment_body:{id}"` and is used for a single running
  assessment's item list, which is heavy to build and identical for every
  student taking that specific assessment, but must never be shared across
  *different* assessments. `get_version` treats a namespace with no
  `cache_versions` row yet as version 0, and `bump_version`'s upsert creates the
  row on first bump — so nothing needs to pre-register a new per-id namespace
  before using it; just pick a naming convention like `<thing>_body:{id}` and
  bump/read it directly.

### 7.3 Automatic invalidation: an `after_flush` listener, mapped by ORM type

You almost never call `bump_version` yourself for a normal ORM write. A
SQLAlchemy `after_flush` event listener (installed once via
`register_invalidation_events()`, called from `bootstrap()` at startup) fires on
every flush — which happens on every `db.commit()` — and inspects
`session.new` / `session.dirty` / `session.deleted` for that flush. Each
changed object is mapped to the namespace(s) it should invalidate by
`_model_namespaces()`, a big `isinstance` chain hand-maintained in `cache.py`
itself (not something each model declares about itself). Some mappings are
direct (`Question` → `Ns.QUESTIONS`); others are *derived*, because a payload in
one namespace displays data that actually lives on a different model — e.g. a
`Question` edit also bumps `Ns.SQL_ANALYTICS` because the analytics view shows
question titles, and `Attempt`/`UserProgress`/`QueryReview`/`TutorChatMessage`/
`User` *all* bump `Ns.SQL_ANALYTICS` too, because that one aggregate is built
from all of them. **If you add a new field to an existing analytics payload
that pulls from a model not already in this chain, you must add that model to
`_model_namespaces()` yourself** — nothing detects "this payload's SQL now
reads from a table this cache doesn't know to watch" automatically; a missed
mapping means that page silently serves stale data after a relevant write.

Manual `bump_version` calls are only needed for two situations, both already
present in the codebase as the pattern to copy:

- **Bulk `update()`/`delete()` calls**, which mutate rows directly in SQL and
  bypass the ORM unit of work entirely — `after_flush` never sees them, so the
  endpoint must call `bump_version(db, Ns.WHATEVER)` itself, before `db.commit()`.
- **Eager cache-warming at a deliberate checkpoint**, rather than waiting for
  the next reader to pay for the recompute. `stop_assessment` and the
  staff-initiated per-student reset (`assessment_reset.py`) both do this: they
  `bump_version(db, Ns.ASSESSMENT_ANALYTICS)` and then *immediately*, in the
  same request, call `assessment_scoring.warm_analytics_cache(db, assessment)`
  to synchronously recompute and repopulate the cache — rather than just
  invalidating and letting whichever staff member opens the analytics page
  first eat the cost. This matters here specifically because "staff opens the
  analytics page right after ending an exam" is a highly predictable,
  near-simultaneous event for a whole class's worth of graders — precomputing
  once beats N staff members racing a cold cache (even with single-flight
  collapsing concurrent misses, the *first* read after a bump is still a full
  live computation; warming skips that for everyone).
- **`Ns.ASSESSMENT_ANALYTICS` is also a deliberate *non*-example worth
  understanding**: a live student's `Attempt`, `LabTaskSubmission`,
  `ErdTutorConversation`, or `AssessmentSession` write does **not** bump it,
  even though those are exactly the writes that happen constantly during a
  running exam. Bumping on every single student answer would force a
  full-cohort recompute after each one — wasted work, since these aggregate
  numbers aren't meant to be shown as "final" until the assessment actually
  ends. Invalidation for this one namespace is deliberately restricted to the
  explicit checkpoints above (stop / reset) plus ordinary `User.class_group`
  edits (an admin action, not something that fires constantly). This is the
  clearest example in the codebase of choosing invalidation triggers by "when
  does this number need to be correct," not "whenever any input to it changes."

### 7.4 Startup bootstrapping and the two aggregates that skip versioning entirely

`bootstrap(engine)` runs once at app startup (`main.py`, after all schema DDL):
idempotently `CREATE TABLE IF NOT EXISTS cache_versions`, seed a version-0 row
for every namespace in `ALL_NAMESPACES` (`INSERT ... ON CONFLICT DO NOTHING`,
safe under concurrent gunicorn workers racing to bootstrap at the same time),
then flip the module-level `_cache_ready` flag and install the `after_flush`
listener. Until `_cache_ready` is `True`, the listener is a deliberate no-op —
this exists so that, on a fresh deploy, a mutation's flush can never try to
bump a namespace before the table backing it is guaranteed to exist (which
would raise mid-flush and, on Postgres, poison the whole transaction the real
mutation was trying to commit).

Two namespaces — `CONCEPT_MASTERY_AGGREGATE` (peer-benchmark class averages,
§6.5) and `RESEARCH_EXPORT` (the cohort research-export summary, §6.6) —
**opt out of the version/invalidation mechanism entirely** and use a
fundamentally different strategy: a **date-stamped cache key**. `lad_service.py`
builds its key as `(class_group or "", date.today().isoformat())` — the
*key itself* changes every day, so there is nothing to invalidate: yesterday's
entry simply becomes unreachable (any read today builds today's key, which is
guaranteed not to exist yet, so it's a normal miss → recompute → cache) and is
eventually evicted by the ordinary LRU cap. This is the right choice here
specifically because both aggregates are expensive, span a half-dozen
high-write tables, and — critically — **don't need to reflect a write that
just happened**: a peer-benchmark average correct as of an hour ago is
completely fine to keep serving for the rest of the day, unlike, say, an
assessment's own item list, which must be correct the instant staff edit it.
If you add a new expensive, cohort-wide, "eventually consistent is fine"
aggregate, prefer this date-stamped-key pattern over wiring up `_model_namespaces`
for a half-dozen tables — it's far less code and there's nothing to keep in
sync as the aggregate's inputs change. Reserve the version-counter mechanism
for payloads that genuinely must reflect the most recent write on the very next
read.

---

## 8. Migrations: the actual workflow

1. Change the SQLAlchemy model in `backend/app/models/`.
2. Write `backend/run_add_<thing>_migration.py` (copy an existing one as a
   template — there are ~30 of them, all idempotent `ALTER TABLE`/`CREATE TABLE`
   wrapped in try/except).
3. Optionally add the equivalent DDL under `backend/migrations/*.sql` for
   reference (not executed automatically).
4. Local dev (SQLite): nothing further needed — `main.py`'s
   `Base.metadata.create_all` picks up new tables, and `main.py` also carries a
   growing list of inline `ALTER TABLE ... ADD COLUMN` statements (wrapped in
   try/except) for columns added to *pre-existing* tables, because `create_all`
   only creates missing tables, not missing columns on ones SQLite already has.
   If you add a column to an existing table, add a matching inline statement in
   `main.py` near the others, or local SQLite databases created before your
   change will be missing it.
5. Production (Postgres): run `python backend/create_tables.py` for a fresh DB,
   or the specific `run_*.py` script(s) for an incremental change, **manually**,
   before deploying code that depends on the new schema. There is no CI step that
   applies migrations automatically.

---

## 9. Deployment topology & CI/CD

- **Backend** → Azure App Service (Python), deployed by
  `.github/workflows/main_fyp-sql-learning.yml` on every push to `main`. Standard
  Oryx build (installs `requirements.txt` server-side).
- **Frontend** → Azure Static Web Apps, deployed by
  `.github/workflows/azure-static-web-apps-zealous-stone-03626e900.yml` on every
  push to `main` (and PR preview builds). **Correction to an earlier draft of
  this document: this is NOT a plain static export**, despite some in-code
  comments (`use-er-draft.ts`) calling it one — `next.config.ts` sets no
  `output: "export"`, `package.json` keeps a `"start": "next start"` script
  (meaningless for static files), and the workflow's `output_location: ""`
  lets Azure auto-detect and deploy it via **Azure Static Web Apps' native
  Next.js hybrid-rendering support** — a real Next.js server runs behind the
  SWA CDN (on Azure's managed compute), not a folder of prebuilt HTML. What
  *is* still true, and universally true for any Next.js build regardless of
  export mode, is that `NEXT_PUBLIC_*` env vars (Google/MS client IDs, API base
  URL) are inlined into the client JS bundle **at build time** — set here in
  the GitHub Actions workflow from repo secrets. Changing one still requires a
  rebuild/redeploy, not just an env var change on the host — the same
  constraint discussed in §5.5 for `ER_MAX_XML_CHARS` — but for a build-time
  reason, not a "there's no server to reconfigure" reason. If you ever need to
  confirm this yourself: a plain static export can't serve a page whose data
  depends on a request header or must run server-only code on each request; if
  any page here relies on that, it's a working, load-bearing sign this is
  hybrid, not static.
- Both pipelines trigger independently on push to `main` — there's no single
  "deploy everything" action. When a change spans both frontend and backend
  (e.g. a new endpoint plus its UI), both will deploy, but not atomically; design
  changes to be backward-compatible for the window between the two deploys
  finishing (the flag-gating pattern in §5.1 already does this for anything
  larger than a small fix).
- CORS origins are hardcoded in `config.py`'s `CORS_ORIGINS` list (localhost dev
  ports + the specific Azure Static Web Apps hostname + the production domain) —
  update this if the SWA hostname or a new environment is added.

---

## 10. Testing

```bash
cd backend
pytest
```

Suite lives in `backend/tests/`, `conftest.py` sets up an isolated test DB.
Notable suites: `test_akela_agents.py` (19 deterministic tests for the LAD's
mastery math and scaffolding transitions — no LLM calls, per §5.2),
`test_assessment_gateway.py` / `test_assessment_analytics.py` (Timing Gateway and
scoring), `test_er_grade_concurrency.py`, `test_gateway_join.py` /
`test_gateway_serialization.py`, `test_platform_usage.py`.

**Not covered by CI**: the ERD LangGraph tutor's own test suite
(`backend/tests/erd_tutor/`, 32 tests) is **gitignored** at the same user request
that gitignored `docs/` — it exists on the original dev machine but is invisible
to `git status` and to any CI runner. If you're picking this project up fresh
from a `git clone`, that test suite does not exist for you; consider whether to
recreate it (the migration handoff doc describes exactly what it covered) or
un-gitignore `backend/tests/` going forward.

Frontend has no test suite at the time of writing — `npm run lint` is the only
automated check (`eslint.config.mjs`).

---

## 11. Known gaps & gotchas

Collected from in-code comments and the ERD migration handoff — worth scanning
before you assume something is a bug versus a known, accepted limitation.

- **`docs/` is `.gitignore`d** (line in `.gitignore`) by a past explicit user
  request, to keep AI-assistant planning artifacts out of version control. This
  means design docs, plans, and one prior comprehensive handoff
  (`docs/erd-langgraph-migration-handoff.md`) exist only on whichever machine
  wrote them and will **not** transfer via `git clone`. If you're the next
  maintainer and that file is missing, it didn't make it into your copy of the
  repo — ask the previous maintainer for it directly, or reconstruct the key
  points, which are summarized in §6.3 above.
- **The prior maintainer's working convention was to never auto-commit** — plans
  and code changes were staged for manual review and commit by hand, including by
  AI coding assistants. If you're an AI assistant reading this: don't assume you
  should `git commit`/`git push` on this repo unless explicitly asked each time.
- **No queue infra** (§5.3) — background agents run via FastAPI `BackgroundTasks`.
  Fine for current class sizes; revisit if enrollment/class-count grows
  substantially (symptom: request latency spikes when a burst of `learning_event`
  writes triggers many background profiling jobs at once).
- **`class_group` is a free-text string**, not a normalized entity (§5.9) — typos
  create silently-broken Timing Gateway windows (a window for `"CZ1XXX"` won't
  match a student whose `class_group` is `"CZ1XXX "` with trailing whitespace, or
  a different casing). No validation currently prevents this.
- **`get_or_create_conversation` race** (ERD tutor persistence, §6.3) — benign
  multi-worker create race, no unique constraint yet.
- **Client disconnect mid-SSE-stream** (ERD tutor, chatbot streaming) — state is
  not persisted if the student closes the tab mid-response; by design, not a bug
  to fix reflexively.
- **Bank-mode ER conversations never expire** — no reset/cleanup mechanism yet.
- **Dify remains a hard dependency** for ER rubric generation regardless of
  `ERD_TUTOR_ENGINE`, and as the ERD tutor's fallback engine — it hasn't been
  fully replaced, only made optional for the tutoring/grading path.
- **`RESTRICTED_USER_EMAILS`** (§5.9) is a narrow patch, not a feature — don't
  grow it into a general permission system without redesigning it as one.
- **Lab task grading trusts the client-reported result set** (§6.7) —
  `POST /labs/tasks/submit` hashes whatever `columns`/`results` the request
  body contains rather than re-running the student's query server-side, unlike
  every other grading path in the app (SQL Questions, Advanced SQL Testing, and
  the lab's own `/execute` step all execute server-side). A student who can
  craft a request body directly (bypassing the UI) could submit a fabricated
  result set that hashes to the correct answer without ever running a query
  that produces it. This has presumably been an accepted risk for a
  low-stakes/practice lab context; revisit before treating lab tasks as
  high-stakes graded content, or fix it by re-executing `submitted_query`
  server-side against the session DB before hashing, matching the Questions
  pattern.

---

## 12. Glossary

| Term | Meaning |
|---|---|
| **Akela** | The platform's name (Jungle Book reference); also used as shorthand for the multi-agent learning-analytics upgrade specifically ("the Akela agents") |
| **Bagheera** | The AI tutor chatbot persona (cosmetic name only) |
| **LAD** | Learning Analytics Dashboard — the student-facing "My Learning" page and its backing agents |
| **SOLO taxonomy** | Structure of Observed Learning Outcomes — an educational framework classifying a student's response complexity; here, an LLM-driven classification per concept, confidence-gated |
| **Scaffolding** | The adaptive-tutor support level for a concept: full → guided → minimal → independent, moved by consecutive success/failure streaks |
| **Concept mastery** | A deterministic 0–1 score per (student, SQL concept), moved by fixed deltas on each attempt |
| **Timing Gateway** | The per-class-group scheduled access window feature for assessments (`AssessmentClassWindow`), distinct from the per-student personal timer |
| **Engine flag** | The `ERD_TUTOR_ENGINE` / `ERD_RUBRIC_ENGINE` (`dify`/`langgraph`) pattern of running two implementations of the same feature side by side, switched by config |
| **`canonical_erd`** | The LangGraph ERD engine's normalized representation of a submitted diagram, persisted so the tutor can reference "what you submitted" in later conversation turns |
| **Cache namespace (`Ns`)** | A row in `cache_versions` — one generation counter per cached, DB-derived payload type (see §7) |

---

## 13. Onboarding checklist

1. Read this document end to end (you just did).
2. Follow `README.md`'s Quick Start to get both servers running locally against
   SQLite — no Postgres or feature flags needed for basic development.
3. Skim `backend/app/config.py` top to bottom — nearly every non-obvious runtime
   behavior in this app is a setting there, usually with a comment explaining why
   it exists and what breaks if it's misconfigured.
4. Run `cd backend && pytest` to confirm the deterministic test suite passes
   before you start changing anything.
5. If your task touches the ERD tutor, also read
   `docs/erd-langgraph-migration-handoff.md` if you have it (§11) — it's denser
   and more current than this document for that one subsystem.
6. If your task is a schema change, follow the migration workflow in §8 exactly —
   both the SQLite inline-`ALTER` path in `main.py` *and* a new `run_*.py` script
   for Postgres, or you'll fix it for yourself locally and break it for everyone
   on Postgres.
7. If your task is a new "intelligent"/AI-adjacent feature, default to the
   patterns in §5.1 (ship dark behind a flag) and §5.2 (deterministic core, LLM
   isolated with a fallback) unless you have a specific reason not to — they're
   the established house style, not incidental choices.

---

## 14. API request/response contracts

Every backend endpoint declares an explicit Pydantic `response_model=`, and
request bodies are always a Pydantic `BaseModel`, never a raw dict. Schemas live
under `backend/app/schemas/`, **one file per feature area** (`attempt.py`,
`question.py`, `lab.py`, `assessment.py`, `er_diagram.py`, ...) — not one file
per endpoint, and not colocated with the endpoint module. When you add an
endpoint, add its request/response classes to the schema file for its feature
area, following the naming already there: `<Thing>Request` /
`<Thing>Response` for a single action, `<Thing>Create` for the input half of a
create operation, `<Thing>Response` (reused) for anything returned that already
has a stable shape.

Two conventions worth internalizing because they recur across almost every
schema in the codebase:

- **`class Config: from_attributes = True`** — lets a response schema be built
  directly from an ORM object (`AttemptResponse.model_validate(attempt_row)` /
  FastAPI does this implicitly via `response_model=`) rather than manually
  unpacking every field. Add it to any new response schema that's meant to wrap
  an ORM row directly.
- **`Optional[X] = None` as a masking mechanism, not just "field may be
  absent"**. Look at `ExecuteResponse.is_correct: Optional[bool] = None` — the
  *real* correctness is always computed and persisted to the `Attempt` row for
  grading, but the field sent back to a student on a `hide_correctness`
  question is `None`, not omitted, so the TypeScript type on the frontend stays
  a stable `boolean | null` rather than an optional key that call sites have to
  guard for. `AttemptResponse.is_correct`, `AttemptHistory.is_correct`, and
  `LabTaskSubmitResponse.is_correct` all follow the identical pattern for the
  identical reason. If you add a new field to a response that should sometimes
  be withheld from students, prefer `Optional[X] = None` over conditionally
  including/excluding the key.

### Worked example: `POST /api/v1/execute`

The full request/response contract for running a SQL Question query
(`backend/app/schemas/attempt.py`), reproduced here as the reference shape for
what a well-formed contract in this codebase looks like:

```python
class ExecuteRequest(BaseModel):
    question_id: int = Field(..., description="Question ID to execute query against")
    query: str = Field(..., min_length=1, description="SQL query to execute")

class ExecuteResponse(BaseModel):
    is_correct: Optional[bool] = None       # None = correctness hidden from this student
    execution_time_ms: float
    results: List[Dict[str, Any]]
    columns: List[str]
    error_message: Optional[str] = None
    row_count: int
    assessment_end_time: Optional[datetime] = None  # credited deadline; None outside a timed assessment
    max_queries: Optional[int] = None                # per-question cap, assessments only
    attempts_used: Optional[int] = None               # None unless max_queries is set
```

Notice `assessment_end_time`, `max_queries`, and `attempts_used` are carried
back on **every** response, not fetched separately — this is the same
"piggyback the answer on a response the client already needed" instinct behind
the no-polling design (§5.4): the frontend never has to make a second request
just to learn its updated countdown or remaining-query count, it reads them off
the response it already has.

### Frontend mirror types have no codegen — they can drift

The frontend hand-maintains a matching TypeScript interface for every schema
above, under `frontend/src/types/*.types.ts` (e.g.
`ExecuteRequest`/`ExecuteResponse` in `attempt.types.ts`). **There is no schema
generation step** (no OpenAPI-to-TS codegen, no shared source of truth) — the
backend Pydantic model and the frontend TypeScript interface are two separate,
manually-synchronized files, and nothing in CI checks that they still agree.
If you change a backend response shape, you must remember to update the
matching frontend type yourself; a mismatch won't be caught until something
breaks at runtime (or not at all, if the drifted field just happens to go
unused). This is a real gap worth closing with a shared/generated type layer if
this project keeps growing — until then, treat "update both sides together" as
a hard rule for every endpoint change.

---

## 15. Frontend wiring — from endpoint to component, worked example

Using the SQL Questions workspace (`frontend/src/components/workspace/SqlWorkspace.tsx`,
the component behind both `/student/workspace` and the assessment item view) as
the concrete trace, because it exercises every wiring pattern this codebase
uses:

1. **`config/api.config.ts`** — the single place every backend path string is
   defined (`API_BASE_URL`, `API_ENDPOINTS.EXECUTE.BASE`, etc.). Services import
   from here; nothing hardcodes a `/api/v1/...` string inline. Add a new path
   here first when wiring up a new endpoint.
2. **`services/api.service.ts`** — one shared `axios` instance every
   `*.service.ts` file imports, with two interceptors that make it more than a
   thin wrapper:
   - *Request*: injects `Authorization: Bearer <token>` from `localStorage` on
     every call — the one place JWT attachment happens, so individual services
     never touch the token.
   - *Response*: on **every successful authenticated call**, lazily imports
     `loginActivityService` and pings a throttled "record activity" call — this
     is how the platform's presence/activity tracking gets its data from normal
     usage instead of a polling timer (ties directly back to §5.4.1: the
     interceptor piggybacks on requests the app was making anyway). It also
     centralizes two pieces of cross-cutting error handling: a `401` triggers a
     global logout + redirect to `/login` (except on the SSO login calls
     themselves, where a `401` means "this token was rejected," a normal login
     failure the caller needs to display, not an expired-session logout); and a
     `"Assessment has ended."` / `"No active session to submit"` error `detail`
     string — which can arrive from *any* assessment-related call — triggers a
     redirect back to the student's assessment list, so a student is never left
     stranded on a dead question page after their session was finalized
     server-side (by staff Stop, timer expiry, or an already-submitted
     session).
3. **`services/execute.service.ts`** — the thinnest possible layer: one async
   function per endpoint, typed with the frontend mirror of the backend schema
   (§14), no branching logic:
   ```ts
   export const executeService = {
     async executeQuery(request: ExecuteRequest): Promise<ExecuteResponse> {
       const response = await api.post<ExecuteResponse>(API_ENDPOINTS.EXECUTE.BASE, request);
       return response.data;
     },
   };
   ```
   Every `services/*.service.ts` file follows this same shape — components
   never call `axios`/`api` directly, always through a named service function.
4. **`services/query-keys.ts`** — a single factory of TanStack Query cache-key
   builders (`queryKeys.questionById(id)`, `queryKeys.studentProgress`, ...).
   Anything that reads a cached value and anything that invalidates it imports
   the key from here, so the two can never drift into using different key
   shapes for the same logical data.
5. **Inside the component, three different data-loading shapes coexist,
   deliberately, for three different kinds of data:**
   - **Static/cacheable** (the question's text, schema, sample data — doesn't
     change while the student is working on it): `useQuery({ queryKey:
     queryKeys.questionById(questionId), queryFn: () =>
     questionService.getQuestionById(questionId) })`. The comment in the code
     is explicit about why: *"cached ... so revisiting this question (e.g.
     switching between assessment items) renders it instantly."*
   - **Live session state that must never be stale** (the student's attempt
     history): a plain `useEffect` that calls `attemptService.getQuestionAttempts`
     directly into local `useState`, deliberately **bypassing** TanStack
     Query's cache — the comment again states the reasoning: *"Attempts are
     live session state (not cached): fetch on mount so a revisit always shows
     the student's latest history."* This is not an oversight or an
     inconsistency with pattern #1 above; it's a considered choice per data
     type.
   - **The mutating action** (clicking Run): **not** `useMutation` — a
     hand-written `async` handler (`handleExecute`) that guards against
     double-submission and an active cooldown, calls `executeService.executeQuery`
     directly, writes the response into local `useState` (`setResult`), shows a
     Mantine `notifications.show(...)` toast keyed off `response.is_correct`
     (three-way: `null` → neutral "Submitted", `true` → "Correct!", `false` →
     no toast, the wrong-answer UI state speaks for itself), and then explicitly
     calls `queryClient.invalidateQueries({ queryKey: queryKeys.studentProgress })`
     and `queryClient.invalidateQueries({ queryKey: ['studentQuestions'] })` —
     because this mutation just changed data that *other, cached* queries
     elsewhere in the app (the student dashboard) depend on, and TanStack Query
     has no way to know that on its own. **This hand-rolled-handler-plus-manual-
     invalidation shape is the established mutation pattern in this codebase,
     not `useMutation`** — follow it for consistency when wiring up a new
     mutating action, rather than introducing `useMutation` into an area that
     doesn't already use it.
6. **Client-side throttling is layered on top of, and independent from, the
   server-side cap.** `useRunCooldown` enforces a purely client-side,
   `sessionStorage`-persisted cooldown between Run clicks — a tiered schedule
   outside assessments (10 free runs, then 5s cooldown) and a fixed
   progressive schedule inside them. This exists to keep the UI/UX pleasant
   (stop a student mashing Run) and is **entirely separate** from the server's
   `max_queries` cap enforced in `execute.py` (§6.7), which exists to bound how
   many *graded* attempts a student gets on a specific assessment question.
   Removing or loosening one does not affect the other — they answer different
   questions ("is this student clicking too fast" vs "has this student used up
   their allotted attempts") and both need to be considered separately if
   either is ever changed.
7. **The assessment countdown timer is paused and resumed around the request**,
   not re-fetched: `timer.pause()` is called immediately before `await
   executeService.executeQuery(...)`, and the response's `assessment_end_time`
   (credited server-side, §6.7) is what `timer.resume()` uses to pick the
   countdown back up — a second concrete instance of the no-polling,
   piggyback-on-the-response pattern from §5.4/§5.4.1, not a coincidence.

If you're wiring up a brand-new endpoint end to end, replicate steps 1–4
exactly regardless of the feature, then pick the right shape from step 5 for
the *kind* of data you're loading (static-cacheable vs. always-live
vs. a mutating action) rather than defaulting to one pattern everywhere.
