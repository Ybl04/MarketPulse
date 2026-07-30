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

Adzuna API → Airflow DAG (daily) → ingest.py → PostgreSQL → FastAPI


**Adzuna API:** job postings provider covering most EU countries
**Apache Airflow:** orchestrates the ingestion pipeline on a daily 
schedule, handles retries and failure alerting  
**ingest.py:** fetches and normalizes raw postings, stores them in 
PostgreSQL with idempotent deduplication  
**PostgreSQL:** persistent storage for all job postings  
**FastAPI:** exposes stored data via REST endpoints  
**Docker / Docker Compose:** full containerized environment: PostgreSQL, 
Airflow scheduler, Airflow webserver, custom image  

---

## Stack

| Technology     | Version | Role                                                    |
|----------------|---------|---------------------------------------------------------|
| Apache Airflow | 2.8.1   | Pipeline orchestration, scheduling, retry and alerting  |
| FastAPI        | 0.111.0 | REST API exposing stored job data                       |
| PostgreSQL     | 15      | Persistent storage for all job postings                 |
| SQLAlchemy     | 1.4.x   | ORM layer between Python and PostgreSQL                 |
| Docker         | —       | Containerized pipeline — no local installs needed       |
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

**4. Access the Airflow UI**

http://localhost:8080

credentials: admin / admin
Unpause the marketpulse_ingest DAG to activate the daily schedule

**5. Access the API**

http://localhost:8000/health
http://localhost:8000/docs


---

## Airflow DAG

The `marketpulse_ingest` DAG runs daily at 07:00 UTC. It fetches job 
postings from the Adzuna API across configured keywords and countries, 
normalizes the data, and inserts new postings into PostgreSQL. Duplicate 
postings are skipped via `external_id` deduplication — the pipeline is 
fully idempotent.

Keywords and target countries are configured in `app/config.py`.

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
runs in Docker alongside a separate metadata database, with a custom 
image that packages the full project environment — the same artifact 
that will be deployed to Azure in V4.

**V3: dbt transformations** ⏳  
A transformation layer on top of the orchestrated ingestion: clean, 
tested, documented analytical models with full lineage.

**V4: Azure cloud deployment** ⏳  
Deploy the full pipeline to Azure. The custom Docker image built in V2 
is the artifact that goes to Azure Container Registry.