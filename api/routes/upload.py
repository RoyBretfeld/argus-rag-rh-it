import re
import tempfile
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse
from api.upload_handler import UploadHandler

router = APIRouter()

MAX_BATCH_FILES = 100
MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".csv", ".xml", ".json", ".eml",
    ".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff",
}

def normalize_source_path(source_path: str, fallback_name: str) -> str:
    """Normalisiert einen Browser-Relativpfad ohne Verzeichnis-Traversal."""
    normalized = (source_path or fallback_name).replace("\\", "/").strip("/")
    parts = [
        part.strip()
        for part in normalized.split("/")
        if part.strip() not in {"", ".", ".."}
    ]
    safe_parts = [re.sub(r"[\x00-\x1f]", "", part) for part in parts]
    safe_path = "/".join(part for part in safe_parts if part)
    return safe_path or Path(fallback_name.replace("\\", "/")).name

@router.post("")
async def upload_documents(
    files: list[UploadFile] = File(...),
    kategorie: str = Form("dokumente"),
    vertraulich: bool = Form(False),
    source_path: str = Form(""),
    ingest_order: int = Form(1),
    total_files: int = Form(1),
):
    if len(files) > MAX_BATCH_FILES:
        return JSONResponse(
            status_code=413,
            content={
                "error": f"Zu viele Dateien: maximal {MAX_BATCH_FILES} Dateien pro Upload-Batch erlaubt."
            },
        )

    handler = UploadHandler()
    total_chunks = 0
    errors = []
    processed_files = []
    
    for file in files:
        # Säubere den Dateinamen von eventuellen Pfadtrennern bei Ordner-Uploads
        # Ersetze Windows-Pfadtrenner durch Unix-Pfadtrenner für plattformübergreifende Robustheit
        upload_name = file.filename or "upload"
        filename_normalized = upload_name.replace("\\", "/")
        safe_filename = Path(filename_normalized).name
        if not safe_filename:
            continue

        extension = Path(safe_filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            errors.append(f"{file.filename}: Dateityp nicht unterstützt")
            continue
            
        relative_source = normalize_source_path(source_path, upload_name)
        file_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=extension,
                prefix="argus_ingest_",
                delete=False,
            ) as buffer:
                file_path = Path(buffer.name)
                bytes_written = 0
                while chunk := await file.read(1024 * 1024):
                    bytes_written += len(chunk)
                    if bytes_written > MAX_FILE_SIZE_BYTES:
                        raise ValueError("Datei größer als 200MB")
                    buffer.write(chunk)
            
            result = handler.process_upload(
                file_path,
                kategorie,
                vertraulich,
                source_path=relative_source,
                ingest_order=max(1, ingest_order),
                total_files=max(1, total_files),
            )
            if result.fehler:
                errors.append(f"{file.filename}: {result.fehler}")
            else:
                total_chunks += result.chunks_erstellt
                processed_files.append(relative_source)
        except Exception as e:
            errors.append(f"{relative_source}: {str(e)}")
        finally:
            if file_path and file_path.exists():
                file_path.unlink()
                
    if errors and not processed_files:
        return JSONResponse(status_code=500, content={"error": "; ".join(errors)})
        
    return JSONResponse(status_code=200, content={
        "message": f"Erfolgreich {len(processed_files)} Dateien verarbeitet.",
        "chunks_erstellt": total_chunks,
        "processed_files": processed_files,
        "errors": errors if errors else None
    })
