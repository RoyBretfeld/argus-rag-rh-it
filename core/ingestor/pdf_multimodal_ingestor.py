# NSI-RAGsystem PDF Multimodal Ingestor
# PDF: Jede Seite hybrid verarbeiten (Text + OCR + Vision) und splitten

import structlog
from pathlib import Path
from io import BytesIO
from PIL import Image
import fitz  # pymupdf

logger = structlog.get_logger(__name__)

# Versuch der Importierung von ModelRouter
try:
    from core.llm.model_router import ModelRouter
    MODEL_ROUTER_AVAILABLE = True
except ImportError:
    MODEL_ROUTER_AVAILABLE = False
    logger.warning("model_router_not_available", message="ModelRouter nicht verfügbar")


class PDFMultimodalIngestor:
    """Extrahiert Text, Tabellen und Medien hybrid aus PDFs unter Nutzung von OCR und Vision-LLMs."""

    def __init__(self, vision_model: str = "moondream", vertraulich: bool = True):
        self.vision_model = vision_model
        self.vertraulich = vertraulich
        self.logger = logger.bind(vision_model=vision_model, vertraulich=vertraulich)
        self.router = ModelRouter() if MODEL_ROUTER_AVAILABLE else None

    def _render_page_as_image(self, page: fitz.Page, resolution: int = 300) -> bytes:
        """Renderiert eine PDF-Seite als hochauflösendes PNG-Bild."""
        mat = fitz.Matrix(resolution / 72, resolution / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _run_easyocr_on_bytes(self, image_bytes: bytes) -> str:
        """Führt EasyOCR auf Bild-Bytes aus, um Text präzise zu extrahieren."""
        try:
            import easyocr
            import numpy as np

            # Konvertiere PIL-Bild zu Numpy-Array für EasyOCR
            image_pil = Image.open(BytesIO(image_bytes))
            img_array = np.array(image_pil)

            if not hasattr(self, "ocr_reader"):
                self.logger.info("pdf_multimodal_ingestor.load_ocr", message="Lade EasyOCR-Modelle...")
                self.ocr_reader = easyocr.Reader(["de", "en"], gpu=False)

            ocr_result = self.ocr_reader.readtext(img_array, detail=0)
            return " ".join(ocr_result)
        except Exception as e:
            self.logger.warning("pdf_multimodal_ingestor.ocr_failed", fehler=str(e))
            return ""

    def _run_vision_analysis(self, image_bytes: bytes) -> str:
        """Erstellt eine visuelle Beschreibung der Seite mittels Vision-LLM."""
        if not self.router:
            return ""

        prompt = (
            "Beschreibe das Layout und die visuellen Elemente dieser Seite auf Deutsch. "
            "Falls Tabellen, Diagramme oder Grafiken vorhanden sind, erkläre deren Aufbau "
            "und Inhalt detailliert. Lies keinen Fließtext vor, sondern konzentriere dich "
            "ausschließlich auf Tabellenwerte, Beschriftungen und Diagrammergebnisse."
        )

        # Verwende lokal gemma3:12b, falls vorhanden, sonst moondream
        model = "gemma3:12b" if self.vertraulich else "gemma4:31b-cloud"

        try:
            response = self.router.generate_vision(
                image_bytes=image_bytes,
                prompt=prompt,
                model=model,
                use_cloud=not self.vertraulich
            )
            return response.strip()
        except Exception as e:
            self.logger.warning("pdf_multimodal_ingestor.vision_failed", fehler=str(e))
            return ""

    def ingest(self, file_path: Path) -> list[dict]:
        """
        Extrahiert strukturierte Inhalte aus einer PDF-Datei durch hybride Text-Extraktion,
        EasyOCR-Erkennung (für Scans) und Vision-LLM-Bildbeschreibungen (für Medien/Tabellen).
        Der resultierende Text wird semantisch in kleinere Chunks zerlegt.

        Args:
            file_path: Pfad zur PDF-Datei

        Returns:
            List von Chunks mit text, typ, seite, quelle, embedding_text
        """
        self.logger.info(
            "pdf_multimodal_ingestor.ingest_start", dateiname=file_path.name
        )

        all_chunks = []

        try:
            doc = fitz.open(file_path)
            total_pages = len(doc)
            self.logger.info("pdf_multimodal_ingestor.pdf_opened", seitenanzahl=total_pages)

            for page_num in range(total_pages):
                page = doc[page_num]
                seite = page_num + 1
                self.logger.info("pdf_multimodal_ingestor.processing_page", seite=seite)

                try:
                    # 1. Native Textextraktion (100% genau bei Text-PDFs)
                    native_text = page.get_text("text").strip()

                    # 2. OCR als Fallback bei Scans (wenn native Textextraktion leer oder sehr kurz ist)
                    ocr_text = ""
                    image_bytes = None

                    if len(native_text) < 50:
                        self.logger.info("pdf_multimodal_ingestor.page_is_scan", seite=seite)
                        image_bytes = self._render_page_as_image(page, resolution=300)
                        ocr_text = self._run_easyocr_on_bytes(image_bytes)

                    # 3. Visuelle Beschreibung der Seite (für Diagramme, Tabellen, Layout)
                    image_list = page.get_images(full=True)
                    vision_description = ""

                    if image_list or len(native_text) < 50:
                        self.logger.info("pdf_multimodal_ingestor.vision_analysis_start", seite=seite)
                        if image_bytes is None:
                            # 200 dpi reicht für rein strukturelle Vision-Beschreibung vollkommen aus
                            image_bytes = self._render_page_as_image(page, resolution=200)
                        vision_description = self._run_vision_analysis(image_bytes)

                    # 4. Inhalte zusammenführen
                    combined_content_parts = []
                    if native_text:
                        combined_content_parts.append(f"Dokumententext (Extrahiert):\n{native_text}")
                    if ocr_text:
                        combined_content_parts.append(f"Gescannter Text (OCR):\n{ocr_text}")
                    if vision_description:
                        combined_content_parts.append(f"Visuelle Beschreibung (Diagramme/Bilder/Layout):\n{vision_description}")

                    combined_text = "\n\n".join(combined_content_parts).strip()

                    if not combined_text:
                        self.logger.warning("pdf_multimodal_ingestor.page_empty", seite=seite)
                        continue

                    # 5. Chunk-Splitting mit Überlappung (1500 Zeichen pro Chunk, 300 Zeichen Overlap)
                    chunk_size = 1500
                    overlap = 300
                    start = 0
                    page_chunks = 0

                    while start < len(combined_text):
                        end = start + chunk_size
                        chunk_payload = combined_text[start:end].strip()

                        if len(chunk_payload) > 10:
                            all_chunks.append({
                                "text": chunk_payload,
                                "typ": "pdf_seite",
                                "seite": seite,
                                "quelle": file_path.name,
                                "embedding_text": chunk_payload,
                            })
                            page_chunks += 1

                        if end >= len(combined_text):
                            break
                        start = end - overlap

                    self.logger.info(
                        "pdf_multimodal_ingestor.page_processed",
                        seite=seite,
                        chunks_erstellt=page_chunks
                    )

                except Exception as e:
                    self.logger.warning(
                        "pdf_multimodal_ingestor.page_failed",
                        seite=seite,
                        fehler=str(e)
                    )
                    # Versuche als Fallback eine einfache lokale Text-Extraktion, damit nichts verloren geht
                    try:
                        text_fallback = page.get_text("text").strip()
                        if text_fallback:
                            all_chunks.append({
                                "text": f"[Fallback-Text-Extraktion] {text_fallback}",
                                "typ": "pdf_seite",
                                "seite": seite,
                                "quelle": file_path.name,
                                "embedding_text": text_fallback,
                            })
                            self.logger.info("pdf_multimodal_ingestor.fallback_success", seite=seite)
                    except Exception as fallback_err:
                        self.logger.error("pdf_multimodal_ingestor.fallback_failed", seite=seite, fehler=str(fallback_err))

            doc.close()

            self.logger.info(
                "pdf_multimodal_ingestor.ingest_complete",
                dateiname=file_path.name,
                chunks_gesamt=len(all_chunks),
            )

            return all_chunks

        except fitz.FileDataError as e:
            self.logger.error(
                "pdf_multimodal_ingestor.invalid_pdf",
                dateiname=file_path.name,
                fehler=str(e),
            )
            raise ValueError(f"Ungültige PDF-Datei: {file_path.name}") from e

        except Exception as e:
            self.logger.error(
                "pdf_multimodal_ingestor.error",
                dateiname=file_path.name,
                fehler=str(e),
            )
            raise
