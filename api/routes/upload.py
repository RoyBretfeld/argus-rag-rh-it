import os
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

@router.post("")
async def upload_documents(
    files: list[UploadFile] = File(...),
    kategorie: str = Form("dokumente"),
    vertraulich: bool = Form(False)
):
    if len(files) > MAX_BATCH_FILES:
        return JSONResponse(
            status_code=413,
            content={
                "error": f"Zu viele Dateien: maximal {MAX_BATCH_FILES} Dateien pro Upload-Batch erlaubt."
            },
        )

    handler = UploadHandler()
    temp_dir = Path("data/tmp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    total_chunks = 0
    errors = []
    processed_files = []
    
    for file in files:
        # Säubere den Dateinamen von eventuellen Pfadtrennern bei Ordner-Uploads
        # Ersetze Windows-Pfadtrenner durch Unix-Pfadtrenner für plattformübergreifende Robustheit
        filename_normalized = file.filename.replace("\\", "/")
        safe_filename = Path(filename_normalized).name
        if not safe_filename:
            continue

        extension = Path(safe_filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            errors.append(f"{file.filename}: Dateityp nicht unterstützt")
            continue
            
        file_path = temp_dir / safe_filename
        
        try:
            content = await file.read()
            if len(content) > MAX_FILE_SIZE_BYTES:
                errors.append(f"{file.filename}: Datei größer als 200MB")
                continue

            with open(file_path, "wb") as buffer:
                buffer.write(content)
            
            result = handler.process_upload(file_path, kategorie, vertraulich)
            if result.fehler:
                errors.append(f"{file.filename}: {result.fehler}")
            else:
                total_chunks += result.chunks_erstellt
                processed_files.append(file.filename)
        except Exception as e:
            errors.append(f"{file.filename}: {str(e)}")
        finally:
            if file_path.exists():
                file_path.unlink()
                
    if errors and not processed_files:
        return JSONResponse(status_code=500, content={"error": "; ".join(errors)})
        
    return JSONResponse(status_code=200, content={
        "message": f"Erfolgreich {len(processed_files)} Dateien verarbeitet.",
        "chunks_erstellt": total_chunks,
        "errors": errors if errors else None
    })
