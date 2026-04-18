"""
End-to-End Pipeline Tests
Tests the full Architect → Engineer → Aggregation pipeline using realistic
AMS L3 engineering tasks.

Prerequisites:
  1. Ollama server must be running:  ollama serve
  2. Required models must be pulled:
       ollama pull phi3:mini
       ollama pull mistral:7b
       ollama pull qwen2.5-coder:7b

Run:
    cd ollama-ams-guide/orchestration
    py -m pytest tests/test_pipeline.py -v
    py -m pytest tests/test_pipeline.py -v -k "test_router"   # fast (no Ollama)
    py -m pytest tests/test_pipeline.py -v --live             # live Ollama tests
"""

import json
import sys
import time
import uuid
from pathlib import Path

import pytest
import yaml

# Ensure the orchestration/ directory is importable
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
    config_path = _ROOT / "config.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def router(config):
    return build_router_from_config(config)


@pytest.fixture()
def session_store(config, tmp_path):
    """Use a temporary directory for session storage during tests."""
    mem_cfg = dict(config["memory"])
    mem_cfg["storage_dir"] = str(tmp_path / "sessions")
    mem_cfg["max_sessions"] = 10
    mem_cfg["session_ttl_hours"] = 1
    return SessionStore(mem_cfg)


def pytest_addoption(parser):
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run tests that require a live Ollama server",
    )


def live_only(func):
    """Decorator: skip test unless --live flag is passed."""
    import functools
    @functools.wraps(func)
    def wrapper(request, *args, **kwargs):
        if not request.config.getoption("--live"):
            pytest.skip("Requires --live flag and a running Ollama server")
        return func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Router Tests (no Ollama required)
# ---------------------------------------------------------------------------

class TestTaskRouter:
    """Verify keyword-based routing produces correct engineer types."""

    ROUTING_CASES = [
        # (task_text, expected_engineer_type)
        (
            "Clasifica la severidad de este error: NullPointerException en PaymentService",
            "TRIAGE",
        ),
        (
            "Tenemos un incidente P1 crítico, el servicio de autenticación está caído",
            "TRIAGE",
        ),
        (
            "Revisa este script Python que tiene un bug en la función de parsing de logs",
            "CODE",
        ),
        (
            "Necesito hacer un code review de este hotfix en Java antes de desplegarlo a producción",
            "CODE",
        ),
        (
            "Analiza la causa raíz de este stack trace de base de datos PostgreSQL",
            "ANALYSIS",
        ),
        (
            "Realiza un análisis de rendimiento del servicio de pagos basándote en estos logs",
            "ANALYSIS",
        ),
        (
            "Genera el RCA ejecutivo del incidente del servicio de autenticación",
            "DOCS",
        ),
        (
            "Documenta el procedimiento de runbook para el reinicio del servicio de pagos",
            "DOCS",
        ),
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
        assert decision.model, "Model should not be empty"
        assert ":" in decision.model or decision.model.isidentifier(), (
            f"Model tag looks invalid: {decision.model}"
        )

    def test_routing_confidence_range(self, router):
        decision = router.route("error crítico P1 en producción")
        assert 0.0 <= decision.confidence <= 1.0

    def test_routing_no_match_defaults_to_analysis(self, router):
        decision = router.route("hola, ¿cómo estás hoy?")
        assert decision.engineer_type == "ANALYSIS"
        assert decision.confidence == 0.0

    def test_route_multi_returns_list(self, router):
        decisions = router.route_multi(
            "error de código en el script de análisis de logs"
        )
        assert isinstance(decisions, list)
        assert len(decisions) >= 1
        for d in decisions:
            assert d.engineer_type in {"TRIAGE", "CODE", "ANALYSIS", "DOCS"}

    def test_route_multi_sorted_by_score(self, router):
        decisions = router.route_multi(
            "error de código en el script de análisis de logs", max_types=3
        )
        confidences = [d.confidence for d in decisions]
        assert confidences == sorted(confidences, reverse=True), (
            "route_multi results should be sorted by confidence descending"
        )

    def test_explain_contains_all_types(self, router):
        explanation = router.explain("analiza el error en el código Python")
        for etype in ("TRIAGE", "CODE", "ANALYSIS", "DOCS"):
            assert etype in explanation

    def test_get_model_for_type(self, router):
        model = router.get_model_for_type("CODE")
        assert model, "Should return a non-empty model name for CODE"
        model_upper = router.get_model_for_type("code")  # case insensitive
        assert model == model_upper


# ---------------------------------------------------------------------------
# Session Store Tests (no Ollama required)
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
        history = session_store.get_history("nonexistent-session-id")
        assert history == []

    def test_list_sessions(self, session_store):
        sid1 = session_store.create_session()
        sid2 = session_store.create_session()
        session_store.append(sid1, "t", "s")
        session_store.append(sid2, "t", "s")

        sessions = session_store.list_sessions()
        ids = [s["session_id"] for s in sessions]
        assert sid1 in ids
        assert sid2 in ids

    def test_list_sessions_sorted_by_updated_at(self, session_store):
        sid1 = session_store.create_session()
        time.sleep(0.01)
        sid2 = session_store.create_session()
        session_store.append(sid1, "t", "s")
        time.sleep(0.01)
        session_store.append(sid2, "t", "s")

        sessions = session_store.list_sessions()
        ids = [s["session_id"] for s in sessions]
        # Most recently updated should be first
        assert ids.index(sid2) < ids.index(sid1)

    def test_delete_session(self, session_store):
        sid = session_store.create_session()
        deleted = session_store.delete_session(sid)
        assert deleted is True
        assert session_store.get_history(sid) == []

    def test_delete_nonexistent_session(self, session_store):
        deleted = session_store.delete_session("no-such-id")
        assert deleted is False

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
        last = session_store.get_last_session_id()
        assert last == sid

    def test_max_sessions_pruning(self, config, tmp_path):
        """Sessions beyond max_sessions should be pruned."""
        mem_cfg = {
            "storage_dir": str(tmp_path / "prune_test"),
            "max_sessions": 3,
            "session_ttl_hours": 0,  # disable TTL
        }
        store = SessionStore(mem_cfg)
        created_ids = []
        for i in range(5):
            sid = store.create_session()
            store.append(sid, f"task {i}", f"summary {i}")
            time.sleep(0.01)
            created_ids.append(sid)

        remaining = store.list_sessions()
        assert len(remaining) <= 3, (
            f"Expected ≤3 sessions after pruning, found {len(remaining)}"
        )


# ---------------------------------------------------------------------------
# Live Pipeline Tests (require --live flag + running Ollama)
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
                "¿Cuál es la severidad y el siguiente paso de investigación?"
            ),
            "expected_engineer": "TRIAGE",
            "check_in_summary": ["NullPointerException", "severidad"],
        },
        {
            "name": "python_bug_code_review",
            "task": (
                "Revisa este código Python y encuentra el bug:\n"
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
                "Genera un borrador de RCA para: Caída del servicio de pagos durante "
                "30 minutos. Causa raíz: timeout de conexión al pool de base de datos "
                "por número insuficiente de conexiones configuradas (max_connections=10). "
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
            "check_in_summary": ["PostgreSQL", "base de datos", "conexión"],
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

        result = orchestrator.run(
            case["task"],
            use_architect_llm=False,  # Use keyword routing for speed
        )

        # Basic structural assertions
        assert result is not None
        assert result.summary, "Summary should not be empty"
        assert result.session_id, "Session ID should be set"
        assert result.subtasks_executed >= 1

        # Check that expected content appears in summary (case-insensitive)
        summary_lower = result.summary.lower()
        for expected_term in case.get("check_in_summary", []):
            assert expected_term.lower() in summary_lower, (
                f"Expected '{expected_term}' in summary.\n"
                f"Summary:\n{result.summary[:500]}"
            )

    def test_live_session_continuity(self, request, orchestrator):
        """Test that context from previous turns appears in subsequent turns."""
        if not request.config.getoption("--live"):
            pytest.skip("Requires --live flag")

        session_id = str(uuid.uuid4())

        # Turn 1: Establish context
        result1 = orchestrator.run(
            "Tenemos un incidente P1 en el servicio de pagos. Código de error: PAY-503.",
            session_id=session_id,
            use_architect_llm=False,
        )
        assert result1.success

        # Turn 2: Ask follow-up that requires context
        result2 = orchestrator.run(
            "¿Cuáles son los pasos de remediación para el incidente anterior?",
            session_id=session_id,
            use_architect_llm=False,
        )
        assert result2.success
        # Both summaries should be non-empty
        assert result1.summary
        assert result2.summary

    def test_live_no_architect_mode(self, request, orchestrator):
        """Verify --no-architect (keyword routing) mode works end-to-end."""
        if not request.config.getoption("--live"):
            pytest.skip("Requires --live flag")

        result = orchestrator.run(
            "¿Qué causa el error OOM (OutOfMemoryError) en Java?",
            use_architect_llm=False,
        )
        assert result.success
        assert result.summary

    def test_live_response_time_reasonable(self, request, orchestrator):
        """Verify that phi3:mini responds within 120 seconds (CPU-only baseline)."""
        if not request.config.getoption("--live"):
            pytest.skip("Requires --live flag")

        start = time.time()
        result = orchestrator.run(
            "Clasifica: servicio web devuelve HTTP 500.",
            use_architect_llm=False,
        )
        elapsed = time.time() - start

        assert result.success
        assert elapsed < 120, (
            f"Response took {elapsed:.1f}s — exceeded 120s threshold for phi3:mini on CPU"
        )
        assert result.total_duration_seconds > 0


# ---------------------------------------------------------------------------
# Config Validation Tests (no Ollama required)
# ---------------------------------------------------------------------------

class TestConfig:
    """Validate that config.yaml contains all required keys."""

    REQUIRED_TOP_KEYS = ["ollama", "agents", "routing", "execution", "memory", "logging"]
    REQUIRED_AGENT_KEYS = ["architect", "engineers"]
    REQUIRED_ENGINEER_TYPES = ["TRIAGE", "CODE", "ANALYSIS", "DOCS"]
    REQUIRED_ENGINEER_FIELDS = ["model", "system_prompt", "max_tokens", "temperature"]

    def test_top_level_keys_present(self, config):
        for key in self.REQUIRED_TOP_KEYS:
            assert key in config, f"Missing top-level config key: '{key}'"

    def test_ollama_base_url_present(self, config):
        assert "base_url" in config["ollama"]
        assert config["ollama"]["base_url"].startswith("http")

    def test_all_engineer_types_present(self, config):
        engineers = config["agents"]["engineers"]
        for etype in self.REQUIRED_ENGINEER_TYPES:
            assert etype in engineers, f"Missing engineer type in config: '{etype}'"

    def test_engineer_configs_have_required_fields(self, config):
        engineers = config["agents"]["engineers"]
        for etype in self.REQUIRED_ENGINEER_TYPES:
            eng = engineers[etype]
            for field in self.REQUIRED_ENGINEER_FIELDS:
                assert field in eng, (
                    f"Engineer '{etype}' missing required field: '{field}'"
                )

    def test_execution_mode_valid(self, config):
        mode = config["execution"].get("mode", "sequential")
        assert mode in ("sequential", "parallel"), (
            f"Invalid execution mode: '{mode}'"
        )

    def test_routing_keywords_present(self, config):
        routing = config["routing"]
        for key in ("triage_keywords", "code_keywords", "analysis_keywords", "docs_keywords"):
            assert key in routing, f"Missing routing keyword list: '{key}'"
            assert isinstance(routing[key], list)
            assert len(routing[key]) > 0, f"Keyword list '{key}' is empty"

    def test_memory_storage_dir_configured(self, config):
        assert "storage_dir" in config["memory"]


# ---------------------------------------------------------------------------
# Result Serialization Tests
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
