from app.database import get_session, get_engine, Base
from app.models import Job
from app.services.adzuna import fetch_jobs, normalize_job
from app.config import KEYWORDS, COUNTRIES


def run():
    # create tables and session inside run(), only executes when Airflow calls the task
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    db = get_session()
    total_inserted = 0

    for country in COUNTRIES:
        for keyword in KEYWORDS:
            print(f"Fetching: {keyword} | {country.upper()}")
            raw_jobs = fetch_jobs(keyword, country, results_per_page=50)

            for raw in raw_jobs:
                normalized = normalize_job(raw, country)
                existing = db.query(Job).filter(
                    Job.external_id == normalized["external_id"]
                ).first()

                if not existing:
                    db.add(Job(**normalized))
                    total_inserted += 1

            db.commit()

    db.close()
    print(f"Ingestion terminée. {total_inserted} nouvelles offres insérées.")

if __name__ == "__main__":
    run()