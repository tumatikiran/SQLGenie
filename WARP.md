# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Repo layout (big picture)
- `backend/`: FastAPI service that (1) introspects a Microsoft SQL Server schema at startup, (2) asks Google Gemini to generate a SQL Server `SELECT` query, (3) validates/normalizes the SQL to be read-only/safe, then (4) executes it via `pyodbc`.
- `frontend/`: React + Vite UI that shows the database schema (sidebar) and a chat experience that calls the backend.

## Common development commands

### Backend (FastAPI)
From repo root:
- Create + activate venv (Windows PowerShell):
  - `cd backend`
  - `python -m venv .venv`
  - `.\.venv\Scripts\Activate.ps1`
- Install deps:
  - `pip install -r requirements.txt`
- Configure env:
  - Copy `backend/.env.example` -> `backend/.env` and fill in SQL Server + `GOOGLE_API_KEY`.
- Run API (reload):
  - `uvicorn main:app --reload --host 127.0.0.1 --port 8000`

Notes:
- The backend loads the DB schema once on startup (see `backend/main.py` startup event). Restart the server to pick up schema changes.

### Frontend (React + Vite)
From repo root:
- Install deps:
  - `cd frontend`
  - `npm install`
- Run dev server:
  - `npm run dev`
- Production build:
  - `npm run build`
- Preview production build:
  - `npm run preview`

Frontend config:
- Optionally set `frontend/.env`:
  - `VITE_API_BASE_URL=http://localhost:8000`

### Tests / lint
- No test runner or lint script is configured in this repo currently (no `tests/`, `pytest.ini`, `ruff`, ESLint, etc.).

## Backend architecture (how a request flows)

### Key endpoints
Implemented in `backend/main.py`:
- `GET /tables`: returns fully-qualified table names (`[schema].[table]`) for the UI.
- `GET /schema`: returns full schema details used by the UI sidebar.
- `POST /chat`: main chat endpoint.

### `/chat` flow
1. Schema prompt is retrieved from `app.state.schema_prompt` (computed at startup).
2. LLM SQL generation:
   - `backend/gemini_llm.py:generate_sql(question, schema_prompt)` builds a prompt that includes the schema and instructs Gemini to output *only* SQL.
   - Model selection is resolved once and cached; can be overridden via `GEMINI_MODEL`.
3. SQL safety validation:
   - `backend/sql_guard.py:validate_and_normalize_sql(sql_raw)` enforces a strict single-statement `SELECT`-only policy.
   - Notable guardrails: disallows comments and CTEs (`WITH`), blocks a set of dangerous tokens, and enforces/caps `TOP (100)`.
4. DB execution:
   - Connection is created per request via `backend/db.py:get_connection()` (DSN-less ODBC connection string from env vars).
   - Query timeout is set (best-effort) via `get_query_timeout_seconds`.
   - Results are returned as `columns` + `rows` (first 100 rows via `fetchmany(100)`).

### Schema loading + prompting
- `backend/schema.py:load_schema(conn)` reads from `INFORMATION_SCHEMA.TABLES` and `INFORMATION_SCHEMA.COLUMNS`.
- `DatabaseSchema.to_prompt_string()` produces a compact, deterministic schema representation that is embedded into the Gemini prompt.

### Configuration points
- DB connectivity and timeouts: `backend/db.py` + `backend/.env`.
- Prompt rules / model behavior: `backend/gemini_llm.py` (the `system_instruction` string is the main place to tweak generation behavior).

## Frontend architecture

### Data access
- `frontend/src/api.js` is the only place that knows the backend endpoints (`/tables`, `/schema`, `/chat`) and normalizes the base URL.

### UI composition
- `frontend/src/App.jsx`: shell layout, API base URL setting (persisted to localStorage), and theme toggle.
- `frontend/src/components/Sidebar.jsx`: loads schema from `GET /schema`, supports filtering, and expands tables to show columns.
- `frontend/src/components/Chat.jsx`: chat state + localStorage history; sends questions to `POST /chat`.
- `frontend/src/components/Message.jsx`: renders the assistant response, generated SQL, and tabular results.
