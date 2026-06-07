# NSI-RAGsystem Upload Handler
# Verarbeitet hochgeladene Dateien aus der WebApp

import structlog
import hashlib
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

logger = structlog.get_logger(__name__)

try:
    from core.ingestor.document_type_router import route
    from core.vectordb.chroma_store import ChromaStore
    CHROMA_STORE = ChromaStore()
except ImportError as e:
    logger.warning("core_imports_failed", fehler=str(e))


@dataclass
class UploadResult:
    """Ergebnis eines Uploads."""
    dateiname: str
    kategorie: str
    chunks_erstellt: int
    collection: str
    dauer_sekunden: float
    fehler: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "dateiname": self.dateiname,
            "kategorie": self.kategorie,
            "chunks_erstellt": self.chunks_erstellt,
            "collection": self.collection,
            "dauer_sekunden": round(self.dauer_sekunden, 2),
            "fehler": self.fehler,
        }


class UploadHandler:
    """Verarbeitet hochgeladene Dateien aus der WebApp."""

    def __init__(self):
        self.logger = logger.bind()
        self.startzeit = None

    def process_upload(
        self,
        file_path: Path,
        kategorie: str,
        vertraulich: bool,
        source_path: str | None = None,
        ingest_order: int = 1,
        total_files: int = 1,
    ) -> UploadResult:
        """
        Verarbeitet eine hochgeladene Datei.

        Args:
            file_path: Pfad zur temporären Datei
            kategorie: "dokumente" | "bilder" | "technische_daten"
            vertraulich: DSGVO-Flag

        Returns:
            UploadResult mit Ergebnis oder Fehler
        """
        self.startzeit = datetime.now()
        source_name = source_path or file_path.name

        self.logger.info(
            "upload_handler.process_start",
            dateiname=source_name,
            kategorie=kategorie,
            vertraulich=vertraulich,
            ingest_order=ingest_order,
            total_files=total_files,
        )

        try:
            source_sha256_before = self._sha256(file_path)

            # Die API hat bereits eine eindeutige temporäre Datei angelegt.
            result = route(file_path, vertraulich)
            source_sha256_after = self._sha256(file_path)
            if source_sha256_before != source_sha256_after:
                raise RuntimeError(
                    "Read-only-Schutz verletzt: Die Ingestion hat die temporäre Quelldatei verändert."
                )

            # Der relative NAS-Pfad bleibt als eindeutige, filterbare Quelle erhalten.
            for chunk_index, chunk in enumerate(result.chunks, start=1):
                chunk["quelle"] = source_name
                chunk["source_path"] = source_name
                chunk["ingest_order"] = ingest_order
                chunk["source_chunk_order"] = chunk_index
                chunk["total_files"] = total_files
                chunk["source_readonly"] = True
                chunk["source_sha256"] = source_sha256_before

            # 3. ChromaStore.add_chunks() aufrufen
            chunks_erstellt = CHROMA_STORE.add_chunks(
                result.chunks,
                result.collection,
            )

            # 4. StructuredAuditLogger loggen
            self._log_audit(
                dateiname=source_name,
                kategorie=kategorie,
                chunks=chunks_erstellt,
                vertraulich=vertraulich,
            )

            # 5. Zeit berechnen
            dauer = (datetime.now() - self.startzeit).total_seconds()

            self.logger.info(
                "upload_handler.process_complete",
                dateiname=source_name,
                chunks=chunks_erstellt,
            )

            return UploadResult(
                dateiname=source_name,
                kategorie=kategorie,
                chunks_erstellt=chunks_erstellt,
                collection=result.collection,
                dauer_sekunden=dauer,
                fehler=None,
            )

        except Exception as e:
            dauer = (datetime.now() - self.startzeit).total_seconds()
            self.logger.error(
                "upload_handler.error",
                dateiname=source_name,
                fehler=str(e),
            )
            return UploadResult(
                dateiname=source_name,
                kategorie=kategorie,
                chunks_erstellt=0,
                collection="",
                dauer_sekunden=dauer,
                fehler=str(e),
            )

    def _log_audit(
        self,
        dateiname: str,
        kategorie: str,
        chunks: int,
        vertraulich: bool,
    ):
        """Protokolliert den Upload audit-tauglich."""
        self.logger.info(
            "upload_handler.audit_log",
            dateiname=dateiname,
            kategorie=kategorie,
            chunks_erstellt=chunks,
            vertraulich=vertraulich,
        )

    @staticmethod
    def _sha256(file_path: Path) -> str:
        """Berechnet den Integritätsnachweis einer ausschließlich gelesenen Quelle."""
        digest = hashlib.sha256()
        with file_path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
