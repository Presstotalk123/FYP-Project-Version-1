# Akela — SQL Learning Platform

A web-based platform for teaching and practising SQL and database design. Teachers author practice questions, hands-on labs, ER-diagram exercises and timed assessments; students solve them interactively with instant feedback, an adaptive AI tutor, and a personal learning-analytics dashboard.

Production: [ntuakela.net](https://ntuakela.net)

## Features

- **SQL Questions** — author and solve SQL practice problems against per-question SQLite databases, with automatic correctness grading and an AI query-review assistant.
- **SQL Labs** — multi-task, session-based lab environments where students run queries against a shared schema.
- **ER Diagram exercises** — draw.io-based entity-relationship modelling questions, graded by a rubric-driven grader with an interactive AI ERD tutor (LangGraph engine).
- **Assessments** — timed, optionally password-gated assessments with per-class scheduling windows and a timing gateway; scoring uses each student's best attempt.
- **AI Tutor ("Bagheera")** — a streaming chatbot that helps students with questions and labs, with an optional adaptive mode driven by concept mastery and scaffolding.
- **Learning Analytics Dashboard (LAD)** — per-student concept mastery, SOLO-taxonomy classification, and anonymized peer benchmarking. Ships behind feature flags (see [Feature flags](#feature-flags)).
- **Admin & analytics** — question/lab/assessment management, user whitelisting, login-activity and presence tracking, cohort analytics, and an anonymized research CSV export.
- **Auth** — JWT sessions with Google and Microsoft (Azure Entra ID) SSO, plus role-based access (student / staff).

## Technology Stack

**Backend**
- FastAPI (Python)
- SQLAlchemy 2.0 + Alembic
- PostgreSQL (production) / SQLite (development)
- LangGraph + LangChain (ERD tutor & rubric engines)
- OpenAI / Azure OpenAI
- JWT auth, Google & Microsoft SSO

**Frontend**
- Next.js 16 + React 19 + TypeScript
- Mantine 8 (UI)
- Monaco Editor (SQL editing)
- TanStack Query (data fetching)
- CASL (permissions), dnd-kit, dagre (graph layout)

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/   # Route handlers (auth, questions, labs, assessments, chatbot, LAD, …)
│   │   ├── core/               # Grading, query execution, security, cache
│   │   ├── models/             # SQLAlchemy models
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── services/           # ERD tutor/rubric, learning analytics, tutor chat
│   │   ├── utils/              # DB managers, storage helpers
│   │   ├── config.py           # Settings (env-driven)
│   │   └── main.py             # App entrypoint + router wiring
│   ├── migrations/             # run_*.py migration scripts (PostgreSQL)
│   ├── tests/
│   └── requirements.txt
├── frontend/                   # Next.js app (src/)
└── docs/                       # Design docs & handoffs
```

## Quick Start

### Backend

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # macOS/Linux
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   ```bash
   cp .env.example .env
   # then edit .env — at minimum set SECRET_KEY (openssl rand -hex 32)
   ```
   See [Configuration](#configuration) for the full list.

5. Run the development server (SQLite tables are auto-created on first run):
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

6. Access the API:
   - API: http://localhost:8000
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

> **PostgreSQL note:** tables are auto-created only for SQLite. For PostgreSQL, pre-create the schema with `python create_tables.py` and apply the relevant `run_*.py` migration scripts before starting the server.

### Frontend

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Run the development server:
   ```bash
   npm run dev
   ```
   The app runs at http://localhost:3000 and expects the backend at http://localhost:8000.

## Configuration

Backend settings are loaded from `backend/.env` (see `backend/.env.example`). Key variables:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | `sqlite:///./sql_learning.db` (dev) or a PostgreSQL URL (prod) |
| `SECRET_KEY` | JWT signing secret — **required** (`openssl rand -hex 32`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT lifetime |
| `GOOGLE_CLIENT_ID` | Google SSO client ID |
| `MICROSOFT_CLIENT_ID` / `MICROSOFT_TENANT_ID` | Microsoft (Azure Entra ID) SSO |
| `AI_PROVIDER` / `AI_API_KEY` / `AI_MODEL` | AI query-review provider (`azure_openai` \| `openai` \| `gemini`) |
| `AI_AZURE_ENDPOINT` / `AI_AZURE_API_VERSION` | Azure OpenAI endpoint config |
| `ERD_TUTOR_ENGINE` / `ERD_RUBRIC_ENGINE` | ERD engine selector (`dify` legacy \| `langgraph`) |
| `ERD_AZURE_OPENAI_*` | Azure OpenAI config for the LangGraph ERD engines |
| `ER_STORAGE_PROVIDER` | ER model-answer storage (`local` \| Azure Blob) |
| `RESEARCH_EXPORT_SALT` | HMAC salt for anonymizing the research CSV export |

See `backend/app/config.py` for the complete, documented list of settings and their defaults.

### Feature flags

The Akela multi-agent learning-analytics platform ships **dark** behind two independent flags (both default `False`):

- `AKELA_AGENTS_ENABLED` — master switch for learning-event logging and the background Learner Profiling / SOLO Classifier agents.
- `SQL_TUTOR_ADAPTIVE` — enables adaptive prompt construction (mastery/scaffolding) in the SQL chatbot.

On PostgreSQL, run `python run_akela_agents_migration.py --seed` before enabling these flags.

## Selected API Endpoints

Base path: `/api/v1`

- **Auth** — `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- **Questions** — `questions/…` (author and solve SQL questions)
- **Execution** — `execute/…` (run queries)
- **Attempts** — `attempts/…`
- **Labs** — `labs/…`, `lab_analytics/…`
- **ER diagrams** — `er_diagram/…`, `er_analytics/…`, `erd_prompts/…`
- **Assessments** — `assessments/…`, `student_assessments/…`
- **AI tutor** — `chatbot/…`
- **Analytics** — `sql_analytics/…`, `lad/…`, `login_activity/…`, `student_report/…`
- **Admin** — `users/…`, `whitelist/…`, `app_settings/…`, `course_info/…`, `research_export/…`
- **Health** — `GET /`, `GET /health`

Full, interactive documentation is available at `/docs` (Swagger) and `/redoc`.

## Testing

Backend tests use `pytest`:

```bash
cd backend
pytest
```

## Deployment

- **Frontend** — deployed to Azure Static Web Apps (see `.github/workflows/`).
- **Backend** — deployed to Azure App Service with PostgreSQL.

## License

MIT License
