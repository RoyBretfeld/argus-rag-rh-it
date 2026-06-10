import structlog
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Logging-Konfiguration zuerst (vor allen anderen Imports)
from api.logging_config import configure_logging
configure_logging()  # Konfiguriert structlog für Konsole + JSON-File

load_dotenv()  # Lädt .env-Konfigurationen

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.ingestion_jobs import job_manager
from api.night_scheduler import start_scheduler, stop_scheduler
from api.idle_watcher import start_idle_watcher, stop_idle_watcher
from api.routes import upload, chat, system, jobs

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    job_manager.start()
    start_scheduler(job_manager)
    start_idle_watcher(job_manager)
    try:
        yield
    finally:
        stop_idle_watcher()
        stop_scheduler()
        job_manager.stop()


app = FastAPI(
    title="Argus RAG API",
    description="Backend for Argus RAG React Frontend",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Für Development, in Prod einschränken!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(system.router, prefix="/api/system", tags=["System"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["Ingestion Jobs"])


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# Produktionsmodus (portables Release): gebautes Frontend statisch ausliefern.
# Im Dev-Betrieb (Vite auf Port 5173) existiert frontend/dist nicht — Mount entfaellt.
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
    logger.info("frontend.static_mounted", dist=str(_frontend_dist))
