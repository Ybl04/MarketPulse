from app.database import get_session, get_engine, Base
from app.models import Job
from app.services.adzuna import fetch_jobs, normalize_job
from app.config import KEYWORDS, COUNTRIES
from azure.storage.blob import BlobServiceClient
from datetime import datetime
from dotenv import load_dotenv
import os
import json

load_dotenv()
BLOB_CONTAINER_NAME = "raw"


def save_to_blob(raw_jobs, country, keyword):
    # Step 1: Connect to Blob Storage
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)

    # Step 2: Build the file path
    now = datetime.now()
    year = now.strftime("%Y")
    month = now.strftime("%m")
    day = now.strftime("%d")
    timestamp = now.strftime("%H%M%S")
    blob_name = f"raw/{year}/{month}/{day}/adzuna_{country}_{keyword}_{timestamp}.json"

    # Step 3: Serialize the data
    json_bytes = json.dumps(raw_jobs).encode("utf-8")

    # Step 4: Upload
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(data=json_bytes, overwrite=True)


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

            save_to_blob(raw_jobs, country, keyword)

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
    print(f"Ingestion finished. {total_inserted} new offers inserted.")


if __name__ == "__main__":
    run()