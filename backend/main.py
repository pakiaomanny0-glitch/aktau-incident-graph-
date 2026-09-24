from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
import models  # noqa: F401 (кестелерді Base.metadata-ға тіркеу үшін импорт керек)
from routers import ingest, incidents, graph, analyze

# Кестелерді автоматты құру (алғашқы деплой үшін жеткілікті; production-да Alembic ұсынылады)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Aktau City Intelligence API",
    description="Ақтаудағы қалалық проблемалардың өзара байланысын көрсететін backend",
    version="0.1.0",
)

# Frontend кез келген origin-нен (mock -> нағыз ауысу оңай болу үшін хакатон кезінде ашық)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(incidents.router)
app.include_router(graph.router)
app.include_router(analyze.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "Aktau City Intelligence API"}


@app.get("/health")
def health():
    return {"status": "healthy"}
