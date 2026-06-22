# SQL Learning Platform

A web-based SQL learning platform where teachers create practice questions and students solve them interactively with instant feedback.

## Technology Stack

**Backend:**
- FastAPI (Python)
- SQLAlchemy 2.0 + Alembic
- PostgreSQL (production) / SQLite (development)
- JWT Authentication

**Frontend:**
- React 18 + TypeScript
- Next.js
- Mantine
- Monaco Editor

## Quick Start

### Backend Setup

1. Navigate to backend directory:
```bash
cd backend
```

2. Create and activate virtual environment:
```bash
python -m venv venv

# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. The `.env` file is already configured with development settings.

5. Initialize database (tables will be created automatically on first run):
```bash
# Optional: Set up Alembic migrations
alembic init alembic
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```

6. Run the development server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

7. Access the API:
- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Frontend Setup

(Coming soon in Phase 4)

## Project Status

### ✅ Completed
- [x] Backend project structure
- [x] Configuration management
- [x] Database setup with SQLAlchemy
- [x] User model and authentication
- [x] JWT token authentication
- [x] Registration and login endpoints
- [x] Protected routes with role-based access

### 🚧 In Progress
- [ ] Question management (Phase 2)
- [ ] Query execution engine (Phase 3)
- [ ] Frontend development (Phase 4-6)

## API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - Login and get JWT token
- `GET /api/v1/auth/me` - Get current user info (requires authentication)

### Health
- `GET /` - Root endpoint
- `GET /health` - Health check

## Testing the API

You can test the API using the Swagger UI at http://localhost:8000/docs or use curl:

### Register a student:
```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "student@example.com", "password": "password123", "role": "student"}'
```

### Register a staff member:
```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "staff@example.com", "password": "password123", "role": "staff"}'
```

### Login:
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "student@example.com", "password": "password123"}'
```

### Get current user (with token):
```bash
curl -X GET "http://localhost:8000/api/v1/auth/me" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## Development Plan

Refer to `.claude/plans/cryptic-floating-key.md` for the detailed implementation plan.

## License

MIT License
