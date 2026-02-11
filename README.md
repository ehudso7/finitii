# Finitii

AI-driven personal finance app that gives you a clear action plan to improve your money — not just dashboards.

## What It Does

- **Onboarding** — Link an account (or add manually), set goals, get your Top 3 moves instantly
- **Cheat Codes** — Step-by-step money moves ranked by impact and confidence, with quick wins you can finish in 10 minutes
- **Safe-to-Spend** — Daily and weekly spending forecast that accounts for upcoming bills and recurring expenses
- **Coach** — Personalized plans, weekly reviews, and recaps based on your actual behavior (template-based, explainable)
- **Learn + Practice** — 10 financial lessons and 10 interactive scenarios with deterministic simulations
- **Vault** — Store receipts and documents, linked to transactions
- **Full Data Control** — Export everything as JSON, delete your account and all data at any time

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Alembic |
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| Database | PostgreSQL 16 |
| Auth | Session-based (X-Session-Token header) |
| Testing | pytest (630 tests), Playwright (4 E2E tests) |

## Project Structure

```
backend/          Python API server
  app/
    models/       SQLAlchemy models
    services/     Business logic
    routers/      FastAPI route handlers
    core/         Auth, middleware, error handling
    schemas/      Pydantic request/response schemas
  tests/          Backend test suite (630 tests)
  alembic/        Database migrations

frontend/         Next.js web app
  app/            Pages (App Router)
  lib/            API client, test IDs, utilities
  components/     Shared components
  tests/          Playwright E2E tests (4 tests)
```

## Local Development

### Backend

```bash
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:3000`, backend on `http://localhost:8000`.

### Run Tests

```bash
# Backend
cd backend && pytest

# E2E
cd frontend && npx playwright test
```

## Environment Variables

### Backend

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL async connection string (`postgresql+asyncpg://...`) |
| `SECRET_KEY` | Yes (prod) | Session secret, 64+ random chars |
| `APP_ENV` | No | `development` (default) or `production` |
| `CORS_ALLOW_ORIGINS` | No | Comma-separated allowed origins |
| `CORS_ALLOW_ORIGIN_REGEX` | No | Regex pattern for CORS origins (e.g. `https://.*\.vercel\.app`) |
| `DEBUG` | No | Enable debug mode and API docs |

### Frontend

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_BASE_URL` | Yes | Backend API URL (e.g. `https://finitii.onrender.com`) |

## Deployment

- **Backend**: Render (or any platform that runs Python) — set Root Directory to `backend`
- **Frontend**: Vercel — set Root Directory to `frontend`
- Database tables are created automatically on startup

## License

Private. All rights reserved.
