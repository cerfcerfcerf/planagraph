# Plangraph Backend

Run the FastAPI app:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Environment variables live in `.env` (copy from `.env.example`).
