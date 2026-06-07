# NSI-RAGsystem SearXNG Client
# Ruft die lokale SearXNG JSON-API ab.

import os
import requests
import structlog
from typing import Optional
from core.search.web_content_fetcher import WebContentFetcher

logger = structlog.get_logger(__name__)


class SearchResult:
    """Ergebnis einer SearXNG-Suche."""
    def __init__(self, titel: str, url: str, snippet: str):
        self.titel = titel
        self.url = url
        self.snippet = snippet
        self.inhalt: str = ""

    def to_dict(self) -> dict:
        return {
            "titel": self.titel,
            "url": self.url,
            "snippet": self.snippet,
            "inhalt": self.inhalt,
        }


class SearchUnavailableError(Exception):
    """Exception wenn SearXNG nicht erreichbar ist."""
    pass


class SearXNGClient:
    """Ruft die lokale SearXNG JSON-API ab."""

    def __init__(
        self,
        searxng_url: str = None,
        timeout: int = None,
    ):
        self.searxng_url = searxng_url or os.environ.get(
            "SEARXNG_URL", "http://localhost:8080"
        )
        self.timeout = timeout or int(os.environ.get("SEARXNG_TIMEOUT", "10"))
        self.logger = logger.bind(searxng_url=self.searxng_url)

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """
        Führt eine Suche bei SearXNG durch.

        Args:
            query: Suchanfrage
            max_results: Maximalanzahl der Ergebnisse

        Returns:
            List von SearchResult Objekten

        Raises:
            SearchUnavailableError: Wenn SearXNG nicht erreichbar ist
        """
        # Inline-Import entfernt, da nun auf Modul-Ebene

        url = f"{self.searxng_url}/search"
        params = {
            "q": query,
            "format": "json",
            "language": "de",
            "categories": "general",
        }

        try:
            response = requests.get(
                url,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()

            data = response.json()
            results_data = data.get("results", [])[:max_results]

            results = []
            for r in results_data:
                result = SearchResult(
                    titel=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", ""),
                )
                results.append(result)

            # WebContentFetcher für jede URL aufrufen
            fetcher = WebContentFetcher()
            for result in results:
                try:
                    result.inhalt = fetcher.fetch(result.url)
                except Exception as e:
                    self.logger.warning(
                        "searxng.content_fetch_error",
                        url=result.url,
                        fehler=str(e),
                    )

            # Audit-Logging
            self.logger.info(
                "searxng.search",
                query=query,
                treffer_count=len(results),
            )

            return results

        except requests.exceptions.ConnectionError as e:
            self.logger.error(
                "searxng.connection_error",
                fehler=str(e),
            )
            raise SearchUnavailableError(
                f"SearXNG nicht erreichbar unter {self.searxng_url}. "
                "Bitte 'docker start searxng' ausführen."
            ) from e

        except requests.exceptions.Timeout as e:
            self.logger.error(
                "searxng.timeout_error",
                fehler=str(e),
            )
            raise SearchUnavailableError(
                f"SearXNG Anfrage timeout nach {self.timeout} Sekunden."
            ) from e

        except Exception as e:
            self.logger.error(
                "searxng.error",
                fehler=str(e),
            )
            raise SearchUnavailableError(
                f"SearXNG nicht erreichbar unter {self.searxng_url}."
            ) from e

    def health_check(self) -> bool:
        """
        Prüft ob SearXNG erreichbar ist.

        Returns:
            True = erreichbar, False = nicht erreichbar
        """
        health_url = f"{self.searxng_url}/healthz"

        try:
            response = requests.get(health_url, timeout=2)
            return response.status_code == 200
        except Exception:
            return False
