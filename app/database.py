from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

load_dotenv()

Base = declarative_base()

def get_engine():
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set")
    return create_engine(DATABASE_URL)

def get_session():
    return sessionmaker(bind=get_engine())()

def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()