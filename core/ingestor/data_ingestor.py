# NSI-RAGsystem Data Ingestor
# CSV, XML, JSON, EML Verarbeitung

import structlog
from pathlib import Path
from typing import Optional

import json
import csv
import xml.etree.ElementTree as ET
import email
from email.parser import BytesParser

logger = structlog.get_logger(__name__)


class DataIngestor:
    """Verarbeitet technische Daten (CSV, XML, JSON, EML)."""

    MAX_CHUNK_SIZE = 1000  # Zeichen

    def ingest(self, file_path: Path) -> list[dict]:
        """
        Verarbeitet eine technische Datei.

        Args:
            file_path: Pfad zur Datei

        Returns:
            List von Chunks mit Metadaten
        """
        logger.info(
            "data_ingestor.ingest_start", dateiname=file_path.name
        )

        suffix = file_path.suffix.lower()

        if suffix == ".csv":
            return self._ingest_csv(file_path)
        elif suffix == ".json":
            return self._ingest_json(file_path)
        elif suffix == ".xml":
            return self._ingest_xml(file_path)
        elif suffix == ".eml":
            return self._ingest_eml(file_path)
        else:
            raise ValueError(f"Nicht unterstützter Typ: {suffix}")

    def _ingest_csv(self, file_path: Path) -> list[dict]:
        """Verarbeitet CSV Dateien."""
        chunks = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                headers = next(reader, None)

                if not headers:
                    return []

                # Jede Zeile als Chunk (max 100 Zeilen pro Chunk)
                row_buffer = []
                chunk_number = 1

                for row in reader:
                    row_buffer.append(row)

                    if len(row_buffer) >= 100:
                        chunk_text = self._rows_to_text(row_buffer, headers)
                        chunks.append(self._create_chunk(chunk_text, chunk_number, file_path))
                        row_buffer = []
                        chunk_number += 1

                # Rest
                if row_buffer:
                    chunk_text = self._rows_to_text(row_buffer, headers)
                    chunks.append(self._create_chunk(chunk_text, chunk_number, file_path))

        except Exception as e:
            logger.error(
                "data_ingestor.csv_error", dateiname=file_path.name, fehler=str(e)
            )

        return chunks

    def _ingest_json(self, file_path: Path) -> list[dict]:
        """Verarbeitet JSON Dateien."""
        chunks = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                # Liste: jedes Element als Chunk
                for i, item in enumerate(data):
                    chunk_text = json.dumps(item, indent=2, ensure_ascii=False)
                    chunks.append(self._create_chunk(chunk_text, i + 1, file_path))
            elif isinstance(data, dict):
                # Dict: Schlüssel-Wert-Paare als Chunk
                for key, value in data.items():
                    chunk_text = f"{key}: {json.dumps(value, ensure_ascii=False)}"
                    chunks.append(self._create_chunk(chunk_text, 1, file_path))
            else:
                # Einfacher Wert
                chunk_text = json.dumps(data, ensure_ascii=False)
                chunks.append(self._create_chunk(chunk_text, 1, file_path))

        except Exception as e:
            logger.error(
                "data_ingestor.json_error", dateiname=file_path.name, fehler=str(e)
            )

        return chunks

    def _ingest_xml(self, file_path: Path) -> list[dict]:
        """Verarbeitet XML Dateien."""
        chunks = []

        try:
            tree = ET.parse(file_path)
            root = tree.getroot()

            # Rekursiv als Text
            def element_to_text(element: ET.Element, depth: int = 0) -> str:
                indent = "  " * depth
                text = f"{indent}{element.tag}"
                if element.attrib:
                    text += f" [{element.attrib}]"
                text += "\n"

                if element.text and element.text.strip():
                    text += f"{indent}  text: {element.text.strip()[:200]}\n"

                for child in element:
                    text += element_to_text(child, depth + 1)

                return text

            full_text = element_to_text(root)

            # In Chunks aufteilen
            for i in range(0, len(full_text), self.MAX_CHUNK_SIZE):
                chunk_text = full_text[i:i + self.MAX_CHUNK_SIZE]
                chunks.append(self._create_chunk(chunk_text, i // self.MAX_CHUNK_SIZE + 1, file_path))

        except Exception as e:
            logger.error(
                "data_ingestor.xml_error", dateiname=file_path.name, fehler=str(e)
            )

        return chunks

    def _ingest_eml(self, file_path: Path) -> list[dict]:
        """Verarbeitet EML Dateien."""
        chunks = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                msg = email.message_from_file(f)

            # Metadaten extrahieren
            subject = msg.get("Subject", "")
            from_addr = msg.get("From", "")
            date = msg.get("Date", "")

            # Body extrahieren
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8")
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8")

            # HTML bereinigen (wenn vorhanden)
            if "<html" in body.lower():
                from html.parser import HTMLParser

                class TextExtractor(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.text = []

                    def handle_data(self, data):
                        self.text.append(data)

                    def get_text(self):
                        return " ".join(self.text)

                parser = TextExtractor()
                parser.feed(body)
                body = parser.get_text()

            chunk_text = f"Betreff: {subject}\nAbsender: {from_addr}\nDatum: {date}\n\nText:\n{body[:1000]}"

            chunks.append({
                "text": chunk_text,
                "typ": "dokument",
                "quelle": file_path.name,
                "metadata": {
                    "betreff": subject,
                    "absender": from_addr,
                    "datum": date,
                },
                "embedding_text": f"{subject} {from_addr} {body[:500]}",
            })

        except Exception as e:
            logger.error(
                "data_ingestor.eml_error", dateiname=file_path.name, fehler=str(e)
            )

        return chunks

    def _create_chunk(self, text: str, number: int, file_path: Path) -> dict:
        """Erstellt einen Chunk mit Metadaten."""
        return {
            "text": text,
            "typ": "dokument",
            "seite": number,
            "quelle": file_path.name,
            "embedding_text": text,
        }

    def _rows_to_text(self, rows: list[list[str]], headers: list[str]) -> str:
        """Konvertiert eine Liste von CSV-Zeilen in einen strukturierten Text."""
        lines = []
        for row in rows:
            line_parts = []
            for i, val in enumerate(row):
                header = headers[i] if i < len(headers) else f"Spalte_{i+1}"
                line_parts.append(f"{header}: {val}")
            lines.append(", ".join(line_parts))
        return "\n".join(lines)
