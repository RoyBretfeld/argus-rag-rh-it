# NSI-RAGsystem Office Ingestor
# DOCX, PPTX, XLSX Verarbeitung

import structlog
from pathlib import Path
from typing import Optional

from unstructured.partition.auto import partition
import pandas as pd

logger = structlog.get_logger(__name__)


class OfficeIngestor:
    """Verarbeitet Office-Dokumente (DOCX, PPTX, XLSX) und Text-Dateien."""

    # Max Words pro Chunk
    MAX_WORDS_PER_CHUNK = 500

    def ingest(self, file_path: Path) -> list[dict]:
        """
        Verarbeitet ein Office-Dokument und extrahiert Chunks.

        Args:
            file_path: Pfad zur Datei

        Returns:
            List von Chunks mit Metadaten
        """
        logger.info(
            "office_ingestor.ingest_start", dateiname=file_path.name
        )

        suffix = file_path.suffix.lower()
        chunks = []

        try:
            # Verschiedene Dateitypen unterschiedlich verarbeiten
            if suffix in [".xlsx", ".xls"]:
                chunks = self._ingest_excel(file_path)
            elif suffix in [".docx", ".doc", ".pptx", ".ppt"]:
                chunks = self._ingest_office(file_path)
            elif suffix in [".txt", ".md", ".html"]:
                chunks = self._ingest_text(file_path)
            else:
                raise ValueError(f"Nicht unterstützter Typ: {suffix}")

            logger.info(
                "office_ingestor.ingest_complete",
                dateiname=file_path.name,
                chunks_erstellt=len(chunks),
            )

            return chunks

        except Exception as e:
            logger.error(
                "office_ingestor.error", dateiname=file_path.name, fehler=str(e)
            )
            raise

    def _ingest_excel(self, file_path: Path) -> list[dict]:
        """Verarbeitet XLSX/XLS Dateien."""
        chunks = []

        try:
            df = pd.read_excel(file_path)

            # Tabellen als strukturierten Text
            # Spaltennamen als Header
            columns = df.columns.tolist()
            header_line = " | ".join(columns)

            chunks.append({
                "text": header_line,
                "typ": "tabelle",
                "quelle": file_path.name,
                "spalten": columns,
                "zeilen_anzahl": len(df),
                "embedding_text": header_line,
            })

            # Alle Daten als Text
            all_data = df.to_string(index=False)

            # In Chunks aufteilen
            words = all_data.split()
            current_chunk = ""
            chunk_number = 1

            for word in words:
                if len(current_chunk.split()) + 1 > self.MAX_WORDS_PER_CHUNK:
                    chunks.append({
                        "text": current_chunk.strip(),
                        "typ": "tabelle",
                        "seite": chunk_number,
                        "quelle": file_path.name,
                        "embedding_text": current_chunk.strip(),
                    })
                    current_chunk = word
                    chunk_number += 1
                else:
                    current_chunk += f" {word}"

            if current_chunk:
                chunks.append({
                    "text": current_chunk.strip(),
                    "typ": "tabelle",
                    "seite": chunk_number,
                    "quelle": file_path.name,
                    "embedding_text": current_chunk.strip(),
                })

        except Exception as e:
            logger.warning(
                "office_ingestor.excel_error",
                dateiname=file_path.name,
                fehler=str(e),
            )

        return chunks

    def _ingest_office(self, file_path: Path) -> list[dict]:
        """Verarbeitet DOCX/PPTX Dateien."""
        elements = partition(str(file_path))
        return self._elements_to_chunks(elements, file_path)

    def _ingest_text(self, file_path: Path) -> list[dict]:
        """Verarbeitet TXT/MD/HTML Dateien."""
        content = file_path.read_text(encoding="utf-8")

        # In Chunks aufteilen
        words = content.split()
        chunks = []
        current_chunk = ""
        chunk_number = 1

        for word in words:
            if len(current_chunk.split()) + 1 > self.MAX_WORDS_PER_CHUNK:
                chunks.append({
                    "text": current_chunk.strip(),
                    "typ": "dokument",
                    "seite": chunk_number,
                    "quelle": file_path.name,
                    "embedding_text": current_chunk.strip(),
                })
                current_chunk = word
                chunk_number += 1
            else:
                current_chunk += f" {word}"

        if current_chunk:
            chunks.append({
                "text": current_chunk.strip(),
                "typ": "dokument",
                "seite": chunk_number,
                "quelle": file_path.name,
                "embedding_text": current_chunk.strip(),
            })

        return chunks

    def _elements_to_chunks(self, elements: list, file_path: Path) -> list[dict]:
        """Konvertiert unstructured elements zu Chunks."""
        chunks = []
        chunk_text = ""
        chunk_number = 1

        for element in elements:
            text = str(element)

            if len(chunk_text.split()) + len(text.split()) > self.MAX_WORDS_PER_CHUNK:
                if chunk_text:
                    chunks.append({
                        "text": chunk_text.strip(),
                        "typ": "dokument",
                        "seite": chunk_number,
                        "quelle": file_path.name,
                        "embedding_text": chunk_text.strip(),
                    })
                    chunk_text = text
                    chunk_number += 1
                else:
                    chunks.append({
                        "text": text,
                        "typ": "dokument",
                        "seite": chunk_number,
                        "quelle": file_path.name,
                        "embedding_text": text,
                    })
                    chunk_number += 1
            else:
                chunk_text += f"\n{text}"

        if chunk_text:
            chunks.append({
                "text": chunk_text.strip(),
                "typ": "dokument",
                "seite": chunk_number,
                "quelle": file_path.name,
                "embedding_text": chunk_text.strip(),
            })

        return chunks
