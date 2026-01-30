# Plangraph MVP Backend

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file (optional) based on `.env.example` to override the default Ollama settings.

## Run

```bash
uvicorn main:app --reload --port 8000
```

## API

### Health

```bash
curl http://localhost:8000/health
```

### Parse

```bash
curl -X POST http://localhost:8000/parse \
  -H "Content-Type: application/json" \
  -d '{"text":"Tomorrow school at 8. Take pills at 7:30. After school buy snacks. Don\u0027t forget headphones.","today":"2024-01-01"}'
```

### Plan

```bash
curl -X POST http://localhost:8000/plan \
  -H "Content-Type: application/json" \
  -d '{"day":"2024-01-02","day_start":"07:00","day_end":"21:00","items":[{"title":"School","type":"event","date":"2024-01-02","start_time":"08:00","end_time":null,"duration_min":0,"priority":2,"location":null,"notes":null},{"title":"Buy snacks","type":"task","date":"2024-01-02","start_time":null,"end_time":null,"duration_min":0,"priority":1,"location":null,"notes":null}]}'
```

The planner is deterministic and explainable. The LLM is only used for parsing text into structured items.
