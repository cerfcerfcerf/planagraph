# Plangraph (Life OS)

Plangraph is a local-first Life OS that parses natural-language plans into reminders, runs a lightweight scheduling policy, and surfaces a calm “next best action” flow. All data is stored in SQLite and the UI uses the browser Notifications API (only while the tab is open).

## File tree

```
plangraph-mvp/
├── backend/
│   ├── .env.example
│   ├── README.md
│   ├── __init__.py
│   ├── database.py
│   ├── llm_client.py
│   ├── main.py
│   ├── models.py
│   ├── parser.py
│   ├── policy.py
│   ├── requirements.txt
│   ├── scheduler.py
│   └── schemas.py
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── postcss.config.cjs
│   ├── tailwind.config.cjs
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx
│       ├── api.ts
│       ├── index.css
│       ├── main.tsx
│       └── types.ts
└── README.md
```

## Prerequisites

- Python 3.11+
- Node.js 18+

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

## Environment configuration

### OpenAI (recommended)

Set your OpenAI API key and select the fast parsing model (default is `gpt-5-mini`).

```
OPENAI_API_KEY=your_api_key
OPENAI_MODEL_FAST=gpt-5-mini
OPENAI_MODEL_REASON=gpt-5.2
OPENAI_BASE_URL=https://api.openai.com/v1
USE_LLM=true
DATABASE_URL=sqlite:///./plangraph.db
APP_ENV=dev
```

If you want “gpt‑5.0 mini”, set it explicitly:

```
OPENAI_MODEL_FAST=gpt-5.0-mini
```

### OpenAI-compatible endpoint

```
OPENAI_BASE_URL=https://your-endpoint/v1
OPENAI_API_KEY=your_api_key
OPENAI_MODEL_FAST=your_model_name
OPENAI_MODEL_REASON=your_reason_model
USE_LLM=true
```

## Notes

- Parsing is deterministic in MVP mode and always uses the local parser for stable results.
- Notifications use the browser Notifications API and only fire while the app is open (no background push support).
- Voice dictation relies on the browser Web Speech API and is best supported in Chromium-based browsers; it may be unavailable in Firefox or privacy-hardened environments.

## Parsing format (spaced schedules)

You can paste time blocks on their own lines, followed by the description on the next line(s):

```
06:30 - 07:30
Morning review + stretch

18:00 - 19:00
Project work block
```

The parser treats each time range as a flexible window and attaches the following non-empty lines until the next time range.

## Development seed

Enable dev seeding with `APP_ENV=dev`, then:

```bash
curl -X POST http://localhost:8000/seed
```


## Parser defaults

- One input line maps to at most one parsed task.
- Supported times: `20:00`, `20.00`, `20`, `8pm`, `8 pm`.
- Supported ranges: `20:00-23:00`, `20:00 - 23:00`, `20.00 to 23.00`, `20.00–23.00`.
- Relative dates: `today`, `tomorrow`, weekdays (`mon`/`monday`, etc.).
- Slash dates default to **DD/MM/YYYY**. Ambiguous slash dates (e.g. `11/12/2026`) return a line-level parse error instead of creating a wrong task.
