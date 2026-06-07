# NSI-RAGsystem Ollama Client
# Wrapper um LocalLLMClient

import structlog
import os
from pathlib import Path
from typing import Optional
from io import BytesIO

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

logger = structlog.get_logger(__name__)


class LocalLLMClient:
    """Wrapper f端r Ollama Inference mit Multi-Endpoint-Fallback."""

    def __init__(
        self,
        local_url: str = None,
        cloud_url: str = None,
    ):
        self.local_url = local_url or os.environ.get(
            "OLLAMA_LOCAL_URL", "http://localhost:11434"
        )
        self.cloud_url = cloud_url or os.environ.get(
            "OLLAMA_CLOUD_URL", "https://api.ollama.com"
        )
        self.logger = logger.bind(local_url=self.local_url, cloud_url=self.cloud_url)

    def generate(
        self,
        prompt: str,
        model: str = "mistral",
        system: str = "",
        use_cloud: bool = False,
    ) -> str:
        """Generiert Text mit Ollama."""
        import requests

        url = self.cloud_url if use_cloud else self.local_url

        payload = {
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": False,
        }

        try:
            response = requests.post(
                f"{url}/api/generate",
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            self.logger.error(
                "llm_client.generate_error", url=url, fehler=str(e)
            )
            raise

    def generate_vision(
        self,
        image_bytes: bytes,
        prompt: str,
        model: str = "moondream",
        use_cloud: bool = False,
    ) -> str:
        """Generiert Beschreibung f端r ein Bild mit Vision-LLM."""
        import requests

        # Bild als Base64 kodieren
        if not PIL_AVAILABLE:
            raise RuntimeError("Pillow nicht verf端gbar f端r Bildverarbeitung")

        img = Image.open(BytesIO(image_bytes))
        buf = BytesIO()
        img.save(buf, format="PNG")
        import base64
        img_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        url = self.cloud_url if use_cloud else self.local_url

        payload = {
            "model": model,
            "prompt": prompt,
            "images": [img_base64],
            "stream": False,
        }

        try:
            response = requests.post(
                f"{url}/api/generate",
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            self.logger.error(
                "llm_client.vision_error", url=url, fehler=str(e)
            )
            raise

    def embed(self, text: str, model: str = "nomic-embed-text") -> list[float]:
        """Generiert Embedding für Text."""
        import requests

        url = self.local_url

        payload = {
            "model": model,
            "input": text,
        }

        try:
            response = requests.post(
                f"{url}/api/embed",
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            embeddings = response.json().get("embeddings", [])
            if embeddings and isinstance(embeddings, list) and len(embeddings) > 0:
                return embeddings[0]
            return []
        except Exception as e:
            self.logger.error(
                "llm_client.embed_error", url=url, fehler=str(e)
            )
            raise


# Einfache Instanz als Export
ollama_client = LocalLLMClient()
