# Database Rescue

Database Rescue is a mission-only SQL debugging competition. Students join and open independent incidents in any order; there are no pre-tests or post-tests. Competition runs and points are separate from ordinary SQL practice attempts and mastery.

## Preview the presentation examples locally

The disposable demo uses the real Competition APIs with a temporary database. It includes the two requested examples from **Presentation slides 22.10.26.pptx**, slides 5–8:

| Incident                | Difficulty | Points | Fault                                                                |
| ----------------------- | ---------- | ------ | -------------------------------------------------------------------- |
| Empty student directory | Easy       | 10     | Student ID used instead of department ID in the join                 |
| Missing residents       | Medium     | 20     | Ticket-status filter in WHERE removes residents with no open tickets |

Visible records, complaints, SQL and expected behaviour follow the presentation. Each incident also has three private fixtures covering additional IDs, shared names, multiple matches, zero counts and empty data. Repairs are compared by output; equivalent SQL can pass. Reference SQL and private expected rows stay on the backend.

From the repository root, start the demo backend in PowerShell:

```powershell
.\.venv\Scripts\python.exe backend\competition_tests\browser_server.py
```

In a second terminal:

```powershell
cd frontend
$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8017/api/v1"
$env:NEXT_PUBLIC_MICROSOFT_CLIENT_ID="00000000-0000-0000-0000-000000000001"
$env:NEXT_PUBLIC_GOOGLE_CLIENT_ID="competition-local-preview"
npm.cmd run dev -- --hostname 127.0.0.1 --port 3017
```

Open **http://127.0.0.1:3017/login**. This preview uses local demo accounts; the Google/Microsoft buttons need real OAuth credentials and do not work with the placeholder IDs above. In this local page's browser developer console, run:

```javascript
{
  const role = "student"; // Change to "staff" for management.
  const response = await fetch(`http://127.0.0.1:8017/test-token/${role}`);
  if (!response.ok) throw new Error("Demo sign-in failed");
  const { token } = await response.json();
  localStorage.setItem("access_token", token);
  location.href =
    role === "staff" ? "/admin/competitions" : "/student/competitions";
}
```

The token endpoint exists only in this loopback demo server. Other application sections require the full backend. Stop either server with Ctrl+C. **Restart the demo backend after changing its packaged examples; all demo work resets on restart.** Development frontend changes refresh automatically.

## Enable and prepare a real cohort

1. Install backend requirements and run `python run_competition_migration.py` from `backend/` against the intended existing metadata database. This adds the 13 Competition tables without resetting application data. Local SQLite app startup also creates missing tables. **Do not run the legacy `create_tables.py` for an upgrade; it contains destructive reset logic.**
2. Configure a private persistent `COMPETITION_DB_PATH`, accessible to all serving workers. Back up the metadata database and preserve fixture storage. Metadata also stores schema/seed manifests to rebuild missing fixture files.
3. Use the full application's normal API URL, CORS and SSO configuration. Sign in as staff/admin and open **Competition**. Staff authoring works while `COMPETITIONS_ENABLED=False`.
4. Open **Question sources → Create an incident**. Choose **Question bank**, select an existing exercise and fault template, enter the complaint/requirements, confirm source permission and click **Create incident draft**. The application imports a source copy and adds the fault automatically. For file-based exercises, use the optional JSON upload and select **Uploaded or previously imported sources**. To author your own exercise, choose **Create from scratch** and click **Create incident draft** to open an editable example; define the schema, faulty/reference SQL, datasets and expected outputs in the editor. **Incident library** is for viewing, editing, validating and approving created incidents; all creation starts under Question sources. The former Prepare starter drafts button and API have been removed; existing incidents are preserved.
5. Review source permission, complaints, business rules, difficulty, SQL and explicit expected outputs. Use the **I have reviewed the expected outputs and business rules** checkbox; no JSON review flag needs editing. Source permission loads from the saved source and can be saved separately or as part of approval. **Approve immutable version** saves changes, validates all scenarios and approves only if all checks pass. Progress/errors appear beside the action. Editing the definition clears the review checkbox. Automatically adapted sources start with duplicate scenario placeholders: replace those with distinct witness/boundary records before approval.
6. Assemble approved incidents into a topic competition. Any mix of difficulties is allowed, including Easy/Medium only. Select the class groups, participation window, answer points and leaderboard tie rule. Publication rejects reused incident identities/schemas and freezes content/scoring.
7. Publish, set `COMPETITIONS_ENABLED=True` and restart the backend. The authenticated capability endpoint makes the student Competition tab visible without a frontend build flag.

Published definitions remain frozen; source/draft edits do not alter running competitions. Update the access window to reopen retained work. Existing databases retain legacy test columns and records without deletion, but those tests are no longer accessible or required. Historical point values for existing published missions remain frozen.

## Approval and source handling

The working definition JSON omits the internal `oracle_confirmed` field. The expected-output review checkbox records it automatically when saving, previewing, validating or approving. Saved confirmation and source authorisation are restored after refresh. An unchecked review or source-permission checkbox gives an actionable message when approval is attempted; the button is no longer silently disabled for these prerequisites. Successful approval invalidates incident/version caches and links to the competition builder. **Refresh incidents** also reloads the selection list, including versions approved in another browser tab.

Source copying and fault adaptation remain separate backend operations to preserve the original question and record provenance. The admin performs them in one form/action for bank questions. Uploaded sources use the same fault/complaint controls. Source diagnostics remain available for exercises that cannot be parsed or do not support the selected fault.

## Student flow and scoring

Join → open a complaint → inspect records and SQL → submit an answer → output checks → feature restoration and points. All required incidents stay accessible in any order.

The presentation examples use **Correct / Incorrect**, an editable SQL query and a **Short explanation**, matching the slides. An incorrect verdict requires a repair attempt. A correct verdict judges the original query. There is no extra mandatory investigation-run or multi-field report for these single-query examples. Both supplied examples contain semantic faults; a correct repair paired with the wrong verdict does not earn points.

Bank adaptations can retain the fuller investigation report: a recorded run, evidence, selected component/cause, repair SQL and consequence explanation. Drafts autosave with revisions; stale writes return a conflict. Submitted reports are immutable snapshots. Submit again to include later edits.

Participation completes automatically once every required incident has a nonempty submitted answer, independently of correctness, points, judging availability or speed. Saving drafts and running/checking SQL do not count as submissions. The optional feedback survey then becomes available.

New competitions default to **10/20/30 answer points for Easy/Medium/Hard**, awarded once per restored incident. No points are awarded simply for submitting. Checkpoints do not reduce points. Default ranking is answer points descending, then elapsed time from joining to the first accepted successful report for the most recently restored incident. Repeat submissions and technical judging delays do not change that incident's award/time. Staff may disable the time tie rule so equal points share rank. A topic badge requires two restored incidents, including a medium/hard incident.

A judging failure retains the accepted answer and participation credit. Retrying its idempotency key, or staff selecting **Retry retained judgement**, rejudges the frozen report even after closing. Points are granted only after successful judging, once.

Staff can record audited diagnosis/explanation rubric scores and export participation, latest mission outcomes (including missing answers), submissions, events, runs and survey responses. Configure `RESEARCH_EXPORT_SALT` for pseudonymous exports; existing staff/test-group exclusions apply. Narrative and SQL exports remain restricted research data.

## Authoring and execution contracts

- Source imports retain original content/hash, identity, parser version and diagnostics. The serving backend creates fixture files.
- The canonical dialect is SQLite, using pinned SQLGlot 30.25.0. Supported generated AST mutations are LEFT→INNER, DISTINCT removal, EXISTS inversion and nullable COUNT. Curated incidents also use wrong join keys, reversed comparisons and WHERE filters on LEFT JOINs.
- Definitions contain 1–4 components, exactly one private culprit, one visible scenario and 2–5 hidden scenarios. A verdict-style incident has one component. Every scenario has explicit expected columns and positional rows. NULL, duplicates, exact whitespace, ordering and numeric tolerance are handled explicitly.
- Validation runs reference and initial SQL against all scenarios. References must match reviewed outputs. Faulty SQL must execute and reproduce the visible complaint; healthy components must remain correct. Distinct fixtures and registered templates are required. Finite tests check fixture coverage, not mathematical SQL equivalence.
- Limits: 20,000 SQL characters, 200 preview rows, 2,000 judged rows, 1 MB output, 5 seconds/query and 15 seconds/overall judging. Each table has at most 2,000 fixture rows. Queries are single read-only SELECTs with an authorizer and deadline; writes, attachments, extensions and randomness are blocked.
- Public responses use an explicit allow list. References, source metadata, private culprit annotations, hidden data and expected outputs are never bundled with student pages.
- Immutable incident artifacts pin source identity/hash and parser version; competition hashes pin selected versions and scoring. Client-provided results and points are never trusted.

## Source utilities

Run imports from `backend/`:

```text
python scripts/prepare_competition_sources.py ../leetcode_questions.json --dry-run
python scripts/prepare_competition_sources.py ../leetcode_questions.json --authorised --api http://localhost:8000/api/v1
```

Writes require a real staff token in `AKELA_ADMIN_TOKEN` and run in idempotent batches. The default API URL is local. From the repository root, `backend/scripts/build_competition_pilot.py` rebuilds bank drafts, and `backend/scripts/build_competition_slides.py` rebuilds the presentation manifest with explicit expected rows. These are offline development utilities; they do not add a starter-draft action to the admin interface or approve generated content.

## Verification

```text
python -m pytest backend/competition_tests -q
cd frontend
npx tsc --noEmit
npx eslint src/components/competition src/app/student/competitions src/app/admin/competitions src/services/competition.service.ts src/types/competition.types.ts
npm run build
npm run test:competition
```

Browser tests need a build with `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8017/api/v1`, dummy public SSO IDs and installed Chrome (or `PLAYWRIGHT_CHANNEL=chromium`). Set `RESCUE_TEST_PYTHON` to a Python executable with backend dependencies when needed. Playwright starts disposable servers on 8017/3017. If your preview occupies those ports, set `RESCUE_TEST_API_PORT` and `RESCUE_TEST_WEB_PORT` to free ports and build with the matching public API URL.

Browser tests cover direct mission access, the presentation examples, editing/previewing/checking/submitting SQL, autosave/resume, 10/20 points, completion, staff setup and mobile layout. The GitHub workflow runs SQLite/PostgreSQL backend tests plus frontend checks. Local PostgreSQL tests require `COMPETITION_TEST_DATABASE_URL` with a database name ending in `_test`; each test uses its own disposable schema. A local PostgreSQL server was unavailable during implementation.

Tests live in `backend/competition_tests/` because this repository ignores `backend/tests/`. Existing broader lint/test debt is outside the targeted checks. Google Fonts remain an existing build-time network dependency.

## To run locally

1. Start the backend in a PowerShell terminal:

```powershell
cd "C:\1. NTU\FYP\FYP-Project-Version-1"
.\.venv\Scripts\python.exe backend\competition_tests\browser_server.py
```

2. Start the frontend in another PowerShell terminal:

```powershell
cd "C:\1. NTU\FYP\FYP-Project-Version-1\frontend"

$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8017/api/v1"
$env:NEXT_PUBLIC_MICROSOFT_CLIENT_ID="00000000-0000-0000-0000-000000000001"
$env:NEXT_PUBLIC_GOOGLE_CLIENT_ID="competition-local-preview"

npm.cmd run dev -- --hostname 127.0.0.1 --port 3017
```

### To login as test student

1. Return to http://127.0.0.1:3017/login.
2. Right click page, select inspect, select console, paste this into console:

```
{
  const role = "student";
  const response = await fetch(
    `http://127.0.0.1:8017/test-token/${role}`
  );

  if (!response.ok) throw new Error("Demo backend sign-in failed");

  const { token } = await response.json();
  localStorage.setItem("access_token", token);

  window.location.href = role === "staff"
    ? "/admin/competitions"
    : "/student/competitions";
}
```

### To login as test admin

1. Return to http://127.0.0.1:3017/login.
2. Right click page, select inspect, select console, paste this into console:
   {
   const response = await fetch(
   "http://127.0.0.1:8017/test-token/staff"
   );
   if (!response.ok) throw new Error("Demo sign-in failed");

const { token } = await response.json();
localStorage.setItem("access_token", token);
window.location.href = "/admin/competitions";
}
