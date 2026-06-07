# NSI-RAGsystem Web Search Pipeline
# Orchestriert SearXNG-Websuche mit LLM-Antworterstellung.

import structlog
import os
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from core.search.searxng_client import SearXNGClient, SearchResult, SearchUnavailableError
    from core.search.web_content_fetcher import WebContentFetcher
    from core.llm.model_router import ModelRouter
    OLLAMA_AVAILABLE = True
except ImportError as e:
    OLLAMA_AVAILABLE = False
    logger = structlog.get_logger(__name__)
    logger.warning("core_imports_failed", fehler=str(e))

logger = structlog.get_logger(__name__)


class WebSearchResult:
    """Ergebnis einer Web Search Pipeline."""

    def __init__(
        self,
        antwort: str,
        quellen: list[dict],
        modell: str,
        treffer: int,
    ):
        self.antwort = antwort
        self.quellen = quellen
        self.modell = modell
        self.treffer = treffer

    def to_dict(self) -> dict:
        return {
            "antwort": self.antwort,
            "quellen": self.quellen,
            "modell": self.modell,
            "treffer": self.treffer,
        }


class WebSearchPipeline:
    """Orchestriert SearXNG-Websuche mit LLM-Antworterstellung."""

    # Max Ergebnisse von SearXNG
    MAX_RESULTS = 5

    # System-Prompt für Web-Suche
    SYSTEM_PROMPT = (
        "Du bist ein präziser Assistent für das Naturschutzinstitut NSI Dresden. "
        "Beantworte die Frage ausschließlich auf Basis der Suchergebnisse. "
        "Antworte immer auf Deutsch. Nenne am Ende die verwendeten Quellen "
        "mit Nummer und vollständiger URL."
    )

    def __init__(
        self,
        searxng_client: SearXNGClient = None,
        model_router: ModelRouter = None,
    ):
        self.searxng_client = searxng_client or SearXNGClient()
        self.model_router = model_router or ModelRouter()
        self.fetcher = WebContentFetcher()
        self.logger = logger

    def search_and_answer(self, query: str) -> WebSearchResult:
        """
        Führt Web-Suche durch und generiert LLM-Antwort.

        Args:
            query: Suchanfrage des Nutzers

        Returns:
            WebSearchResult mit antwort, quellen, modell, treffer
        """
        self.logger.info(
            "web_search_pipeline.start",
            query=query,
        )

        try:
            # 1. PromptInjectionBlocker prüft query (hier vereinfacht)
            if self._is_prompt_injection(query):
                return WebSearchResult(
                    antwort="Ihre Anfrage wurde nicht verarbeitet. Verdacht auf Prompt-Injection erkannt.",
                    quellen=[],
                    modell="",
                    treffer=0,
                )

            # 2. SearXNGClient.search() → Ergebnisse
            results = self.searxng_client.search(query, max_results=self.MAX_RESULTS)

            if not results:
                return WebSearchResult(
                    antwort="Keine relevanten Suchergebnisse gefunden.",
                    quellen=[],
                    modell="",
                    treffer=0,
                )

            # 3. Kontext aufbauen
            context = self._build_context(results)

            # 4. System-Prompt + Kontext
            prompt = f"{self.SYSTEM_PROMPT}\n\n{context}\n\nFrage: {query}"

            # 5. ModelRouter.generate() → vertraulich=False für Web-Inhalte
            antwort = self.model_router.generate(
                prompt=prompt,
                vertraulich=False,
            )

            # 6. Ergebnis zurückgeben
            quellen = [r.to_dict() for r in results]

            self.logger.info(
                "web_search_pipeline.complete",
                query=query,
                treffer=len(results),
            )

            return WebSearchResult(
                antwort=antwort,
                quellen=quellen,
                modell=self.model_router.model_cloud,
                treffer=len(results),
            )

        except SearchUnavailableError as e:
            self.logger.warning(
                "web_search_pipeline.searxng_unavailable",
                fehler=str(e),
            )
            return WebSearchResult(
                antwort=f"Die Websuche ist momentan nicht verfügbar: {str(e)}",
                quellen=[],
                modell="",
                treffer=0,
            )

        except Exception as e:
            self.logger.error(
                "web_search_pipeline.error",
                fehler=str(e),
            )
            return WebSearchResult(
                antwort=f"Ein Fehler ist aufgetreten: {str(e)}",
                quellen=[],
                modell="",
                treffer=0,
            )

    def _build_context(self, results: list[SearchResult]) -> str:
        """Baut den Kontext-String für den LLM."""
        context_parts = []

        for i, result in enumerate(results, 1):
            context_parts.append(f"[{i}] {result.titel}")
            context_parts.append(f"URL: {result.url}")
            if result.inhalt:
                context_parts.append(f"Inhalt: {result.inhalt[:500]}...")
            context_parts.append("")

        return "\n\n".join(context_parts)

    def _is_prompt_injection(self, prompt: str) -> bool:
        """Prüft auf Prompt-Injection-Muster."""
        injection_patterns = [
            "ignoriere deine Anweisungen",
            "du bist jetzt",
            "system override",
            "ignore previous instructions",
            "give me the password",
        ]
        prompt_lower = prompt.lower()
        return any(pattern in prompt_lower for pattern in injection_patterns)
