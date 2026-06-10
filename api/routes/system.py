import subprocess
import shutil
import structlog
from fastapi import APIRouter, HTTPException
from core.vectordb.chroma_store import ChromaStore

try:
    from api.idle_watcher import get_idle_seconds
    HAS_IDLE_WATCHER = True
except ImportError:
    HAS_IDLE_WATCHER = False

logger = structlog.get_logger(__name__)
router = APIRouter()

try:
    chroma_store = ChromaStore()
except Exception as e:
    logger.error("system_router.chroma_init_failed", fehler=str(e))
    chroma_store = None

def get_gpu_info():
    """Versucht GPU-Informationen (VRAM) über PyTorch oder nvidia-smi zu ermitteln."""
    # 1. PyTorch CUDA check (bevorzugt)
    try:
        import torch
        if torch.cuda.is_available():
            device_id = torch.cuda.current_device()
            props = torch.cuda.get_device_properties(device_id)
            total_vram = props.total_memory / (1024 ** 2)  # MB
            allocated = torch.cuda.memory_allocated(device_id) / (1024 ** 2)  # MB
            free_vram = total_vram - allocated
            return {
                "available": True,
                "name": props.name,
                "total_vram_mb": round(total_vram, 1),
                "used_vram_mb": round(allocated, 1),
                "free_vram_mb": round(free_vram, 1),
                "method": "pytorch"
            }
    except Exception as e:
        logger.debug("system_router.gpu_pytorch_failed", fehler=str(e))

    # 2. Fallback auf nvidia-smi
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, check=True
            )
            lines = res.stdout.strip().split("\n")
            if lines:
                parts = [p.strip() for p in lines[0].split(",")]
                if len(parts) >= 4:
                    return {
                        "available": True,
                        "name": parts[0],
                        "total_vram_mb": float(parts[1]),
                        "free_vram_mb": float(parts[2]),
                        "used_vram_mb": float(parts[3]),
                        "method": "nvidia-smi"
                    }
        except Exception as e:
            logger.debug("system_router.gpu_nvidiasmi_failed", fehler=str(e))

    return {
        "available": False,
        "name": "Keine kompatible GPU gefunden",
        "total_vram_mb": 0.0,
        "used_vram_mb": 0.0,
        "free_vram_mb": 0.0,
        "method": "none"
    }

def get_system_ram():
    """Ermittelt den System-Arbeitsspeicher (RAM)."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / (1024 ** 3), 1),
            "used_gb": round(mem.used / (1024 ** 3), 1),
            "available_gb": round(mem.available / (1024 ** 3), 1),
            "percent": mem.percent
        }
    except ImportError:
        # Fallback wenn psutil fehlt
        return {
            "total_gb": 0.0,
            "used_gb": 0.0,
            "available_gb": 0.0,
            "percent": 0.0
        }

@router.get("/stats")
def get_system_stats():
    """Liefert Hardware-Status und ChromaDB-Chunk-Statistiken."""
    try:
        db_stats = {"nsi_local": 0, "nsi_cloud": 0}
        if chroma_store:
            db_stats = chroma_store.collection_stats()
            
        gpu_info = get_gpu_info()
        ram_info = get_system_ram()
        
        return {
            "database": db_stats,
            "gpu": gpu_info,
            "ram": ram_info
        }
    except Exception as e:
        logger.error("system_router.stats_error", fehler=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/idle")
def get_idle_status():
    """Gibt aktuelle Idle-Zeit des Systems zurück."""
    if not HAS_IDLE_WATCHER:
        return {
            "idle_seconds": 0.0,
            "idle_minutes": 0.0,
            "is_idle": False,
            "error": "Idle-Watcher nicht verfügbar"
        }
    try:
        idle_seconds = get_idle_seconds()
        idle_minutes = idle_seconds / 60
        # Standard-Threshold ist 15 Minuten
        is_idle = idle_seconds >= 15 * 60
        return {
            "idle_seconds": round(idle_seconds, 2),
            "idle_minutes": round(idle_minutes, 2),
            "is_idle": is_idle
        }
    except Exception as e:
        logger.error("system_router.idle_error", fehler=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
def reset_database():
    """Bereinigt beide ChromaDB-Collections."""
    try:
        if not chroma_store:
            raise HTTPException(status_code=503, detail="Datenbank-Store nicht initialisiert")
        chroma_store.reset()
        return {"status": "ok", "message": "Datenbank erfolgreich zurückgesetzt"}
    except Exception as e:
        logger.error("system_router.reset_error", fehler=str(e))
        raise HTTPException(status_code=500, detail=str(e))
