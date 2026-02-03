# Plangraph Backend

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file (optional) based on `.env.example` to override default values.

## Run

```bash
uvicorn main:app --reload --port 8000
```

## API

- `POST /parse` – Parse plan text (LLM + deterministic fallback)
- `GET/POST /tasks` – List or create tasks
- `PATCH /tasks/{id}` – Update a task
- `GET/POST /settings` – View/update policy settings
- `GET /now` – Next best action + upcoming reminders
- `POST /reminders/{id}/action` – done/snooze/dismiss
- `GET /insights` – Metrics for charts
- `POST /seed` – Dev-only demo data (`APP_ENV=dev`)
