# NSI-RAGsystem Web Content Fetcher
# Ruft HTML-Content von URLs ab und extrahiert Text.

import requests
from bs4 import BeautifulSoup
import re
import structlog

logger = structlog.get_logger(__name__)


class WebContentFetcher:
    """Ruft HTML-Content von URLs ab und extrahiert Text."""

    # Timeout in Sekunden
    TIMEOUT = 8

    # Max Zeichen im Ergebnis
    MAX_LENGTH = 3000

    # User-Agent für Anfragen
    USER_AGENT = "NSI-RAGsystem/1.0 (naturschutzinstitut.de)"

    def fetch(self, url: str) -> str:
        """
        Ruft Content von einer URL ab und extrahiert Fließtext.

        Args:
            url: Ziel-URL

        Returns:
            Extrahierter Text, max 3000 Zeichen
        """
        try:
            # 1. Request mit Timeout
            response = requests.get(
                url,
                timeout=self.TIMEOUT,
                headers={"User-Agent": self.USER_AGENT},
            )

            # 2. Status prüfen
            if response.status_code != 200:
                self.logger.warning(
                    "web_fetcher.http_error",
                    url=url,
                    status_code=response.status_code,
                )
                return ""

            # 3. BeautifulSoup parsen
            soup = BeautifulSoup(response.text, "html.parser")

            # 4. Entfernen unerwünschter Elemente
            for selector in [
                "script",
                "style",
                "nav",
                "footer",
                "header",
                "aside",
                ".ads",
                ".cookie-banner",
            ]:
                for element in soup.select(selector):
                    element.decompose()

            # 5. Text aus relevanten Elementen extrahieren
            text_parts = []

            # Primäre Textquellen
            for tag in ["p", "article", "main", "section"]:
                for element in soup.find_all(tag):
                    text = element.get_text(" ", strip=True)
                    if text:
                        text_parts.append(text)

            # Fallback: body-Text
            if not text_parts:
                body = soup.find("body")
                if body:
                    text_parts = [body.get_text(" ", strip=True)]

            # 6. Text zusammenfügen und normalisieren
            full_text = "\n\n".join(text_parts)

            # Whitespace normalisieren (mehrfache Leerzeilen → eine)
            full_text = re.sub(r"\n\s*\n", "\n\n", full_text)
            full_text = re.sub(r" +", " ", full_text)

            # 7. Auf max LENGTH kürzen am letzten Satzende
            if len(full_text) > self.MAX_LENGTH:
                # Suche letzten Satzende vor MAX_LENGTH
                cutoff = full_text[: self.MAX_LENGTH]
                last_dot = max(cutoff.rfind("."), cutoff.rfind("!"), cutoff.rfind("?"))

                if last_dot > 0:
                    full_text = cutoff[: last_dot + 1].strip()
                else:
                    full_text = cutoff.strip()

            self.logger.info(
                "web_fetcher.fetch_success",
                url=url[:50] + "..." if len(url) > 50 else url,
                length=len(full_text),
            )

            return full_text

        except requests.exceptions.Timeout:
            self.logger.warning(
                "web_fetcher.timeout",
                url=url,
            )
            return ""

        except requests.exceptions.RequestException as e:
            self.logger.warning(
                "web_fetcher.request_error",
                url=url,
                fehler=str(e),
            )
            return ""

        except Exception as e:
            self.logger.error(
                "web_fetcher.error",
                url=url,
                fehler=str(e),
            )
            return ""
