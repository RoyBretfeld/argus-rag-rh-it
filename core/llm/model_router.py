# NSI-RAGsystem Model Router
# Wrapper um MultiTierLLMRouter

import structlog
import os
from typing import Optional

try:
    from core.llm.ollama_client import LocalLLMClient, ollama_client
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger = structlog.get_logger(__name__)
    logger.warning("ollama_client_not_available", message="LLM nicht verf端gbar")

logger = structlog.get_logger(__name__)


class ModelRouter:
    """Wrapper um MultiTierLLMRouter mit 3-Tier Lokal/Cloud-Routing."""

    def __init__(
        self,
        local_url: str = None,
        cloud_url: str = None,
        model_local: str = None,
        model_cloud: str = None,
        model_vision: str = None,
    ):
        self.local_url = local_url or os.environ.get(
            "OLLAMA_LOCAL_URL", "http://localhost:11434"
        )
        self.cloud_url = cloud_url or os.environ.get(
            "OLLAMA_CLOUD_URL", "https://api.ollama.com"
        )
        self.model_local = model_local or os.environ.get(
            "MODEL_LOCAL", "mistral"
        )
        self.model_cloud = model_cloud or os.environ.get(
            "MODEL_CLOUD", "mistral-large-2512"
        )
        self.model_vision = model_vision or os.environ.get(
            "MODEL_VISION", "moondream"
        )

        self.client = ollama_client if OLLAMA_AVAILABLE else None
        self.logger = logger.bind(
            local_url=self.local_url,
            cloud_url=self.cloud_url,
        )

    def generate(
        self,
        prompt: str,
        vertraulich: bool,
        system: str = "",
    ) -> str:
        """
        Generiert Text mit dem passenden Modell.

        Args:
            prompt: Nutzer-Frage
            vertraulich: True = lokal (DSGVO), False = Cloud (Mistral Large)
            system: System-Prompt (optional)

        Returns:
            LLM-Antwort
        """
        if not OLLAMA_AVAILABLE:
            raise RuntimeError("Ollama nicht verf端gbar")

        if vertraulich:
            # IMMER lokal bei vertraulichen Dokumenten
            model = self.model_local
            use_cloud = False
        else:
            # Cloud bevorzugt, Fallback lokal
            model = self.model_cloud
            use_cloud = True

        try:
            response = self.client.generate(
                prompt=prompt,
                model=model,
                system=system,
                use_cloud=use_cloud,
            )

            self.logger.info(
                "model_router.generate",
                vertraulich=vertraulich,
                use_cloud=use_cloud,
                model=model,
            )

            return response

        except Exception as e:
            # Fallback wenn Cloud nicht erreichbar oder Fehler wirft (z.B. 401 Unauthorized)
            if use_cloud:
                self.logger.warning(
                    "model_router.cloud_fallback",
                    fehler=str(e),
                    message="Cloud fehlgeschlagen. Falle auf lokal zurück",
                )
                return self.client.generate(
                    prompt=prompt,
                    model=self.model_local,
                    system=system,
                    use_cloud=False,
                )
            raise

    def generate_vision(
        self,
        image_bytes: bytes,
        prompt: str,
        model: Optional[str] = None,
        use_cloud: bool = False,
    ) -> str:
        """
        Generiert Beschreibung für ein Bild.

        Args:
            image_bytes: Bild-Daten
            prompt: Prompt für das Bild
            model: Optionaler Modellname zur Überschreibung
            use_cloud: True, um Cloud-Verbindung zu nutzen

        Returns:
            Vision-Beschreibung
        """
        if not OLLAMA_AVAILABLE:
            raise RuntimeError("Ollama nicht verfügbar")

        if model is None:
            model = "gemma4:31b-cloud" if use_cloud else self.model_vision

        try:
            response = self.client.generate_vision(
                image_bytes=image_bytes,
                prompt=prompt,
                model=model,
                use_cloud=use_cloud,
            )
            return response
        except Exception as e:
            self.logger.error(
                "model_router.vision_error",
                fehler=str(e),
                model=model,
                use_cloud=use_cloud,
            )
            if use_cloud:
                self.logger.warning(
                    "model_router.vision_cloud_fallback",
                    fehler=str(e),
                    message="Cloud-Vision fehlgeschlagen. Falle auf lokal zurück",
                )
                try:
                    return self.client.generate_vision(
                        image_bytes=image_bytes,
                        prompt=prompt,
                        model=self.model_vision,
                        use_cloud=False,
                    )
                except Exception as local_err:
                    self.logger.error(
                        "model_router.vision_local_fallback_error",
                        fehler=str(local_err),
                    )
            raise
