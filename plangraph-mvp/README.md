# Plangraph (Life OS)

Plangraph is a local-first planning assistant that parses plans into tasks, schedules reminders, and helps you act on the next best step. All user data is stored in SQLite on your machine. The LLM is only used for plan parsing and the short "why now" explanation, and it is fully configurable through environment variables.

## Tech stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy, SQLite
- **Frontend:** React + Vite + TypeScript + Tailwind CSS
- **Charts:** Recharts
- **Scheduler:** in-process loop checks reminders every 30–60s
- **Notifications:** Browser Notifications API (works while the app tab is open)

> **Notification limitation:** Because the app uses the browser Notifications API, reminders will only appear while the web app is open in your browser. The backend does not push system-level notifications.

## Monorepo layout

```
backend/   FastAPI app, scheduler, LLM client, deterministic parser
frontend/  Vite + React UI
```

## Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

### LLM configuration

By default, the backend uses a local OpenAI-compatible endpoint (e.g., Ollama):

```bash
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=llama3.1
USE_LLM=true
```

To point at any OpenAI-compatible endpoint, change the base URL, API key, and model:

```bash
LLM_BASE_URL=https://your-host.example/v1
LLM_API_KEY=your-key
LLM_MODEL=your-model-name
```

If LLM output is invalid JSON or fails validation, Plangraph automatically falls back to a deterministic parser.

### Optional seed data

Enable seed data for local demos:

```bash
DEV_SEED=true
```

Then call:

```bash
curl -X POST http://localhost:8000/seed
```

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

By default, the frontend expects the backend at `http://localhost:8000`. To override:

```bash
VITE_API_URL=http://localhost:8000
```

## Key endpoints

- `POST /parse` — parse freeform plan text into tasks (LLM or fallback)
- `GET/POST /tasks` — list or create tasks
- `PATCH /tasks/{id}` — update tasks
- `GET/POST /settings` — reminder policy settings
- `GET /now` — next best action, upcoming tasks, and “why now”
- `POST /reminders/{id}/action` — done, snooze, dismiss
- `GET /insights` — aggregated metrics and time series
- `POST /seed` — dev seed data (if enabled)
