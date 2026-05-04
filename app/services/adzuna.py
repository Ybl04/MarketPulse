import requests
import os
from dotenv import load_dotenv

load_dotenv()

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")
BASE_URL = "https://api.adzuna.com/v1/api/jobs"

def fetch_jobs(keyword: str, country: str = "fr", results_per_page: int = 20) -> list[dict]:
    
    # Call Adzuna API and return a list of offers for France
    
    url = f"{BASE_URL}/{country}/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": results_per_page,
        "what": keyword,
        "content-type": "application/json"
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    data = response.json()
    return data.get("results", [])


def normalize_job(raw: dict, country: str) -> dict:
    
    # Transform a norma Adzuna offer to a dictionnary
    
    salary = raw.get("salary_min"), raw.get("salary_max")

    return {
        "external_id": raw.get("id"),
        "title": raw.get("title", "").strip(),
        "company": raw.get("company", {}).get("display_name"),
        "location": raw.get("location", {}).get("display_name"),
        "country": country.upper(),
        "salary_min": salary[0],
        "salary_max": salary[1],
        "description": raw.get("description", "").strip(),
        "category": raw.get("category", {}).get("label"),
    }