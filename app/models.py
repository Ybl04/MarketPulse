from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base



class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer,primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True)
    title = Column(String, nullable=False)
    company = Column(String)
    location = Column(String)
    country = Column(String)
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    description = Column(Text)
    category = Column(String)
    created_at = Column(DateTime, server_default=func.now())