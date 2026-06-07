# NSI-RAGsystem Image Ingestor
# JPG, PNG, GIF, TIFF Verarbeitung

import structlog
from pathlib import Path
from typing import Optional

from PIL import Image
from io import BytesIO

logger = structlog.get_logger(__name__)

# Versuchsanmeldung für Ollama Client import
try:
    from core.llm.ollama_client import LocalLLMClient as OllamaClient
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("ollama_client_not_available", message="Vision-Beschreibung nicht verfügbar")


class ImageIngestor:
    """Verarbeitet Bilder (JPG, PNG, GIF, TIFF, WEBP)."""

    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"}

    def ingest(self, file_path: Path) -> list[dict]:
        """
        Verarbeitet ein Bild und extrahiert Informationen.

        Args:
            file_path: Pfad zum Bild

        Returns:
            List mit einem Chunk (Bild-Beschreibung)
        """
        logger.info(
            "image_ingestor.ingest_start", dateiname=file_path.name
        )

        suffix = file_path.suffix.lower()

        if suffix not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Nicht unterstützter Bildtyp: {suffix}")

        if not OLLAMA_AVAILABLE:
            self.logger.warning(
                "image_ingestor.vision_not_available",
                message="Ollama nicht verfügbar, Bild wird nicht beschrieben"
            )
            return []

        client = OllamaClient()

        try:
            # Bild laden
            with Image.open(file_path) as img:
                width, height = img.size
                format_name = img.format

                # GIF: nur erstes Frame
                if format_name == "GIF":
                    img.seek(0)

                # Bild als Bytes
                img_bytes = BytesIO()
                img.save(img_bytes, format="PNG")
                img_bytes = img_bytes.getvalue()

            # An Ollama schicken
            prompt = (
                "Beschreibe dieses Bild präzise auf Deutsch. "
                "Wenn es eine Grafik, Tabelle oder Formel ist, "
                "erkläre den Inhalt vollständig."
            )

            description = client.generate_vision(
                model="moondream",
                image_bytes=img_bytes,
                prompt=prompt
            )

            chunk = {
                "text": description or "Bild konnte nicht beschrieben werden.",
                "typ": "bild",
                "quelle": file_path.name,
                "aufloesung": {"breite": width, "höhe": height},
                "format": format_name,
                "embedding_text": description or "",
            }

            logger.info(
                "image_ingestor.ingest_complete",
                dateiname=file_path.name,
                width=width,
                height=height,
            )

            return [chunk]

        except Exception as e:
            logger.error(
                "image_ingestor.error", dateiname=file_path.name, fehler=str(e)
            )
            raise
