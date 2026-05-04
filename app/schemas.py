from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class JobBase(BaseModel):
    title: str
    company: Optional[str]
    location: Optional[str]
    country: Optional[str]
    salary_min: Optional[float]
    salary_max: Optional[float]
    category: Optional[str]

class JobResponse(JobBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class JobStats(BaseModel):
    keyword: str
    total_jobs: int
    avg_salary_min: Optional[float]
    avg_salary_max: Optional[float]
    top_locations: list[dict]