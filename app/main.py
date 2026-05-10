from fastapi import FastAPI
from app.database import engine, Base
from app.routers import jobs

# Crer les tables au demarrage
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="MarketPulse API",
    description="pipeline: Tech job market in Europe",
    version="1.0.0"
)

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}

app.include_router(jobs.router)