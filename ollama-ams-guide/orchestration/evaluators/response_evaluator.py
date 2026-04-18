"""
Response Evaluator Module
Assigns a quality confidence score (0.0–1.0) to each EngineerResult
using pure heuristics — no LLM call required, runs in < 500ms.

Scoring criteria (weights must sum to 1.0):
  - Completeness      20%  — response addresses the prompt
  - Structure         15%  — headers, lists, code blocks present
  - Coherence         20%  — logical connectors, no contradictions
  - Length            10%  — appropriate detail level
  - Confidence weight 15%  — model's self-assessed confidence (HIGH/MEDIUM/LOW)
  - Response time     10%  — completed within expected threshold
  - Domain markers    10%  — technical vocabulary for the engineer type
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.engineer import EngineerResult


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Expected max inference time (seconds) per model tier
_RESPONSE_TIME_THRESHOLDS: dict[str, float] = {
    "phi3:mini":         20.0,
    "qwen2.5-coder:7b":  45.0,
    "mistral:7b":        45.0,
}
_DEFAULT_THRESHOLD = 60.0

# Minimum / ideal response length (chars) per engineer type
_LENGTH_PARAMS: dict[str, tuple[int, int, int]] = {
    # (too_short, ideal_min, too_long)
    "TRIAGE":   (80,  300,  2000),
    "CODE":     (100, 400,  4000),
    "ANALYSIS": (150, 500,  5000),
    "DOCS":     (200, 600,  6000),
}
_DEFAULT_LENGTH = (80, 300, 3000)

# Domain-specific vocabulary markers
_DOMAIN_MARKERS: dict[str, list[str]] = {
    "TRIAGE": [
        "severidad", "prioridad", "clasificación", "impacto", "p1", "p2",
        "componente", "síntoma", "alerta", "urgente",
    ],
    "CODE": [
        "def ", "function", "```", "error", "fix", "línea", "exception",
        "traceback", "import", "return", "class ", "método",
    ],
    "ANALYSIS": [
        "causa", "hipótesis", "impacto", "diagnóstico", "recomend",
        "evidencia", "correlaci", "rendimiento", "latencia", "bottleneck",
    ],
    "DOCS": [
        "##", "**", "incidente", "acción", "fecha", "runbook",
        "procedimiento", "responsable", "rca", "postmortem",
    ],
}

# Logical connectors that indicate coherence
_COHERENCE_MARKERS = [
    "por lo tanto", "en consecuencia", "debido a", "dado que", "ya que",
    "sin embargo", "no obstante", "además", "por otro lado", "finalmente",
    "en primer lugar", "a continuación", "en resumen", "therefore",
    "because", "however", "furthermore", "as a result", "in summary",
]

# Structure indicators
_STRUCTURE_MARKERS = [
    r"^#{1,3}\s",       # Markdown headers
    r"^\s*[-*•]\s",     # Bullet lists
    r"^\s*\d+\.\s",     # Numbered lists
    r"```",             # Code blocks
    r"\*\*[^*]+\*\*",   # Bold text
    r"`[^`]+`",         # Inline code
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ResponseEvaluation:
    """Quality evaluation result for a single EngineerResult."""

    engineer_result_id: str
    overall_score: float         # 0.0–1.0 weighted composite

    # Individual criterion scores (0.0–1.0 each)
    completeness: float
    structure: float
    coherence: float
    length_score: float
    confidence_weight: float
    response_time_score: float
    domain_markers: float

    # Decision flags
    is_acceptable: bool          # overall_score >= 0.7
    needs_human_review: bool     # 0.5 <= overall_score < 0.7
    needs_escalation: bool       # overall_score < 0.5

    reasoning: str               # Human-readable explanation

    # Optional: serialisable dict for session persistence
    def to_dict(self) -> dict:
        return {
            "engineer_result_id": self.engineer_result_id,
            "overall_score": round(self.overall_score, 4),
            "criteria": {
                "completeness":       round(self.completeness, 4),
                "structure":          round(self.structure, 4),
                "coherence":          round(self.coherence, 4),
                "length_score":       round(self.length_score, 4),
                "confidence_weight":  round(self.confidence_weight, 4),
                "response_time_score": round(self.response_time_score, 4),
                "domain_markers":     round(self.domain_markers, 4),
            },
            "decision": {
                "is_acceptable":       self.is_acceptable,
                "needs_human_review":  self.needs_human_review,
                "needs_escalation":    self.needs_escalation,
            },
            "reasoning": self.reasoning,
        }


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class ResponseEvaluator:
    """
    Heuristic quality scorer for EngineerResult objects.

    Usage:
        evaluator = ResponseEvaluator(engineer_type="ANALYSIS", model="mistral:7b")
        evaluation = evaluator.evaluate(result)
        print(evaluation.overall_score)
    """

    # Criterion weights — must sum to 1.0
    WEIGHTS = {
        "completeness":        0.20,
        "structure":           0.15,
        "coherence":           0.20,
        "length_score":        0.10,
        "confidence_weight":   0.15,
        "response_time_score": 0.10,
        "domain_markers":      0.10,
    }

    def __init__(self, engineer_type: str, model: str) -> None:
        self.engineer_type = engineer_type.upper()
        self.model = model

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def evaluate(self, result: "EngineerResult") -> ResponseEvaluation:
        """
        Score a complete EngineerResult.
        Runs in < 500ms (pure heuristics, no I/O).
        """
        text = result.result or ""

        completeness   = self._score_completeness(text)
        structure      = self._score_structure(text)
        coherence      = self._score_coherence(text)
        length_score   = self._score_length(text, result.engineer_type)
        conf_weight    = self._score_confidence(result.confidence)
        time_score     = self._score_response_time(
                             result.duration_seconds, result.model_used
                         )
        domain         = self._score_domain_markers(text, result.engineer_type)

        overall = (
            completeness   * self.WEIGHTS["completeness"]
            + structure    * self.WEIGHTS["structure"]
            + coherence    * self.WEIGHTS["coherence"]
            + length_score * self.WEIGHTS["length_score"]
            + conf_weight  * self.WEIGHTS["confidence_weight"]
            + time_score   * self.WEIGHTS["response_time_score"]
            + domain       * self.WEIGHTS["domain_markers"]
        )
        overall = round(min(max(overall, 0.0), 1.0), 4)

        is_acceptable      = overall >= 0.70
        needs_human_review = 0.50 <= overall < 0.70
        needs_escalation   = overall < 0.50

        reasoning = self._build_reasoning(
            overall, completeness, structure, coherence,
            length_score, conf_weight, time_score, domain,
            result.engineer_type, result.model_used,
        )

        return ResponseEvaluation(
            engineer_result_id   = result.task_id,
            overall_score        = overall,
            completeness         = completeness,
            structure            = structure,
            coherence            = coherence,
            length_score         = length_score,
            confidence_weight    = conf_weight,
            response_time_score  = time_score,
            domain_markers       = domain,
            is_acceptable        = is_acceptable,
            needs_human_review   = needs_human_review,
            needs_escalation     = needs_escalation,
            reasoning            = reasoning,
        )

    def quick_score(self, text: str, engineer_type: str) -> float:
        """
        Lightweight score for plain text — no EngineerResult needed.
        Skips confidence and response-time criteria; weights redistributed.
        """
        et = engineer_type.upper()
        c  = self._score_completeness(text)
        s  = self._score_structure(text)
        co = self._score_coherence(text)
        le = self._score_length(text, et)
        d  = self._score_domain_markers(text, et)

        # Simplified equal-weight blend of the 5 available criteria
        return round((c + s + co + le + d) / 5.0, 4)

    # ------------------------------------------------------------------
    # Individual criterion scorers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_completeness(text: str) -> float:
        """
        Proxy for completeness: penalise very short or clearly truncated
        responses. A response ending mid-sentence suggests truncation.
        """
        if not text:
            return 0.0
        length = len(text)
        if length < 30:
            return 0.05
        if length < 80:
            return 0.30

        # Penalise responses that seem cut off (no sentence-ending punctuation)
        stripped = text.rstrip()
        ends_cleanly = stripped[-1] in ".!?»\"'"
        penalty = 0.0 if ends_cleanly else 0.10

        # Reward structured responses (more content = more complete, up to a cap)
        score = min(1.0, length / 800.0) * 0.85 + 0.15
        return round(max(0.0, score - penalty), 4)

    @staticmethod
    def _score_structure(text: str) -> float:
        """Count distinct structural markdown patterns present."""
        if not text:
            return 0.0

        hits = 0
        for pattern in _STRUCTURE_MARKERS:
            if re.search(pattern, text, re.MULTILINE):
                hits += 1

        # Normalise: 0 hits → 0.1, max (all patterns) → 1.0
        return round(min(1.0, 0.10 + hits * (0.90 / len(_STRUCTURE_MARKERS))), 4)

    @staticmethod
    def _score_coherence(text: str) -> float:
        """Count logical connector phrases as coherence proxies."""
        if not text:
            return 0.0
        lower = text.lower()
        hits = sum(1 for c in _COHERENCE_MARKERS if c in lower)
        # 0 connectors → 0.3 (neutral), each connector improves score
        return round(min(1.0, 0.30 + hits * 0.12), 4)

    @staticmethod
    def _score_length(text: str, engineer_type: str) -> float:
        """Penalise too-short or excessively long responses."""
        if not text:
            return 0.0
        too_short, ideal_min, too_long = _LENGTH_PARAMS.get(
            engineer_type.upper(), _DEFAULT_LENGTH
        )
        length = len(text)
        if length < too_short:
            return 0.10
        if length < ideal_min:
            # Linear ramp from 0.40 to 1.0
            return round(0.40 + 0.60 * (length - too_short) / (ideal_min - too_short), 4)
        if length > too_long:
            # Mild penalty for bloat
            return 0.75
        return 1.0

    @staticmethod
    def _score_confidence(confidence: str) -> float:
        """Map model's self-assessed confidence string to a score."""
        return {"HIGH": 1.0, "MEDIUM": 0.60, "LOW": 0.20}.get(
            (confidence or "").upper(), 0.40
        )

    @staticmethod
    def _score_response_time(duration: float, model: str) -> float:
        """
        Score latency: within threshold → full score,
        up to 2× threshold → partial, beyond → low.
        """
        if duration <= 0:
            return 0.50  # unknown duration — neutral
        threshold = _RESPONSE_TIME_THRESHOLDS.get(model, _DEFAULT_THRESHOLD)
        if duration <= threshold:
            return 1.0
        if duration <= threshold * 2:
            return round(1.0 - 0.50 * (duration - threshold) / threshold, 4)
        return 0.10

    @staticmethod
    def _score_domain_markers(text: str, engineer_type: str) -> float:
        """Count domain-specific vocabulary hits."""
        if not text:
            return 0.0
        markers = _DOMAIN_MARKERS.get(engineer_type.upper(), [])
        if not markers:
            return 0.50
        lower = text.lower()
        hits = sum(1 for m in markers if m in lower)
        # Normalise: need at least 3 hits for a high score
        return round(min(1.0, hits / 3.0), 4)

    # ------------------------------------------------------------------
    # Reasoning builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_reasoning(
        overall: float,
        completeness: float,
        structure: float,
        coherence: float,
        length_score: float,
        conf_weight: float,
        time_score: float,
        domain: float,
        engineer_type: str,
        model: str,
    ) -> str:
        parts: list[str] = []

        # Overall verdict
        if overall >= 0.80:
            parts.append(f"✅ Respuesta de alta calidad (score={overall:.2f}). Aceptable sin revisión.")
        elif overall >= 0.70:
            parts.append(f"✅ Respuesta aceptable (score={overall:.2f}). Puede usarse directamente.")
        elif overall >= 0.50:
            parts.append(f"⚠️ Calidad media (score={overall:.2f}). Se recomienda revisión humana antes de usar.")
        else:
            parts.append(f"🔴 Calidad baja (score={overall:.2f}). Escalar a FRIDA o reintentar con otro modelo.")

        # Highlight weak criteria
        weak: list[str] = []
        if completeness < 0.50:
            weak.append("completitud insuficiente (respuesta muy corta o truncada)")
        if structure < 0.30:
            weak.append("sin estructura markdown (faltan headers o listas)")
        if coherence < 0.35:
            weak.append("baja coherencia (pocos conectores lógicos)")
        if length_score < 0.40:
            weak.append("longitud fuera del rango ideal para " + engineer_type)
        if conf_weight < 0.30:
            weak.append("confianza del modelo declarada como LOW")
        if time_score < 0.50:
            weak.append(f"tiempo de respuesta elevado para {model}")
        if domain < 0.33:
            weak.append(f"vocabulario técnico de {engineer_type} escaso")

        if weak:
            parts.append("Áreas débiles: " + "; ".join(weak) + ".")

        # Highlight strong criteria
        strong: list[str] = []
        if completeness >= 0.80:
            strong.append("completitud")
        if structure >= 0.70:
            strong.append("estructura")
        if coherence >= 0.70:
            strong.append("coherencia")
        if domain >= 0.67:
            strong.append("vocabulario de dominio")
        if strong:
            parts.append("Puntos fuertes: " + ", ".join(strong) + ".")

        return " ".join(parts)
