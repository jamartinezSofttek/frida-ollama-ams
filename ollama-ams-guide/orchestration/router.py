"""
Task Router Module
Implements keyword-based and heuristic task routing logic.
Determines which engineer type (TRIAGE, CODE, ANALYSIS, DOCS) and which
local Ollama model should handle a given task, without requiring an LLM call.

Used as:
  - A fast pre-filter before architect LLM decomposition
  - A standalone fallback when the architect model is unavailable
  - A direct router for single-task mode (no decomposition needed)
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_ENGINEER_TYPES = {"TRIAGE", "CODE", "ANALYSIS", "DOCS"}

# Default model assignment per engineer type (matches config.yaml)
DEFAULT_MODEL_MAP: dict[str, str] = {
    "TRIAGE":   "phi3:mini",
    "CODE":     "qwen2.5-coder:7b",
    "ANALYSIS": "mistral:7b",
    "DOCS":     "mistral:7b",
}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RoutingDecision:
    """Result of a routing evaluation for a single task."""
    engineer_type: str          # TRIAGE | CODE | ANALYSIS | DOCS
    model: str                  # Ollama model tag
    confidence: float           # 0.0 – 1.0 (how confident the router is)
    reason: str                 # Human-readable explanation
    keyword_hits: list[str]     # Keywords that matched


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class TaskRouter:
    """
    Routes a task description to the most appropriate engineer type and model
    using configurable keyword lists and heuristic scoring.

    Configuration is loaded from the 'routing' and 'agents.engineers'
    sections of config.yaml.  The router is stateless and thread-safe.
    """

    def __init__(self, routing_config: dict, engineer_config: dict):
        """
        Args:
            routing_config: The 'routing' section of config.yaml
                            (keyword lists per engineer type).
            engineer_config: The 'agents.engineers' section of config.yaml
                             (model assignments per engineer type).
        """
        self.keywords: dict[str, list[str]] = {
            "TRIAGE":   [k.lower() for k in routing_config.get("triage_keywords",   [])],
            "CODE":     [k.lower() for k in routing_config.get("code_keywords",     [])],
            "ANALYSIS": [k.lower() for k in routing_config.get("analysis_keywords", [])],
            "DOCS":     [k.lower() for k in routing_config.get("docs_keywords",     [])],
        }

        self.model_map: dict[str, str] = {
            etype: cfg.get("model", DEFAULT_MODEL_MAP.get(etype, "mistral:7b"))
            for etype, cfg in engineer_config.items()
            if etype in VALID_ENGINEER_TYPES
        }
        # Fill gaps with defaults
        for etype, model in DEFAULT_MODEL_MAP.items():
            self.model_map.setdefault(etype, model)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(text: str) -> str:
        """
        Lowercase and strip Unicode accent marks so that accented Spanish
        characters (á, é, í, ó, ú, ü, ñ, …) match ASCII keywords stored
        in config.yaml without needing duplicate entries.

        Example: "crítico" → "critico", "caído" → "caido"
        """
        nfkd = unicodedata.normalize("NFKD", text.lower())
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    def route(self, task: str) -> RoutingDecision:
        """
        Evaluate a task string and return the best RoutingDecision.

        Scoring:
          - Each keyword match in the task adds 1 point to that type's score.
          - Longer keyword phrases get a 1.5× weight (more specific → higher trust).
          - The type with the highest score wins.
          - Ties are broken by priority order: CODE > ANALYSIS > DOCS > TRIAGE.
          - If no keywords match, defaults to ANALYSIS/mistral:7b.
        """
        task_lower = self._normalize(task)
        scores: dict[str, float] = {etype: 0.0 for etype in VALID_ENGINEER_TYPES}
        hits: dict[str, list[str]] = {etype: [] for etype in VALID_ENGINEER_TYPES}

        for etype, kw_list in self.keywords.items():
            for kw in kw_list:
                if kw in task_lower:
                    weight = 1.5 if len(kw.split()) > 1 else 1.0
                    scores[etype] += weight
                    hits[etype].append(kw)

        # Tie-breaking priority
        priority = ["CODE", "ANALYSIS", "DOCS", "TRIAGE"]
        best_type = max(
            priority,
            key=lambda t: (scores[t], priority.index(t) * -1)
        )

        total_hits = sum(scores.values())
        confidence = min(1.0, scores[best_type] / 5.0) if total_hits > 0 else 0.0

        if total_hits == 0:
            best_type = "ANALYSIS"
            reason = "No keyword matches found; defaulting to ANALYSIS."
        else:
            reason = (
                f"Matched {len(hits[best_type])} keyword(s) for {best_type}: "
                f"{', '.join(hits[best_type][:5])}"
            )

        decision = RoutingDecision(
            engineer_type=best_type,
            model=self.model_map[best_type],
            confidence=round(confidence, 3),
            reason=reason,
            keyword_hits=hits[best_type],
        )

        logger.debug(
            "[Router] '%s...' → %s (model=%s, confidence=%.2f)",
            task[:60], best_type, decision.model, confidence
        )
        return decision

    def route_multi(self, task: str, max_types: int = 3) -> list[RoutingDecision]:
        """
        Return up to max_types RoutingDecisions sorted by score descending.
        Useful when the orchestrator wants to build a multi-engineer pipeline
        without using the architect LLM.

        Only types with at least 1 keyword match are included.
        Always includes at least one decision (the top result from route()).
        """
        task_lower = self._normalize(task)
        scores: dict[str, float] = {etype: 0.0 for etype in VALID_ENGINEER_TYPES}
        hits: dict[str, list[str]] = {etype: [] for etype in VALID_ENGINEER_TYPES}

        for etype, kw_list in self.keywords.items():
            for kw in kw_list:
                if kw in task_lower:
                    weight = 1.5 if len(kw.split()) > 1 else 1.0
                    scores[etype] += weight
                    hits[etype].append(kw)

        # Sort by score descending, keep only those with hits
        sorted_types = sorted(
            [t for t in VALID_ENGINEER_TYPES if scores[t] > 0],
            key=lambda t: scores[t],
            reverse=True,
        )

        # Guarantee at least one result
        if not sorted_types:
            return [self.route(task)]

        decisions: list[RoutingDecision] = []
        total = sum(scores[t] for t in sorted_types)

        for etype in sorted_types[:max_types]:
            confidence = min(1.0, scores[etype] / 5.0)
            decisions.append(RoutingDecision(
                engineer_type=etype,
                model=self.model_map[etype],
                confidence=round(confidence, 3),
                reason=f"Score {scores[etype]:.1f}/{total:.1f}; hits: {', '.join(hits[etype][:5])}",
                keyword_hits=hits[etype],
            ))

        return decisions

    def get_model_for_type(self, engineer_type: str) -> str:
        """Return the configured model for a given engineer type."""
        return self.model_map.get(engineer_type.upper(), "mistral:7b")

    def explain(self, task: str) -> str:
        """
        Return a human-readable routing explanation string.
        Useful for debugging and CLI --verbose mode.
        """
        task_lower = self._normalize(task)
        lines = ["=== Task Routing Analysis ===", f"Task: {task[:120]}...", ""]

        total_scores: dict[str, float] = {}
        for etype, kw_list in self.keywords.items():
            score = 0.0
            matched = []
            for kw in kw_list:
                if kw in task_lower:
                    w = 1.5 if len(kw.split()) > 1 else 1.0
                    score += w
                    matched.append(kw)
            total_scores[etype] = score
            icon = "✅" if score > 0 else "  "
            lines.append(f"{icon} {etype:<10} score={score:.1f}  hits={matched}")

        best = max(total_scores, key=lambda t: total_scores[t])
        lines.append("")
        lines.append(f"→ Selected: {best} (model: {self.model_map[best]})")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Standalone helper: build a TaskRouter from the full config dict
# ---------------------------------------------------------------------------

def build_router_from_config(config: dict) -> TaskRouter:
    """
    Convenience factory that constructs a TaskRouter directly from the
    full config.yaml dictionary (as returned by yaml.safe_load).
    """
    routing_cfg = config.get("routing", {})
    engineer_cfg = config.get("agents", {}).get("engineers", {})
    return TaskRouter(routing_cfg, engineer_cfg)


# ---------------------------------------------------------------------------
# Quick test (run directly: python router.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import yaml, sys

    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    router = build_router_from_config(cfg)

    test_tasks = [
        "Analiza el stack trace de Java y dime cuál es la causa raíz del NullPointerException",
        "Revisa este script Python que parsea logs y tiene un bug en la función de regex",
        "Genera el RCA del incidente P1 del servicio de pagos",
        "Clasifica la severidad de este error de base de datos",
        "Hola, ¿cómo estás?",
    ]

    for task in test_tasks:
        print(router.explain(task))
        print()
