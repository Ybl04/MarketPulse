# MarketPulse

MarketPulse is a data pipeline that collects, stores, and analyzes tech job postings in Europe in real time. Its goal is to answer concrete questions: what skills are most in demand right now in France and Belgium, what are the prevailing salaries, and which companies are actively recruiting? The project is designed as a real-world production system — not an academic exercise. Each version adds a layer of complexity that reflects the work of enterprise data teams.

## Architecture

**Adzuna API** — source of job offers, covers France, Belgium, and the UK  
**ingest.py** — batch script that fetches and normalizes raw offers, then stores them in PostgreSQL  
**PostgreSQL** — persistent storage for all job offers  
**SQLAlchemy** — ORM layer between Python and PostgreSQL  
**FastAPI** — exposes the stored data via REST endpoints  

## Stack

| Technology   | Version | Role                                                              |
|--------------|---------|-------------------------------------------------------------------|
| FastAPI      | 0.111.0 | Exposes data via REST endpoints                                   |
| PostgreSQL   | 15      | Persistent storage for all job offers                             |
| SQLAlchemy   | 2.0.30  | ORM layer between Python and PostgreSQL                           |
| Docker       | —       | Runs PostgreSQL in an isolated container, no local install needed |
| Adzuna API   | —       | Public job offers API covering major European markets             |

## Getting Started

**1. Clone and install**
```bash
git clone https://github.com/Ybl04/marketpulse
cd marketpulse
pip install -r requirements.txt
```

**2. Configure environment variables**
```bash
cp .env.example .env
# Fill in your Adzuna API credentials and PostgreSQL credentials
```

**3. Start PostgreSQL**
```bash
docker-compose up -d
```

**4. Run the API**
```bash
uvicorn app.main:app --reload
```

**5. Test**
```
http://localhost:8000/health
http://localhost:8000/jobs/data engineer
http://localhost:8000/jobs/data engineer/stats
http://localhost:8000/docs        ← automatic interactive documentation
```

## Endpoints

### GET /health
Checks that the API is running and returns its current version.

```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

### GET /jobs/{keyword}
Calls Adzuna, stores any new offers in PostgreSQL, and returns the results. Entry point for fresh data.

```json
[
  {
    "title": "Alternant Data Analyst",
    "company": "OpenClassrooms",
    "location": "Hésingue, Saint-Louis",
    "country": "FR",
    "salary_min": 108000,
    "salary_max": 192000,
    "category": "Emplois Autres/Général",
    "id": 21,
    "created_at": "2026-05-13T22:15:43.289373"
  },
  {
    "title": "Data Analyst",
    "company": "Wave Works",
    "location": "Paris, Ile-de-France",
    "country": "FR",
    "salary_min": null,
    "salary_max": null,
    "category": "Unknown",
    "id": 22,
    "created_at": "2026-05-13T22:15:43.321698"
  }
]
```

---

### GET /jobs/{keyword}/stats
Queries what is already stored in PostgreSQL and returns aggregated statistics.

```json
{
  "keyword": "data analyst",
  "total_jobs": 20,
  "avg_salary_min": 52101.33,
  "avg_salary_max": 82434.67,
  "top_locations": [
    { "location": "France", "count": 4 },
    { "location": "Aix-en-Provence, Bouches-du-Rhône", "count": 2 },
    { "location": "Hésingue, Saint-Louis", "count": 1 },
    { "location": "Paris, Ile-de-France", "count": 1 },
    { "location": "Lille, Nord", "count": 1 }
  ]
}
```

## Roadmap

- ✅ V1 — Batch ingestion, PostgreSQL, FastAPI
- 🔄 V2 — Kafka streaming (in progress)
- ⏳ V3 — dbt transformations
- ⏳ V4 — Airflow orchestration
- ⏳ V5 — PySpark analytics
- ⏳ V6 — Docker + deployment