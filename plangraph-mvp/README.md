# Plangraph Execution Assistant

Plangraph is a local-first execution assistant. It turns natural language into reminders, surfaces what to do now, and learns when you act so future reminders are timed better.

## Prerequisites

- Python 3.12
- Node.js 18+
- Ollama running locally at `http://localhost:11434` with the `llama3.1:8b` model

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

Open `http://localhost:5173` to use the app. The UI is organized into Now, Add, and Tasks screens.

## Key features

- **Local-first**: SQLite persistence lives alongside the app.
- **Reminders-first**: the Now screen shows what is due now, next, and later today.
- **Learning habits**: reminder timing adapts to your completion history.
- **Natural language input**: paste a plan or add one item in a single line.

The planner is deterministic and explainable. The LLM is only used for parsing text into structured items.
