import structlog
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()  # Lädt .env-Konfigurationen

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.ingestion_jobs import job_manager
from api.routes import upload, chat, system, jobs

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    job_manager.start()
    try:
        yield
    finally:
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
