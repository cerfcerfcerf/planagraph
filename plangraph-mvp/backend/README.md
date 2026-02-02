# Plangraph Backend

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file (optional) based on `.env.example` to override the default Ollama settings and SQLite path.

## Run

```bash
uvicorn main:app --reload --port 8000
```

## API

### Health

```bash
curl http://localhost:8000/health
```

### Create Entry (parse + store)

```bash
curl -X POST http://localhost:8000/entry \
  -H "Content-Type: application/json" \
  -d '{"text":"Tomorrow school at 8. Take pills at 7:30. After school buy snacks. Don\u0027t forget headphones.","today":"2024-01-01"}'
```

### Plan (store + generate reminders)

```bash
curl -X POST http://localhost:8000/plan \
  -H "Content-Type: application/json" \
  -d '{"day":"2024-01-02","day_start":"07:00","day_end":"21:00","items":[{"title":"School","type":"event","date":"2024-01-02","start_time":"08:00","end_time":null,"duration_min":0,"priority":2,"location":null,"notes":null},{"title":"Buy snacks","type":"task","date":"2024-01-02","start_time":null,"end_time":null,"duration_min":0,"priority":1,"location":null,"notes":null}]}'
```

### Now feed

```bash
curl "http://localhost:8000/now?now=2024-01-02T07:20:00"
```

### Reminders due + ack

```bash
curl "http://localhost:8000/reminders/due?now=2024-01-02T07:20:00"

curl -X POST http://localhost:8000/reminders/1/ack \
  -H "Content-Type: application/json" \
  -d '{"action":"done"}'

curl -X POST http://localhost:8000/reminders/1/ack \
  -H "Content-Type: application/json" \
  -d '{"action":"cancel_forever"}'
```

### Tasks

```bash
curl "http://localhost:8000/tasks?from=2024-01-01&to=2024-01-07&type=task"

curl -X POST http://localhost:8000/tasks/quick_add \
  -H "Content-Type: application/json" \
  -d '{"title":"Quick task","date":"2024-01-02","time":"10:00","priority":1}'

curl -X PATCH http://localhost:8000/tasks/1 \
  -H "Content-Type: application/json" \
  -d '{"title":"Updated task","priority":2}'

curl -X POST http://localhost:8000/tasks/1/edit \
  -H "Content-Type: application/json" \
  -d '{"title":"Updated task","priority":2}'

curl -X POST http://localhost:8000/tasks/1/delete
```

### Habits

```bash
curl -X POST http://localhost:8000/habits/rules \
  -H "Content-Type: application/json" \
  -d '{"key":"pills","title":"Take pills","lead_min":10,"enabled":true,"default_time":"07:30","target_per_week":7}'

curl http://localhost:8000/habits/rules
```

### History

```bash
curl "http://localhost:8000/history?limit=10"
```

The planner is deterministic and explainable. The LLM is only used for parsing text into structured items.
