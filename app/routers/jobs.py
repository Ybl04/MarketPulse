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


@router.get("/{keyword}/stats", response_model=JobStats)
def get_stats(keyword: str, db: Session = Depends(get_db)):
    """
    Retourne des statistiques agregees sur les offres stockees en base
    pour un keyword donné.
    """
    jobs = db.query(Job).filter(
        Job.title.ilike(f"%{keyword}%")
    ).all()

    if not jobs:
        raise HTTPException(status_code=404, detail="Aucune donnée pour ce keyword")

    salaries_min = [j.salary_min for j in jobs if j.salary_min]
    salaries_max = [j.salary_max for j in jobs if j.salary_max]

    # Top 5 locations
    location_counts = {}
    for job in jobs:
        if job.location:
            location_counts[job.location] = location_counts.get(job.location, 0) + 1

    top_locations = sorted(
        [{"location": k, "count": v} for k, v in location_counts.items()],
        key=lambda x: x["count"],
        reverse=True
    )[:5]

    return JobStats(
        keyword=keyword,
        total_jobs=len(jobs),
        avg_salary_min=round(sum(salaries_min) / len(salaries_min), 2) if salaries_min else None,
        avg_salary_max=round(sum(salaries_max) / len(salaries_max), 2) if salaries_max else None,
        top_locations=top_locations
    )
