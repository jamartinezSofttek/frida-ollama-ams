"""
Architect Agent Module
Decomposes high-level user tasks into specialized subtasks and
assigns each one to the most appropriate engineer model.
"""

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional
import requests

logger = logging.getLogger(__name__)


@dataclass
class SubtaskSpec:
    """A single subtask as defined by the Architect Agent."""
    id: int
    tipo: str           # TRIAGE | CODE | ANALYSIS | DOCS
    descripcion: str
    input: str
    modelo: str


@dataclass
class DecompositionResult:
    """The full decomposition produced by the Architect Agent."""
    session_id: str
    tarea_original: str
    subtareas: list[SubtaskSpec] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None
    duration_seconds: float = 0.0


class ArchitectAgent:
    """
    Calls a local Ollama model to decompose a high-level task into
    structured subtasks following the Architect-Engineer protocol.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        system_prompt: str,
        temperature: float = 0.2,
        num_ctx: int = 4096,
        timeout: int = 120,
        max_retries: int = 2,
        retry_delay: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.api_url = f"{self.base_url}/api/chat"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def decompose(self, user_task: str, session_id: Optional[str] = None) -> DecompositionResult:
        """
        Send a high-level task to the architect model and parse the
        resulting JSON decomposition into SubtaskSpec objects.
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        logger.info("[Architect] Decomposing task for session %s", session_id)
        logger.debug("[Architect] Task: %s", user_task[:120])

        last_error: Optional[str] = None
        for attempt in range(1, self.max_retries + 2):
            try:
                result = self._call_and_parse(user_task, session_id)
                logger.info(
                    "[Architect] Decomposition complete: %d subtasks in %.1fs",
                    len(result.subtareas), result.duration_seconds
                )
                return result
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "[Architect] Attempt %d/%d failed: %s",
                    attempt, self.max_retries + 1, exc
                )
                if attempt <= self.max_retries:
                    time.sleep(self.retry_delay)

        logger.error("[Architect] Decomposition failed after %d attempts", self.max_retries + 1)
        return DecompositionResult(
            session_id=session_id,
            tarea_original=user_task,
            success=False,
            error=last_error,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_and_parse(self, user_task: str, session_id: str) -> DecompositionResult:
        """Call the Ollama API and parse the JSON response."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user",   "content": user_task},
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
            },
        }

        start_time = time.time()
        response = requests.post(self.api_url, json=payload, timeout=self.timeout)
        duration = time.time() - start_time

        response.raise_for_status()
        data = response.json()

        raw_content = (
            data.get("message", {}).get("content", "")
            or data.get("response", "")
        ).strip()

        logger.debug("[Architect] Raw response: %s", raw_content[:300])

        parsed = self._extract_json(raw_content)
        subtareas = self._parse_subtasks(parsed.get("subtareas", []))

        return DecompositionResult(
            session_id=session_id,
            tarea_original=parsed.get("tarea_original", user_task),
            subtareas=subtareas,
            success=True,
            duration_seconds=round(duration, 2),
        )

    @staticmethod
    def _extract_json(text: str) -> dict:
        """
        Extract a JSON object from the model response.
        The model may wrap JSON in markdown code blocks; handle both cases.
        """
        # Remove markdown code fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()

        # Try to find the first complete JSON object
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())

        # Fallback: try parsing the whole cleaned string
        return json.loads(cleaned)

    @staticmethod
    def _parse_subtasks(raw_list: list) -> list[SubtaskSpec]:
        """Convert the raw list of dicts into SubtaskSpec objects."""
        subtasks: list[SubtaskSpec] = []
        valid_types = {"TRIAGE", "CODE", "ANALYSIS", "DOCS"}
        valid_models = {"phi3:mini", "qwen2.5-coder:7b", "mistral:7b"}

        for item in raw_list:
            tipo = str(item.get("tipo", "ANALYSIS")).upper()
            if tipo not in valid_types:
                tipo = "ANALYSIS"

            modelo = item.get("modelo", "mistral:7b")
            if modelo not in valid_models:
                modelo = "mistral:7b"

            subtasks.append(SubtaskSpec(
                id=int(item.get("id", len(subtasks) + 1)),
                tipo=tipo,
                descripcion=str(item.get("descripcion", "")),
                input=str(item.get("input", "")),
                modelo=modelo,
            ))

        return subtasks

    # ------------------------------------------------------------------
    # Fallback: simple keyword-based decomposition (no LLM required)
    # ------------------------------------------------------------------

    @staticmethod
    def simple_decompose(user_task: str, routing_config: dict) -> list[SubtaskSpec]:
        """
        Lightweight fallback that uses keyword matching to build a
        single-subtask decomposition without calling any LLM.
        Used when Ollama is unavailable or RAM is critically low.
        """
        task_lower = user_task.lower()

        triage_hits = sum(
            1 for kw in routing_config.get("triage_keywords", []) if kw in task_lower
        )
        code_hits = sum(
            1 for kw in routing_config.get("code_keywords", []) if kw in task_lower
        )
        analysis_hits = sum(
            1 for kw in routing_config.get("analysis_keywords", []) if kw in task_lower
        )
        docs_hits = sum(
            1 for kw in routing_config.get("docs_keywords", []) if kw in task_lower
        )

        scores = {
            "TRIAGE":   (triage_hits,   "phi3:mini"),
            "CODE":     (code_hits,     "qwen2.5-coder:7b"),
            "ANALYSIS": (analysis_hits, "mistral:7b"),
            "DOCS":     (docs_hits,     "mistral:7b"),
        }

        best_type, (_, best_model) = max(scores.items(), key=lambda x: x[1][0])

        # Default to ANALYSIS if no keywords matched
        if scores[best_type][0] == 0:
            best_type = "ANALYSIS"
            best_model = "mistral:7b"

        return [
            SubtaskSpec(
                id=1,
                tipo=best_type,
                descripcion=user_task,
                input=user_task,
                modelo=best_model,
            )
        ]
