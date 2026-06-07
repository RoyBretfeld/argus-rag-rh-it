# NSI-RAGsystem Document Type Router
# Dateityperkennung und Routing zu den richtigen Ingestoren

import structlog
from pathlib import Path
from typing import Literal

from core.ingestor.pdf_multimodal_ingestor import PDFMultimodalIngestor
from core.ingestor.office_ingestor import OfficeIngestor
from core.ingestor.image_ingestor import ImageIngestor
from core.ingestor.data_ingestor import DataIngestor

logger = structlog.get_logger(__name__)


# Routing-Tabelle: Erweiterung → Kategorie → Ingestor
FILE_TYPE_MAP: dict[str, tuple[Literal["dokumente", "bilder", "technische_daten"], str]] = {
    # Dokumente
    ".pdf": ("dokumente", "pdf"),
    ".docx": ("dokumente", "docx"),
    ".doc": ("dokumente", "docx"),
    ".pptx": ("dokumente", "pptx"),
    ".ppt": ("dokumente", "pptx"),
    ".xlsx": ("dokumente", "xlsx"),
    ".xls": ("dokumente", "xlsx"),
    ".txt": ("dokumente", "txt"),
    ".md": ("dokumente", "md"),
    ".html": ("dokumente", "html"),
    # Bilder
    ".jpg": ("bilder", "jpg"),
    ".jpeg": ("bilder", "jpg"),
    ".png": ("bilder", "png"),
    ".gif": ("bilder", "gif"),
    ".bmp": ("bilder", "bmp"),
    ".tiff": ("bilder", "tiff"),
    ".tif": ("bilder", "tiff"),
    ".webp": ("bilder", "webp"),
    # Technische Daten
    ".csv": ("technische_daten", "csv"),
    ".xml": ("technische_daten", "xml"),
    ".json": ("technische_daten", "json"),
    ".eml": ("technische_daten", "eml"),
}


class IngestResult:
    """Ergebnis eines Ingest-Vorgangs."""

    def __init__(
        self,
        chunks: list[dict],
        count: int,
        collection: str,
        dateiname: str,
        typ: str,
        kategorie: str,
    ):
        self.chunks = chunks
        self.count = count
        self.collection = collection
        self.dateiname = dateiname
        self.typ = typ
        self.kategorie = kategorie

    def to_dict(self) -> dict:
        return {
            "chunks": self.chunks,
            "count": self.count,
            "collection": self.collection,
            "dateiname": self.dateiname,
            "typ": self.typ,
            "kategorie": self.kategorie,
        }


def route(file_path: Path, vertraulich: bool) -> IngestResult:
    """
    Erkennt den Dateityp und leitet an den richtigen Ingestor weiter.

    Args:
        file_path: Pfad zur hochgeladenen Datei
        vertraulich: DSGVO-Flag für Collection-Auswahl

    Returns:
        IngestResult mit chunks, count, collection, dateiname, typ, kategorie

    Raises:
        ValueError: Bei unbekannten Dateitypen
    """
    suffix = file_path.suffix.lower()

    if suffix not in FILE_TYPE_MAP:
        verfügbare_typen = sorted(set(FILE_TYPE_MAP.keys()))
        raise ValueError(
            f"Nicht unterstützter Dateityp: '{suffix}'. "
            f"Unterstützt: {', '.join(verfügbare_typen)}"
        )

    kategorie, dateityp = FILE_TYPE_MAP[suffix]

    # Collection-Auswahl
    collection = "nsi_local" if vertraulich else "nsi_cloud"

    logger.info(
        "document_router.route",
        dateiname=file_path.name,
        kategorie=kategorie,
        dateityp=dateityp,
        collection=collection,
    )

    # Aufruf des richtigen Ingestors
    if kategorie == "dokumente":
        if suffix == ".pdf":
            result = PDFMultimodalIngestor(vertraulich=vertraulich).ingest(file_path)
        else:
            result = OfficeIngestor().ingest(file_path)

    elif kategorie == "bilder":
        result = ImageIngestor().ingest(file_path)

    elif kategorie == "technische_daten":
        result = DataIngestor().ingest(file_path)

    else:
        raise ValueError(f"Unbekannte Kategorie: {kategorie}")

    for chunk in result:
        chunk["kategorie"] = kategorie
        chunk["dateityp"] = dateityp

    logger.info(
        "document_router.route_success",
        dateiname=file_path.name,
        chunks_erstellt=len(result),
    )

    return IngestResult(
        chunks=result,
        count=len(result),
        collection=collection,
        dateiname=file_path.name,
        typ=dateityp,
        kategorie=kategorie,
    )
