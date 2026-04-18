"""
Orchestrator Module
Main engine of the Architect-Engineer framework.
Receives a high-level task, delegates decomposition to the Architect Agent,
routes each subtask to the appropriate Engineer Agent, aggregates results,
and returns a consolidated response.
"""

import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

import yaml

from agents.architect import ArchitectAgent, SubtaskSpec, DecompositionResult
from agents.engineer import EngineerAgent, EngineerTask, EngineerResult, create_engineer_task
from memory.session_store import SessionStore

try:
    from evaluators.response_evaluator import ResponseEvaluator
    _EVALUATOR_AVAILABLE = True
except ImportError:
    _EVALUATOR_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class OrchestratorResult:
    """Final aggregated result returned to the user."""
    session_id: str
    original_task: str
    subtasks_executed: int
    summary: str
    details: list[dict] = field(default_factory=list)
    models_used: list[str] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    total_tokens_used: int = 0
    success: bool = True
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """
    Coordinates the full Architect → Engineer pipeline.

    Workflow:
        1. Load configuration
        2. Architect decomposes the task into subtasks (with LLM or keyword fallback)
        3. Each subtask is sent to the appropriate Engineer Agent
        4. Results are aggregated and a consolidated summary is produced
        5. Interaction is saved to session memory
    """

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self._setup_logging()

        ollama_cfg = self.config["ollama"]
        exec_cfg = self.config["execution"]
        arch_cfg = self.config["agents"]["architect"]

        self.architect = ArchitectAgent(
            base_url=ollama_cfg["base_url"],
            model=arch_cfg["model"],
            system_prompt=arch_cfg["system_prompt"],
            temperature=arch_cfg["temperature"],
            num_ctx=arch_cfg["num_ctx"],
            timeout=ollama_cfg["timeout"],
            max_retries=exec_cfg["max_retries"],
            retry_delay=exec_cfg["retry_delay_seconds"],
        )

        self.engineer_agent = EngineerAgent(
            base_url=ollama_cfg["base_url"],
            timeout=ollama_cfg["timeout"],
            max_retries=exec_cfg["max_retries"],
            retry_delay=exec_cfg["retry_delay_seconds"],
        )

        self.execution_mode = exec_cfg.get("mode", "sequential")
        self.parallel_workers = exec_cfg.get("parallel_max_workers", 2)
        self.routing_config = self.config.get("routing", {})
        self.session_store = SessionStore(self.config["memory"])

        logger.info("Orchestrator initialized (mode=%s, architect=%s)",
                    self.execution_mode, arch_cfg["model"])

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(
        self,
        task: str,
        session_id: Optional[str] = None,
        use_architect_llm: bool = True,
    ) -> OrchestratorResult:
        """
        Execute the full pipeline for a given task.

        Args:
            task: High-level task description from the user.
            session_id: Optional existing session ID to continue a conversation.
            use_architect_llm: If False, skip the LLM decomposition and use
                               the lightweight keyword-based fallback instead.

        Returns:
            OrchestratorResult with aggregated findings and summary.
        """
        start_time = time.time()
        if session_id is None:
            session_id = str(uuid.uuid4())

        logger.info("=== Orchestrator.run  session=%s ===", session_id)

        # ---- Step 1: Build context from session history ----
        history = self.session_store.get_history(session_id)
        context_str = self._build_context_string(history)

        enriched_task = task
        if context_str:
            enriched_task = f"[HISTORIAL PREVIO]\n{context_str}\n\n[NUEVA TAREA]\n{task}"

        # ---- Step 2: Decompose task ----
        if use_architect_llm:
            decomposition = self.architect.decompose(enriched_task, session_id)
            if not decomposition.success or not decomposition.subtareas:
                logger.warning("Architect LLM failed; falling back to keyword routing")
                subtasks = ArchitectAgent.simple_decompose(task, self.routing_config)
                decomposition.subtareas = subtasks
                decomposition.success = True
        else:
            subtasks = ArchitectAgent.simple_decompose(task, self.routing_config)
            decomposition = DecompositionResult(
                session_id=session_id,
                tarea_original=task,
                subtareas=subtasks,
            )

        logger.info("Subtasks to execute: %d", len(decomposition.subtareas))

        # ---- Step 3: Execute subtasks ----
        engineer_tasks = self._build_engineer_tasks(decomposition.subtareas, task)

        if self.execution_mode == "parallel" and len(engineer_tasks) > 1:
            engineer_results = self._run_parallel(engineer_tasks)
        else:
            engineer_results = self._run_sequential(engineer_tasks)

        # ---- Step 4: Aggregate ----
        result = self._aggregate(
            session_id=session_id,
            original_task=task,
            decomposition=decomposition,
            engineer_results=engineer_results,
            total_duration=time.time() - start_time,
        )

        # ---- Step 5: Persist to session ----
        self.session_store.append(session_id, task, result.summary)

        logger.info(
            "=== Pipeline complete: %d subtasks, %.1fs, %d tokens ===",
            result.subtasks_executed,
            result.total_duration_seconds,
            result.total_tokens_used,
        )
        return result

    # ------------------------------------------------------------------
    # Task building
    # ------------------------------------------------------------------

    def _build_engineer_tasks(
        self, subtasks: list[SubtaskSpec], original_task: str
    ) -> list[EngineerTask]:
        """Map SubtaskSpec objects to EngineerTask objects using config prompts."""
        engineers_cfg = self.config["agents"]["engineers"]
        tasks: list[EngineerTask] = []

        for spec in subtasks:
            tipo = spec.tipo if spec.tipo in engineers_cfg else "ANALYSIS"
            eng_cfg = engineers_cfg[tipo]

            # Use spec.input as the user prompt; fall back to original task
            user_prompt = spec.input if spec.input.strip() else original_task

            tasks.append(create_engineer_task(
                engineer_type=tipo,
                model=spec.modelo,
                system_prompt=eng_cfg["system_prompt"],
                user_prompt=user_prompt,
                max_tokens=eng_cfg.get("max_tokens", 500),
                temperature=eng_cfg.get("temperature", 0.1),
                num_ctx=eng_cfg.get("num_ctx", 2048),
            ))

        return tasks

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------

    def _run_sequential(self, tasks: list[EngineerTask]) -> list[EngineerResult]:
        """Execute engineer tasks one by one."""
        results: list[EngineerResult] = []
        for task in tasks:
            logger.info("Running engineer [%s] model=%s", task.engineer_type, task.model)
            result = self.engineer_agent.execute(task)
            results.append(result)
        return results

    def _run_parallel(self, tasks: list[EngineerTask]) -> list[EngineerResult]:
        """Execute engineer tasks concurrently (use only with ample RAM)."""
        results: list[Optional[EngineerResult]] = [None] * len(tasks)

        with ThreadPoolExecutor(max_workers=self.parallel_workers) as executor:
            future_to_idx = {
                executor.submit(self.engineer_agent.execute, task): idx
                for idx, task in enumerate(tasks)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    logger.error("Engineer thread failed: %s", exc)
                    task = tasks[idx]
                    results[idx] = EngineerResult(
                        task_id=task.task_id,
                        engineer_type=task.engineer_type,
                        model_used=task.model,
                        result="",
                        confidence="LOW",
                        success=False,
                        error=str(exc),
                    )

        return [r for r in results if r is not None]

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate(
        self,
        session_id: str,
        original_task: str,
        decomposition: DecompositionResult,
        engineer_results: list[EngineerResult],
        total_duration: float,
    ) -> OrchestratorResult:
        """Combine individual engineer results into a single response."""
        details: list[dict] = []
        models_used: list[str] = []
        total_tokens = 0
        warnings: list[str] = []
        successful_results: list[EngineerResult] = []

        for res in engineer_results:
            total_tokens += res.tokens_used
            if res.model_used not in models_used:
                models_used.append(res.model_used)

            # Quality evaluation (heuristic, no LLM, < 500ms)
            evaluation_dict: Optional[dict] = None
            if _EVALUATOR_AVAILABLE and res.success:
                try:
                    evaluator = ResponseEvaluator(
                        engineer_type=res.engineer_type,
                        model=res.model_used,
                    )
                    ev = evaluator.evaluate(res)
                    evaluation_dict = ev.to_dict()
                    if ev.needs_escalation:
                        warnings.append(
                            f"[Evaluator] {res.engineer_type} score={ev.overall_score:.2f} "
                            f"— baja calidad, considerar escalación a FRIDA."
                        )
                    elif ev.needs_human_review:
                        warnings.append(
                            f"[Evaluator] {res.engineer_type} score={ev.overall_score:.2f} "
                            f"— revisión humana recomendada."
                        )
                except Exception as eval_exc:
                    logger.debug("[Evaluator] Skipped due to error: %s", eval_exc)

            if not res.success:
                warnings.append(
                    f"Subtarea {res.engineer_type} falló: {res.error}"
                )
                details.append({
                    "type": res.engineer_type,
                    "model": res.model_used,
                    "finding": "[ERROR] No se pudo completar esta subtarea.",
                    "confidence": "LOW",
                    "duration_s": res.duration_seconds,
                })
            else:
                successful_results.append(res)
                detail: dict = {
                    "type": res.engineer_type,
                    "model": res.model_used,
                    "finding": res.result,
                    "confidence": res.confidence,
                    "duration_s": res.duration_seconds,
                    "tokens": res.tokens_used,
                }
                if evaluation_dict is not None:
                    detail["evaluation"] = evaluation_dict
                details.append(detail)

        summary = self._build_summary(original_task, successful_results, warnings)

        return OrchestratorResult(
            session_id=session_id,
            original_task=original_task,
            subtasks_executed=len(engineer_results),
            summary=summary,
            details=details,
            models_used=models_used,
            total_duration_seconds=round(total_duration, 2),
            total_tokens_used=total_tokens,
            success=len(successful_results) > 0,
            warnings=warnings,
        )

    @staticmethod
    def _build_summary(
        original_task: str,
        results: list[EngineerResult],
        warnings: list[str],
    ) -> str:
        """Compose a readable multi-section summary from all engineer findings."""
        if not results:
            return "⚠️ No se pudo completar ninguna subtarea. Verifica que Ollama esté activo."

        sections: list[str] = []
        type_labels = {
            "TRIAGE":   "🔍 Triaje y Clasificación",
            "CODE":     "💻 Análisis de Código",
            "ANALYSIS": "🧠 Análisis Técnico",
            "DOCS":     "📄 Documentación",
        }

        for res in results:
            label = type_labels.get(res.engineer_type, res.engineer_type)
            conf_icon = {"HIGH": "✅", "MEDIUM": "⚠️", "LOW": "❓"}.get(res.confidence, "")
            header = f"## {label} {conf_icon} *(modelo: {res.model_used})*"
            sections.append(f"{header}\n\n{res.result}")

        body = "\n\n---\n\n".join(sections)

        if warnings:
            warn_block = "\n".join(f"- {w}" for w in warnings)
            body += f"\n\n---\n\n⚠️ **Advertencias:**\n{warn_block}"

        return body

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _build_context_string(history: list[dict], max_turns: int = 3) -> str:
        """
        Build a compact context string from the last N conversation turns.
        Keeps only summaries to stay within context window limits.
        """
        if not history:
            return ""

        recent = history[-max_turns:]
        parts: list[str] = []
        for turn in recent:
            parts.append(f"Usuario: {turn.get('task', '')[:200]}")
            parts.append(f"Sistema: {turn.get('summary', '')[:300]}")

        return "\n".join(parts)

    @staticmethod
    def _load_config(path: str) -> dict:
        """Load YAML configuration file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Config file not found: {path}\n"
                "Run from the orchestration/ directory or pass the correct path."
            )

    def _setup_logging(self) -> None:
        """Configure logging based on config file settings."""
        log_level = self.config.get("logging", {}).get("level", "INFO").upper()
        logging.basicConfig(
            level=getattr(logging, log_level, logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )

    # ------------------------------------------------------------------
    # Convenience: format result as JSON string
    # ------------------------------------------------------------------

    @staticmethod
    def result_to_json(result: OrchestratorResult, indent: int = 2) -> str:
        """Serialize an OrchestratorResult to a pretty-printed JSON string."""
        return json.dumps(
            {
                "session_id": result.session_id,
                "original_task": result.original_task,
                "subtasks_executed": result.subtasks_executed,
                "summary": result.summary,
                "details": result.details,
                "models_used": result.models_used,
                "total_duration_seconds": result.total_duration_seconds,
                "total_tokens_used": result.total_tokens_used,
                "success": result.success,
                "warnings": result.warnings,
            },
            ensure_ascii=False,
            indent=indent,
        )
