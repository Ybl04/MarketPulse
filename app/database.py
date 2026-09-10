from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

load_dotenv()

Base = declarative_base()

def get_engine():
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("POSTGRES_HOST")
    db = os.getenv("POSTGRES_DB")

    missing = [name for name, val in {
        "POSTGRES_USER": user,
        "POSTGRES_PASSWORD": password,
        "POSTGRES_HOST": host,
        "POSTGRES_DB": db
    }.items() if not val]

    if missing:
        raise ValueError(f"Missing required env vars: {', '.join(missing)}")

    DATABASE_URL = f"postgresql+psycopg2://{user}:{password}@{host}:5432/{db}"
    return create_engine(DATABASE_URL)

def get_session():
    return sessionmaker(bind=get_engine())()

def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()