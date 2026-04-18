"""
End-to-End Pipeline Tests — FRIDA Orchestration Framework
Covers: Router, SessionStore, ResponseEvaluator, MetricsCollector (mocked),
        OrchestratorResult serialization, and live pipeline (--live flag).

Run:
    cd ollama-ams-guide/orchestration
    py -m pytest tests/test_pipeline.py -v
    py -m pytest tests/test_pipeline.py -v -k "not Live"   # fast, no Ollama
    py -m pytest tests/test_pipeline.py -v --live          # live Ollama tests
"""

import json
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from router import TaskRouter, build_router_from_config, RoutingDecision
from memory.session_store import SessionStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def config():
    with open(_ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def router(config):
    return build_router_from_config(config)


@pytest.fixture()
def session_store(config, tmp_path):
    mem_cfg = dict(config["memory"])
    mem_cfg["storage_dir"] = str(tmp_path / "sessions")
    mem_cfg["max_sessions"] = 10
    mem_cfg["session_ttl_hours"] = 1
    return SessionStore(mem_cfg)


# ---------------------------------------------------------------------------
# 1. Router Tests (no Ollama required)
# ---------------------------------------------------------------------------

class TestTaskRouter:
    """Verify keyword-based routing produces correct engineer types."""

    ROUTING_CASES = [
        ("Clasifica la severidad de este error: NullPointerException en PaymentService", "TRIAGE"),
        ("Tenemos un incidente P1 crítico, el servicio de autenticación está caído", "TRIAGE"),
        ("Revisa este script Python que tiene un bug en la función de parsing de logs", "CODE"),
        ("Necesito hacer un code review de este hotfix en Java antes de desplegarlo a producción", "CODE"),
        ("Analiza la causa raíz de este stack trace de base de datos PostgreSQL", "ANALYSIS"),
        ("Realiza un análisis de rendimiento del servicio de pagos basándote en estos logs", "ANALYSIS"),
        ("Genera el RCA ejecutivo del incidente del servicio de autenticación", "DOCS"),
        ("Documenta el procedimiento de runbook para el reinicio del servicio de pagos", "DOCS"),
    ]

    @pytest.mark.parametrize("task,expected_type", ROUTING_CASES)
    def test_routing_type(self, router, task, expected_type):
        decision = router.route(task)
        assert isinstance(decision, RoutingDecision)
        assert decision.engineer_type == expected_type, (
            f"Task: '{task[:60]}...'\n"
            f"Expected: {expected_type}, Got: {decision.engineer_type}\n"
            f"Reason: {decision.reason}"
        )

    def test_routing_returns_valid_model(self, router):
        decision = router.route("analiza este log de error de base de datos")
        assert decision.model
        assert ":" in decision.model or decision.model.isidentifier()

    def test_routing_confidence_range(self, router):
        decision = router.route("error crítico P1 en producción")
        assert 0.0 <= decision.confidence <= 1.0

    def test_routing_no_match_defaults_to_analysis(self, router):
        decision = router.route("hola, ¿cómo estás hoy?")
        assert decision.engineer_type == "ANALYSIS"
        assert decision.confidence == 0.0

    def test_route_multi_returns_sorted_list(self, router):
        decisions = router.route_multi("error de código en el script de análisis de logs", max_types=3)
        assert isinstance(decisions, list) and len(decisions) >= 1
        for d in decisions:
            assert d.engineer_type in {"TRIAGE", "CODE", "ANALYSIS", "DOCS"}
        confidences = [d.confidence for d in decisions]
        assert confidences == sorted(confidences, reverse=True)

    def test_explain_contains_all_types(self, router):
        explanation = router.explain("analiza el error en el código Python")
        for etype in ("TRIAGE", "CODE", "ANALYSIS", "DOCS"):
            assert etype in explanation

    def test_get_model_for_type_case_insensitive(self, router):
        model = router.get_model_for_type("CODE")
        assert model
        assert model == router.get_model_for_type("code")


# ---------------------------------------------------------------------------
# 2. Session Store Tests (no Ollama required)
# ---------------------------------------------------------------------------

class TestSessionStore:
    """Verify session persistence, history retrieval, and pruning."""

    def test_create_session(self, session_store):
        sid = session_store.create_session()
        assert sid
        assert len(sid) == 36  # UUID format

    def test_append_and_get_history(self, session_store):
        sid = session_store.create_session()
        session_store.append(sid, "task 1", "summary 1")
        session_store.append(sid, "task 2", "summary 2")
        history = session_store.get_history(sid)
        assert len(history) == 2
        assert history[0]["task"] == "task 1"
        assert history[1]["summary"] == "summary 2"
        assert history[0]["turn"] == 1
        assert history[1]["turn"] == 2

    def test_get_history_unknown_session(self, session_store):
        assert session_store.get_history("nonexistent-id") == []

    def test_list_sessions_sorted_by_updated_at(self, session_store):
        sid1 = session_store.create_session()
        time.sleep(0.01)
        sid2 = session_store.create_session()
        session_store.append(sid1, "t", "s")
        time.sleep(0.01)
        session_store.append(sid2, "t", "s")
        sessions = session_store.list_sessions()
        ids = [s["session_id"] for s in sessions]
        assert sid1 in ids and sid2 in ids
        assert ids.index(sid2) < ids.index(sid1)

    def test_delete_session(self, session_store):
        sid = session_store.create_session()
        assert session_store.delete_session(sid) is True
        assert session_store.get_history(sid) == []

    def test_delete_nonexistent_session(self, session_store):
        assert session_store.delete_session("no-such-id") is False

    def test_export_session_markdown(self, session_store):
        sid = session_store.create_session()
        session_store.append(sid, "Analiza el error", "El error es un NPE en línea 42")
        md = session_store.export_session(sid)
        assert "# Session:" in md
        assert "Analiza el error" in md
        assert "NPE" in md

    def test_export_unknown_session(self, session_store):
        md = session_store.export_session("no-such-id")
        assert "not found" in md.lower() or "Session" in md

    def test_get_last_session_id(self, session_store):
        sid = session_store.create_session()
        session_store.append(sid, "t", "s")
        assert session_store.get_last_session_id() == sid

    def test_max_sessions_pruning(self, config, tmp_path):
        mem_cfg = {"storage_dir": str(tmp_path / "prune"), "max_sessions": 3, "session_ttl_hours": 0}
        store = SessionStore(mem_cfg)
        for i in range(5):
            sid = store.create_session()
            store.append(sid, f"task {i}", f"summary {i}")
            time.sleep(0.01)
        assert len(store.list_sessions()) <= 3


# ---------------------------------------------------------------------------
# 3. Response Evaluator Tests (no Ollama required — pure heuristics)
# ---------------------------------------------------------------------------

class TestResponseEvaluator:
    """Unit tests for heuristic quality scoring of engineer responses."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from evaluators.response_evaluator import ResponseEvaluator, ResponseEvaluation
        self.EV = ResponseEvaluator
        self.EVAL = ResponseEvaluation

    def _mock_result(self, text, engineer_type="ANALYSIS", confidence="HIGH",
                     duration=10.0, model="mistral:7b", task_id="test-task-001"):
        r = MagicMock()
        r.result = text
        r.engineer_type = engineer_type
        r.confidence = confidence
        r.duration_seconds = duration
        r.model_used = model
        r.task_id = task_id
        return r

    # -- quick_score --

    def test_quick_score_empty_is_low(self):
        assert self.EV("TRIAGE", "phi3:mini").quick_score("", "TRIAGE") < 0.30

    def test_quick_score_rich_triage_passes_threshold(self):
        text = (
            "## Clasificación de Incidente\n\n**Severidad:** P1\n\n"
            "- Componente: PaymentService\n- Impacto: crítico\n- Prioridad: urgente\n"
            "La clasificación ha sido completada. Alerta enviada."
        )
        assert self.EV("TRIAGE", "phi3:mini").quick_score(text, "TRIAGE") >= 0.50

    def test_quick_score_always_in_range(self):
        ev = self.EV("CODE", "qwen2.5-coder:7b")
        for text in ["", "x", "a" * 100, "a" * 5000]:
            assert 0.0 <= ev.quick_score(text, "CODE") <= 1.0

    # -- static criterion scorers --

    def test_completeness_empty_zero(self):
        assert self.EV._score_completeness("") == 0.0

    def test_completeness_improves_with_length(self):
        s = self.EV._score_completeness
        assert s("a" * 50) < s("a" * 400) <= s("a" * 800)

    def test_completeness_penalises_truncated(self):
        clean = self.EV._score_completeness("Análisis completado con éxito.")
        trunc = self.EV._score_completeness("El análisis muestra que el sistema falla porque")
        assert clean >= trunc

    def test_structure_empty_zero(self):
        assert self.EV._score_structure("") == 0.0

    def test_structure_plain_prose_low(self):
        assert self.EV._score_structure("The error occurred.") <= 0.25

    def test_structure_markdown_improves_score(self):
        plain = self.EV._score_structure("plain text")
        rich = self.EV._score_structure("## Título\n\nContenido con **bold** y `código`.\n- item")
        assert rich > plain

    def test_structure_code_block_detected(self):
        assert self.EV._score_structure("```python\nprint('hello')\n```") > 0.10

    def test_coherence_empty_zero(self):
        assert self.EV._score_coherence("") == 0.0

    def test_coherence_no_connectors_baseline(self):
        assert self.EV._score_coherence("El sistema falló.") == pytest.approx(0.30, abs=0.05)

    def test_coherence_connectors_improve_score(self):
        text = "Por lo tanto falló. Sin embargo, hay solución. Además, verifique. En resumen, reinicie."
        assert self.EV._score_coherence(text) > 0.30

    def test_length_empty_zero(self):
        assert self.EV._score_length("", "TRIAGE") == 0.0

    def test_length_too_short_low(self):
        assert self.EV._score_length("x" * 30, "TRIAGE") <= 0.15

    def test_length_ideal_range_one(self):
        assert self.EV._score_length("x" * 500, "TRIAGE") == 1.0

    def test_length_too_long_partial(self):
        assert self.EV._score_length("x" * 3000, "TRIAGE") == pytest.approx(0.75, abs=0.05)

    def test_confidence_scores(self):
        assert self.EV._score_confidence("HIGH") == 1.0
        assert self.EV._score_confidence("MEDIUM") == pytest.approx(0.60)
        assert self.EV._score_confidence("LOW") == pytest.approx(0.20)
        assert self.EV._score_confidence("") == pytest.approx(0.40)
        assert self.EV._score_confidence(None) == pytest.approx(0.40)

    def test_response_time_within_threshold_full_score(self):
        assert self.EV._score_response_time(10.0, "phi3:mini") == 1.0

    def test_response_time_zero_neutral(self):
        assert self.EV._score_response_time(0.0, "phi3:mini") == pytest.approx(0.50)

    def test_response_time_double_threshold_low(self):
        # phi3:mini threshold=20s -> 41s > 2x -> 0.10
        assert self.EV._score_response_time(41.0, "phi3:mini") == pytest.approx(0.10)

    def test_domain_markers_empty_zero(self):
        assert self.EV._score_domain_markers("", "TRIAGE") == 0.0

    def test_domain_markers_triage_vocabulary_detected(self):
        text = "La severidad del incidente es P1. Impacto critico. Clasificacion urgente."
        assert self.EV._score_domain_markers(text, "TRIAGE") >= 0.60

    def test_domain_markers_code_vocabulary_detected(self):
        text = "```python\ndef fix_error():\n    return 'fixed'\n```\nThe exception traceback shows an import error."
        assert self.EV._score_domain_markers(text, "CODE") >= 0.60

    def test_domain_markers_type_specificity(self):
        triage_text = "Severidad P1, clasificacion urgente, impacto alto."
        assert (self.EV._score_domain_markers(triage_text, "TRIAGE") >
                self.EV._score_domain_markers(triage_text, "CODE"))

    # -- full evaluate() --

    def test_evaluate_returns_evaluation_instance(self):
        ev = self.EV("ANALYSIS", "mistral:7b")
        r = self._mock_result("## Diagnostico\n\nCausa: timeout. Hipotesis: pool. Por lo tanto, aumentar conexiones.")
        assert isinstance(ev.evaluate(r), self.EVAL)

    def test_evaluate_score_in_range(self):
        ev = self.EV("TRIAGE", "phi3:mini")
        eval_ = ev.evaluate(self._mock_result("Incidente clasificado.", engineer_type="TRIAGE"))
        assert 0.0 <= eval_.overall_score <= 1.0

    def test_evaluate_high_quality_is_acceptable(self):
        ev = self.EV("ANALYSIS", "mistral:7b")
        text = (
            "## Analisis de Causa Raiz\n\n**Hipotesis:** Timeout en pool PostgreSQL.\n\n"
            "### Evidencia\n- `[ERROR] Connection refused` a las 14:30:01\n- 3 reintentos fallidos\n\n"
            "### Diagnostico\nDebido a que `max_connections=10`, las conexiones se agotaron. "
            "Por lo tanto, el servicio entro en estado unavailable.\n\n"
            "### Recomendacion\nAumentar a 50. En resumen, es problema de capacidad."
        )
        eval_ = ev.evaluate(self._mock_result(text, engineer_type="ANALYSIS", confidence="HIGH", duration=20.0))
        assert eval_.is_acceptable, f"score={eval_.overall_score}"
        assert not eval_.needs_escalation

    def test_evaluate_empty_needs_escalation(self):
        ev = self.EV("TRIAGE", "phi3:mini")
        eval_ = ev.evaluate(self._mock_result("", engineer_type="TRIAGE", confidence="LOW"))
        assert eval_.needs_escalation
        assert not eval_.is_acceptable

    def test_evaluate_flags_mutually_exclusive(self):
        ev = self.EV("CODE", "qwen2.5-coder:7b")
        for text in ["", "short", "medium " * 50, "## H\n\n" + "**bold** `code`\n" * 30]:
            eval_ = ev.evaluate(self._mock_result(text, engineer_type="CODE"))
            flags = [eval_.is_acceptable, eval_.needs_human_review, eval_.needs_escalation]
            assert sum(flags) == 1, f"score={eval_.overall_score}, flags={flags}"

    def test_evaluate_reasoning_non_empty(self):
        ev = self.EV("ANALYSIS", "mistral:7b")
        eval_ = ev.evaluate(self._mock_result("Analisis.", engineer_type="ANALYSIS"))
        assert isinstance(eval_.reasoning, str) and len(eval_.reasoning) > 0

    def test_evaluate_to_dict_json_serializable(self):
        ev = self.EV("TRIAGE", "phi3:mini")
        eval_ = ev.evaluate(self._mock_result("## Triage\n\nSeveridad P1. Impacto: critico.", engineer_type="TRIAGE"))
        parsed = json.loads(json.dumps(eval_.to_dict()))
        assert "overall_score" in parsed
        assert "criteria" in parsed
        assert "decision" in parsed
        assert "reasoning" in parsed
        assert parsed["engineer_result_id"] == "test-task-001"

    def test_evaluate_slow_response_penalised(self):
        ev = self.EV("TRIAGE", "phi3:mini")
        text = "## Triage\n\nSeveridad P1. Impacto alto. Alerta enviada. Clasificacion urgente."
        fast = ev.evaluate(self._mock_result(text, duration=5.0, model="phi3:mini"))
        slow = ev.evaluate(self._mock_result(text, duration=120.0, model="phi3:mini"))
        assert fast.overall_score > slow.overall_score


# ---------------------------------------------------------------------------
# 4. MetricsCollector Tests (mock psutil + requests — no Ollama required)
# ---------------------------------------------------------------------------

class TestMetricsCollector:
    """Unit tests for MetricsCollector using mocked system calls."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from monitors.metrics_monitor import (
            MetricsCollector, CpuMetrics, RamMetrics,
            OllamaMetrics, OllamaModel, MetricsSnapshot,
        )
        self.MC = MetricsCollector
        self.CpuMetrics = CpuMetrics
        self.RamMetrics = RamMetrics
        self.OllamaMetrics = OllamaMetrics
        self.OllamaModel = OllamaModel
        self.MetricsSnapshot = MetricsSnapshot

    @patch("monitors.metrics_monitor.psutil.cpu_count")
    @patch("monitors.metrics_monitor.psutil.cpu_freq")
    @patch("monitors.metrics_monitor.psutil.cpu_percent")
    def test_collect_cpu_returns_dataclass(self, mock_pct, mock_freq, mock_count):
        mock_pct.side_effect = [[45.1, 12.3, 67.8, 23.4, 55.6, 31.2], 34.2]
        mock_freq.return_value = MagicMock(current=2100.0)
        mock_count.side_effect = [6, 12]
        cpu = self.MC().collect_cpu()
        assert isinstance(cpu, self.CpuMetrics)
        assert cpu.core_count == 6
        assert cpu.thread_count == 12
        assert cpu.frequency_mhz == pytest.approx(2100.0)
        assert len(cpu.per_core) == 6

    @patch("monitors.metrics_monitor.psutil.virtual_memory")
    def test_collect_ram_returns_dataclass(self, mock_vm):
        GB = 1024 ** 3
        mock_vm.return_value = MagicMock(total=16 * GB, used=12 * GB, available=4 * GB, percent=75.0)
        ram = self.MC().collect_ram()
        assert isinstance(ram, self.RamMetrics)
        assert ram.total_gb == pytest.approx(16.0, abs=0.1)
        assert ram.used_gb == pytest.approx(12.0, abs=0.1)
        assert ram.available_gb == pytest.approx(4.0, abs=0.1)
        assert ram.percent == 75.0

    @patch("monitors.metrics_monitor.requests.get")
    def test_collect_ollama_available_with_models(self, mock_get):
        GB = 1024 ** 3
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"models": [
                {"name": "mistral:7b", "size": int(4.4 * GB), "digest": "abc123456789",
                 "expires_at": "2026-04-17T18:00:00Z", "size_vram": 0}
            ]}
        )
        ollama = self.MC().collect_ollama()
        assert ollama.available is True
        assert len(ollama.models_loaded) == 1
        assert ollama.models_loaded[0].name == "mistral:7b"
        assert ollama.models_loaded[0].size_gb == pytest.approx(4.4, abs=0.1)

    @patch("monitors.metrics_monitor.requests.get")
    def test_collect_ollama_unavailable_connection_error(self, mock_get):
        import requests as req_lib
        mock_get.side_effect = req_lib.exceptions.ConnectionError("refused")
        ollama = self.MC().collect_ollama()
        assert ollama.available is False
        assert ollama.error is not None
        assert len(ollama.models_loaded) == 0

    @patch("monitors.metrics_monitor.requests.get")
    def test_collect_ollama_timeout_handled(self, mock_get):
        import requests as req_lib
        mock_get.side_effect = req_lib.exceptions.Timeout("timeout")
        ollama = self.MC().collect_ollama()
        assert ollama.available is False
        assert ollama.error is not None

    @patch("monitors.metrics_monitor.requests.get")
    @patch("monitors.metrics_monitor.psutil.virtual_memory")
    @patch("monitors.metrics_monitor.psutil.cpu_count")
    @patch("monitors.metrics_monitor.psutil.cpu_freq")
    @patch("monitors.metrics_monitor.psutil.cpu_percent")
    def test_collect_full_snapshot_structure(self, mock_pct, mock_freq, mock_count, mock_vm, mock_get):
        GB = 1024 ** 3
        mock_pct.side_effect = [[10.0] * 4, 25.0]
        mock_freq.return_value = MagicMock(current=1800.0)
        mock_count.side_effect = [4, 8]
        mock_vm.return_value = MagicMock(total=16 * GB, used=8 * GB, available=8 * GB, percent=50.0)
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"models": []})

        snap = self.MC().collect()
        assert isinstance(snap, self.MetricsSnapshot)
        assert snap.timestamp
        assert isinstance(snap.cpu, self.CpuMetrics)
        assert isinstance(snap.ram, self.RamMetrics)
        assert isinstance(snap.ollama, self.OllamaMetrics)

    @patch("monitors.metrics_monitor.requests.get")
    @patch("monitors.metrics_monitor.psutil.virtual_memory")
    @patch("monitors.metrics_monitor.psutil.cpu_count")
    @patch("monitors.metrics_monitor.psutil.cpu_freq")
    @patch("monitors.metrics_monitor.psutil.cpu_percent")
    def test_collect_snapshot_json_serializable(self, mock_pct, mock_freq, mock_count, mock_vm, mock_get):
        from dataclasses import asdict
        GB = 1024 ** 3
        mock_pct.side_effect = [[5.0] * 4, 10.0]
        mock_freq.return_value = MagicMock(current=1600.0)
        mock_count.side_effect = [4, 8]
        mock_vm.return_value = MagicMock(total=16 * GB, used=8 * GB, available=8 * GB, percent=50.0)
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"models": []})

        snap = self.MC().collect()
        parsed = json.loads(json.dumps(asdict(snap)))
        assert "timestamp" in parsed
        assert "cpu" in parsed
        assert "ram" in parsed
        assert "ollama" in parsed


# ---------------------------------------------------------------------------
# 5. Config Validation Tests (no Ollama required)
# ---------------------------------------------------------------------------

class TestConfig:
    """Validate that config.yaml contains all required keys."""

    REQUIRED_TOP = ["ollama", "agents", "routing", "execution", "memory", "logging"]
    REQUIRED_ENGINEER_TYPES = ["TRIAGE", "CODE", "ANALYSIS", "DOCS"]
    REQUIRED_ENGINEER_FIELDS = ["model", "system_prompt", "max_tokens", "temperature"]

    def test_top_level_keys_present(self, config):
        for key in self.REQUIRED_TOP:
            assert key in config, f"Missing: '{key}'"

    def test_ollama_base_url_present(self, config):
        assert "base_url" in config["ollama"]
        assert config["ollama"]["base_url"].startswith("http")

    def test_all_engineer_types_present(self, config):
        engineers = config["agents"]["engineers"]
        for etype in self.REQUIRED_ENGINEER_TYPES:
            assert etype in engineers, f"Missing engineer type: '{etype}'"

    def test_engineer_configs_have_required_fields(self, config):
        for etype in self.REQUIRED_ENGINEER_TYPES:
            eng = config["agents"]["engineers"][etype]
            for field in self.REQUIRED_ENGINEER_FIELDS:
                assert field in eng, f"Engineer '{etype}' missing field: '{field}'"

    def test_execution_mode_valid(self, config):
        mode = config["execution"].get("mode", "sequential")
        assert mode in ("sequential", "parallel"), f"Invalid mode: '{mode}'"

    def test_routing_keywords_present(self, config):
        routing = config["routing"]
        for key in ("triage_keywords", "code_keywords", "analysis_keywords", "docs_keywords"):
            assert key in routing, f"Missing: '{key}'"
            assert isinstance(routing[key], list) and len(routing[key]) > 0

    def test_memory_storage_dir_configured(self, config):
        assert "storage_dir" in config["memory"]


# ---------------------------------------------------------------------------
# 6. Result Serialization Tests
# ---------------------------------------------------------------------------

class TestResultSerialization:
    """Verify OrchestratorResult can be serialized to JSON."""

    def test_result_to_json(self):
        from orchestrator import Orchestrator, OrchestratorResult

        result = OrchestratorResult(
            session_id="test-session-123",
            original_task="Test task",
            subtasks_executed=2,
            summary="## ANALYSIS\n\nTest finding.",
            details=[{"type": "ANALYSIS", "model": "mistral:7b", "finding": "ok"}],
            models_used=["mistral:7b"],
            total_duration_seconds=5.23,
            total_tokens_used=120,
            success=True,
            warnings=[],
        )

        json_str = Orchestrator.result_to_json(result)
        parsed = json.loads(json_str)

        assert parsed["session_id"] == "test-session-123"
        assert parsed["subtasks_executed"] == 2
        assert parsed["success"] is True
        assert isinstance(parsed["details"], list)
        assert parsed["total_tokens_used"] == 120


# ---------------------------------------------------------------------------
# 7. Live Pipeline Tests (require --live flag + running Ollama)
# ---------------------------------------------------------------------------

class TestLivePipeline:
    """
    End-to-end tests using real Ollama models.
    Run with: py -m pytest tests/test_pipeline.py -v --live
    """

    LIVE_TASKS = [
        {
            "name": "java_npe_triage",
            "task": (
                "Clasifica este incidente: java.lang.NullPointerException at "
                "com.empresa.PaymentService.processPayment(PaymentService.java:142). "
                "Cual es la severidad y el siguiente paso de investigacion?"
            ),
            "expected_engineer": "TRIAGE",
            "check_in_summary": ["NullPointerException", "severidad"],
        },
        {
            "name": "python_bug_code_review",
            "task": (
                "Revisa este codigo Python y encuentra el bug:\n"
                "def get_errors(log_lines):\n"
                "    errors = []\n"
                "    for line in log_lines:\n"
                "        if 'ERROR' in line\n"
                "            errors.append(line)\n"
                "    return errors"
            ),
            "expected_engineer": "CODE",
            "check_in_summary": ["SyntaxError", "dos puntos", ":"],
        },
        {
            "name": "rca_generation",
            "task": (
                "Genera un borrador de RCA para: Caida del servicio de pagos durante "
                "30 minutos. Causa raiz: timeout de conexion al pool de base de datos "
                "por numero insuficiente de conexiones configuradas (max_connections=10). "
                "Impacto: 500 transacciones fallidas."
            ),
            "expected_engineer": "DOCS",
            "check_in_summary": ["RCA", "causa", "pool"],
        },
        {
            "name": "log_analysis",
            "task": (
                "Analiza estos logs y determina la causa del problema:\n"
                "[ERROR] 2026-04-17 14:30:01 - Connection refused: PostgreSQL:5432\n"
                "[ERROR] 2026-04-17 14:30:02 - Retry 1/3 failed\n"
                "[ERROR] 2026-04-17 14:30:05 - Retry 2/3 failed\n"
                "[CRITICAL] 2026-04-17 14:30:08 - Service unavailable"
            ),
            "expected_engineer": "ANALYSIS",
            "check_in_summary": ["PostgreSQL", "base de datos", "conexion"],
        },
    ]

    @pytest.fixture(scope="class")
    def orchestrator(self):
        try:
            from orchestrator import Orchestrator
            return Orchestrator(config_path=str(_ROOT / "config.yaml"))
        except Exception as exc:
            pytest.skip(f"Could not initialize Orchestrator: {exc}")

    @pytest.mark.parametrize("case", LIVE_TASKS, ids=[c["name"] for c in LIVE_TASKS])
    def test_live_pipeline(self, request, orchestrator, case):
        if not request.config.getoption("--live"):
            pytest.skip("Requires --live flag")

        result = orchestrator.run(case["task"], use_architect_llm=False)

        assert result is not None
        assert result.summary, "Summary should not be empty"
        assert result.session_id, "Session ID should be set"
        assert result.subtasks_executed >= 1

        summary_lower = result.summary.lower()
        for expected_term in case.get("check_in_summary", []):
            assert expected_term.lower() in summary_lower, (
                f"Expected '{expected_term}' in summary.\nSummary:\n{result.summary[:500]}"
            )

    def test_live_session_continuity(self, request, orchestrator):
        if not request.config.getoption("--live"):
            pytest.skip("Requires --live flag")

        session_id = str(uuid.uuid4())
        result1 = orchestrator.run(
            "Tenemos un incidente P1 en el servicio de pagos. Codigo de error: PAY-503.",
            session_id=session_id, use_architect_llm=False,
        )
        assert result1.success

        result2 = orchestrator.run(
            "Cuales son los pasos de remediacion para el incidente anterior?",
            session_id=session_id, use_architect_llm=False,
        )
        assert result2.success
        assert result1.summary and result2.summary

    def test_live_no_architect_mode(self, request, orchestrator):
        if not request.config.getoption("--live"):
            pytest.skip("Requires --live flag")

        result = orchestrator.run(
            "Que causa el error OOM (OutOfMemoryError) en Java?",
            use_architect_llm=False,
        )
        assert result.success and result.summary

    def test_live_response_time_reasonable(self, request, orchestrator):
        if not request.config.getoption("--live"):
            pytest.skip("Requires --live flag")

        start = time.time()
        result = orchestrator.run(
            "Clasifica: servicio web devuelve HTTP 500.",
            use_architect_llm=False,
        )
        elapsed = time.time() - start

        assert result.success
        assert elapsed < 120, f"Response took {elapsed:.1f}s exceeded 120s threshold"
        assert result.total_duration_seconds > 0
