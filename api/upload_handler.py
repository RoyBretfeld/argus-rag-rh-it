# NSI-RAGsystem Upload Handler
# Verarbeitet hochgeladene Dateien aus der WebApp

import structlog
import tempfile
import os
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
        self, file_path: Path, kategorie: str, vertraulich: bool
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

        self.logger.info(
            "upload_handler.process_start",
            dateiname=file_path.name,
            kategorie=kategorie,
            vertraulich=vertraulich,
        )

        try:
            # 1. Datei temporär speichern (bereits passiert, file_path ist da)
            temp_dir = Path(tempfile.gettempdir()) / "nsi_rag"
            temp_dir.mkdir(exist_ok=True)
            temp_file = temp_dir / file_path.name

            # Datei kopieren (falls notwendig)
            if not temp_file.exists():
                temp_file.write_bytes(file_path.read_bytes())

            # 2. DocumentTypeRouter.route() aufrufen
            result = route(temp_file, vertraulich)

            # 3. ChromaStore.add_chunks() aufrufen
            chunks_erstellt = CHROMA_STORE.add_chunks(
                result.chunks,
                result.collection,
            )

            # 4. Temporäre Datei löschen
            if temp_file.exists():
                temp_file.unlink()

            # 5. StructuredAuditLogger loggen
            self._log_audit(
                dateiname=file_path.name,
                kategorie=kategorie,
                chunks=chunks_erstellt,
                vertraulich=vertraulich,
            )

            # 6. Zeit berechnen
            dauer = (datetime.now() - self.startzeit).total_seconds()

            self.logger.info(
                "upload_handler.process_complete",
                dateiname=file_path.name,
                chunks=chunks_erstellt,
            )

            return UploadResult(
                dateiname=file_path.name,
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
                dateiname=file_path.name,
                fehler=str(e),
            )
            return UploadResult(
                dateiname=file_path.name,
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
