# MarketPulse — Engineering Log

> Internal documentation. Captures architecture decisions, trade-offs,
> pivots, and reasoning behind every version.
> This document prioritizes *why* over *what* — the README covers what exists.

---

## V1 — Batch Ingestion

### What was built

An end-to-end batch ingestion pipeline collecting European tech job postings from the Adzuna API and exposing them via REST endpoints.

Components: Adzuna API (source) → `ingest.py` (fetch + normalize) → PostgreSQL via SQLAlchemy ORM → FastAPI (REST exposure). All services containerized with Docker Compose. A single `docker-compose.yml` runs PostgreSQL; the application and FastAPI layer run directly.

---

### What was considered and rejected

**Kafka for streaming ingestion** was in the original V2 roadmap. Rejected before implementation. MarketPulse's data source is a REST API polled on a schedule — a fundamentally batch pattern. Kafka solves a real-time streaming problem that does not exist here. Introducing it would add infrastructure complexity (brokers, topics, consumers, offset management) without any architectural justification. The correct diagnostic question is "does the business problem require streaming?" — the answer was no. Kafka was dropped not as a convenience but as a deliberate signal that the architecture should match the data flow, not the other way around. This decision is documented explicitly in the README as an intentional reversal.

**PySpark for analytics** was also on the original roadmap. Rejected for the same reason: PySpark's value is distributed processing of large-scale data. MarketPulse processes tens of thousands of job postings, not billions of rows. Forcing Spark in would repeat the Kafka mistake — complexity without a problem to solve. Deferred to post-PFE learning as a standalone topic.

---

### Key decisions and trade-offs

**SQLAlchemy ORM over raw psycopg2:** Chosen for V1 because the FastAPI layer benefits from ORM-style models (Pydantic schema integration, cleaner endpoint code). Trade-off: slightly more abstraction than needed for a pure ingestion script. This was addressed in the learning track by writing `script_classic.py` separately using raw psycopg2 — proving the lower-level pattern works without disrupting the project codebase.

**FastAPI retained as a V1 artifact:** FastAPI exposes raw job postings via REST. As dbt transformation models are added in V3, the API should ideally serve mart data rather than raw postings. Decision: leave FastAPI in place and update its endpoints in V4/V5 rather than removing it now. Removing a working component mid-project introduces risk with no immediate benefit.

**Idempotency via `external_id`:** The ingestion script uses Adzuna's job ID as `external_id` with `ON CONFLICT (external_id) DO NOTHING`. This makes the script safe to run multiple times without producing duplicate rows. The constraint is enforced at the database level, not in application logic — meaning it survives code refactors.

---

### Pivots and discoveries during build

**Recognition-recall gap discovered post-V1:** V1 was built with AI assistance and served as the foundation. The key discovery in the post-V1 phase was that the codebase could be read but not reproduced from scratch — the recognition-recall gap. This led to `script_classic.py` being built independently as a parallel learning artifact, rebuilding the same ingestion logic from scratch without AI generating the skeleton. This surfaced several implementation details that had been absorbed passively: the `psycopg2` connection lifecycle, named placeholders vs string formatting in SQL queries, the difference between `fetchall()` returning tuples vs ORM returning objects.

---

### Current state at end of V1

- Adzuna API → PostgreSQL ingestion working and idempotent
- FastAPI endpoints exposing raw job data
- Docker Compose running PostgreSQL in isolation
- GitHub: `main` branch stable with full V1 codebase
- `script_classic.py` at project root: standalone learning artifact with function-based refactor, psycopg2 direct connection, `ON CONFLICT DO NOTHING`, `fetched_at DEFAULT CURRENT_TIMESTAMP`, `try/except` on both API call and DB connection

---

## V2 — Airflow Orchestration

### What was built

Apache Airflow 2.8.1 integrated into the project via Docker Compose, running alongside the existing MarketPulse PostgreSQL instance. The environment runs five Docker services: `db` (MarketPulse PostgreSQL on port 5432), `airflow-db` (separate PostgreSQL instance for Airflow metadata only), `airflow-init` (one-shot service that runs DB migration and creates admin user), `airflow-webserver` (UI at localhost:8080), and `airflow-scheduler`. All three Airflow services are built from a custom Docker image (`FROM apache/airflow:2.8.1`) that bakes the MarketPulse project code into the image and sets `PYTHONPATH` so the `app/` module is importable inside the container.

A single DAG (`marketpulse_ingest`) runs daily at 07:00 UTC, calling the existing `run()` function from `app/scripts/ingest.py` via a `PythonOperator`. The DAG is idempotent — consecutive runs on the same data insert zero new rows. Failure alerting is configured via `email_on_failure` in `default_args`.

The V1 codebase was updated in parallel: `database.py` was refactored for SQLAlchemy 1.4 compatibility and lazy initialization, `adzuna.py` had type hint fixes for Python 3.8, `ingest.py` was refactored to import configuration from a new `app/config.py` file, and `requirements-app.txt` was introduced as a Docker-safe dependency file separate from the original `requirements.txt`.

---

### What was considered and rejected

**Installing Airflow directly on the host machine (pip install):** Considered as a simpler starting point. Rejected because: Airflow has multiple cooperating processes (webserver, scheduler, init) that need to run together, and Docker Compose manages their startup order and dependencies cleanly; a Dockerized setup is closer to production deployment patterns; the project already uses Docker for PostgreSQL — adding Airflow to the same compose file is architecturally consistent.

**Copying a docker-compose configuration from a Medium article without understanding it:** This was the initial approach. It produced a broken configuration that could not be debugged because the structure was not understood. Rejected mid-build in favor of reading the official Airflow documentation and rebuilding each section from understanding. The lesson: copying infrastructure configuration without understanding it delays problems rather than preventing them.

**Sharing the MarketPulse PostgreSQL database with Airflow's metadata:** Initially configured this way by pointing Airflow's `SQL_ALCHEMY_CONN` at the existing `db` service. Rejected because Airflow creates hundreds of internal tables (dag_run, task_instance, log, slot_pool, etc.) that would pollute the MarketPulse schema. Separated into a dedicated `airflow-db` service.

**Volume mounting instead of custom Docker image:** The first proposed solution to the `ModuleNotFoundError: No module named 'app'` error was mounting the project directory into the Airflow container at runtime (`./:/opt/airflow/marketpulse`). Rejected because it only works on the developer's local machine — the mounted path doesn't exist in any other environment. The Dockerfile approach bakes the code into the image, making it portable and production-honest. The same image artifact is what will be pushed to Azure Container Registry in V4.

**BashOperator instead of PythonOperator:** Considered as a fallback to avoid the module import complexity. Rejected because `PythonOperator` with a proper Python import is how real Airflow pipelines work. `BashOperator` calling a Python script via shell is a workaround that obscures the dependency graph and loses structured return values.

**Single `requirements.txt` for both app and Airflow dependencies:** The original plan was to install `requirements.txt` inside the Dockerfile. Rejected after it caused an `sqlalchemy.exc.ArgumentError: Invalid value for 'executemany_mode'` crash — the file contained `sqlalchemy==2.0.30` which overwrote Airflow 2.8.1's pinned SQLAlchemy 1.4.x, breaking Airflow's internal ORM. The fix was `requirements-app.txt` containing only the packages the app needs that Airflow doesn't already provide.

---

### Key decisions and trade-offs

**LocalExecutor over CeleryExecutor:** LocalExecutor runs tasks in the same process as the scheduler — simpler, no message broker required, appropriate for a single-machine setup. CeleryExecutor distributes tasks across multiple workers via a Redis or RabbitMQ broker. For MarketPulse's single daily ingestion task, CeleryExecutor would add infrastructure (Redis container, worker containers, flower monitoring) with no throughput benefit. LocalExecutor is the correct choice at this scale.

**`catchup=False` on the DAG:** With `catchup=True` (Airflow's default), if the scheduler starts after `start_date` it will attempt to backfill all missed runs. With `start_date=datetime(2026, 7, 1)` and `catchup=True`, triggering the DAG in late July would attempt to run ~25 consecutive daily runs — hitting an external API with rate limits and producing duplicate-handling overhead. `catchup=False` means only the current scheduled interval runs.

**`airflow-init` as an ephemeral service:** Rather than running `airflow db migrate` and `airflow users create` as part of the webserver or scheduler startup, these are isolated in a dedicated `airflow-init` service that runs once and exits with code 0. This separates initialization from runtime concerns, fails loudly if the metadata database is unavailable, and `depends_on: condition: service_healthy` ensures it only runs after `airflow-db` is confirmed ready.

**Two-volume separation:** `postgres_data` for MarketPulse data, `airflow-db-data` for Airflow metadata. Both are named Docker volumes that persist across `docker-compose down` but are wiped by `docker-compose down -v`. This separation means a clean Airflow reset does not touch job posting data.

**Custom Docker image over official image with volume mounts:** Baking project code into the image via `COPY . /opt/airflow/marketpulse` means every code change requires a rebuild. The trade-off is slower iteration during development in exchange for a self-contained, portable artifact that runs identically in any environment. This is the correct production pattern and directly prepares for V4 Azure deployment.

**`config.py` for keywords and countries:** Keywords and target countries were originally hardcoded inside `ingest.py`. Moved to `app/config.py` to separate *what to fetch* from *how to fetch it*. Adding a new country now means editing one file with one clear purpose. This also prepares for the future pattern of reading configuration from a database table at runtime.

**Lazy DB initialization:** `engine = create_engine(DATABASE_URL)` at module level causes `AttributeError: 'NoneType' object has no attribute '_instantiate_plugins'` when Airflow imports the DAG file during scanning — at that point environment variables are not yet injected into the process. Moving engine creation inside `get_engine()` means it only executes when `run()` is actually called by the scheduler, at which point the environment is fully configured.

---

### Pivots and discoveries during build

**`FATAL: database "airflow" does not exist` — typo invisible to casual review:** Initial hypothesis was a stale volume. Applied the standard fix (`docker-compose down` → `docker volume rm` → restart). Error persisted. Correct diagnosis required running `docker-compose config` to inspect the fully resolved configuration — revealed that `POSTGRES_DB: aiflow` (missing 'r') was a typo. PostgreSQL had created a database called `aiflow`; Airflow's connection string was looking for `airflow`. Fix: correct the typo, delete the stale volume, restart. Key lesson: `docker-compose config` is the mandatory first debugging command for any Docker Compose issue — it shows actual values after all variable substitution and YAML anchor expansion.

**YAML multiline `>` operator splitting bash commands:** After fixing the database typo, `airflow db migrate` succeeded but user creation failed with `/bin/bash: line 2: --username: command not found`. Root cause: YAML multiline string using `>` operator was being interpreted as separate bash commands. Fix: collapse the entire command onto a single line, eliminating multiline YAML parsing ambiguity.

**`AIRFLOW__CORE__SQL_ALCHEMY_CONN` vs `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN`:** Airflow 2.3+ moved the metadata database connection string from the `[core]` config section to `[database]`. Articles written before 2.3 still reference the old key. Using the old key causes Airflow to silently fall back to a SQLite database — all state appears to work locally but nothing persists correctly. The correct key for Airflow 2.8.1 is `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN`.

**Service name resolution in Docker networking — `@postgres` vs `@db`:** The initial configuration referenced `@postgres` in the connection string. The actual service name in docker-compose was `db`. Docker's internal DNS resolves container hostnames by service name — `@postgres` resolved to nothing, `@db` resolves correctly.

**`ModuleNotFoundError: No module named 'app'`:** The DAG file imports `from app.scripts.ingest import run`. Inside the Airflow container, Python has no knowledge of the `app/` directory because it lives on the host machine, not in the container. This forced the move from the planned volume-mount approach to the custom Docker image approach with `ENV PYTHONPATH="/opt/airflow/marketpulse:${PYTHONPATH}"`.

**Windows file locking blocking Docker build context:** `docker-compose build` failed with `error from sender: open C:\marketpulse\logs\scheduler\latest: The file cannot be accessed by the system.` Docker's build context transfer attempts to copy the entire project directory, including `logs/` which contains a file locked by a running Windows process. Fix: `.dockerignore` file excluding `logs/`, `__pycache__/`, `.env`, `.git/`.

**SQLAlchemy version conflict (`executemany_mode: 'values'`):** Installing `requirements.txt` inside the Dockerfile upgraded SQLAlchemy from 1.4.x (Airflow's pinned version) to 2.0.30. The `executemany_mode` parameter was renamed between versions, causing Airflow's internal `create_engine()` call to fail at startup. Resolution: `requirements-app.txt` that deliberately excludes `sqlalchemy` and `psycopg2-binary`.

**`DeclarativeBase` does not exist in SQLAlchemy 1.4:** `app/database.py` was written for SQLAlchemy 2.0 using `from sqlalchemy.orm import DeclarativeBase`. Inside the container running 1.4, this raises `ImportError`. Fix: `from sqlalchemy.orm import declarative_base` and `Base = declarative_base()` — the 1.4 factory function pattern.

**`DATABASE_URL=None` at DAG import time:** Even after fixing the `DeclarativeBase` issue, `database.py` called `create_engine(DATABASE_URL)` at module level, where `DATABASE_URL = os.getenv("DATABASE_URL")` returned `None` because environment variables are not yet available when Airflow scans and imports DAG files. Fix: restructuring the entire database module around lazy initialization.

**`list[dict]` type hint syntax fails on Python 3.8:** `app/services/adzuna.py` used `-> list[dict]:` as a return type annotation, which is only valid in Python 3.9+. The Airflow 2.8.1 base image runs Python 3.8. Fix: `from typing import List, Dict` and `-> List[Dict]`. This class of error affects any file in the codebase using built-in generic type hints.

**`DATABASE_URL` pointing to `localhost` inside Docker:** After fixing all import errors, the task failed despite the variable being present in `.env`. Root cause: `DATABASE_URL=postgresql://...@localhost:5432/MarketJobs` — inside the Airflow container, `localhost` resolves to the container itself, not the `db` service. Fix: `DATABASE_URL=postgresql://...@db:5432/MarketJobs` using the Docker Compose service name.

**Explicit env var injection required:** Even after correcting `DATABASE_URL`, `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` were not reaching the Airflow scheduler. Docker Compose does not automatically pass variables from `.env` into service environments — they must be explicitly declared in the `environment:` block of `docker-compose.yml`. The symptom was a `400 Bad Request` from Adzuna with no `app_id` or `app_key` query parameters in the URL.

**`content-type` as a query parameter:** `adzuna.py` included `"content-type": "application/json"` in the `params` dict passed to `requests.get()`. This caused it to be appended as a URL query parameter, which Adzuna rejects with a 400 error. HTTP headers and query parameters are distinct. Simplest fix: remove it entirely.

**Cron expression typo:** When changing the schedule from `@daily` to `"0 7 * * *"`, a typo produced `"*0 7 * * *"` which Airflow's cron validator rejected with `CroniterNotAlphaError`. Fix: correct the minute field.

---

### Current state at end of V2

- All five Docker services running via `docker-compose up -d`
- `marketpulse_ingest` DAG active and unpaused in Airflow UI (localhost:8080)
- DAG scheduled `0 7 * * *` (daily at 07:00 UTC), `catchup=False`
- Task `run_ingestion` confirmed successful across multiple consecutive runs
- 570+ job postings in `public.jobs` across FR, BE, DE, GB
- Idempotency confirmed: consecutive runs on unchanged data produce zero new inserts
- `email_on_failure: True` configured in `default_args`
- `app/config.py` contains `KEYWORDS` and `COUNTRIES` — decoupled from ingestion logic
- Commits pushed to `main` branch: SQLAlchemy compat fix, V2 Airflow orchestration, README rewrite
- `dev` branch created from `main` — all V3 work goes here

---

## V3 — dbt Transformation Layer

### What was built

A dbt transformation layer on top of the existing Airflow-orchestrated PostgreSQL pipeline. Five models across three layers:

- `stg_jobs` (view) — staging model selecting explicit columns from `public.jobs`, applying `TRIM`, `COALESCE` for nulls, `UPPER` for country codes, `::numeric` casts on salary fields, and `WHERE external_id IS NOT NULL` filter. Uses `{{ source('marketpulse', 'jobs') }}` macro.
- `int_jobs_enriched` (view) — intermediate model deriving two fields from staging: `seniority_level` via `CASE/WHEN LIKE` on title keywords (Senior, Lead, Junior, Alternant, Mid as default), and `salary_mid` as `ROUND((salary_min + salary_max) / 2, 2)` with NULL guard.
- `mart_top_companies` (table) — CTE counting postings per company/country, then `DENSE_RANK() OVER (PARTITION BY country ORDER BY posting_volume DESC)` for within-country ranking.
- `mart_salary_ranges` (table) — two-CTE structure: total postings per country/seniority unfiltered, salary postings filtered where `salary_mid IS NOT NULL`, joined to compute `coverage_pct = ROUND(salary_count * 100.0 / total_count, 1)`.
- `mart_skills_demand` (table) — CROSS JOIN between an inline `VALUES` skills list and `int_jobs_enriched`, counting `description ILIKE '%' || skill || '%'` matches per skill/country/seniority with coverage metrics.

28 generic dbt tests across all models: `not_null`, `unique`, `accepted_values`. Schema `.yml` files with descriptions written for all three layers. `dbt docs generate` run successfully; lineage graph saved to `marketpulse_dbt/docs/dbt_lineage_graph.png`. `profiles.yml` placed inside `marketpulse_dbt/` using `env_var()` syntax.

---

### What was considered and rejected

**Dropping `mart_skills_demand` entirely:** Considered when the Adzuna description field was found to contain company descriptions rather than skill requirements. Rejected in favor of building the mart honestly with explicit coverage metrics — dropping it would hide a data quality finding rather than surface it.

**Replacing `mart_skills_demand` with `mart_contract_types`:** Considered as a cleaner alternative using fields the data actually supports. Rejected because skills demand is the core analytical question MarketPulse was designed to answer. Building around the limitation was considered more defensible than abandoning the question entirely.

**`dbt run && dbt test` in the DAG:** Considered for the V3.5 Airflow integration. Rejected in favor of `dbt build` — `dbt build` runs each model then immediately tests it in dependency order, stopping at first failure. `dbt run && dbt test` runs all models first then all tests — meaning a broken intermediate model would still attempt to build dependent marts before failing.

**Singular dbt tests:** Considered for additional coverage (e.g. `coverage_pct > 100`, negative salary guard). Deferred — not blocking V3 completion.

**dbt Fusion Engine + VS Code extension:** The dbt Labs fundamentals course demonstrates setup using the new Fusion Engine (released 2025, rewritten in Rust) with a VS Code extension. Rejected because Fusion Engine is not yet standard in FR/BE enterprise environments — production teams run dbt-postgres; the VS Code extension adds UI abstraction that hides what's actually happening; all dbt concepts are identical between the two.

**dbt inside Docker during V3 development:** Considered installing dbt inside the Airflow Docker environment from the start. Rejected for the development phase because dbt is a CLI tool that exits after each run. Installing locally allows fast iteration: `dbt run`, check output, edit model, repeat. The production integration via DockerOperator is a V3.5 concern, not a V3 development concern.

---

### Key decisions and trade-offs

**`SELECT *` rejected in all models including intermediate:** `SELECT *` in a transformation model means upstream column additions or removals propagate silently to downstream models. In a multi-layer dbt project, a silent schema change in staging would break intermediate and all three marts without a clear error. Explicit column selection in every model makes the contract between layers explicit and forces intentional decisions about what propagates downstream.

**`DENSE_RANK()` over `RANK()` in `mart_top_companies`:** `RANK()` produces gaps when rows tie — companies tied at posting_volume=5 would both get rank 1, and the next company would get rank 3. `DENSE_RANK()` eliminates gaps. For a hiring volume ranking used in analytics, gapped ranks are misleading.

**Two-CTE structure in `mart_salary_ranges`:** The naive approach — `WHERE salary_mid IS NOT NULL` then computing coverage — always returns 100% coverage because both numerator and denominator come from the already-filtered set. The correct pattern requires computing total postings (unfiltered) and salary postings (filtered) separately in CTEs, then joining on country and seniority.

**CROSS JOIN with inline VALUES for `mart_skills_demand`:** Skills are not a column in the database — they're keywords to search for. The only SQL-native way to produce one row per skill per country is to define the skills as a static lookup table inside the query using `VALUES`, then `CROSS JOIN` it against the jobs data. The alternative — one column per skill — produces a single wide row that can't be filtered, grouped, or extended without rewriting the model.

**Data observability pattern in `mart_skills_demand`:** When profiling revealed Adzuna descriptions have max ~16% keyword coverage, the decision was to build the mart with `mention_count`, `total_count`, and `coverage_pct` columns explicitly visible — rather than either dropping the mart or building it without disclosing the limitation. A mart that shows its own coverage percentage is more trustworthy than one that presents incomplete data as complete.

**`profiles.yml` inside `marketpulse_dbt/` with `env_var()` syntax:** dbt's default behavior looks for `profiles.yml` in `~/.dbt/` on the host machine. This path doesn't exist inside a Docker container, and hardcoded credentials can't be committed to version control. Moving `profiles.yml` into the project folder and using `env_var()` for all connection parameters solves both problems: the file travels with the project inside the Docker image, and no credentials appear in the codebase.

**`version: 2` in schema `.yml` files (not `version: 1.0.0`):** The `version` field in dbt schema files is a format identifier, not a semantic version number. It tells dbt's parser which syntax rules to apply. The correct value is the integer `2` regardless of dbt installation version. Common confusion because `dbt_project.yml` uses `version` as a project version field where `1.0.0` is valid — two different uses of the same field name in different files.

**`dbt_dev` schema for all dbt output:** All dbt-managed models write to a separate `dbt_dev` schema, not to `public`. This enforces the ownership boundary: Airflow owns `public.jobs` (raw data), dbt owns `dbt_dev.*` (transformed models). Nothing in dbt touches the raw table directly except through `{{ source() }}` references. Dropping and rebuilding the entire dbt layer has zero impact on raw data.

**Three-layer architecture (staging → intermediate → marts):** Flat transformation makes schema changes and debugging expensive. The three-layer pattern assigns one responsibility per layer: staging absorbs raw data variation, intermediate builds shared derived logic, marts answer specific business questions. A change in Adzuna's API response only requires updating `stg_jobs.sql` — nothing downstream breaks.

**Materializations by layer:** Staging and intermediate models are views because the raw data changes daily and views always reflect the current state without storing a copy. Mart models are tables because analytical queries on aggregated data are expensive to recompute on every query — pre-computing and storing them is the correct trade-off when query performance matters over storage cost.

**`{{ source() }}` as the only reference to raw tables:** Any model that writes `FROM public.jobs` directly is coupled to the raw schema. `{{ source('marketpulse', 'jobs') }}` centralizes that dependency in `sources.yml` — one file to update if the raw layer changes.

---

### Pivots and discoveries during build

**`stg_jobs.sql` initially written as `SELECT * FROM jobs`:** Without first establishing the full dbt project architecture, the staging model was written as a direct passthrough with a hardcoded table reference. This violates both the `SELECT *` anti-pattern and the `{{ source() }}` convention. Correct sequence: define business questions first, define marts that answer them, define shared intermediate logic, define what staging needs to clean — then write models bottom-up.

**`sources.yml` version field written as `version: 1.0.0`:** Incorrect — dbt schema files use `version: 2` as a format tag. Fixed before first commit.

**`TRIM()` on description field:** Initially questioned whether `TRIM()` should be applied to the description column since it's a paragraph. Clarification: `TRIM()` only removes leading and trailing whitespace — it doesn't touch internal spaces or paragraph structure.

**`mart_salary_ranges` coverage_pct always returning 100%:** The first implementation used `WHERE salary_mid IS NOT NULL` then computed coverage within the filtered set. Because the `WHERE` clause pre-filters rows, both numerator and denominator only see non-null rows — the result is always 100%. Fix: two-CTE structure.

**`mart_skills_demand` coverage_pct returning 0 despite correct mention_counts:** The `ILIKE` expression in `ROUND(COUNT(*) FILTER ...)` computing coverage_pct was missing the wildcard concatenation (`'%' || l.skill || '%'`) while mention_count had it. Two different expressions for what should be the same filter — the one without wildcards matched nothing, producing `0 * 100.0 / total_count = 0.0`.

**Adzuna description field data quality discovery:** The core analytical question of MarketPulse — which skills are most in demand — assumed the `description` field would contain role requirements and skill lists. Profiling revealed it contains primarily company background descriptions. Verified with `COUNT(*) FILTER (WHERE description ILIKE '%keyword%')` across 18 DE-relevant keywords: maximum coverage 16% (Python), most tools under 2%. This forced an architectural decision about `mart_skills_demand` mid-build.

**dbt-postgres dependency — no SQLAlchemy conflict detected at this stage:** When adding `dbt-postgres==1.11.0` to `requirements-app.txt`, the risk was a SQLAlchemy conflict with Airflow 2.8.1. Investigation revealed dbt-core 1.12.0 no longer lists SQLAlchemy as a direct dependency. The only shared dependency requiring verification was `psycopg2-binary`: confirmed at 2.9.9 in both environments. No conflict detected. Note: this analysis was done against the local Python 3.10 environment and did not account for the Python version difference between local and container environments. The actual conflict — `dbt-postgres==1.11.0` requires Python 3.10+, the Airflow base image runs Python 3.8 — was only discovered during V3.5 when the Docker build was first attempted.

**`localhost` in profiles.yml:** The locally-generated `profiles.yml` used `host: localhost`. Inside Docker, `localhost` refers to the container itself. The correct value is the Compose service name `host: db`. The `profiles.yml` inside `marketpulse_dbt/` uses `env_var('POSTGRES_HOST')` which maps to `db` in the Airflow environment block.

**`POSTGRES_*` variables not available to Airflow containers:** The `docker-compose.yml` environment block for Airflow services only contained `DATABASE_URL`, `ADZUNA_APP_ID`, and `ADZUNA_APP_KEY`. `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` were only declared on the `db` service. dbt running inside the Airflow container couldn't read those variables. Fix: explicitly add all four PostgreSQL-related vars to the `x-airflow-common` environment block.

---

### Current state at end of V3

- All 5 dbt models built and running locally in `dbt_dev` schema
- 28 generic tests passing: `PASS=28 WARN=0 ERROR=0`
- `dbt docs generate` completed; lineage graph saved to `marketpulse_dbt/docs/dbt_lineage_graph.png`
- `profiles.yml` inside `marketpulse_dbt/` with `env_var()` syntax — safe to commit
- `dbt-postgres==1.11.0` added to `requirements-app.txt`
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST: db` added to Airflow environment block in `docker-compose.yml`
- All V3 files committed and pushed to `dev` branch (5 commits)
- `main` branch untouched — merge pending until V3.5 DAG integration complete and tested

---

## V3.5 — Docker Architecture Refactor + dbt-Airflow Integration

### What was built

Three isolated Docker images replacing the original single monolithic image:

- `marketpulse-airflow` — built from `docker/airflow/Dockerfile`, base `apache/airflow:2.8.1-python3.10`, contains full project code, installs `requirements-airflow.txt` (requests, psycopg2-binary, python-dotenv, apache-airflow-providers-docker, docker==6.1.3)
- `marketpulse-app` — built from `docker/app/Dockerfile`, base `python:3.11-slim`, contains full project code, installs `requirements-app.txt` (fastapi, uvicorn, pydantic, sqlalchemy, python-dotenv, requests)
- `marketpulse-dbt` — built from `docker/dbt/Dockerfile`, base `python:3.11-slim`, contains only `marketpulse_dbt/`, installs `dbt-postgres==1.11.0` inline (no requirements file)

A `tecnativa/docker-socket-proxy` service exposes the Docker daemon over TCP at `tcp://docker-proxy:2375`, allowing the Airflow container to manage Docker containers without direct Unix socket access.

The Airflow DAG was updated from a single `PythonOperator` task to a two-task pipeline:

```
[run_ingestion]  →  [run_dbt_build]
 PythonOperator     DockerOperator
                    image: marketpulse-dbt
                    command: dbt build
                    network_mode: marketpulse_default
                    docker_url: tcp://docker-proxy:2375
                    force_pull: False
                    mount_tmp_dir: False
                    environment: injected via os.environ
```

End result: triggering the DAG runs ingestion then automatically runs `dbt build` across all 5 models and 28 tests — fully automated, no manual steps. Final confirmed run: `PASS=33 WARN=0 ERROR=0 SKIP=0 TOTAL=33`.

---

### What was considered and rejected

**Initial assumption: no Python version conflict (invalidated immediately):** The V3 dependency analysis concluded there was no conflict between dbt-postgres and Airflow's environment. This was wrong — the analysis was done against the local Python 3.10 environment, not the container. The first `docker-compose build` with `dbt-postgres==1.11.0` in `requirements-app.txt` failed immediately: `dbt-postgres==1.11.0 Requires-Python >=3.10.0` — the Airflow 2.8.1 base image runs Python 3.8. This single discovery invalidated the entire original V3.5 plan (BashOperator + single image) and triggered the full architectural refactor.

**BashOperator running dbt inside the Airflow container:** The original V3.5 plan. Invalidated by the Python version conflict — dbt cannot be installed in the same Python environment as Airflow 2.8.1. Even after upgrading the base image to `apache/airflow:2.8.1-python3.10`, forcing dbt's dependencies into Airflow's pinned dependency tree continues to cause conflicts. More fundamentally, it violates the separation of concerns principle: one image doing too many things.

**Upgrading the base image to `apache/airflow:2.8.1-python3.10` and keeping one image:** Considered as a quick fix to the Python version problem. Rejected because it solves the version constraint but not the architectural problem — Airflow has its own pinned dependency tree and dbt's dependencies continue to create conflicts within the same environment.

**Docker Unix socket mount (`/var/run/docker.sock`):** First attempt at DockerOperator connectivity after deciding on separate images. Failed on Windows Docker Desktop with `Not supported URL scheme http+docker`. The Unix socket approach does not work reliably with Docker Desktop's networking layer on Windows regardless of version pinning or permission fixes.

**Pinning `apache-airflow-providers-docker==3.8.0` and `docker==6.1.3`:** Attempted as a version compatibility fix for the socket error. Correct versions were installed and confirmed via `pip show docker` inside the container. Error persisted — the issue was Windows Docker Desktop's socket handling, not a version incompatibility.

**Adding airflow user to docker group:** `USER root` + `groupadd -f docker` + `usermod -aG docker airflow` added to the Dockerfile. Rebuilt with `--no-cache`. Same error. Reverted when docker-socket-proxy was identified as the correct fix.

**`dbt` service with `profiles: ["dbt"]`:** Added to prevent dbt from running as a persistent service during `docker-compose up`. Correct intent, wrong implementation — Docker Compose skips building images for profiled services during `docker-compose build`. The `marketpulse-dbt` image was never created. DockerOperator then attempted to pull it from Docker Hub, failed with 404. Fixed by removing `profiles` and adding an explicit `image: marketpulse-dbt:latest` tag.

**Virtual environment for dbt inside the Airflow image:** Considered — install dbt in a separate venv at `/opt/dbt-env/` inside the Airflow container, call it via BashOperator. Rejected in favor of the separate image approach — the venv isolates Python dependencies but keeps both tools in the same container, which doesn't map cleanly to the Azure deployment model where each service is an independently deployable container.

---

### Key decisions and trade-offs

**Separate images per service as the architectural fix:** The Python version conflict was the trigger, but the decision was justified on broader grounds: each service has one responsibility and one dependency tree, no conflicts are possible between services, and each image maps directly to an independently deployable Azure container in V4. The added complexity — three Dockerfiles, split requirements files, DockerOperator instead of BashOperator — is justified complexity, each piece solving a real problem.

**DockerOperator over BashOperator:** BashOperator runs commands inside the Airflow container. DockerOperator delegates to Docker to spin up a separate container, run the command, and return the result. The dbt image being separate makes BashOperator impossible and DockerOperator necessary. Side benefit: dbt runs in complete isolation — its Python environment, dependencies, and execution context are entirely separate from Airflow's.

**Ephemeral dbt container (task container pattern):** The dbt service has no persistent process. DockerOperator launches it on demand, runs `dbt build`, and tears it down (`auto_remove=True`). This is the correct production pattern — only keep alive what must be always available. The dbt transformation only needs to run after ingestion, not continuously. In production on Kubernetes, this maps directly to KubernetesPodOperator.

**`tecnativa/docker-socket-proxy` over raw socket mount:** The proxy exposes the Docker daemon over TCP instead of Unix socket. This solves the Windows Docker Desktop compatibility problem and is also a better security posture — the proxy exposes only specific Docker API endpoints (CONTAINERS, IMAGES, AUTH, POST) rather than full daemon access. On Linux in production, the same proxy pattern is used for the same security reason.

**`docker-compose build` builds all images including dbt:** Removing `profiles` means `docker-compose build` builds all three images. The dbt container exits immediately when started because it has no persistent process — correct behavior. This ensures the image is always available for DockerOperator without a separate manual build step.

**`force_pull=False` on DockerOperator:** DockerOperator defaults to pulling the image from a remote registry before running. `marketpulse-dbt` is a local image that doesn't exist on Docker Hub. `force_pull=False` tells DockerOperator to use the locally available image.

**`mount_tmp_dir=False` on DockerOperator:** DockerOperator by default mounts a temporary directory from the host into the container. This fails when using a remote Docker daemon via proxy because the host path doesn't exist from the daemon's perspective. Since dbt doesn't need to pass data back to Airflow through a temp mount, disabling it is both the fix and the correct behavior.

**Environment variables injected via `os.environ`:** The dbt container needs PostgreSQL credentials to connect to the `db` service. The `environment` block in the dbt service definition in `docker-compose.yml` doesn't automatically pass to DockerOperator-spawned containers — they must be passed explicitly in the DAG. Using `os.environ.get()` reads from Airflow's own environment and forwards them to the dbt container at runtime.

**Build context set to project root for all three Dockerfiles:** Initial attempt used `build: ./docker/airflow` which sets the build context to that subdirectory only — making project files unavailable to `COPY`. Fixed by using the expanded form `build: context: . / dockerfile: ./docker/airflow/Dockerfile` for all three services.

---

### Pivots and discoveries during build

**The Python version conflict was the root cause of everything:** V3.5 started as "add a BashOperator dbt task to the DAG." It became a full architectural refactor because `dbt-postgres==1.11.0` requires Python 3.10+ and the Airflow base image runs Python 3.8. This wasn't discovered until the first `docker-compose build` failed. The error message listed every available dbt-postgres version with their Python requirements, making the incompatibility unambiguous.

**Windows Docker Desktop makes Unix socket unreliable:** The standard DockerOperator setup (mount `/var/run/docker.sock`) works on Linux but fails on Windows Docker Desktop with `Not supported URL scheme http+docker`. This error persisted through multiple fix attempts — version pinning, permission changes, Dockerfile modifications — before the root cause was identified as a Windows-specific Docker Desktop networking limitation. The docker-socket-proxy bypasses this entirely by switching from Unix socket to TCP.

**DockerOperator pulls from remote registry by default:** After the socket issue was resolved via proxy, the next error was `404 Not Found` for `marketpulse-dbt` on Docker Hub. DockerOperator's default behavior is `force_pull=True`. Local-only images fail this check. Setting `force_pull=False` was the fix, but it only worked after confirming the image was actually built — which led to discovering the `profiles` build-skip problem.

**`profiles: ["dbt"]` silently skips image building:** Adding `profiles: ["dbt"]` prevents the service from starting as a persistent service but also prevents `docker-compose build` from building its image. Discovered when `docker images | grep dbt` returned nothing. Fixed by removing `profiles` — a service with no persistent process exits immediately, achieving the same result without blocking the build.

**`mount_tmp_dir` fails with remote Docker daemon:** After fixing the image and pull issues, the container started but immediately failed with `bind source path does not exist: /tmp/airflowtmpXXXXX`. DockerOperator tries to mount a temp directory from the Airflow container's filesystem into the dbt container. When using a remote daemon via proxy, the daemon tries to find that path on the host machine — not inside the Airflow container. `mount_tmp_dir=False` disables this behavior.

**Environment variables don't propagate from docker-compose to DockerOperator:** The dbt service in `docker-compose.yml` has `POSTGRES_HOST`, `POSTGRES_USER`, etc. defined under `environment`. This does nothing for DockerOperator-spawned containers — those are separate container runs that need their environment set explicitly in the DAG. Discovered when dbt failed with `Env var required but not provided: 'POSTGRES_HOST'` despite the variable being defined in docker-compose.

**dbt deprecation warning fixed before merge:** After the pipeline ran successfully, logs showed `MissingArgumentsPropertyInGenericTestDeprecation: 3 occurrences` — `accepted_values` test arguments were defined at the top level instead of nested under `arguments:` in the schema.yml files. Fixed in `models/intermediate/schema.yml` and `models/marts/schema.yml` before merging to main. Subsequent DAG run confirmed `WARN=0`.

---

### Current state at end of V3.5

```
marketpulse/
├── docker/
│   ├── airflow/Dockerfile    ← apache/airflow:2.8.1-python3.10 base
│   ├── app/Dockerfile        ← python:3.11-slim base
│   └── dbt/Dockerfile        ← python:3.11-slim base, dbt-postgres==1.11.0 inline
├── dags/ingest_dag.py        ← PythonOperator + DockerOperator
├── requirements-airflow.txt  ← airflow image deps only
├── requirements-app.txt      ← fastapi image deps only
├── docker-compose.yml        ← three build contexts, docker-proxy service
└── marketpulse_dbt/          ← 5 models, 28 tests, 0 warnings
```

DAG `marketpulse_ingest` runs daily at 07:00 UTC. Both tasks confirmed green: `run_ingestion` (PythonOperator) → `run_dbt_build` (DockerOperator). Last confirmed run: `PASS=33 WARN=0 ERROR=0 SKIP=0 TOTAL=33`. Committed on `dev`, merged to `main`. Repository clean and stable.

---

## V4 — Azure Cloud Deployment

### Architecture overview

V4 migrates the full MarketPulse pipeline from a locally-run Docker Compose setup to a cloud-native deployment on Azure. The goal is not just migration — it is redesigning MarketPulse as a production data pipeline that runs reliably, cost-efficiently, and observably without any local machine dependency.

The three-image architecture from V3.5 maps directly to Azure's container execution model. No structural changes to the pipeline logic are required — only the deployment target changes.

```
Orchestration: Azure Container Apps (Airflow scheduler + webserver)
    ↓                                      ↓
Task 1: Container Apps Job         Task 2: Container Apps Job
Python ingestion (ephemeral)       dbt build (ephemeral)
→ writes raw JSON to Blob Storage  → transforms PostgreSQL marts
→ loads to PostgreSQL

Storage:
  Bronze layer: Azure Blob Storage (/raw/YYYY/MM/DD/adzuna_*.json)
  Silver + Gold: Azure Database for PostgreSQL Flexible Server
    public.jobs → dbt_dev.stg_jobs → dbt_dev.int_jobs_enriched
    → dbt_dev.mart_top_companies / mart_salary_ranges / mart_skills_demand

Serving: Metabase on Container Apps
  Reads dbt marts directly. Dashboards refresh on query.

Supporting services:
  Azure Container Registry — image storage
  Azure Key Vault — secrets management (replaces .env)
  Azure Monitor + Log Analytics — pipeline observability
```

---

### Architecture decisions and trade-offs

**Azure Container Apps (Airflow) over a VM**
What it replaces locally: the Airflow service in docker-compose.yml. A VM runs 24/7 and bills 24/7. Container Apps bills on actual consumption — vCPU-seconds and memory-seconds. Airflow is active approximately 30 minutes daily for a daily pipeline; it idles at near-zero cost the rest of the time. AKS (Kubernetes) was also considered and rejected: it requires an always-on node pool at a minimum of ~€70/month just for the cluster, which is architecturally unjustified at MarketPulse's scale. Trade-off: Container Apps has less control than a VM — unusual Airflow plugins or configurations may be constrained by what fits in a container. Acceptable at this scale. Cost: €2–5/month.

**Container Apps Jobs for ingestion and dbt (ephemeral task pattern)**
What it replaces locally: DockerOperator spawning ephemeral containers in V3.5. The ephemeral task pattern built locally is correct production thinking — spin up a container, run the task, tear it down. Container Apps Jobs maps this pattern directly to Azure. These tasks run for 2–5 minutes daily; paying for always-on containers would be wasteful and architecturally wrong. Trade-off: slightly more complex to debug than a long-running container because the container exits after execution. Logs must be captured to Log Analytics before the container disappears. Cost: <€1/month.

**Azure Blob Storage as Bronze layer**
What it replaces locally: nothing — this is a new layer added in V4. Without it, raw data exists only in PostgreSQL after ingestion. If a transformation bug is discovered later, reprocessing is impossible because the raw API response was never preserved. Blob Storage adds a permanent archive of every raw API response exactly as received from Adzuna, before any transformation. This enables reprocessing, debugging, and makes the architecture honest about data lineage. Folder structure: `/raw/YYYY/MM/DD/adzuna_*.json`. ADLS Gen2 was considered and rejected: it adds a hierarchical namespace better suited for Spark and distributed processing, which MarketPulse does not need. Standard Blob Storage achieves the same goal at the same price with less complexity. Trade-off: adds one step to the ingestion script. Minimal engineering cost. Cost: <€0.10/month.

**Azure Database for PostgreSQL Flexible Server over Synapse Analytics**
What it replaces locally: the PostgreSQL container in docker-compose. The database is the only component in the architecture that must never lose data. A managed service handles backups, point-in-time restore, patching, and high availability automatically. Running a database in a container in production is an anti-pattern — container failures can corrupt volumes. PostgreSQL was chosen over Azure Synapse Analytics for three reasons: (1) scale mismatch — Synapse is designed for terabytes, MarketPulse processes thousands of rows daily; (2) cost — Synapse starts at €200–700/month minimum, unjustifiable here; (3) pattern transferability — the architecture pattern (PostgreSQL + dbt + Airflow + BI) is structurally identical to what would be built with Synapse at 100x the scale, and the concepts transfer directly. Trade-off: PostgreSQL is not a columnar analytical store — aggregation queries across very large tables would eventually be slower than Synapse. At MarketPulse's current and foreseeable scale, this is irrelevant. Cost: €0 for 12 months (B1ms free tier), then €13/month.

**Metabase on Container Apps over Power BI**
What it replaces locally: FastAPI was serving raw job postings. Metabase replaces the serving concept entirely — serving analytical data via a BI layer is the correct production pattern, not a REST API over raw tables. Power BI Service requires a Pro license (€9.40/user/month) and is designed for the Microsoft SaaS ecosystem with Azure Synapse and SQL Server. Metabase is open-source, runs as a Docker container, connects natively to PostgreSQL, and costs nothing in licensing. Metabase connects directly and permanently to PostgreSQL — it does not get added to the Airflow DAG. It reads from dbt mart tables on demand whenever a dashboard is opened. Airflow writes; Metabase reads. The storage layer is the integration point. Trade-off: Power BI is what French and Belgian enterprises actually use. Metabase won't appear on job postings as a required skill. Counter-argument: BI tool syntax is not the transferable skill — analytical thinking and data modeling are. Those transfer. Cost: €2–4/month (Container Apps consumption).

**Azure Container Registry (ACR)**
What it replaces locally: images that exist only on the local machine with `force_pull=False`. Container Apps cannot pull from a local machine — every image must exist in a registry accessible from Azure. ACR is Azure's private registry. Images are pushed here; Container Apps pulls from here. This replaces the local-only image pattern from V3.5. Trade-off: adds a rebuild-and-push step to the development workflow every time an image changes. Cost: €4.50/month (Basic tier).

**Azure Key Vault over environment variables**
What it replaces locally: the `.env` file. Environment variables set directly in container configuration are stored in plain text in the Azure Portal and in ARM deployment templates — anyone with resource access can read them. Key Vault stores secrets encrypted, with access controlled by Managed Identity. Managed Identity is a service account Azure assigns to a resource so services can authenticate to each other without passwords or shared secrets. Only services explicitly authorized can read specific secrets from the vault. Trade-off: introduces the Managed Identity concept as a new mental model. Small learning overhead, significant security improvement. Cost: <€1/month.

**Azure Monitor + Log Analytics**
What it replaces locally: opening the Airflow UI in the browser and reading logs directly. In the cloud, Container Apps Jobs exit after execution — if a job fails, the container is gone. Without centralized logging, there is no way to see what happened. Log Analytics captures all container output before containers exit and stores it queryable for 30 days. This is what "observable" means in production: you can debug a failure without SSH access to any machine. Trade-off: small cost per GB ingested beyond the free 5GB/month tier. At MarketPulse's log volume, the free tier is sufficient. Cost: €0–2/month.

---

### Region decision and constraint

All V4 resources are deployed to **Spain Central**. This was not the first choice — West Europe was the original target, and France Central was the second. Both were blocked at deployment by an Azure for Students subscription policy: `Allowed resource deployment regions` restricts provisioning to: `spaincentral`, `polandcentral`, `norwayeast`, `belgiumcentral`, `denmarkeast`. This policy was discovered by navigating to Policies → Assignments → Allowed resource deployment regions → Parameters in the Azure Portal. Spain Central was selected as the best available option: it is the only Tier 1 EU region in the allowed list, geographically closest to the target French and Belgian markets, and entirely within the EU for data residency purposes. All subsequent resources (Container Apps, ACR, Key Vault, Blob Storage) will be deployed to Spain Central for consistency and to avoid cross-region bandwidth charges.

---

### Branch strategy for V4

The `dev/main` branch strategy established in V1 is unchanged. A `prod` branch is not introduced in V4 because there is only one Azure environment — adding a `prod` branch without a separate staging environment adds process overhead without adding safety. The `prod` branch becomes relevant when CI/CD is introduced (deferred to a later phase), at which point `main` becomes the staging deploy trigger and `prod` becomes the production deploy trigger.

Development loop for V4: edit code locally → test with local docker-compose → rebuild affected image → push to ACR → update Container Apps to use new image tag → trigger manual DAG run to verify → merge dev to main when stable.

---

### Cost summary

| Service | Tier | Estimated monthly cost |
|---|---|---|
| PostgreSQL Flexible Server | B1ms (free 12 months) | €0 → €13 after |
| Container Apps (Airflow) | Consumption | €2–5 |
| Container Apps Jobs (ingestion + dbt) | Per execution | <€1 |
| Container Apps (Metabase) | Consumption | €2–4 |
| Azure Container Registry | Basic | €4.50 |
| Azure Key Vault | Standard | <€1 |
| Azure Monitor + Log Analytics | Free tier | €0–2 |
| Azure Blob Storage | LRS, ~5MB/day | <€0.10 |
| **Total** | | **~€9–18/month** |

Covered by Azure for Students $100 credit (expires 28/08/2027) for the full V4 build phase.

---

### Current state at start of V4

- Azure for Students subscription active — $100 credits, expires 28/08/2027
- Resource group `marketpulse-rg` created (West Europe metadata, resources in Spain Central)
- Azure Database for PostgreSQL Flexible Server deployed — `marketpulse-postgres`, Spain Central, B1ms free tier, PostgreSQL 16, public access with firewall rules, 7-day backup retention
- All other V4 components pending deployment