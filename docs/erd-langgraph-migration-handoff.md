# ERD Tutor: Dify → LangGraph Migration — Handoff Document

> **Purpose**: resume-anywhere summary of the migration work done on branch
> `feat/erd-langgraph-migration` (sessions of 2026-07-14/15). Written for agents
> or developers with no access to the original session.
>
> **NOTE**: `docs/` is gitignored (user request), so this file lives only on
> this machine. The 32-test suite under `backend/tests/erd_tutor/` is likewise
> gitignored but present on disk.

## 1. What this work is

The "V3 Database ER Diagram Peer Tutor" (a hosted Dify chatflow, source YAML at
`C:\Users\James\Desktop\Stuff\School\Y3S2\FYP\V3 Database ER Diagram Peer tutor.yml`)
was ported to a local LangGraph engine at `backend/app/services/erd_tutor/`.
It grades student ER diagrams (Submit mode) and tutors them Socratically
(Query mode), with Inquiry-Based-Learning state (stage + hint level 1-4).

Engine selection: `settings.ERD_TUTOR_ENGINE` — `"dify"` (default, legacy
hosted path, byte-for-byte unchanged) or `"langgraph"` (new local engine).
Rollback is instant via the env var.

## 2. Git state — READ THIS FIRST

- **Branch**: `feat/erd-langgraph-migration` (tracks nothing; main = de9f78c).
- **NOTHING IS COMMITTED YET.** ~26 files are **staged** and waiting; the user
  (James) tests manually and **commits himself — never run `git commit` for him**
  (also recorded in agent memory: feedback_no_auto_commit).
- `stash@{0}` (`!!GitHub_Desktop<feat/erd-langgraph-migration>`) still exists —
  it was the original home of this work (the branch had zero commits; the code
  lived only in that GitHub Desktop auto-stash). It was `git stash apply`d
  (not popped). Safe to drop only after the user's commit is verified.
- Staged: `backend/app/services/erd_tutor/**`, `backend/app/models/erd_tutor_*`,
  `backend/app/models/__init__.py`, `backend/app/api/v1/endpoints/er_diagram.py`,
  `backend/app/services/er_grading.py`, `backend/app/config.py`,
  `backend/requirements.txt`, `backend/migrations/add_erd_tutor_tables.sql`,
  `backend/run_erd_tutor_migration.py`, `.gitignore`, and 5 frontend files
  (`api.config.ts`, `er-diagram.types.ts`, `er-diagram.service.ts`,
  `ChatPanel.tsx`, `ERDiagramWorkspace.tsx`).
- **Deliberately NOT staged** (unrelated Google-login work, leave alone):
  `backend/app/api/v1/endpoints/auth.py`, `frontend/src/components/auth/LoginForm.tsx`,
  `frontend/src/services/auth.service.ts`. Also untracked junk: `.codex/`,
  `.lavish/`, `.understand-anything/` (first two gitignored).
- Gitignored at user request: `backend/tests/`, `docs/`, `.lavish/`,
  `.understand-anything/`, `frontend/.npm-cache/`.

## 3. Architecture (after this work)

```
POST /api/v1/er-diagram/submission  (bank: question_id | lab: er_lab_id+er_lab_question_id)
  mode=Submit ─ engine=langgraph → runner.stream_er_submission_grading
  │                → submit_graph: observe → normalize → grade → score(SSE done)
  mode=Query  ─ engine=langgraph → runner.stream_er_query
  │                → query_graph: tutor → state_update
  └─ engine=dify → legacy hosted Dify (unchanged)

Conversation state (langgraph only): erd_tutor_conversations (snapshot) +
erd_tutor_messages (transcript). Persistence happens via the SSE overlay
_stream_with_erd_tutor_state in er_diagram.py after the `done` event.

GET /api/v1/er-diagram/conversation?question_id=N  (or er_lab_id+er_lab_question_id)
  → read-only transcript+state fetch; frontend restores chat log on mount.
```

Key files (all under `backend/app/services/erd_tutor/` unless noted):

| File | Role |
|---|---|
| `llm.py` | Stage→deployment map + client factory. **Uses Azure's unified v1 API surface** (`ChatOpenAI` with `base_url={endpoint}/openai/v1`, Bearer auth) — see §5. `max_retries=3`, grade uses `model_kwargs={"max_completion_tokens": 2000}` |
| `prompts.py` | Verbatim prompt port from the Dify DSL (leaked `{{#…#}}` placeholders cleaned; TUTOR_USER extended with `{current_erd_model}` + `{last_submit_feedback}`) |
| `nodes.py` | observe/normalize/grade/tutor/state_update node functions |
| `schemas.py` | Pydantic mirrors of the DSL structured-output schemas |
| `scoring.py` | Deterministic score calc (port of Dify code node). Decodes prev `checks` JSON string so progress improvements/regressions work |
| `submit_graph.py`, `query_graph.py` | StateGraph wiring |
| `runner.py` | SSE entrypoints; emits `canonical_erd` alongside `done`; MIME-sniffs image data URLs |
| `persistence.py` | `find_conversation` (read-only) / `get_or_create_conversation` / `loaded_state` / `save_state` / `append_message` / `transcript` |
| `../er_grading.py` | Engine dispatch (`stream_er_submission_grading`); materializes `image_bytes` from UploadFile for langgraph |
| `../../api/v1/endpoints/er_diagram.py` | Both submission branches (bank + lab), the persistence overlay, and `GET /conversation` |
| `../../models/erd_tutor_conversation.py`, `erd_tutor_message.py` | ORM models |
| `backend/run_erd_tutor_migration.py` | Dialect-agnostic table creation via `Base.metadata.create_all` (SQL file is Postgres reference DDL) |

Conversation scoping: bank = `(user_id, er_diagram_question_id)` context_type
`standalone`, persists indefinitely; lab = `(user_id, er_lab_question_id,
session_id)` context_type `lab`, fresh per lab session.

## 4. Everything fixed in these sessions (chronological)

Original review findings (all fixed):
- **F0** stash rescue + selective staging.
- **F1** Query mode wired to LangGraph with state persistence (was dead code; Dify got all queries stateless).
- **F2** tutor stage → `AZURE_OPENAI_TUTOR_DEPLOYMENT` (gpt-5.4-nano), was wrongly the full gpt-5.4.
- **F3** `max_tokens` → `max_completion_tokens` (gpt-5.x rejects the former).
- **F4** literal Dify placeholders removed from OBSERVE_SYSTEM / NORMALIZE_SYSTEM / TUTOR_USER.
- **F5** progress comparison fixed (prev report's `checks` is a JSON string; now decoded).
- **F6** migration made Postgres-compatible (create_all; SQL file = Postgres DDL).
- **F7** `max_retries=3` restored (DSL parity).
- **F8** unused `submission_xml` state field renamed `submission_description` (WIP input, no node reads it yet).

Live-testing fixes (found with real Azure calls):
- **Azure v1-only resource**: the user's Azure OpenAI resource rejects ALL dated
  api-versions ("API version not supported"). `AzureChatOpenAI` cannot be used.
  Fix: `ChatOpenAI` against `{endpoint}/openai/v1` (deployment name as `model`,
  Bearer auth, no api-version). Verified live on all three deployments.
- **Bank-mode image loss**: bank route passed `erd_img` (UploadFile) but the
  runner only reads `image_bytes` → vision stage ran imageless → "empty ERD"
  grades. Fixed in er_grading dispatch (reads bytes; seek(0) first).
- **MIME sniffing** in `runner._image_b64` (was hardcoded image/png).
- **UnboundLocalError** on `stream_er_submission_grading`: a function-local
  re-import in the lab branch shadowed the module-level name for the whole
  function, 500ing the new bank branch (browser showed it as CORS). Fixed by
  removing the local import — comment in place warns against reintroducing it.
- **Submission↔query context disconnect** ("the tutor doesn't know what I
  submitted"): submit now persists `canonical_erd` → `current_erd_model` (only
  when non-empty, so failed parses don't clobber); tutor prompt receives the
  ERD model + compact last-submit feedback; bank mode got standalone
  conversations (was lab-only).
- **Transcript endpoint + frontend restore**: `GET /er-diagram/conversation` +
  ChatPanel `historyMessages` prop + fetch-on-mount in ERDiagramWorkspace, so
  the chat log survives page reloads (history renders unanimated after the
  greeting; best-effort, never blocks the workspace).

## 5. Environment & running locally

`backend/.env` (user's real values are in place, not committed):
```
ERD_TUTOR_ENGINE=langgraph            # dify = legacy/rollback
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<key>
# deployment names default to gpt-5.4 / gpt-5.4-mini / gpt-5.4-nano and MATCH
# the user's Azure deployments (confirmed via portal screenshot).
# AZURE_OPENAI_API_VERSION is now UNUSED (v1 surface has no api-version).
```

- Local DB is SQLite (`sqlite:///./sql_learning.db`); `main.py` auto-creates
  the erd_tutor tables on startup for SQLite (models are registered in
  `app/models/__init__.py`). Postgres needs `python backend/run_erd_tutor_migration.py` once.
- Dev servers: `.claude/launch.json` defines `backend` (uvicorn :8000, --reload)
  and `frontend` (next dev :3000). Beware reload races: a request landing during
  a WatchFiles restart hits the old code — restart cleanly after edits.
- Deps were installed with `python -m pip install --user` (system Python 3.12;
  plain `pip` points elsewhere and system site-packages needs elevation).
- Tests: `cd backend && python -m pytest tests/erd_tutor` → **32 passed** as of
  handoff. `test_config.py` uses `Settings(_env_file=None)` to isolate from .env.

## 6. Verification status

Confirmed working live (by the user, gpt-5.4* deployments, real images):
- Bank submit via image upload and via draw.io export (vision extraction
  produces correct entities/relationships/attributes).
- Query mode answers.
- All three Azure deployments respond on the v1 surface.

Not yet user-verified at handoff:
- Submission→query context (tutor referencing the persisted ERD) end-to-end in
  the browser after the wiring — code-complete, tests pass.
- Frontend transcript restore after reload — code-complete, tsc clean; a
  Fast-Refresh-only "deps array changed size" console error was explained
  (hot-swap artifact; impossible after a hard reload).
- Lab-mode submit/query/second-submit sequence.
- Progress improvements/regressions across two submits in the UI.

## 7. Production checklist (discussed with user)

1. **Run the migration on Postgres/Supabase manually** — `main.py` only
   auto-creates tables for SQLite. Do this BEFORE flipping the engine flag.
2. Set env vars in prod; deploy dark (flag still `dify`), then flip.
3. SSE responses run 30–90 s — check reverse-proxy idle timeouts.
4. Each submit ≈ threadpool thread held for the LLM duration; watch concurrency
   for class-sized labs; Azure TPM quotas can 429 under burst.
5. `get_or_create_conversation` has a multi-worker create race (no unique
   constraint) — benign but a unique index would close it.
6. Client disconnect mid-stream = state not persisted (by design).
7. Bank conversations never expire; no reset mechanism yet.
8. Tests are gitignored → CI cannot run them. Reconsider before serious deploys.

## 8. Known gaps / natural next steps

- `submission_description` is a plumbed-but-unused WIP input; XML-only submits
  still grade nothing real (pre-existing Dify gap; plan post-migration).
- Tutor has no chat-history replay (memory = state snapshot only; transcript
  exists in DB and could be fed in).
- No "reset conversation" control for students.
- Lab transcript restore only works while the same lab session is active.
- Dify remains required for rubric generation and as the fallback engine.
- Ported-as-is Dify quirks (intentional): OBSERVE_USER reads like the stage-2
  prompt; STATE_USER repeats the tutor reply twice.

## 9. Artifacts from the review session

- Interactive review page (local only, gitignored): `.lavish/erd-langgraph-migration-review.html`.
- Original design doc + plan: `docs/superpowers/specs/2026-06-30-erd-langgraph-migration-design.md`,
  `docs/superpowers/plans/2026-06-30-erd-langgraph-migration.md`.
- Parity harness (opt-in, needs real creds): `backend/tests/erd_tutor/parity/run_parity.py`.
