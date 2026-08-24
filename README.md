# MarketPulse

MarketPulse is a data pipeline that collects, transforms, and stores 
job postings from across Europe to answer concrete analytical questions: 
what skills are most in demand right now in EU countries? What are the prevailing salaries? Which companies are 
actively recruiting?

I built this project for learning and practice — but from day one, I 
designed it as a real production system, applying the best practices of 
modern data engineering. Every decision in this project had to be 
justified by the problem, not by what's popular or trending. That 
principle shaped the roadmap more than once.

---

## Architecture

```
Adzuna API → Airflow DAG (daily) → ingest.py → PostgreSQL → dbt (staging → intermediate → marts) → FastAPI
                                                                ↑
                                                    DockerOperator spins up
                                                    marketpulse-dbt container,
                                                    runs dbt build, container exits
```

**Adzuna API:** job postings provider covering most EU countries  
**Apache Airflow:** orchestrates the full pipeline on a daily schedule — ingestion then transformation — handles retries and failure alerting  
**ingest.py:** fetches and normalizes raw postings, stores them in PostgreSQL with idempotent deduplication  
**PostgreSQL:** persistent storage for all job postings  
**dbt:** transformation layer — cleans, enriches, and materializes analytical models from raw data, run automatically by Airflow via DockerOperator  
**FastAPI:** exposes stored data via REST endpoints  
**Docker / Docker Compose:** three isolated images per service — no dependency conflicts, clean separation of concerns  

---

## Docker Architecture (V3.5)

The project uses three separate Docker images, each with its own isolated dependency environment:

| Image | Dockerfile | Role |
|---|---|---|
| `marketpulse-airflow` | `docker/airflow/Dockerfile` | Airflow webserver, scheduler, and ingestion script |
| `marketpulse-app` | `docker/app/Dockerfile` | FastAPI serving layer |
| `marketpulse-dbt` | `docker/dbt/Dockerfile` | dbt transformation layer — ephemeral task container |

**Why three images?** dbt requires Python 3.10+ while Airflow 2.8.1 runs Python 3.8 in its default image. Installing both in a single image creates irresolvable dependency conflicts. The correct architectural fix is separation: each service owns its own Python environment and its own dependencies. This also maps directly to the Azure deployment model in V4 — each image becomes an independently deployable container.

**DockerOperator pattern:** The dbt image is not a long-running service. Airflow's `DockerOperator` spins it up as an ephemeral task container after each ingestion run, executes `dbt build`, and tears it down. This is the standard production pattern for running transformation tasks in isolated environments without keeping a container alive between runs.

**Docker socket proxy:** A `tecnativa/docker-socket-proxy` service exposes the Docker daemon to Airflow over TCP (`tcp://docker-proxy:2375`), allowing the DockerOperator to manage containers without mounting the raw Unix socket — a more controlled and portable approach.

### Services

| Service | Image | Description |
|---|---|---|
| `db` | `postgres:15` | Data store for job postings |
| `airflow-db` | `postgres:15` | Airflow metadata database |
| `airflow-webserver` | `marketpulse-airflow` | Airflow UI on port 8080 |
| `airflow-scheduler` | `marketpulse-airflow` | DAG scheduling and execution |
| `airflow-init` | `marketpulse-airflow` | One-time DB migration and admin user creation |
| `app` | `marketpulse-app` | FastAPI on port 8000 |
| `dbt` | `marketpulse-dbt` | Built at compose time, launched on-demand by DockerOperator |
| `docker-proxy` | `tecnativa/docker-socket-proxy` | Docker daemon proxy for DockerOperator |

---

## Stack

| Technology     | Version | Role                                                    |
|----------------|---------|---------------------------------------------------------|
| Apache Airflow | 2.8.1   | Pipeline orchestration, scheduling, retry and alerting  |
| dbt-postgres   | 1.11.0  | Transformation layer — staging, intermediate, marts     |
| FastAPI        | 0.111.0 | REST API exposing stored job data                       |
| PostgreSQL     | 15      | Persistent storage for all job postings                 |
| SQLAlchemy     | 1.4.x   | ORM layer between Python and PostgreSQL                 |
| Docker         | —       | Three isolated images — no local installs needed        |
| Adzuna API     | —       | Public job postings API covering major European markets |

---

## Getting Started

**1. Clone the repository**
```bash
git clone https://github.com/Ybl04/marketpulse
cd marketpulse
```

**2. Configure environment variables**
```bash
cp .env.example .env
# Fill in: ADZUNA_APP_ID, ADZUNA_APP_KEY, POSTGRES_USER, 
# POSTGRES_PASSWORD, POSTGRES_DB, DATABASE_URL
```

**3. Build and start all services**
```bash
docker-compose build
docker-compose run --rm airflow-init
docker-compose up -d
```

All three images are built in a single `docker-compose build`. The dbt image is built alongside the others and launched on-demand by Airflow — no manual step required.

**4. Access the Airflow UI**

http://localhost:8080

credentials: admin / admin  
Unpause the `marketpulse_ingest` DAG to activate the daily schedule.

**5. Access the API**

http://localhost:8000/health  
http://localhost:8000/docs

---

## Airflow DAG

The `marketpulse_ingest` DAG runs daily at 07:00 UTC with two sequential tasks:

**Task 1 — `run_ingestion` (PythonOperator)**  
Fetches job postings from the Adzuna API across configured keywords and countries, normalizes the data, and inserts new postings into PostgreSQL. Duplicate postings are skipped via `external_id` deduplication — the pipeline is fully idempotent.

**Task 2 — `run_dbt_build` (DockerOperator)**  
After ingestion completes, Airflow instructs Docker to spin up the `marketpulse-dbt` container and run `dbt build`. This executes all 5 models and 28 tests in dependency order — stopping at the first failure. The container exits after completion and returns a success or failure status to Airflow.

```
[run_ingestion] → [run_dbt_build]
 PythonOperator    DockerOperator
                   image: marketpulse-dbt
                   command: dbt build
                   network: marketpulse_default
```

Keywords and target countries are configured in `app/config.py`.

---

## dbt Transformation Layer (V3)

V3 adds the analytics backbone to the MarketPulse architecture — a dbt 
transformation layer that sits on top of the Airflow-orchestrated PostgreSQL 
database and prepares data for analytical consumption.

Once data is ingested and stored in PostgreSQL by the Airflow DAG, the dbt 
layer extracts from raw sources, applies cleaning and business logic, and 
materializes analytical models ready for reporting or downstream use.

### Layer Structure

![dbt lineage graph](marketpulse_dbt/docs/dbt_lineage_graph.png)

**Staging (`stg_jobs`)** — acts as the single source of truth and schema 
evolution firewall. All column selection, type casting, null handling, and 
renaming happens here. If Adzuna changes a column name or structure, only 
this layer needs updating.

**Intermediate (`int_jobs_enriched`)** — lightweight business logic layer. 
Derives two enriched fields from staging: `seniority_level` classified from 
job title keywords, and `salary_mid` computed as the average of min and max 
salary where both values are present.

**Marts** — analytical models that answer specific business questions:
- `mart_top_companies` — hiring volume by company and country, ranked within each country
- `mart_salary_ranges` — compensation ranges by country and seniority level, with salary coverage metrics
- `mart_skills_demand` — skill keyword mentions by country and seniority level, with coverage percentage

### Tests

28 generic dbt tests across all 5 models: `not_null`, `unique`, and 
`accepted_values` — covering all critical columns. Tests run automatically 
as part of `dbt build` after every ingestion — no manual step needed.

### Data Quality Findings

A significant data quality issue was identified during the V3 build: the 
Adzuna `description` field — which typically lists role requirements and 
skills in most job posting platforms — contains primarily company 
descriptions rather than structured skill requirements.

**Investigation:** Keyword matching across job postings (1,366 records at 
time of analysis) revealed a maximum coverage of ~16% for any single skill 
keyword (Python), with most DE-relevant tools appearing in under 2% of 
descriptions.

**Decision:** Rather than dropping `mart_skills_demand` or masking the 
limitation, the mart was built with explicit coverage metrics 
(`mention_count`, `total_count`, `coverage_pct`) — making the data quality 
signal visible to any consumer of the mart. This follows a data observability 
pattern: surfaces available signal honestly rather than hiding limitations.

**Future enhancement (V5):** Integrate a second data source with structured 
skill fields to improve signal quality. Scoped out deliberately to prioritize 
V4 cloud deployment.

---

## API Endpoints

### GET /health
```json
{ "status": "ok", "version": "1.0.0" }
```

### GET /jobs/{keyword}
Returns stored job postings matching the keyword.

### GET /jobs/{keyword}/stats
Returns aggregated statistics: total postings, average salary range, 
top locations.

---

## Roadmap

This project was planned from the beginning as a progressive system. 
Each version adds a layer of complexity that reflects the work of 
real enterprise data teams.

**V1: Batch ingestion** ✅  
The foundation layer: fetch job postings from the Adzuna API, normalize 
them, and store them in PostgreSQL. FastAPI exposes the data via REST 
endpoints. PostgreSQL runs in Docker, isolated from the local environment.

**V2: Airflow orchestration** ✅  
Originally planned as a Kafka streaming layer. After reading more about 
DE best practices, I realized that adding Kafka to a REST API polled on 
a schedule would be technically dishonest — complexity the data flow 
doesn't require. The right next layer was orchestration: making the 
pipeline run itself, recover from failures, and be observable. Airflow 
runs in Docker alongside a separate metadata database.

**V3: dbt transformations** ✅  
A transformation layer on top of the orchestrated ingestion: clean, 
tested, documented analytical models with full lineage. Five models 
across three layers (staging, intermediate, marts), 28 passing tests, 
and a formally documented data quality finding in `mart_skills_demand`.

**V3.5: Docker architecture refactor** ✅  
Separated the monolithic Docker image into three isolated images — one per 
service (Airflow, FastAPI, dbt). Resolved a fundamental Python version 
conflict between Airflow 2.8.1 (Python 3.8) and dbt-postgres 1.11.0 
(Python 3.10+) that made co-installation impossible. Integrated dbt into 
the Airflow DAG via `DockerOperator`, completing the end-to-end automated 
pipeline: ingestion and transformation now run as a single observable DAG 
without any manual steps. A `docker-socket-proxy` service handles Docker 
daemon access securely over TCP.

**V4: Azure cloud deployment** ⏳  
Deploy the full pipeline to Azure. Each Docker image maps directly to an 
independently deployable container — the architecture is already structured 
for this transition.

**V5: Enhanced skill signal** ⏳  
Integrate a second structured data source to improve skill demand 
analytics beyond what the Adzuna description field supports.