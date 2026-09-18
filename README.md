# GridWise LLM

FastAPI service for the BUP CSE Fest 2026 Smart Campus Energy Optimization preliminary. It interprets operator notes with an LLM and returns a minimum-cost, valid 24-hour energy schedule.

- API: `https://gridwise-llm.vercel.app`
  - Interactive docs: `https://gridwise-llm.vercel.app/docs`
- Source: `https://github.com/tanvir-gellar-DU/BUP_Preli`
- Docker: `ghcr.io/tanvir-gellar-du/bup_preli:latest`

## Architecture

```text
Request validation
→ OpenRouter interpretation
→ deterministic directive guardrails and application
→ PuLP/CBC optimization
→ independent schedule validation
→ recalculated totals and JSON response
```

OpenRouter is used only to convert each natural-language operator note into a structured directive. The application validates the model output before using it. PuLP with CBC performs the optimization, and a separate validator replays the final schedule, battery state, energy balance, directive constraints, and totals.

Provider and models:

- OpenRouter
- Primary: `deepseek/deepseek-v4-flash-0731`
- Malformed-output fallback: `openai/gpt-5-nano`

## Local setup

Requirements: Python 3.12 and an OpenRouter API key with available quota.

```bash
git clone https://github.com/tanvir-gellar-DU/BUP_Preli.git
cd BUP_Preli
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Configure `.env`:

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_API_KEYS=[]
OPENROUTER_MODEL=deepseek/deepseek-v4-flash-0731
OPENROUTER_FALLBACK_MODEL=openai/gpt-5-nano
OPENROUTER_TIMEOUT_SECONDS=15
```

Use either `OPENROUTER_API_KEY` or a JSON array in `OPENROUTER_API_KEYS`. Start the service:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API

Health check:

```bash
curl --fail http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Run public Sample 1 against the optimization endpoint:

```bash
jq '.cases[0].input' BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json \
  | curl --fail --json @- http://localhost:8000/optimize-energy
```

The response must contain the same `scenario_id`, one `directive_interpretation` per note, 24 `hourly_plan` entries, and recalculated totals. For Sample 1, the optimal aggregates are:

```json
{
  "total_grid_kwh": 2692.5,
  "total_cost_bdt": 38365,
  "peak_grid_kwh": 175
}
```


## Docker fallback

The public image supports `linux/amd64` and `linux/arm64`.

```bash
docker pull ghcr.io/tanvir-gellar-du/bup_preli:latest
docker run --rm -d --name gridwise --env-file .env -p 8000:8000 \
  ghcr.io/tanvir-gellar-du/bup_preli:latest
curl --fail http://localhost:8000/health
docker stop gridwise
```

Immutable image reference:

```text
ghcr.io/tanvir-gellar-du/bup_preli@sha256:7d9f9014d15da98ae8864d5b4bdd40a1ad1a4e1ec6444e8127cd3d0fea477c46
```

Build the same service locally if needed:

```bash
docker build -t gridwise:local .
docker run --rm --env-file .env -p 8000:8000 gridwise:local
```

## Deployment

Vercel runs the same FastAPI application through `api/index.py`. Configure the environment variables listed above in Vercel, then deploy with `vercel deploy --prod`. The submitted public base URL is:

```text
https://gridwise-llm.vercel.app
```

## Dependencies and limitations

All runtime and test dependencies are declared in `requirements.txt`. The main libraries are FastAPI, Pydantic, HTTPX, PuLP, CBC, Uvicorn, and pytest.

- Optimization requests require OpenRouter network access, valid credentials, model availability, and sufficient quota.
- Latency depends on OpenRouter and the selected model.
- Unknown request fields are rejected to preserve the exact API contract.

## Security

Never commit `.env`, API keys, tokens, or credentials. Secrets are provided only through runtime environment variables and are not included in the Docker image or API responses.
