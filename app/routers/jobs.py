from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Job
from app.schemas import JobResponse, JobStats
from app.services.adzuna import fetch_jobs, normalize_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{keyword}", response_model=list[JobResponse])
def get_jobs(keyword: str, country: str = "fr", db: Session = Depends(get_db)):
    """
    Récupere les offres depuis Adzuna, les stocke en base, et les retourne.
    Si une offre existe dejà (via external_id), on ne la duplique pas.
    """
    raw_jobs = fetch_jobs(keyword, country)

    if not raw_jobs:
        raise HTTPException(status_code=404, detail="Aucune offre trouvée")

    saved = []
    for raw in raw_jobs:
        normalized = normalize_job(raw, country)

        # Deduplication : on verifie si l'offre existe deja
        existing = db.query(Job).filter(
            Job.external_id == normalized["external_id"]
        ).first()

        if not existing:
            job = Job(**normalized)
            db.add(job)
            db.commit()
            db.refresh(job)
            saved.append(job)
        else:
            saved.append(existing)

    return saved
