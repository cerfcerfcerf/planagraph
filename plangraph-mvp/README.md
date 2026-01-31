# Plangraph MVP (Infomatrix Gold)

A local-first full-stack app that parses natural-language plans with Ollama, builds an explainable schedule, and runs a reminder + habit engine on top of SQLite persistence.

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

Open `http://localhost:5173` to use the app.

## How reminders work

- **Event reminders** are created for each planned item with a start time (lead times by type).
- **Contextual reminders** attach untimed reminders to the earliest anchor event.
- **Habit reminders** learn from completions and schedule around the median completion time.

The planner is deterministic and explainable. The LLM is only used for parsing text into structured items.
