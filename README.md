# GridWise LLM

GridWise LLM is a FastAPI service for the BUP CSE Fest 2026 Smart Campus Energy Optimization preliminary. It interprets 1–3 natural-language operator notes with OpenRouter, validates the resulting directives, and computes a valid minimum-cost 24-hour grid/solar/battery schedule with PuLP and CBC.

## Architecture

```text
HTTP request → Pydantic validation → OpenRouter semantic extraction
→ typed directive guardrails → deterministic directive application
→ PuLP/CBC optimization → independent schedule replay
→ aggregate recalculation → exact JSON response
```

The LLM only performs semantic extraction. It does not optimize, validate the schedule, or write the summary. Model output is treated as untrusted until Pydantic and scenario-aware guardrails validate its count, order, type, adjustment shape, hours, values, and `applies` semantics.

The optimizer uses a signed battery-flow variable: positive means charging and negative means discharging. This represents exactly one public battery action per hour without simultaneous charging and discharging. Solar may be curtailed; grid export and battery losses are not modeled because the organizer specification does not define them. Final battery energy equals initial energy.

## Requirements

- Python 3.12
- OpenRouter API key with funded credits
- An OpenRouter model supporting strict structured outputs
- CBC (the PuLP wheel includes CBC on supported platforms; Docker installs it explicitly)

Core dependencies are FastAPI, Pydantic, pydantic-settings, HTTPX, PuLP, Uvicorn, pytest, and pytest-asyncio.

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Set these values in `.env`:

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=deepseek/deepseek-v4-flash-0731
OPENROUTER_TIMEOUT_SECONDS=15
```

Never commit `.env` or put credentials in source, Docker images, `vercel.json`, logs, or API responses.

Start locally:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl --fail http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Optimization request

Send any `input` object from `BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json`:

```bash
jq '.cases[0].input' BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json \
  | curl --fail --json @- http://localhost:8000/optimize-energy
```

The response contains the echoed `scenario_id`, one ordered `directive_interpretation` per note, 24 ordered `hourly_plan` entries, recalculated grid energy/cost/peak, and a deterministic summary.

## Tests and public validation

Normal tests mock OpenRouter and consume no quota:

```bash
pytest -q
pytest tests/test_public_cases.py -q
```

The public-case suite validates all ten reference interpretations through directive application, optimization, independent replay, neutrality, and aggregate comparison. Equivalent optimal schedules are accepted by comparing cost rather than action sequence.

Optional paid real-model interpretation evaluation:

```bash
python -m scripts.evaluate_llm
python -m scripts.evaluate_llm --limit 1
python -m scripts.evaluate_paraphrases
```

The internal paraphrase corpus contains 18 notes covering every supported directive and `no_op`, including 12/24-hour clocks, fractions, percentages, and alternate operational wording. Its evaluator reports relevance, directive type, hours, numeric extraction, adjustment shape, and exact-note accuracy.

## Docker fallback

Build and run locally:

```bash
docker build -t gridwise:local .
docker run --rm -p 8000:8000 \
  -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  -e OPENROUTER_MODEL="deepseek/deepseek-v4-flash-0731" \
  -e OPENROUTER_TIMEOUT_SECONDS=15 \
  gridwise:local
```

Verify `http://localhost:8000/health`. Replace `gridwise:local` with the final submitted registry tag or digest after publishing; no public image has been claimed yet.

## Vercel

Production base URL: `https://gridwise-llm.vercel.app`

Vercel's native FastAPI adapter deploys the same application used locally and in Docker. The production project stores `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, and `OPENROUTER_TIMEOUT_SECONDS` as encrypted environment variables. On September 18, 2026, external checks returned HTTP 200 from both `/health` and `/optimize-energy`; the latter returned a complete 24-hour schedule for public Sample 1.

To deploy a separately owned copy, link the repository with Vercel, configure those three production variables, and run `vercel deploy --prod` from the repository root.

## Failure behavior

- Malformed or structurally invalid requests: controlled HTTP 400.
- Well-formed but infeasible scenarios: controlled HTTP 422.
- Missing credentials, authentication, quota, rate limits, provider failures, timeouts, malformed model output, or rejected candidate schedules: controlled HTTP 500 without secrets or stack traces.
- Provider calls use one request for all notes, strict JSON Schema, a 1,200-token output cap, minimal reasoning, a 15-second configured timeout, and at most one retry for transient failures.

## Known limitations

- A hosted OpenRouter dependency requires valid credentials, funded quota, model availability, and network access during judging.
- The organizer does not define how overlapping directives of the same type compose. This implementation applies the most restrictive value: lowest solar factor/grid cap and highest reserve.
- Unknown request fields are rejected to protect the exact contract.
- The Docker image has been built and exercised locally, but publication to a public registry remains required before submission.

## Security

Only synthetic challenge data is processed. Authorization headers and secret values are never logged or returned. Use a dedicated, spending-limited OpenRouter key and rotate or revoke it after evaluation.
