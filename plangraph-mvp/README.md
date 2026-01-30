# Plangraph MVP

A minimal full-stack app that parses natural-language plans with Ollama and builds an explainable daily schedule.

## Prerequisites

- Python 3.12
- Node.js 18+
- Ollama running locally at `http://localhost:11434` with the `llama3.1:8b` model

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` to use the app.

## Notes

- The planner is deterministic and explainable.
- The LLM is only used for parsing text into structured items.
