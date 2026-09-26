# FixOps

> **FixOps is an AI-powered self-healing system that detects application errors, finds their root cause, generates a fix, tests it, and applies it — reducing the amount of manual work required from developers and DevOps engineers.**

> Today, when software breaks, humans have to find the problem, understand it, fix it, and test the solution. FixOps automates this entire loop.

FixOps turns error detection into an automated repair loop:

```
Find  ->  Understand  ->  Fix  ->  Test  ->  Apply
```

* **Find** — detects an error in a running application (from container logs).
* **Understand** — indexes the codebase, builds a call graph, and locates the root-cause function.
* **Fix** — an LLM generates a patch and a regression test.
* **Test** — applies the change in an isolated working copy and verifies it with tests.
* **Apply** — after successful verification, rebuilds the container and commits/pushes the fix to git.

---

## The problem

A modern application is a web of services, containers, dependencies, and code. When something breaks, the process looks like this:

```
error -> alert -> DevOps/developer reads logs -> finds the cause
      -> locates the faulty code -> writes a fix -> tests it -> deploys
```

This is slow and needs a human at every step. Existing self-healing mechanisms (for example, Kubernetes) mostly repair the **infrastructure** — they restart crashed containers — but they do **not** fix the bug in the application code.

As a result, the system usually only reports an error, and a human still has to understand it, fix the code, and make sure the fix actually works.

## What FixOps does

FixOps runs the full **diagnose -> remediate -> verify** loop:

1. listens to the stdout of containers labeled `fixops.enabled=true`;
2. recognizes a structured ERROR record and extracts the error coordinates (`file`, `line`, `function`, `error`);
3. statically indexes the project (AST) and builds a call graph;
4. matches the error to a graph node and collects the `callers -> error -> callees` chain;
5. feeds the LLM the real source code of that chain and asks for a patch plus a test;
6. applies the patch, runs the tests and `reproduce.py` (if present);
7. on failure, resets the project and retries (up to `ANALYSIS_MAX_FIX_ATTEMPTS`);
8. shows progress and results in the web dashboard; after success, the fix can be deployed to git with one click.

---

## How it works

### Pipeline (LangGraph)

Orchestration lives in `backend/services/workflow.py` and is a state graph:

```
                 ┌───────────┐
                 │  indexer  │  AST index of the project
                 └─────┬─────┘
                       v
                 ┌─────────────┐
                 │graph_builder│  call graph
                 └─────┬───────┘
                       v
                 ┌──────────────┐
                 │error_analyzer│  error -> node + callers/callees
                 └──────┬───────┘
              node not found ──> END
                       v
                ┌───────────────┐
                │context_builder│  real function source -> prompt
                └──────┬────────┘
                       v
                    ┌──────┐
                    │ llm  │  DeepSeek: patch + test
                    └──┬───┘
                       v
                  ┌───────────┐
                  │ apply_fix │  SEARCH/REPLACE + write test
                  └─────┬─────┘
            applied ────> run_tests
            not applied and attempts exhausted ──> END
                       v
                  ┌───────────┐
                  │ run_tests │  pytest (+ reproduce.py)
                  └─────┬─────┘
              success ───> END
              otherwise -> reset_project (git reset --hard) -> indexer
```

### Steps

| Node | File | What it does |
|---|---|---|
| `indexer` | `code_intel/indexer.py` | walks `.py` files and extracts imports, classes, functions, calls, and local type assignments via `ast`. Code is never executed. |
| `graph_builder` | `code_intel/graph.py`, `resolver.py` | resolves calls (imports, `self`, local constructions) and builds the call graph. |
| `error_analyzer` | `code_intel/error_analyzer.py` | finds the node by `file` + `function` from the log, recursively collects callers and callees, and proposes root-cause candidates. |
| `context_builder` | `code_intel/context_builder.py` | pulls the real source of every node in the chain (with imports, class docstring, and decorators) and renders a strict LLM prompt with output-format rules. |
| `llm` | `ai/deepseek.py` | sends the prompt to DeepSeek and keeps the conversation history. |
| `apply_fix` | `code_intel/executor.py` | parses the ` ```fix ` / ` ```test ` blocks, applies `SEARCH/REPLACE` (exact/normalized/fuzzy matching), and writes the test file. |
| `run_tests` | `code_intel/executor.py` | runs `pytest` (or `test_command`), classifies the result (`SUCCESS` / `CODE_FAILURE` / `INFRA_FAILURE`), and runs `reproduce.py` if present. |
| `reset_project` | `services/workflow.py` | `git reset --hard`, removes `.fixops/` and `tests/`, then restarts the pipeline. |

### Events and dashboard

Progress is streamed to the frontend over WebSockets (`/api/ws`, `/api/ws/jobs/{job_id}`). The `@log_execution` decorator on every node emits `node_started` / `node_completed` / `node_failed`, while `AnalyzeJob` emits `workflow_started` / `workflow_finished`.

The dashboard (`frontend/`, React + TypeScript + Vite):

* `/dashboard/` — **Overview**: system health, counters (Monitored / Healthy / Incidents / Repairs), and the container list;
* `/dashboard/containers` — **Containers**: monitored Docker workloads;
* `/dashboard/incidents` — **Incidents**: incident history (stored in Postgres, survives reloads);
* `/dashboard/incidents/{jobId}` — **Incident Detail**: workflow steps, AI context and diagnosis, fix diff, verification result, and Apply / Rollback buttons.

The FixOps landing page is the main screen (`/`); the **Open Dashboard** button leads to `/dashboard/`.

---

## Quick start

You need Docker and Docker Compose, plus access to the Docker host (FixOps manages containers).

```bash
cp .env.example .env      # fill in the variables (see "Environment variables")
docker compose up --build -d
```

Services:

| Service | Address | Purpose |
|---|---|---|
| `frontend` | `http://<host>:3000/` | landing page; dashboard at `http://<host>:3000/dashboard/` |
| `fixops` | `http://<host>:8000/` | backend API; Swagger at `/api/docs` |
| `postgres` | internal network | incident history |
| `redis` | internal network | LLM conversation history |

FixOps mounts:

* `/var/run/docker.sock` — to see and manage containers;
* `/home/virtu/projects:/projects` — working copies of monitored projects (inside FixOps);
* the same `/home/virtu/projects:/home/virtu/projects` — so `docker compose` can work with host paths;
* `/home/virtu/.ssh:/root/.ssh:ro` — SSH key for `git push` (mounted **read-only**).

Running without Docker:

```bash
# backend
uvicorn api.main:app --reload --port 8000          # from the backend/ folder

# frontend
cd frontend && npm install && npm run dev          # http://localhost:5173/
```

---

## Connecting your own project

FixOps needs three things: a **host path**, a **git repository**, and **structured logs**. In addition, the monitored container must **mount its source code** so FixOps can read it (see step 3).

### 1. Put the project on the host

The project source must live under `PATH_HOST_PROJECTS_ROOT` (default `/home/virtu/projects`), for example:

```
/home/virtu/projects/orderflow
```

The same directory is mounted into FixOps as `/projects/orderflow`, so `fixops.project_path=/projects/orderflow`.

### 2. Label the container for FixOps

| Label | Value | Required |
|---|---|---|
| `fixops.enabled` | `"true"` — enables monitoring | yes |
| `fixops.project_path` | path inside FixOps, e.g. `/projects/orderflow` | yes |
| `fixops.project` | human-readable project name | no |

### 3. Grant FixOps read access to the source in docker-compose

FixOps reads the project source from the shared `PATH_HOST_PROJECTS_ROOT` mount, and it maps every path from a traceback (for example `/app/services/pricing.py`) onto that directory. For the running code and the source FixOps reads to be the same, the monitored service must **bind-mount its project directory into the container**.

Add a `volumes:` entry and set `working_dir` to the mount target, so log paths resolve to the project root FixOps sees:

```yaml
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile

    container_name: orderflow-backend

    restart: unless-stopped

    # The code that shows up in tracebacks is /app/... , so the container
    # runs from /app and /app must map to the project root FixOps reads
    # ( /projects/orderflow  <->  /home/virtu/projects/orderflow ).
    working_dir: /app
    volumes:
      # Read access to the project source. Use :ro if the app never writes
      # to its own code; omit :ro if it does. This is what lets FixOps read
      # the exact code that produced the error.
      - /home/virtu/projects/orderflow:/app:ro

    ports:
      - "8001:8001"

    labels:
      # FixOps should monitor this container.
      fixops.enabled: "true"

      # Project name.
      fixops.project: "orderflow"

      # Path to the source project in the filesystem FixOps sees.
      fixops.project_path: "/projects/orderflow"

    networks:
      - orderflow

  frontend:
    image: python:3.12-slim

    container_name: orderflow-frontend

    working_dir: /app
    volumes:
      - ./frontend:/app

    command: python -m http.server 3001 --bind 0.0.0.0

    ports:
      - "3001:3001"

    restart: unless-stopped

    networks:
      - orderflow

networks:
  orderflow:
    driver: bridge
```

Rules of thumb:

* The container's `working_dir` (here `/app`) plus the code layout must match the host project that `fixops.project_path` points to. The path mapping is: `/app/services/pricing.py` -> `services/pricing.py` -> `/projects/orderflow/services/pricing.py` `-> /home/virtu/projects/orderflow/services/pricing.py`.
* If the backend code sits in a subdirectory (`orderflow/backend/...`), point `fixops.project_path` at that subdirectory (`/projects/orderflow/backend`) or mount it accordingly, so the mapping stays correct.
* The mount can be read-only (`:ro`) — FixOps reads the source itself; it writes patches through its own `/projects` mount, not through the monitored container.

### 4. Project requirements

* **A git repository.** FixOps uses git to roll back (`git reset --hard`, `git restore`) and to record the result (`add` + `commit` + `push`). Pushing needs a configured remote and credentials (in the provided compose, an SSH key is mounted at `/root/.ssh` **read-only**).
* **A predictable layout.** Code that appears in logs must live in the container's working directory so traceback paths map unambiguously to project files.
* **Tests.** `python -m pytest` runs by default. The test generated by the LLM is written into `tests/`.
* **`reproduce.py` (optional).** If `reproduce.py` exists in the project root, it runs after the tests to confirm the bug is reproduced/fixed.
* **Logs with error coordinates** (see the next section).

---

## Project logging setup

FixOps reads the **container's stdout** and expects **one JSON record per line**. A ready-made logging stack lives in `backend/core/` — copy it into your project as a `core/` package:

| File | Purpose |
|---|---|
| `core/logging.py` | loguru configuration: JSON to stdout and to a file, plus `app_logger` and `get_logger(event, **context)`. |
| `core/decorators.py` | the `@log_execution(event=...)` decorator — automatically logs a function's start/success/failure and its arguments (with secret masking). |
| `core/middleware.py` | a FastAPI middleware that adds `X-Request-ID` (for HTTP services). |

### `core/logging.py`

On first import the module:

* reads `APP_SERVICE_NAME` (service name in every record), `APP_ENV`, and `APP_LOG_DIR` (log file folder);
* with `APP_ENV=production` writes JSON to **stdout** (`serialize=True`) — this is the format FixOps reads;
* always also writes JSON to `<APP_LOG_DIR>/app.log` (10 MB rotation, 7-day retention, `.gz` compression).

```python
from core.logging import get_logger

log = get_logger(event="inventory.get", sku="SKU-999")
log.info("Requested SKU")
```

`get_logger` adds `event` and a unique `event_id` to every record, plus any fields you pass.

### `core/decorators.py`

The main tool is `@log_execution`. It supports both sync and async functions:

```python
from core.decorators import log_execution
from core.logging import get_logger


@log_execution(event="pricing.calculate_total")
def calculate_total(self, items):
    log = get_logger(event="pricing.calculate_total")
    ...
    log.debug("Total calculated")
    return total
```

On every call the decorator writes:

* **DEBUG** `"Function started"`;
* **INFO** `"Function completed"` with `status="success"`, `severity="INFO"`, `duration_ms` — on success;
* **ERROR** `"Function failed"` via `log.exception(...)` (with the full traceback) — on exception, after which it **re-raises**.

The ERROR record carries the **error coordinates** that FixOps looks for:

| Field | Source |
|---|---|
| `file` | last traceback frame (`last.filename`) |
| `line` | `last.lineno` |
| `function` | `last.name` |
| `error` | `{"type": <exception class>, "message": <text>}` |

Before writing, the function arguments pass through `sanitize()`: the keys `password`, `token`, `access_token`, `refresh_token`, `authorization`, `api_key`, `secret` become `"***"`, and unknown objects become `"<ClassName>"`.

### Example JSON record

```json
{
  "text": "Order failed",
  "record": {
    "level": { "name": "ERROR" },
    "message": "Function failed",
    "extra": {
      "service": "orderflow",
      "environment": "production",
      "event": "pricing.calculate_total",
      "event_id": "0f7c2c2e-...",
      "status": "error",
      "severity": "ERROR",
      "duration_ms": 1.27,
      "file": "/app/services/pricing.py",
      "line": 12,
      "function": "calculate_total",
      "error": {
        "type": "AttributeError",
        "message": "'NoneType' object has no attribute 'price'"
      },
      "arguments": { "args": ["..."], "kwargs": {} }
    }
  }
}
```

FixOps treats a record as an error when `record.level.name == "ERROR"` or `record.extra.severity == "ERROR"`. The required coordinate keys are configured by `ANALYSIS_REQUIRED_ERROR_KEYS` (default `file`, `function`, `line`, `error`). A path like `/app/...` is stripped to its relative part and joined with the project root.

Additional behavior:

* a repeated identical error within 2 seconds is ignored (loop protection);
* `HTTPException` is not treated as an application error and is skipped;
* only the log tail is read (`ANALYSIS_LOG_TAIL_LINES`), not the whole file.

### Usage rules

* use `event` in `<domain>.<action>` notation (`pricing.calculate_total`);
* do not wrap a function in `try/except` just to log — the decorator already logs and re-raises;
* use loguru `{}` placeholders, not `%s` from the standard `logging` module;
* avoid putting secrets in arguments, but if you do, `sanitize()` masks them on failure.

A deeper walkthrough (including middleware and a logging cheat sheet) is in `LOGGING_README.md`.

---

## Environment variables

All settings are read from `.env` (pydantic-settings). The main variables:

```dotenv
# ---- Error analysis ----
ANALYSIS_MAX_FIX_ATTEMPTS=5
ANALYSIS_EXTRA_IGNORE_DIRS=[]
ANALYSIS_LOG_TAIL_LINES=5
ANALYSIS_REQUIRED_ERROR_KEYS=["file","function","line","error"]

# ---- Project paths ----
PATH_HOST_PROJECTS_ROOT=/home/virtu/projects
PATH_FIXOPS_PROJECTS_ROOT=/projects

# ---- Redis (LLM conversation history) ----
REDIS_NAME=0
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=redispass

# ---- Postgres (incident history) ----
POSTGRES_NAME=my_db
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# ---- Application ----
APP_SERVICE_NAME=fixops
APP_ENV=development
APP_LOG_DIR=logs

# ---- LLM ----
DEEPSEEK_TOKEN=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ---- Frontend ----
VITE_API_URL=http://<host>:8000
```

| Variable | Description |
|---|---|
| `ANALYSIS_MAX_FIX_ATTEMPTS` | how many repair attempts to make before giving up. |
| `ANALYSIS_EXTRA_IGNORE_DIRS` | extra directories excluded from AST indexing. |
| `ANALYSIS_LOG_TAIL_LINES` | how many trailing log lines to analyze. |
| `ANALYSIS_REQUIRED_ERROR_KEYS` | keys an ERROR record must contain to be treated as error coordinates. |
| `PATH_HOST_PROJECTS_ROOT` | projects path on the host (needed for `docker compose`). |
| `PATH_FIXOPS_PROJECTS_ROOT` | the same path inside the FixOps container. |
| `REDIS_*` | Redis connection (message history). `REDIS_HOST` must match the service name in `docker-compose.yml` (`redis`). |
| `POSTGRES_*` | Postgres connection (the `incident_results` table). |
| `APP_SERVICE_NAME` / `APP_ENV` / `APP_LOG_DIR` | FixOps' own service name, environment, and log folder; set `APP_ENV=production` in a monitored project's container to get JSON logs. |
| `DEEPSEEK_TOKEN` | DeepSeek API key. Keep it only in `.env`; never commit it. |
| `VITE_API_URL` | backend base URL used when building the frontend. |

> Keep secrets (`DEEPSEEK_TOKEN`, DB/Redis passwords) in `.env` — the file is in `.gitignore`.

---

## API

All endpoints are prefixed with `/api`:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api` | health check. |
| `GET` | `/api/containers` | containers labeled `fixops.enabled=true`. |
| `POST` | `/api/containers/{id}/apply` | `docker compose down/up --build` + commit/push. |
| `POST` | `/api/containers/{id}/rollback` | `git restore .` in the project. |
| `GET` | `/api/incidents` | incident history (summary cards). |
| `GET` | `/api/incidents/{job_id}` | full incident details. |
| `POST` | `/api/incidents/{job_id}/apply` | apply the fix and record it in the DB. |
| `POST` | `/api/incidents/{job_id}/rollback` | revert the fix. |
| `WS` | `/api/ws` | global stream: `job_started`. |
| `WS` | `/api/ws/jobs/{job_id}` | workflow progress for a specific job. |

Swagger UI: `/api/docs`.

### The two meanings of "apply"

* **`apply_fix` (inside the workflow)** — the LLM patch is written into the project working copy (`/projects/<name>`) and a test is created. This is not a deploy yet.
* **Apply in the dashboard** (`/api/.../apply`) — after tests pass, the container is rebuilt (`docker compose down/up --build`), and the changes are committed and pushed to git.

Until the fix is applied with the button, it can always be discarded (`git reset --hard` / Rollback).

---

## Repository structure

```
backend/
  api/            FastAPI routers: containers, incidents, ws, main
  ai/             LLM providers (DeepSeek), conversation history
  code_intel/     AST indexing, resolver, graph, error analysis, context, executor
  core/           logging, @log_execution decorator, events, middleware, DB/Redis
  services/       workflow (LangGraph), docker-watcher, container-manager, git
  db/             Postgres and Redis models
  config.py       settings from .env

frontend/
  index.html          landing page (main screen, /)
  dashboard/          dashboard entry (/dashboard)
  src/
    pages/            Overview, Containers, Incidents, IncidentDetail
    components/       Sidebar, Workflow, AIAnalysis, DiffViewer, Verification, ...
    hooks/            useAppState, useMonitorSocket, useJobSocket
    services/api.ts   the only place that talks to the REST API
    styles/           tokens and component styles

docker-compose.yml  postgres + redis + fixops + frontend
LOGGING_README.md   detailed logging/decorator documentation
```

---

## Limitations

* Call resolution is heuristic (imports, `self`, local `x = ClassName()`). Dynamic polymorphism and chains like `ClassName().method()` may resolve imprecisely.
* Only the log tail is read (`ANALYSIS_LOG_TAIL_LINES`): if many records sit between the error and the end of the log, increase the value.
* Auto-repair targets Python projects with a clear structure and test coverage.
* The dashboard shows no CPU/memory: the backend does not provide those metrics, so the UI contains no fake data.

---

## Team

**CoreDev** — Margarita · Daniil · Maksim
