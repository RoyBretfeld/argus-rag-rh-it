# NSI-RAGsystem Source Verifier
# Bewertet Quellenqualität, Antwortsicherheit und einfache Widersprüche.

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class SourceEvidence:
    """Normalisierte Quelle für interne und Web-Belege."""

    source_type: str
    title: str
    text: str
    score: float | None = None


class SourceVerifier:
    """Erstellt eine nachvollziehbare Vertrauensbewertung für Chat-Antworten."""

    DATE_PATTERN = re.compile(
        r"\b(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{1,2}-\d{1,2})\b"
    )
    NUMBER_PATTERN = re.compile(r"\b\d+(?:[,.]\d+)?\s?(?:kg|g|m|cm|mm|%|eur|euro|mb|gb|tb)\b", re.IGNORECASE)

    def verify(
        self,
        frage: str,
        antwort: str,
        rag_quellen: list[dict[str, Any]] | None = None,
        web_quellen: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Bewertet Antwort und Quellen als strukturierte Prüf-Metadaten."""
        evidence = self._normalize_sources(rag_quellen or [], web_quellen or [])
        if self._is_system_profile_answer(evidence):
            return {
                "confidence": 0.95,
                "confidence_label": "hoch",
                "source_quality": "hoch",
                "verdict": "sicher",
                "needs_human_review": False,
                "conflicts": [],
                "source_counts": {
                    "total": len(evidence),
                    "internal": len(evidence),
                    "web": 0,
                },
                "evidence_notes": [
                    "Antwort stammt aus dem festen Argus-Systemprofil.",
                    "Diese Quelle definiert Identität, Rolle und Autonomiegrenzen.",
                ],
            }

        conflicts = self._detect_conflicts(evidence)
        confidence = self._calculate_confidence(evidence, conflicts)
        source_quality = self._quality_label(confidence)
        needs_human_review = bool(conflicts) or confidence < 0.55

        if conflicts:
            verdict = "widerspruch_gefunden"
        elif needs_human_review:
            verdict = "menschliche_pruefung_empfohlen"
        elif confidence >= 0.75:
            verdict = "sicher"
        else:
            verdict = "teilweise_unsicher"

        return {
            "confidence": round(confidence, 2),
            "confidence_label": self._confidence_label(confidence),
            "source_quality": source_quality,
            "verdict": verdict,
            "needs_human_review": needs_human_review,
            "conflicts": conflicts,
            "source_counts": {
                "total": len(evidence),
                "internal": sum(1 for item in evidence if item.source_type == "internal"),
                "web": sum(1 for item in evidence if item.source_type == "web"),
            },
            "evidence_notes": self._build_notes(frage, antwort, evidence, conflicts, confidence),
        }

    def _normalize_sources(
        self,
        rag_quellen: list[dict[str, Any]],
        web_quellen: list[dict[str, Any]],
    ) -> list[SourceEvidence]:
        evidence: list[SourceEvidence] = []

        for source in rag_quellen:
            title = str(source.get("quelle") or "Interne Wissensbasis")
            page = source.get("seite")
            if page not in (None, "", 0):
                title = f"{title} S.{page}"
            score = self._coerce_score(source.get("score"))
            evidence.append(
                SourceEvidence(
                    source_type="internal",
                    title=title,
                    text=str(source.get("text") or ""),
                    score=score,
                )
            )

        for source in web_quellen:
            title = str(source.get("titel") or source.get("title") or source.get("url") or "Webquelle")
            text = str(source.get("inhalt") or source.get("content") or source.get("snippet") or "")
            evidence.append(
                SourceEvidence(
                    source_type="web",
                    title=title,
                    text=text,
                    score=self._coerce_score(source.get("score")),
                )
            )

        return evidence

    def _is_system_profile_answer(self, evidence: list[SourceEvidence]) -> bool:
        """Erkennt Antworten aus dem festen Argus-Systemprofil."""
        if not evidence:
            return False
        return all(item.title.startswith("argus_profile") for item in evidence)

    def _detect_conflicts(self, evidence: list[SourceEvidence]) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        conflicts.extend(self._detect_value_conflicts(evidence, self.DATE_PATTERN, "Datumsangabe"))
        conflicts.extend(self._detect_value_conflicts(evidence, self.NUMBER_PATTERN, "Zahlenwert"))
        return conflicts[:5]

    def _detect_value_conflicts(
        self,
        evidence: list[SourceEvidence],
        pattern: re.Pattern[str],
        topic: str,
    ) -> list[dict[str, Any]]:
        values_by_source: list[tuple[SourceEvidence, set[str]]] = []
        for item in evidence:
            values = {self._normalize_value(match.group(0)) for match in pattern.finditer(item.text)}
            if values:
                values_by_source.append((item, values))

        conflicts: list[dict[str, Any]] = []
        for index, (source_a, values_a) in enumerate(values_by_source):
            for source_b, values_b in values_by_source[index + 1:]:
                if values_a.isdisjoint(values_b):
                    conflicts.append(
                        {
                            "topic": topic,
                            "source_a": source_a.title,
                            "value_a": sorted(values_a)[0],
                            "source_b": source_b.title,
                            "value_b": sorted(values_b)[0],
                            "severity": "mittel",
                        }
                    )
        return conflicts

    def _calculate_confidence(self, evidence: list[SourceEvidence], conflicts: list[dict[str, Any]]) -> float:
        if not evidence:
            return 0.2

        internal_count = sum(1 for item in evidence if item.source_type == "internal")
        web_count = sum(1 for item in evidence if item.source_type == "web")
        scored = [item.score for item in evidence if item.score is not None]

        confidence = 0.35
        confidence += min(len(evidence), 5) * 0.07
        if internal_count:
            confidence += 0.12
        if web_count:
            confidence += 0.08
        if internal_count and web_count:
            confidence += 0.08
        if scored:
            confidence += max(0.0, min(sum(scored) / len(scored), 1.0)) * 0.18
        if conflicts:
            confidence -= min(len(conflicts), 3) * 0.16

        return max(0.0, min(confidence, 0.95))

    def _build_notes(
        self,
        frage: str,
        antwort: str,
        evidence: list[SourceEvidence],
        conflicts: list[dict[str, Any]],
        confidence: float,
    ) -> list[str]:
        if not evidence:
            return ["Keine belastbaren Quellen für diese Antwort gefunden."]

        notes = [f"{len(evidence)} Quellen geprüft."]
        if any(item.source_type == "internal" for item in evidence):
            notes.append("Interne Wissensbasis wurde berücksichtigt.")
        if any(item.source_type == "web" for item in evidence):
            notes.append("Webquellen wurden berücksichtigt.")
        if conflicts:
            notes.append("Abweichende Werte zwischen Quellen erkannt.")
        elif confidence >= 0.75:
            notes.append("Quellenlage wirkt konsistent.")
        if frage and antwort and "nicht" in antwort.lower() and confidence < 0.6:
            notes.append("Antwort enthält Einschränkungen und sollte geprüft werden.")
        return notes

    def _coerce_score(self, value: Any) -> float | None:
        try:
            if value is None:
                return None
            return max(0.0, min(float(value), 1.0))
        except (TypeError, ValueError):
            return None

    def _normalize_value(self, value: str) -> str:
        return value.strip().lower().replace(",", ".")

    def _quality_label(self, confidence: float) -> str:
        if confidence >= 0.75:
            return "hoch"
        if confidence >= 0.55:
            return "mittel"
        return "niedrig"

    def _confidence_label(self, confidence: float) -> str:
        if confidence >= 0.75:
            return "hoch"
        if confidence >= 0.55:
            return "mittel"
        return "niedrig"
