import structlog
from dotenv import load_dotenv
load_dotenv()  # Lädt .env-Konfigurationen

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import upload, chat, system

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Argus RAG API",
    description="Backend for Argus RAG React Frontend",
    version="1.0.0"
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


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
