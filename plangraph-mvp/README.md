# Plangraph (Life OS)

Local-first planning OS with SQLite persistence, a minimal policy engine, and a focused LLM workflow (only plan parsing + short “why now” explanations).

## Stack

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, SQLite
- **Frontend**: React + Vite + TypeScript + Tailwind
- **Charts**: Recharts
- **Scheduler**: in-process loop checking reminders every 30 seconds
- **Notifications**: Browser Notifications API (only while app is open)

## Environment

Create `backend/.env` from `backend/.env.example`:

```bash
DB_PATH=plangraph.db
USE_LLM=true
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=llama3.1
ALLOW_SEED=true
```

### LLM configuration

The backend uses an OpenAI-compatible chat/completions API. Defaults target a local Ollama server.

- **Local LLM (default)**: nothing to change.
- **OpenAI-compatible endpoint**: set `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` to match your provider.

If the LLM output is invalid JSON or fails validation, the backend falls back to a deterministic parser.

## Run backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Seed data (dev only)

```bash
curl -X POST http://localhost:8000/seed
```

Enable with `ALLOW_SEED=true` in `backend/.env`.

## Reminders + policy notes

- **Baseline**: one reminder at `due_at - lead_time` (or `window_start` for flexible tasks).
- **Adaptive**: recurring tasks learn preferred time-of-day from completion events, then schedule inside the window.
- **Daily budget** and **quiet hours** are enforced when scheduling.

## Notification limitation

Browser notifications only fire while the app is open in a tab. The backend does not send system-level notifications.
