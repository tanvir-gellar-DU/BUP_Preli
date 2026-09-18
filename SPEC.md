# GridWise LLM --- Spec-Driven Development Specification

**Project:** BUP CSE Fest 2026 Hackathon Preliminary --- Smart Campus
Energy Optimization Challenge\
**Purpose:** Single source of implementation instructions for Codex\
**Development style:** Specification-first, phase-gated, test-driven\
**Primary deployment decision:** Vercel\
**LLM gateway decision:** OpenRouter\
**Backend decision:** Python + FastAPI + Pydantic\
**Optimizer decision:** PuLP + CBC\
**Fallback:** Docker image of the same service

------------------------------------------------------------------------

## 0. Authority and Source of Truth

Before changing code, Codex **must read all organizer-provided artifacts
in the workspace**:

1.  `BUP_CSE_FEST_2026_Preliminary_Problem_Statement_GridWise_LLM.pdf`
2.  `BUP_CSE_FEST_2026_Participant_Guide_&_Evaluation_Rubric_GridWise_LLM.pdf`
3.  `BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json`

The documents have different authority:

-   **Problem Statement** is canonical for challenge behavior, endpoint
    names, request/response fields, supported directives, interpretation
    guardrails, battery behavior, energy accounting, optimization rules,
    and validity.
-   **Participant Guide & Evaluation Rubric** is canonical for
    deployment, repository policy, submission procedure, performance,
    scoring, penalties, Docker fallback, reproducibility, and
    tie-breaks.
-   **Public Sample Cases** are worked references for local validation.
    They are **not** the hidden judge set and must never be hard-coded.

### Conflict rule

If this development specification conflicts with an organizer document,
**the organizer document wins**.

If a requirement is unclear, do not guess. Record it as:

> **SPECIFICATION QUESTION:**
> `<exact ambiguity and affected implementation>`

If the organizer does not prescribe an engineering detail, record the
chosen approach as:

> **IMPLEMENTATION DECISION:** `<decision and reason>`

------------------------------------------------------------------------

# 1. Challenge Goal

Build **one publicly reachable HTTP API service** that receives:

-   a scenario identifier;
-   24 hourly demand/solar/tariff records;
-   battery configuration;
-   1--3 natural-language operator notes;

and returns:

-   exactly one machine-checkable interpretation for every operator
    note;
-   a valid 24-hour energy schedule;
-   total grid energy;
-   total grid cost;
-   peak hourly grid energy;
-   a short plan summary.

The required conceptual pipeline is:

``` text
HTTP Request
    ↓
Request Validation
    ↓
OpenRouter LLM Interpretation
    ↓
Deterministic Directive Guardrails
    ↓
Directive Application
    ↓
24-Hour Mathematical Optimizer
    ↓
Independent Schedule Validator
    ↓
Aggregate Recalculation
    ↓
Exact JSON Response
```

The LLM's job is **language interpretation**.\
The optimizer's job is **energy scheduling**.\
The validator's job is **independent correctness verification**.

Never merge these responsibilities into one opaque LLM prompt.

------------------------------------------------------------------------

# 2. Mandatory LLM Requirement

Every `operator_notes` entry must pass through a **language-capable
generative model** in the actual interpretation path.

The structured interpretation produced from the LLM must be the
interpretation used downstream by the optimizer after deterministic
validation.

The following are **not compliant**:

-   regex-only interpretation;
-   keyword matching as the sole interpreter;
-   hard-coded public sample phrases;
-   calling an LLM but ignoring its result;
-   using an LLM only for `plan_summary`;
-   using an LLM only for documentation or cosmetic text.

Deterministic validation **after** LLM interpretation is required by our
architecture.

------------------------------------------------------------------------

# 3. Implementation Stack

These are implementation decisions, not organizer requirements unless
separately stated.

  Concern              Decision
  -------------------- --------------------------------------
  Language             Python
  HTTP API             FastAPI
  Data validation      Pydantic
  LLM gateway          OpenRouter
  LLM model            Configurable with `OPENROUTER_MODEL`
  LLM credential       `OPENROUTER_API_KEY`
  Optimizer            PuLP + CBC
  Tests                pytest
  Primary deployment   Vercel
  Required fallback    Docker
  CI tests             Mock LLM; no quota consumption

Do not hard-code an underlying OpenRouter model into business logic.

Changing `OPENROUTER_MODEL` must not require changes to:

-   directive models;
-   guardrails;
-   directive application;
-   optimizer;
-   final validator;
-   response calculation.

------------------------------------------------------------------------

# 4. Required HTTP Endpoints

## 4.1 `GET /health`

When ready, return HTTP 200:

``` json
{
  "status": "ok"
}
```

The service must become ready within the organizer's startup window.

## 4.2 `POST /optimize-energy`

This is the main endpoint.

It must execute:

``` text
validate request
→ interpret notes with LLM
→ validate directives
→ apply directives
→ optimize
→ independently validate schedule
→ recalculate totals
→ return response
```

Malformed/model/provider/internal failures must be controlled. Never
expose API keys, Authorization headers, raw secrets, or sensitive stack
traces.

------------------------------------------------------------------------

# 5. Request Contract

The exact field names and constraints must be implemented from the
Problem Statement.

Conceptually:

``` json
{
  "scenario_id": "string",
  "operator_notes": ["string"],
  "hours": [
    {
      "hour": 0,
      "demand_kwh": 0,
      "solar_kwh": 0,
      "tariff_bdt_per_kwh": 0
    }
  ],
  "battery": {
    "capacity_kwh": 0,
    "initial_energy_kwh": 0,
    "minimum_energy_kwh": 0,
    "max_charge_kwh_per_hour": 0,
    "max_discharge_kwh_per_hour": 0
  }
}
```

Mandatory structural rules include:

-   `operator_notes`: exactly 1--3 non-empty notes;
-   `hours`: exactly 24 entries;
-   hour identifiers uniquely cover integers 0--23;
-   numeric fields must satisfy organizer-defined validity rules;
-   invalid structural input must not reach the LLM or optimizer.

Do not silently rename organizer fields.

------------------------------------------------------------------------

# 6. Supported Directive Domain

There are **exactly six** legal interpretations.

## 6.1 `solar_reduction`

Structured adjustment:

``` json
{
  "hours": [13, 14],
  "factor": 0.2
}
```

`factor` is the **usable fraction remaining**, not the amount lost.

Examples:

``` text
80% reduction → factor = 0.2
20% remains   → factor = 0.2
one-fifth remains → factor = 0.2
```

Effect:

``` text
effective_solar[h] = original_solar[h] × factor
```

for affected hours.

## 6.2 `minimum_battery_reserve`

Structured adjustment:

``` json
{
  "hours": [18, 19],
  "minimum_energy_kwh": 12.0
}
```

For affected hours:

``` text
battery_after[h] >= max(
    base_minimum_energy,
    directive_minimum_energy
)
```

## 6.3 `no_charge_window`

Structured adjustment:

``` json
{
  "hours": [10, 11]
}
```

Effect:

``` text
charge[h] = 0
```

for affected hours.

## 6.4 `no_discharge_window`

Structured adjustment:

``` json
{
  "hours": [17, 18]
}
```

Effect:

``` text
discharge[h] = 0
```

for affected hours.

## 6.5 `max_grid_window`

Structured adjustment:

``` json
{
  "hours": [19, 20],
  "max_grid_kwh": 15.0
}
```

Effect:

``` text
grid[h] <= max_grid_kwh
```

for affected hours.

## 6.6 `no_op`

For an irrelevant note:

``` json
{
  "applies": false,
  "directive_type": "no_op",
  "structured_adjustment": null
}
```

It introduces no optimization constraint.

Never invent a seventh directive.

------------------------------------------------------------------------

# 7. Interpretation Contract

For `N` notes, return exactly `N` `directive_interpretation` entries.

They must be in original note order:

``` text
note_index = 0, 1, ..., N-1
```

Rules:

-   non-`no_op` → `applies = true`;
-   `no_op` → `applies = false`;
-   `no_op` → `structured_adjustment = null`;
-   every real directive has the exact required adjustment shape;
-   explanation text may be concise, but machine-checkable fields are
    primary.

### Hour normalization

All directive `hours` arrays must contain:

-   integers only;
-   values 0--23;
-   unique values;
-   ascending order.

### Whole-hour interval convention

Intervals are **start-inclusive and end-exclusive**.

``` text
1 PM to 3 PM → [13, 14]
2 PM to 4 PM → [14, 15]
6 PM to 9 PM → [18, 19, 20]
```

Do not include the ending hour.

------------------------------------------------------------------------

# 8. OpenRouter Integration

Suggested files:

``` text
app/llm/
├── openrouter_client.py
├── interpreter.py
└── prompt.py
```

## 8.1 Configuration

Use environment variables:

``` text
OPENROUTER_API_KEY=
OPENROUTER_MODEL=
OPENROUTER_TIMEOUT_SECONDS=
```

Provide placeholders in `.env.example`.

Never commit real credentials.

Centralize configuration in `app/config.py`.

## 8.2 Client responsibility

`openrouter_client.py` handles only provider communication:

-   authentication;
-   HTTP requests;
-   timeout;
-   429/rate limiting;
-   provider 5xx;
-   model unavailability;
-   malformed provider responses;
-   safe error mapping.

## 8.3 Interpreter responsibility

`interpreter.py`:

1.  receives all 1--3 notes;
2.  preferably sends them in one LLM request;
3.  parses structured output;
4.  validates it with typed models;
5.  sends it to deterministic semantic guardrails.

## 8.4 Prompt responsibility

`prompt.py` must teach only semantic extraction:

-   choose exactly one supported directive per note;
-   preserve `note_index`;
-   distinguish relevant notes from `no_op`;
-   extract normalized hours;
-   follow start-inclusive/end-exclusive semantics;
-   extract kWh values;
-   convert solar reduction language to fraction remaining;
-   never invent missing values;
-   never invent directives.

Do **not** ask the model to optimize the energy schedule.

## 8.5 Structured output

Prefer OpenRouter/model JSON Schema or structured-output support where
available.

Still validate all returned content with Pydantic and deterministic
guardrails. Provider-level schema enforcement is not sufficient by
itself.

------------------------------------------------------------------------

# 9. LLM Failure Handling

Handle at least:

-   missing API key;
-   missing/invalid model;
-   authentication error;
-   rate limit (`429`);
-   provider unavailable;
-   provider `5xx`;
-   timeout;
-   malformed response;
-   invalid JSON;
-   schema mismatch;
-   semantically invalid interpretation.

A small bounded retry may be used for appropriate transient/model-format
failures, but it must respect the overall endpoint latency budget.

Never implement an unlimited retry loop.

Never replace a failed LLM interpretation with a regex-only semantic
bypass.

------------------------------------------------------------------------

# 10. Deterministic Directive Guardrails

Never pass raw model output directly to optimization.

Validate:

1.  interpretation count equals note count;
2.  `note_index` sequence exactly matches `0..N-1`;
3.  order is correct;
4.  directive type is one of the six supported values;
5.  `applies` semantics are correct;
6.  adjustment shape matches directive;
7.  `no_op` has null adjustment;
8.  real directives have required adjustment;
9.  hours are integers;
10. hours are 0--23;
11. hours are unique;
12. hours are ascending;
13. required numeric values exist;
14. numeric values are finite;
15. factor/value ranges are semantically valid;
16. unsupported fields cannot create constraints.

Do not silently invent a missing factor, hour, reserve, or grid cap.

------------------------------------------------------------------------

# 11. Directive Application Layer

Convert validated directives into deterministic 24-hour constraint data
before optimization.

Suggested internal arrays:

``` text
effective_solar[24]
minimum_reserve[24]
charge_allowed[24]
discharge_allowed[24]
max_grid[24]
```

Initialize from the base scenario, then apply directives.

This layer must be independent from:

-   FastAPI;
-   OpenRouter;
-   PuLP;
-   public response formatting.

------------------------------------------------------------------------

# 12. Energy and Battery Model

For each hour `h ∈ [0,23]`, model quantities such as:

``` text
grid[h]
solar_used[h]
charge[h]
discharge[h]
battery_after[h]
```

## 12.1 Solar

Solar can be curtailed.

``` text
0 <= solar_used[h] <= effective_solar[h]
```

Do not invent solar export.

## 12.2 Energy balance

Every hour must satisfy:

``` text
grid[h] + solar_used[h] + discharge[h]
=
demand[h] + charge[h]
```

## 12.3 Battery transition

Hour 0:

``` text
battery_after[0]
=
initial_energy + charge[0] - discharge[0]
```

Hour `h > 0`:

``` text
battery_after[h]
=
battery_after[h-1] + charge[h] - discharge[h]
```

Do not invent battery efficiency/losses unless the organizer
specification states them.

## 12.4 Battery bounds

For every hour:

``` text
minimum_allowed[h]
<= battery_after[h]
<= capacity_kwh
```

where `minimum_allowed[h]` incorporates the base minimum and applicable
reserve directive.

## 12.5 Rate limits

``` text
0 <= charge[h] <= max_charge_kwh_per_hour
0 <= discharge[h] <= max_discharge_kwh_per_hour
```

Apply no-charge, no-discharge, and max-grid directives as hard
constraints.

------------------------------------------------------------------------

# 13. End-of-Day Neutrality

Mandatory:

``` text
battery_after[23] = initial_energy_kwh
```

within allowed numeric tolerance.

The optimizer must not reduce cost by consuming the starting battery as
free one-time energy.

------------------------------------------------------------------------

# 14. Optimization Objective

After all hard constraints are applied:

``` text
minimize Σ(grid[h] × tariff[h]), h = 0..23
```

Priority:

1.  validity;
2.  cost minimization.

An invalid cheap plan is not an acceptable result.

Do not add secondary objectives that can alter the specified primary
optimum unless explicitly justified and verified against the organizer
specification.

------------------------------------------------------------------------

# 15. Battery Action Mapping

Public hourly output has exactly one:

``` text
charge
discharge
idle
```

and a non-negative `battery_kwh`.

Mapping:

``` text
charge > tolerance, discharge ≈ 0 → "charge"
discharge > tolerance, charge ≈ 0 → "discharge"
both ≈ 0 → "idle", battery_kwh = 0
```

Avoid simultaneous charging and discharging in the selected solution.

If solver degeneracy makes this possible, choose a formulation
consistent with the organizer specification and document the
implementation decision. Do not introduce an arbitrary constraint that
changes the required optimum without verification.

------------------------------------------------------------------------

# 16. Response Contract

Successful response must contain the exact organizer-required fields:

``` json
{
  "scenario_id": "same-as-request",
  "directive_interpretation": [],
  "hourly_plan": [],
  "total_grid_kwh": 0,
  "total_cost_bdt": 0,
  "peak_grid_kwh": 0,
  "plan_summary": "..."
}
```

`hourly_plan` must contain exactly 24 entries for hours 0--23.

Each hourly entry contains:

``` json
{
  "hour": 0,
  "grid_kwh": 0,
  "solar_used_kwh": 0,
  "battery_action": "idle",
  "battery_kwh": 0,
  "battery_energy_after_kwh": 0
}
```

Do not rename or omit required fields.

------------------------------------------------------------------------

# 17. Aggregate Recalculation

The final `hourly_plan` is the source of truth.

After validation, independently calculate:

``` text
total_grid_kwh = Σ grid_kwh[h]

total_cost_bdt =
Σ(grid_kwh[h] × request_tariff[h])

peak_grid_kwh =
max(grid_kwh[h])
```

Do not trust solver metadata or pre-rounded values for the public
aggregates.

------------------------------------------------------------------------

# 18. Independent Final Schedule Validator

Implement a validator independent from PuLP's own constraints.

Suggested file:

``` text
app/validation/schedule_validator.py
```

For every hour verify:

-   correct hour;
-   non-negative grid;
-   non-negative solar usage;
-   solar usage does not exceed effective solar;
-   valid battery action;
-   non-negative `battery_kwh`;
-   idle means zero `battery_kwh`;
-   charge rate;
-   discharge rate;
-   no-charge directive;
-   no-discharge directive;
-   max-grid directive;
-   battery transition;
-   capacity;
-   base minimum reserve;
-   directive minimum reserve;
-   energy balance;
-   demand satisfaction.

After hour 23 verify:

``` text
final battery ≈ initial battery
```

Then independently recalculate all aggregates.

If the validator rejects the candidate plan, **do not return it as a
successful optimization response**.

------------------------------------------------------------------------

# 19. Numeric Precision

Organizer comparisons normally use absolute tolerance of approximately:

``` text
0.01 kWh
0.01 BDT
```

unless the official judge package specifies stricter values.

Internally:

-   keep full solver precision;
-   do not round intermediate battery transitions;
-   avoid exact floating-point equality;
-   use a tighter internal tolerance where practical;
-   normalize public output carefully.

------------------------------------------------------------------------

# 20. Plan Summary

Generate `plan_summary` deterministically from the actual directives and
resulting plan.

Do not make a second LLM request solely for summary generation.

Reasons:

-   lower latency;
-   fewer OpenRouter calls;
-   lower rate-limit risk;
-   fewer provider failures;
-   no hallucinated strategy.

------------------------------------------------------------------------

# 21. Performance Requirements

Organizer requirements include:

``` text
GET /health ready within 60 seconds of service start
POST /optimize-energy timeout: 30 seconds
```

Latency scoring:

``` text
p95 <= 5 s       → full latency points
>5 s to 15 s     → reduced
>15 s to 30 s    → further reduced
>30 s            → timeout/failure
```

Development target:

``` text
p95 < 5 seconds
```

During profiling measure separately:

-   request validation;
-   OpenRouter latency;
-   guardrails;
-   directive application;
-   optimizer;
-   final validator;
-   total endpoint latency.

Prefer:

-   one LLM request for all notes;
-   concise prompt;
-   small output;
-   bounded retry;
-   deterministic summary;
-   reusable HTTP client where safe.

------------------------------------------------------------------------

# 22. Scoring Priorities

Base score: **100 points**.

  Category                                           Points
  ------------------------------------------------ --------
  LLM Directive Interpretation                           25
  Directive Application & Constraint Correctness         25
  Optimization Quality                                   10
  API Contract & Schema                                  10
  Performance & Reliability                              10
  Deployment & Docker Fallback                           10
  Documentation & Local Reproducibility                  10

Interpretation scoring includes relevance/`no_op`, directive type,
affected hours, numeric values/adjustment shape, and paraphrase
robustness.

The judge evaluates the solution as a pipeline:

``` text
understand
→ validate
→ apply
→ satisfy constraints
→ optimize
```

A low-cost schedule based on a wrong directive is not a correct
solution.

------------------------------------------------------------------------

# 23. Critical Evaluation Behavior

The judge has organizer ground truth.

It does **not** simply trust our `directive_interpretation`.

Therefore:

-   incorrectly reporting a real directive as `no_op` does not make the
    true constraint disappear;
-   a correctly extracted directive that is not applied to the schedule
    is still a failure;
-   the judge independently replays battery state;
-   the judge independently checks energy balance;
-   the judge independently checks effective solar;
-   the judge independently checks directive constraints;
-   the judge independently checks end-of-day battery neutrality;
-   totals are recalculated from the hourly plan.

Invalid hidden cases receive no optimization credit for that case.

Absence of the required LLM from the operator-note interpretation path
is a mandatory-requirement failure and affects shortlist eligibility.

------------------------------------------------------------------------

# 24. Hidden Tests

Expect hidden tests to vary:

-   paraphrasing;
-   12-hour/24-hour time expressions;
-   percentages;
-   fractions;
-   equivalent numeric wording;
-   demand;
-   solar;
-   tariffs;
-   battery state;
-   capacity;
-   reserve/rate limits;
-   compatible directive combinations.

Every hidden scoring note maps to exactly one supported directive type
or `no_op`.

Hidden tests do not require an unpublished seventh directive.

Equivalent valid optimal schedules may differ.

Never hard-code:

-   public scenario IDs;
-   public note text;
-   public numerical values;
-   reference schedules;
-   phrase lookup tables.

------------------------------------------------------------------------

# 25. Repository Structure

Use a maintainable structure approximately like:

``` text
gridwise/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── request.py
│   │   ├── response.py
│   │   └── directives.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── openrouter_client.py
│   │   ├── interpreter.py
│   │   └── prompt.py
│   ├── guardrails/
│   │   ├── __init__.py
│   │   └── directive_validator.py
│   ├── optimization/
│   │   ├── __init__.py
│   │   ├── directive_application.py
│   │   ├── optimizer.py
│   │   └── result_mapper.py
│   ├── validation/
│   │   ├── __init__.py
│   │   └── schedule_validator.py
│   └── services/
│       ├── __init__.py
│       └── optimization_service.py
├── tests/
│   ├── test_health.py
│   ├── test_request_validation.py
│   ├── test_directive_models.py
│   ├── test_directive_guardrails.py
│   ├── test_directive_application.py
│   ├── test_optimizer.py
│   ├── test_schedule_validator.py
│   ├── test_llm_interpreter.py
│   ├── test_public_cases.py
│   └── test_api.py
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── .gitignore
├── .env.example
├── vercel.json          # only if needed
├── README.md
└── SPEC.md
```

Codex may improve this structure only for a concrete engineering reason.

Do not collapse the project into one large `app.py`.

------------------------------------------------------------------------

# 26. Required Tests

## 26.1 Request validation

Test:

-   valid request;
-   23 hours;
-   25 hours;
-   duplicate hour;
-   missing hour;
-   invalid hour;
-   zero notes;
-   four notes;
-   empty note;
-   invalid battery configuration;
-   malformed/non-finite values.

## 26.2 Directive models and guardrails

Test all six directives plus:

-   unsupported type;
-   wrong `applies`;
-   wrong adjustment shape;
-   duplicate hours;
-   unsorted hours;
-   hour `-1`;
-   hour `24`;
-   missing numeric value;
-   non-finite numeric value;
-   `no_op` with non-null adjustment;
-   real directive with null adjustment.

## 26.3 Time semantics

Explicitly verify:

``` text
1 PM–3 PM → [13,14]
2 PM–4 PM → [14,15]
6 PM–9 PM → [18,19,20]
```

## 26.4 Solar semantics

Explicitly verify:

``` text
80% reduction → factor 0.2
20% remaining → factor 0.2
```

## 26.5 Optimizer

Test:

-   baseline/no-op;
-   each directive independently;
-   compatible multiple directives;
-   tariff shifting;
-   solar curtailment;
-   capacity;
-   minimum battery;
-   charge rate;
-   discharge rate;
-   end-of-day neutrality.

Use small manually understandable scenarios.

## 26.6 Validator mutation tests

Start from a valid plan and deliberately corrupt:

-   grid;
-   solar;
-   battery state;
-   capacity;
-   reserve;
-   charge during no-charge;
-   discharge during no-discharge;
-   grid cap;
-   charge rate;
-   discharge rate;
-   final battery;
-   idle action with nonzero `battery_kwh`.

The independent validator must reject each corruption.

## 26.7 LLM tests

Normal automated tests must mock OpenRouter.

Test:

-   valid structured response;
-   malformed JSON;
-   schema mismatch;
-   timeout;
-   429;
-   provider 5xx;
-   missing API key;
-   invalid directive;
-   invalid hours;
-   missing adjustment.

Real OpenRouter integration tests must be optional and run only when
credentials/model are configured.

------------------------------------------------------------------------

# 27. Paraphrase Evaluation

Create an internal semantic test corpus beyond organizer public notes.

Include multiple ways of expressing every directive:

-   12-hour clock;
-   24-hour clock;
-   "from one until three";
-   percentages;
-   fractions;
-   "one-fifth remains";
-   "four-fifths unavailable";
-   reserve wording;
-   charging unavailable wording;
-   discharge prohibition wording;
-   grid-cap wording;
-   irrelevant campus chatter.

Measure:

-   relevance/`no_op`;
-   directive type;
-   hours;
-   numeric extraction;
-   adjustment shape.

Fix general prompt/schema weaknesses only. Never add
public-case-specific branches.

------------------------------------------------------------------------

# 28. Public Sample Validation

Run all organizer public cases.

For each case report:

  Field                         Result
  ----------------------------- -----------
  Case                          ID
  Interpretation                pass/fail
  Directive application         pass/fail
  Schedule validity             pass/fail
  Our recalculated cost         value
  Reference cost, if supplied   value
  Difference                    value
  Total latency                 value

Equivalent valid optimal schedules do not need byte-for-byte equality
with a reference schedule.

Investigate mathematical/semantic discrepancies, not formatting
differences alone.

------------------------------------------------------------------------

# 29. Security

Never commit:

``` text
.env
API keys
tokens
passwords
credentials
```

`.env.example` contains placeholders only.

Never:

-   log `OPENROUTER_API_KEY`;
-   expose it in exceptions;
-   include it in README;
-   include it in `vercel.json`;
-   bake it into Docker;
-   commit provider Authorization headers.

Audit repository history before submission.

------------------------------------------------------------------------

# 30. Docker Fallback

The organizer requires a working pullable Docker fallback image.

The same FastAPI application must run in Docker.

Conceptual local verification:

``` bash
docker build -t gridwise .

docker run \
  -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  -e OPENROUTER_MODEL="$OPENROUTER_MODEL" \
  -p 8000:8000 \
  gridwise
```

Then:

``` text
GET http://localhost:8000/health
```

must return:

``` json
{"status":"ok"}
```

Credentials are injected at runtime only.

Document exact pull/run commands for the final published image.

------------------------------------------------------------------------

# 31. Vercel Deployment

Primary deployment decision: Vercel.

Requirements for our deployment:

-   public HTTPS base URL;
-   `/health` externally reachable;
-   `/optimize-energy` externally reachable;
-   no login/VPN/manual approval;
-   OpenRouter secrets configured as deployment environment variables;
-   same core application remains runnable locally and in Docker.

Do not claim deployment success until both endpoints have been
externally tested.

------------------------------------------------------------------------

# 32. README Requirements

The final README must be self-contained and include:

1.  project overview;
2.  architecture;
3.  processing pipeline;
4.  local setup;
5.  Python version;
6.  dependency installation;
7.  environment-variable names;
8.  OpenRouter provider;
9.  selected model/configuration;
10. exact role of the LLM;
11. deterministic guardrails;
12. optimizer/solver;
13. independent validator;
14. exact local run command;
15. `/health` example;
16. `/optimize-energy` example;
17. public sample validation procedure;
18. pytest commands;
19. Docker build/run/pull instructions;
20. Vercel deployment/configuration;
21. dependencies;
22. known limitations;
23. secret-handling guidance.

A judge should be able to reproduce the service from a clean environment
without team intervention.

------------------------------------------------------------------------

# 33. Final Deliverables

Treat this as a deployed-system submission, not just a code submission.

Final organizer-required artifacts include:

-   one HTTP API service;
-   publicly reachable endpoint;
-   `GET /health`;
-   `POST /optimize-energy`;
-   source repository;
-   self-contained README;
-   model/provider disclosure;
-   optimizer/solver disclosure;
-   pullable Docker fallback image;
-   required architecture/solution video;
-   submission links/details required by the Participant Guide.

The repository policy and exact submission procedure must be followed
from the Participant Guide.

------------------------------------------------------------------------

# 34. Video

The required video must be accessible and no longer than 3 minutes.

It should clearly explain:

-   problem understanding;
-   architecture;
-   solution flow;
-   LLM interpretation;
-   deterministic guardrails;
-   optimizer;
-   how to run/test the submission.

The rubric uses the video as a tie-break, not part of the base 100
points.

Do not prioritize video polish over system correctness.

------------------------------------------------------------------------

# 35. Phase-Gated Development Process

Codex must work phase by phase.

## Phase 0 --- Specification Audit

**No implementation changes.**

Tasks:

1.  read all organizer artifacts;
2.  inspect repository;
3.  compare this `SPEC.md` against organizer documents;
4.  identify conflicts;
5.  identify ambiguities;
6.  identify existing implementation/dependencies;
7.  propose architecture.

Return:

-   challenge understanding;
-   mandatory deliverables;
-   exact API contract;
-   six directives and mathematical effects;
-   energy/battery rules;
-   scoring;
-   performance thresholds;
-   critical penalties;
-   hidden-test expectations;
-   proposed repository architecture;
-   proposed dependencies;
-   specification questions;
-   conflicts with `SPEC.md`.

**STOP. Wait for approval.**

## Phase 1 --- Skeleton and Health

Implement:

-   package structure;
-   FastAPI app;
-   config;
-   dependencies;
-   `.gitignore`;
-   `.env.example`;
-   pytest setup;
-   `GET /health`.

Run tests and report.

**STOP.**

## Phase 2 --- Exact API Models

Implement:

-   request models;
-   response models;
-   structural/semantic validation.

No LLM. No optimizer.

Run tests and report.

**STOP.**

## Phase 3 --- Directive Domain and Guardrails

Implement:

-   all six typed directive models;
-   deterministic validation;
-   normalization allowed by the specification.

No OpenRouter.

Run exhaustive tests.

**STOP.**

## Phase 4 --- OpenRouter Interpreter

Implement:

-   OpenRouter client;
-   prompt;
-   structured output;
-   parsing;
-   timeout;
-   bounded retry;
-   provider error handling.

Use mocks first.

If credentials are available, optionally run a real integration test and
report model + latency.

**STOP.**

## Phase 5 --- Directive Application

Implement deterministic 24-hour constraints:

-   effective solar;
-   reserve floors;
-   charge permission;
-   discharge permission;
-   grid caps.

Test each directive and combinations.

**STOP.**

## Phase 6 --- Optimizer

Implement PuLP/CBC:

-   energy balance;
-   solar bounds;
-   battery transitions;
-   battery bounds;
-   rate limits;
-   directive constraints;
-   final neutrality;
-   grid-cost objective.

Test manually understandable scenarios.

**STOP.**

## Phase 7 --- Independent Validator

Implement schedule replay independently from PuLP.

Mutation-test valid plans by corrupting them.

**STOP.**

## Phase 8 --- Complete Endpoint

Implement full `POST /optimize-energy` pipeline:

``` text
request validation
→ OpenRouter
→ guardrails
→ directive application
→ optimizer
→ result mapping
→ independent validation
→ aggregate recalculation
→ deterministic summary
→ response
```

Add controlled errors.

Run integration tests.

**STOP.**

## Phase 9 --- Organizer Public Cases

Run all public cases.

Produce a case-by-case validation table.

Never hard-code a fix for one sample.

**STOP.**

## Phase 10 --- Paraphrase Robustness

Create additional paraphrases for all directive types and `no_op`.

Measure semantic extraction accuracy.

Improve general prompt/schema/guardrails only.

**STOP.**

## Phase 11 --- Performance

Measure:

-   OpenRouter;
-   optimizer;
-   validator;
-   total;
-   p50;
-   p95.

Target p95 \< 5 seconds.

Optimize based on evidence.

**STOP.**

## Phase 12 --- Docker

Build and run a clean image.

Verify:

-   startup;
-   `/health`;
-   `/optimize-energy`;
-   runtime secret injection;
-   no baked credentials.

**STOP.**

## Phase 13 --- Vercel

Deploy.

Externally verify both endpoints and latency.

**STOP.**

## Phase 14 --- Final Compliance Audit

Read organizer documents again.

Produce:

  Requirement   Implementation   Test/Evidence   Status
  ------------- ---------------- --------------- --------

Run:

-   complete pytest;
-   all public cases;
-   paraphrase suite;
-   Docker test;
-   deployed endpoint test;
-   secret scan.

Do not mark the project submission-ready while a mandatory requirement
remains unverified.

------------------------------------------------------------------------

# 36. Codex Operating Rules

Before each phase:

1.  state what will change;
2.  state which organizer requirements it satisfies.

After each phase:

1.  run relevant tests;
2.  provide exact results;
3.  list files changed;
4.  summarize implementation;
5.  identify risks;
6.  identify specification questions;
7.  identify implementation decisions;
8.  stop before the next major phase.

Never claim something works if it can be tested.

Never silently alter organizer schemas.

Never introduce unsupported battery/energy assumptions.

Never hard-code public examples.

Never make large unrelated refactors during a phase.

Never expose secrets.

------------------------------------------------------------------------

# 37. Non-Negotiable Architecture Boundary

``` text
┌─────────────────────┐
│ Operator Notes      │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ OpenRouter LLM      │
│ semantic extraction │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Typed Interpretation│
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Guardrails          │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Directive Layer     │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ PuLP / CBC          │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Candidate Schedule  │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Final Validator     │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Recalculated Output │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ API Response        │
└─────────────────────┘
```

Provider/model-specific code must not leak into mathematical scheduling
or validation.

------------------------------------------------------------------------

# 38. Core Development Principle

Always preserve this sequence:

``` text
UNDERSTAND
    ↓
VALIDATE INTERPRETATION
    ↓
APPLY DIRECTIVE
    ↓
OPTIMIZE
    ↓
INDEPENDENTLY VALIDATE
    ↓
RECALCULATE
    ↓
RETURN
```

Never:

``` text
LLM → blindly trust → response
```

Never:

``` text
public phrase → hard-coded mapping → response
```

Never:

``` text
optimizer → blindly trust → response
```

Never:

``` text
invalid schedule → return because it is cheaper
```

**Correctness first. Optimization second.**

------------------------------------------------------------------------

# 39. Codex Start Command

When Codex receives this file for the first time, it must begin with:

> Read `SPEC.md` and all organizer-provided Problem Statement,
> Participant Guide/Evaluation Rubric, and Public Sample Cases
> completely. Then perform **Phase 0 --- Specification Audit only**. Do
> not modify implementation files yet. If `SPEC.md` conflicts with an
> organizer artifact, report the conflict and follow the organizer
> artifact. Do not guess missing rules.
