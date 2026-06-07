# NSI-RAGsystem Chat Handler
# Erweitert um Modus-Router: Wissensbasis / Internet / Beides

from __future__ import annotations

import structlog
import os
from typing import Optional
from dataclasses import dataclass
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = structlog.get_logger(__name__)

try:
    from core.agent.argus_profile import ArgusProfile
    from core.rag.rag_pipeline import RAGPipeline
    from core.reasoning.source_verifier import SourceVerifier
    from core.search.web_search_pipeline import WebSearchPipeline
    from core.search.searxng_client import SearchUnavailableError
    RAG_AVAILABLE = True
except ImportError as e:
    RAG_AVAILABLE = False
    ArgusProfile = None
    SourceVerifier = None
    logger.warning("rag_imports_failed", fehler=str(e))


class Modus:
    """Verfügbare Modi für die Chat-Verarbeitung."""
    WISSENSBASIS = "wissensbasis"
    INTERNET = "internet"
    BEIDES = "beides"


@dataclass
class ChatResult:
    """Ergebnis einer Chat-Verarbeitung."""
    antwort: str
    rag_quellen: list[dict]
    web_quellen: list[dict]
    modell: str
    modus: str
    vertraulich: bool
    dauer_sekunden: float
    verification: dict

    def to_dict(self) -> dict:
        return {
            "antwort": self.antwort,
            "rag_quellen": self.rag_quellen,
            "web_quellen": self.web_quellen,
            "modell": self.modell,
            "modus": self.modus,
            "vertraulich": self.vertraulich,
            "dauer_sekunden": round(self.dauer_sekunden, 2),
            "verification": self.verification,
        }


class ChatHandler:
    """Verarbeitet Chat-Anfragen mit Modus-Router."""

    def __init__(
        self,
        rag_pipeline: RAGPipeline = None,
        web_search_pipeline: WebSearchPipeline = None,
        model_router: object = None,
        source_verifier: SourceVerifier = None,
        argus_profile: ArgusProfile = None,
    ):
        self.rag_pipeline = rag_pipeline
        self.web_search_pipeline = web_search_pipeline
        self.model_router = model_router
        self.source_verifier = source_verifier or (SourceVerifier() if SourceVerifier else None)
        self.argus_profile = argus_profile or (ArgusProfile() if ArgusProfile else None)
        self.logger = logger

    def answer(self, frage: str, modus: str, vertraulich: bool, filter_metadata: Optional[dict] = None) -> ChatResult:
        """
        Verarbeitet eine Chat-Frage mit dem gewählten Modus.

        Args:
            frage: Nutzer-Frage
            modus: "wissensbasis" | "internet" | "beides"
            vertraulich: DSGVO-Flag für lokal/cloud Routing
            filter_metadata: Optionaler Metadaten-Filter

        Returns:
            ChatResult mit Antwort und Quellen
        """
        startzeit = datetime.now()

        self.logger.info(
            "chat_handler.answer",
            frage=frage[:50] + "..." if len(frage) > 50 else frage,
            modus=modus,
            vertraulich=vertraulich,
            filter_metadata=filter_metadata,
        )

        try:
            if self.argus_profile and self.argus_profile.is_identity_question(frage):
                result = self._handle_identity_question()

            elif modus == Modus.WISSENSBASIS:
                result = self._handle_wissensbasis(frage, vertraulich, filter_metadata)

            elif modus == Modus.INTERNET:
                result = self._handle_internet(frage)

            elif modus == Modus.BEIDES:
                result = self._handle_beides(frage, vertraulich, filter_metadata)

            else:
                raise ValueError(f"Unbekannter Modus: {modus}")

            result.dauer_sekunden = max(0.0001, (datetime.now() - startzeit).total_seconds())
            result.verification = self._verify_sources(frage, result)

            return result

        except Exception as e:
            self.logger.error(
                "chat_handler.error",
                frage=frage,
                modus=modus,
                fehler=str(e),
            )
            return ChatResult(
                antwort=f"Ein Fehler ist aufgetreten: {str(e)}",
                rag_quellen=[],
                web_quellen=[],
                modell="",
                modus=modus,
                vertraulich=vertraulich,
                dauer_sekunden=max(0.0001, (datetime.now() - startzeit).total_seconds()),
                verification={},
            )

    def _verify_sources(self, frage: str, result: ChatResult) -> dict:
        """Führt Quellenprüfung aus, falls der SourceVerifier verfügbar ist."""
        if not self.source_verifier:
            return {}
        return self.source_verifier.verify(
            frage=frage,
            antwort=result.antwort,
            rag_quellen=result.rag_quellen,
            web_quellen=result.web_quellen,
        )

    def _handle_identity_question(self) -> ChatResult:
        """Antwortet aus dem Argus-Profil statt aus der Dokumentenbasis."""
        return ChatResult(
            antwort=self.argus_profile.answer_identity(),
            rag_quellen=self.argus_profile.capability_sources(),
            web_quellen=[],
            modell="argus-profile",
            modus="systemprofil",
            vertraulich=False,
            dauer_sekunden=0,
            verification={},
        )

    def _handle_wissensbasis(self, frage: str, vertraulich: bool, filter_metadata: Optional[dict] = None) -> ChatResult:
        """Verarbeitung im Wissensbasis-Modus (nur RAG)."""
        if not RAG_AVAILABLE:
            return ChatResult(
                antwort="RAG-Pipeline nicht verfügbar. Bitte System administrator kontaktieren.",
                rag_quellen=[],
                web_quellen=[],
                modell="",
                modus=Modus.WISSENSBASIS,
                vertraulich=vertraulich,
                dauer_sekunden=0,
                verification={},
            )

        rag_result = self.rag_pipeline.query(frage, filter_metadata)

        return ChatResult(
            antwort=rag_result.get("antwort", ""),
            rag_quellen=rag_result.get("quellen", []),
            web_quellen=[],
            modell=rag_result.get("modell", "mistral-7b-lokal"),
            modus=Modus.WISSENSBASIS,
            vertraulich=rag_result.get("vertraulich", vertraulich),
            dauer_sekunden=0,
            verification=rag_result.get("verification", {}),
        )

    def _handle_internet(self, frage: str) -> ChatResult:
        """Verarbeitung im Internet-Modus (nur Web-Suche)."""
        if not RAG_AVAILABLE:
            return ChatResult(
                antwort="Web-Suche nicht verfügbar. Bitte SearXNG prüfen.",
                rag_quellen=[],
                web_quellen=[],
                modell="",
                modus=Modus.INTERNET,
                vertraulich=False,
                dauer_sekunden=0,
                verification={},
            )

        web_result = self.web_search_pipeline.search_and_answer(frage)

        return ChatResult(
            antwort=web_result.antwort,
            rag_quellen=[],
            web_quellen=web_result.quellen,
            modell=web_result.modell,
            modus=Modus.INTERNET,
            vertraulich=False,
            dauer_sekunden=0,
            verification={},
        )

    def _handle_beides(self, frage: str, vertraulich: bool, filter_metadata: Optional[dict] = None) -> ChatResult:
        """Verarbeitung im Beides-Modus (RAG + Web-Suche)."""
        if not RAG_AVAILABLE:
            return ChatResult(
                antwort="Kombinierte Suche nicht verfügbar. Bitte Systemadministrator kontaktieren.",
                rag_quellen=[],
                web_quellen=[],
                modell="",
                modus=Modus.BEIDES,
                vertraulich=vertraulich,
                dauer_sekunden=0,
                verification={},
            )

        # Beide Pipelines parallel ausführen
        rag_futures = []
        web_futures = []

        with ThreadPoolExecutor(max_workers=2) as executor:
            # RAG Pipeline im Thread
            rag_futures.append(
                executor.submit(self.rag_pipeline.query, frage, filter_metadata)
            )
            # Web Search im Thread
            web_futures.append(
                executor.submit(self.web_search_pipeline.search_and_answer, frage)
            )

        # Ergebnisse sammeln
        rag_result = None
        web_result = None

        for future in as_completed(rag_futures + web_futures):
            try:
                result = future.result()
                if isinstance(result, dict):  # RAG-Ergebnis
                    rag_result = result
                else:  # Web-Search-Ergebnis (Objekt)
                    web_result = result
            except Exception as e:
                self.logger.warning(
                    "chat_handler.parallel_error",
                    fehler=str(e),
                )

        # Synthese-Antwort generieren
        if rag_result and web_result:
            synthese_prompt = (
                f"Kombiniere folgende zwei Antwortquellen zu einer kohärenten Antwort auf Deutsch. "
                f"Quelle 1 (interne Wissensbasis): {rag_result.get('antwort', '')} "
                f"Quelle 2 (aktuelle Websuche): {web_result.antwort} "
                f"Frage: {frage}"
            )

            synthese_antwort = self.model_router.generate(
                prompt=synthese_prompt,
                vertraulich=vertraulich,
            )

            return ChatResult(
                antwort=synthese_antwort,
                rag_quellen=rag_result.get("quellen", []),
                web_quellen=web_result.quellen,
                modell=self.model_router.model_cloud if not vertraulich else self.model_router.model_local,
                modus=Modus.BEIDES,
                vertraulich=vertraulich,
                dauer_sekunden=0,
                verification={},
            )

        # Fallback: nur eine Quelle verfügbar
        if rag_result:
            return ChatResult(
                antwort=rag_result.get("antwort", ""),
                rag_quellen=rag_result.get("quellen", []),
                web_quellen=[],
                modell=rag_result.get("modell", "mistral-7b-lokal"),
                modus=Modus.BEIDES,
                vertraulich=vertraulich,
                dauer_sekunden=0,
                verification=rag_result.get("verification", {}),
            )

        if web_result:
            return ChatResult(
                antwort=web_result.antwort,
                rag_quellen=[],
                web_quellen=web_result.quellen,
                modell=web_result.modell,
                modus=Modus.BEIDES,
                vertraulich=False,
                dauer_sekunden=0,
                verification={},
            )

        return ChatResult(
            antwort="Keine Ergebnisse aus beiden Quellen.",
            rag_quellen=[],
            web_quellen=[],
            modell="",
            modus=Modus.BEIDES,
            vertraulich=vertraulich,
            dauer_sekunden=0,
            verification={},
        )
