"""
Engineer Agent Module
Handles execution of specialized subtasks using local Ollama models.
Each engineer receives a focused subtask and returns a structured result.
"""

import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional
import requests

logger = logging.getLogger(__name__)


@dataclass
class EngineerTask:
    """Represents a subtask assigned to an engineer agent."""
    task_id: str
    engineer_type: str          # TRIAGE | CODE | ANALYSIS | DOCS
    model: str
    system_prompt: str
    user_prompt: str
    context: str = ""
    max_tokens: int = 500
    temperature: float = 0.1
    num_ctx: int = 2048


@dataclass
class EngineerResult:
    """Represents the result produced by an engineer agent."""
    task_id: str
    engineer_type: str
    model_used: str
    result: str
    confidence: str             # HIGH | MEDIUM | LOW
    tokens_used: int = 0
    duration_seconds: float = 0.0
    success: bool = True
    error: Optional[str] = None


class EngineerAgent:
    """
    Executes a specialized subtask by calling a local Ollama model.
    Supports retry logic and graceful error handling.

    Performance notes:
    - Uses a split (connect, read) timeout: fast fail on connection errors
      while allowing sufficient time for model inference.
    - Exposes warm_up() to pre-load a model into VRAM/RAM before the first
      real request, eliminating cold-start latency.
    """

    # Connect timeout: fail quickly if Ollama is not running
    CONNECT_TIMEOUT = 5   # seconds

    def __init__(self, base_url: str, timeout: int = 120,
                 max_retries: int = 2, retry_delay: int = 3):
        self.base_url = base_url.rstrip("/")
        self.read_timeout = timeout       # model inference timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.api_url = f"{self.base_url}/api/chat"
        self.generate_url = f"{self.base_url}/api/generate"

    # ------------------------------------------------------------------
    # Pre-warming
    # ------------------------------------------------------------------

    def warm_up(self, model: str) -> bool:
        """
        Send a minimal no-op request to load the model into memory.
        Call this once at startup to eliminate cold-start latency on the
        first real request.

        Returns True if the model responded, False if unavailable.
        """
        logger.info("[Engineer] Warming up model %s …", model)
        try:
            payload = {
                "model": model,
                "prompt": "",
                "stream": False,
                "keep_alive": "10m",
            }
            resp = requests.post(
                self.generate_url,
                json=payload,
                timeout=(self.CONNECT_TIMEOUT, 30),
            )
            resp.raise_for_status()
            logger.info("[Engineer] Model %s is warm.", model)
            return True
        except Exception as exc:
            logger.warning("[Engineer] Warm-up failed for %s: %s", model, exc)
            return False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def execute(self, task: EngineerTask) -> EngineerResult:
        """Run a subtask and return a structured result, with retries."""
        logger.info(
            "[Engineer:%s] Starting task %s using model %s",
            task.engineer_type, task.task_id, task.model
        )

        last_error: Optional[str] = None
        for attempt in range(1, self.max_retries + 2):  # +2: initial + N retries
            try:
                result = self._call_ollama(task)
                logger.info(
                    "[Engineer:%s] Task %s completed in %.1fs",
                    task.engineer_type, task.task_id, result.duration_seconds
                )
                return result
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "[Engineer:%s] Attempt %d/%d failed: %s",
                    task.engineer_type, attempt, self.max_retries + 1, exc
                )
                if attempt <= self.max_retries:
                    time.sleep(self.retry_delay)

        # All attempts exhausted
        logger.error(
            "[Engineer:%s] Task %s failed after %d attempts",
            task.engineer_type, task.task_id, self.max_retries + 1
        )
        return EngineerResult(
            task_id=task.task_id,
            engineer_type=task.engineer_type,
            model_used=task.model,
            result="",
            confidence="LOW",
            success=False,
            error=last_error,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_messages(self, task: EngineerTask) -> list:
        """Construct the message list for the Ollama chat API."""
        messages = [{"role": "system", "content": task.system_prompt}]

        if task.context:
            messages.append({
                "role": "user",
                "content": f"[CONTEXTO ADICIONAL]\n{task.context}"
            })
            messages.append({
                "role": "assistant",
                "content": "Entendido. Tengo el contexto. Procedo con la subtarea."
            })

        messages.append({"role": "user", "content": task.user_prompt})
        return messages

    def _call_ollama(self, task: EngineerTask) -> EngineerResult:
        """Send a request to the Ollama chat endpoint and parse the response."""
        messages = self._build_messages(task)

        payload = {
            "model": task.model,
            "messages": messages,
            "stream": False,
            "keep_alive": "10m",   # keep model warm between consecutive calls
            "options": {
                "temperature": task.temperature,
                "num_ctx": task.num_ctx,
                "num_predict": task.max_tokens,
            },
        }

        start_time = time.time()
        # Split timeout: (connect_timeout, read_timeout)
        # connect_timeout catches "Ollama not running" immediately
        # read_timeout allows sufficient time for model inference on CPU
        response = requests.post(
            self.api_url,
            json=payload,
            timeout=(self.CONNECT_TIMEOUT, self.read_timeout),
        )
        duration = time.time() - start_time

        response.raise_for_status()
        data = response.json()

        content = (
            data.get("message", {}).get("content", "")
            or data.get("response", "")
        ).strip()

        tokens_used = (
            data.get("eval_count", 0) + data.get("prompt_eval_count", 0)
        )

        confidence = self._assess_confidence(content, task.engineer_type)

        return EngineerResult(
            task_id=task.task_id,
            engineer_type=task.engineer_type,
            model_used=task.model,
            result=content,
            confidence=confidence,
            tokens_used=tokens_used,
            duration_seconds=round(duration, 2),
            success=True,
        )

    @staticmethod
    def _assess_confidence(content: str, engineer_type: str) -> str:
        """
        Heuristic confidence assessment based on response length and
        presence of expected structural markers.
        """
        if not content or len(content) < 30:
            return "LOW"

        markers = {
            "TRIAGE": ["severidad", "componente", "prioridad", "clasificación"],
            "CODE":   ["def ", "function", "```", "error", "fix", "línea"],
            "ANALYSIS": ["causa", "hipótesis", "impacto", "diagnóstico", "recomend"],
            "DOCS": ["#", "##", "**", "incidente", "acción", "fecha"],
        }

        expected = markers.get(engineer_type, [])
        hits = sum(1 for m in expected if m.lower() in content.lower())

        if hits >= 3:
            return "HIGH"
        if hits >= 1:
            return "MEDIUM"
        return "LOW"


def create_engineer_task(
    engineer_type: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    context: str = "",
    max_tokens: int = 500,
    temperature: float = 0.1,
    num_ctx: int = 2048,
) -> EngineerTask:
    """Factory function to create an EngineerTask with a generated UUID."""
    return EngineerTask(
        task_id=str(uuid.uuid4()),
        engineer_type=engineer_type,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        context=context,
        max_tokens=max_tokens,
        temperature=temperature,
        num_ctx=num_ctx,
    )
