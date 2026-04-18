"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           TASK BRIEF — Ingeniero de Alertas Local (Ollama)                 ║
║           Módulo: alert_engine.py                                           ║
║           Asignado por: FRIDA (Arquitecta Orquestadora)                     ║
║           Fecha: 2026-04-18                                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  CONTEXTO                                                                   ║
║  Este módulo evalúa cada ExtendedSnapshot contra reglas predefinidas y      ║
║  genera eventos de alerta. Es consumido por monitor_main.py y por          ║
║  AdvancedDashboard para colorear la sección de alertas.                     ║
║  No tiene CLI propio ni dependencia de rich — produce datos puros.          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  ENTREGABLES REQUERIDOS                                                     ║
║  1. AlertSeverity   — Enum con INFO / WARN / CRITICAL                      ║
║  2. AlertRule       — dataclass que encapsula una regla                    ║
║  3. AlertEvent      — dataclass que representa una alerta disparada         ║
║  4. AlertEngine     — clase principal: evalúa reglas, persiste, consulta   ║
║  5. PREDEFINED_RULES — lista de reglas listas para usar (ver spec abajo)   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  ESPECIFICACIÓN TÉCNICA                                                     ║
║                                                                             ║
║  AlertSeverity(Enum):                                                       ║
║    INFO     = "INFO"                                                        ║
║    WARN     = "WARN"                                                        ║
║    CRITICAL = "CRITICAL"                                                    ║
║                                                                             ║
║  AlertRule:                                                                 ║
║    name: str                  — identificador único de la regla             ║
║    condition: Callable[[ExtendedSnapshot, deque], bool]                    ║
║      — función que recibe (snapshot_actual, deque_últimos_N_snapshots)     ║
║        y retorna True si la alerta debe dispararse                          ║
║    severity: AlertSeverity                                                  ║
║    message: str               — mensaje de alerta legible                  ║
║    suggested_action: str      — qué hacer cuando se dispara                ║
║                                                                             ║
║  AlertEvent:                                                                ║
║    rule_name: str                                                           ║
║    severity: str              — valor del enum (no el objeto)              ║
║    message: str                                                             ║
║    suggested_action: str                                                    ║
║    triggered_at: str          — ISO-8601 timestamp                         ║
║    snapshot_timestamp: str    — timestamp del snapshot que lo disparó      ║
║                                                                             ║
║  REGLAS PREDEFINIDAS (PREDEFINED_RULES):                                    ║
║                                                                             ║
║  R1. ram_warn                                                               ║
║      Condición: snapshot.ram.available_gb < 3.0                            ║
║      Severidad: WARN                                                        ║
║      Mensaje: "RAM disponible baja: {X} GB"                                ║
║      Acción: "Ejecutar cleanup_for_ollama.ps1"                             ║
║                                                                             ║
║  R2. ram_critical                                                           ║
║      Condición: snapshot.ram.available_gb < 2.0                            ║
║      Severidad: CRITICAL                                                    ║
║      Mensaje: "RAM CRÍTICA: solo {X} GB disponibles"                       ║
║      Acción: "Ejecutar cleanup_for_ollama.ps1 -Aggressive y detener modelos"║
║                                                                             ║
║  R3. cpu_sustained_high                                                     ║
║      Condición: los últimos 3 snapshots en el deque tienen                 ║
║                 cpu.total_percent > 80%                                     ║
║      Severidad: WARN                                                        ║
║      Mensaje: "CPU sostenida >80% durante los últimos 3 ciclos"            ║
║      Acción: "Verificar procesos con Task Manager"                         ║
║                                                                             ║
║  R4. cpu_critical                                                           ║
║      Condición: snapshot.cpu.total_percent > 95                            ║
║      Severidad: CRITICAL                                                    ║
║      Mensaje: "CPU al {X}% — sistema saturado"                             ║
║      Acción: "Pausar inferencia y revisar procesos inmediatamente"         ║
║                                                                             ║
║  R5. ollama_unreachable                                                     ║
║      Condición: snapshot.ollama.available == False                         ║
║      Severidad: CRITICAL                                                    ║
║      Mensaje: "Servidor Ollama no disponible"                               ║
║      Acción: "Ejecutar 'ollama serve' en terminal separada"               ║
║                                                                             ║
║  R6. model_expiring_soon                                                    ║
║      Condición: algún modelo en ollama.models_loaded tiene                 ║
║                 expires_at tal que quedan < 5 minutos (300 segundos)       ║
║      Severidad: INFO                                                        ║
║      Mensaje: "Modelo {nombre} expira en {X}m {Y}s"                       ║
║      Acción: "Hacer una consulta al modelo para renovar keep_alive"        ║
║      NOTA: Si múltiples modelos expiran, generar un AlertEvent por cada uno║
║                                                                             ║
║  R7. disk_usage_high                                                        ║
║      Condición: alguna partición en snapshot.disks tiene percent > 90      ║
║      Severidad: WARN                                                        ║
║      Mensaje: "Disco {mountpoint} al {X}% de uso"                         ║
║      Acción: "Limpiar logs y archivos temporales"                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  CLASE AlertEngine                                                          ║
║                                                                             ║
║  __init__(rules=PREDEFINED_RULES, alert_log_dir="logs/alerts"):            ║
║    - Inicializa con las reglas recibidas                                    ║
║    - Crea un deque(maxlen=10) para historial de snapshots recientes         ║
║    - Crea una lista self._active_alerts para las alertas actuales           ║
║    - Crea una lista self._alert_history para el historial persistente       ║
║                                                                             ║
║  evaluate(snapshot: ExtendedSnapshot) → List[AlertEvent]:                  ║
║    - Añade snapshot al deque interno                                        ║
║    - Evalúa cada regla; si condition(snapshot, deque) es True:             ║
║        * Crea AlertEvent con timestamp actual                               ║
║        * Añade a self._active_alerts                                        ║
║        * Añade a self._alert_history                                        ║
║        * Si alert_log_dir está configurado, llama a _persist()             ║
║    - Reemplaza self._active_alerts con la lista nueva                       ║
║    - Retorna la lista de eventos activos                                    ║
║                                                                             ║
║  get_active_alerts() → List[AlertEvent]:                                   ║
║    - Retorna self._active_alerts (vacía si no se ha llamado evaluate())    ║
║                                                                             ║
║  get_alert_history(hours: int = 24) → List[AlertEvent]:                   ║
║    - Filtra self._alert_history por las últimas `hours` horas              ║
║    - Retorna los eventos dentro del rango temporal                         ║
║                                                                             ║
║  _persist(events: List[AlertEvent]) → None:                                ║
║    - Guarda los eventos en logs/alerts/alerts_YYYY-MM-DD.json              ║
║    - Formato: lista JSON, un archivo por día, modo append (no sobrescribir)║
║    - Tolerancia a errores de I/O — nunca crashear el ciclo principal       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  REGLAS DE IMPLEMENTACIÓN                                                   ║
║  - Las condiciones de las reglas son lambdas o funciones nombradas         ║
║  - La condición recibe (snapshot, recent_deque) → bool                     ║
║  - Para R3 (CPU sostenida), recent_deque debe tener ≥ 3 snapshots          ║
║  - Para R6 (model_expiring_soon), usa la misma lógica de _countdown()     ║
║    del advanced_dashboard pero retorna segundos en lugar de string         ║
║  - No importar desde advanced_dashboard (evitar dependencia circular)      ║
║  - Importar ExtendedSnapshot desde extended_metrics_collector              ║
║  - _persist() crea el directorio si no existe                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  CRITERIOS DE ACEPTACIÓN                                                   ║
║  C1. evaluate() retorna lista vacía si no se dispara ninguna regla         ║
║  C2. R3 (cpu_sustained) solo dispara si hay ≥ 3 snapshots en el deque     ║
║  C3. R6 genera un AlertEvent separado por cada modelo que expira pronto    ║
║  C4. _persist() crea el archivo si no existe, hace append si ya existe     ║
║  C5. get_alert_history(hours=1) solo retorna alertas de la última hora     ║
║  C6. Ninguna excepción propagada al consumidor                             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable, Deque, List, Optional

from monitors.extended_metrics_collector import ExtendedSnapshot

__all__ = [
    "AlertSeverity",
    "AlertRule",
    "AlertEvent",
    "AlertEngine",
    "PREDEFINED_RULES",
]


# ---------------------------------------------------------------------------
# Severity enum
# ---------------------------------------------------------------------------


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AlertRule:
    """
    Encapsulates a single alerting rule.

    Parameters
    ----------
    condition:
        Callable that receives (current_snapshot, recent_deque) and returns
        True when the alert should fire.  The deque contains the last N
        snapshots (including the current one after it has been appended).
    """

    name: str
    condition: Callable[[ExtendedSnapshot, Deque[ExtendedSnapshot]], bool]
    severity: AlertSeverity
    message_template: str      # May use {value}, {mountpoint}, {name}, etc.
    suggested_action: str


@dataclass
class AlertEvent:
    """An alert that fired for a specific snapshot."""

    rule_name: str
    severity: str              # AlertSeverity value (plain string for JSON)
    message: str
    suggested_action: str
    triggered_at: str          # ISO-8601 UTC
    snapshot_timestamp: str    # Timestamp of the snapshot that triggered it


# ---------------------------------------------------------------------------
# Helper: seconds remaining until ISO-8601 expiry timestamp
# ---------------------------------------------------------------------------


def _seconds_until(expires_at_iso: str) -> float:
    """
    Returns seconds remaining until expires_at_iso.
    Returns -1.0 if empty, already expired, or unparseable.
    """
    if not expires_at_iso:
        return -1.0
    try:
        ts = expires_at_iso.replace("Z", "+00:00")
        expires = datetime.fromisoformat(ts)
        now = datetime.now(tz=timezone.utc)
        delta = (expires - now).total_seconds()
        return delta
    except Exception:
        return -1.0


# ---------------------------------------------------------------------------
# Predefined rules
# ---------------------------------------------------------------------------


def _ram_warn_cond(snap: ExtendedSnapshot, _: Deque) -> bool:
    return snap.ram.available_gb < 3.0


def _ram_critical_cond(snap: ExtendedSnapshot, _: Deque) -> bool:
    return snap.ram.available_gb < 2.0


def _cpu_sustained_cond(snap: ExtendedSnapshot, recent: Deque) -> bool:
    if len(recent) < 3:
        return False
    last_three = list(recent)[-3:]
    return all(s.cpu.total_percent > 80 for s in last_three)


def _cpu_critical_cond(snap: ExtendedSnapshot, _: Deque) -> bool:
    return snap.cpu.total_percent > 95


def _ollama_unreachable_cond(snap: ExtendedSnapshot, _: Deque) -> bool:
    return not snap.ollama.available


def _disk_high_cond(snap: ExtendedSnapshot, _: Deque) -> bool:
    return any(d.percent > 90 for d in (snap.disks or []))


# NOTE: model_expiring_soon is handled specially in AlertEngine.evaluate()
# because it may produce multiple AlertEvents (one per expiring model).
# A sentinel rule is included here so PREDEFINED_RULES is the single source
# of truth, but the engine handles it via a dedicated code path.

def _model_expiring_cond(snap: ExtendedSnapshot, _: Deque) -> bool:
    """True if ANY loaded model expires within 5 minutes."""
    if not snap.ollama.available:
        return False
    for m in snap.ollama.models_loaded:
        if 0 < _seconds_until(m.expires_at) < 300:
            return True
    return False


PREDEFINED_RULES: List[AlertRule] = [
    AlertRule(
        name="ram_warn",
        condition=_ram_warn_cond,
        severity=AlertSeverity.WARN,
        message_template="RAM disponible baja: {value:.2f} GB",
        suggested_action="Ejecutar cleanup_for_ollama.ps1",
    ),
    AlertRule(
        name="ram_critical",
        condition=_ram_critical_cond,
        severity=AlertSeverity.CRITICAL,
        message_template="RAM CRÍTICA: solo {value:.2f} GB disponibles",
        suggested_action="Ejecutar cleanup_for_ollama.ps1 -Aggressive y detener modelos",
    ),
    AlertRule(
        name="cpu_sustained_high",
        condition=_cpu_sustained_cond,
        severity=AlertSeverity.WARN,
        message_template="CPU sostenida >80% durante los últimos 3 ciclos",
        suggested_action="Verificar procesos con Task Manager",
    ),
    AlertRule(
        name="cpu_critical",
        condition=_cpu_critical_cond,
        severity=AlertSeverity.CRITICAL,
        message_template="CPU al {value:.1f}% — sistema saturado",
        suggested_action="Pausar inferencia y revisar procesos inmediatamente",
    ),
    AlertRule(
        name="ollama_unreachable",
        condition=_ollama_unreachable_cond,
        severity=AlertSeverity.CRITICAL,
        message_template="Servidor Ollama no disponible",
        suggested_action="Ejecutar 'ollama serve' en terminal separada",
    ),
    AlertRule(
        name="model_expiring_soon",
        condition=_model_expiring_cond,
        severity=AlertSeverity.INFO,
        message_template="Modelo {name} expira en {value}",
        suggested_action="Hacer una consulta al modelo para renovar keep_alive",
    ),
    AlertRule(
        name="disk_usage_high",
        condition=_disk_high_cond,
        severity=AlertSeverity.WARN,
        message_template="Disco {mountpoint} al {value:.1f}% de uso",
        suggested_action="Limpiar logs y archivos temporales",
    ),
]


# ---------------------------------------------------------------------------
# AlertEngine
# ---------------------------------------------------------------------------


class AlertEngine:
    """
    Evaluates AlertRules against each new ExtendedSnapshot and manages
    alert lifecycle (active, history, persistence).

    Typical usage from monitor_main.py:

        engine = AlertEngine()
        ...
        snap = collector.collect()
        active_alerts = engine.evaluate(snap)
        dashboard.render(snap, history, active_alerts)
    """

    def __init__(
        self,
        rules: Optional[List[AlertRule]] = None,
        alert_log_dir: str = "logs/alerts",
    ):
        self._rules: List[AlertRule] = rules if rules is not None else PREDEFINED_RULES
        self._alert_log_dir: Path = Path(alert_log_dir)
        self._recent: Deque[ExtendedSnapshot] = deque(maxlen=10)
        self._active_alerts: List[AlertEvent] = []
        self._alert_history: List[AlertEvent] = []

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------

    def evaluate(self, snapshot: ExtendedSnapshot) -> List[AlertEvent]:
        """
        Evaluates all rules against `snapshot`.

        Steps:
        1. Append snapshot to internal deque (kept for sustained conditions).
        2. For each rule, call condition(snapshot, deque).
        3. If True, build one or more AlertEvent objects.
        4. Replace self._active_alerts with the new list.
        5. Extend self._alert_history.
        6. Persist new events if alert_log_dir is set.
        7. Return the active alert list.
        """
        self._recent.append(snapshot)
        new_alerts: List[AlertEvent] = []
        now_iso = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")

        for rule in self._rules:
            try:
                fired = rule.condition(snapshot, self._recent)
            except Exception:
                fired = False

            if not fired:
                continue

            # Special multi-event handling for model_expiring_soon
            if rule.name == "model_expiring_soon":
                for m in (snapshot.ollama.models_loaded if snapshot.ollama.available else []):
                    secs = _seconds_until(m.expires_at)
                    if 0 < secs < 300:
                        mins = int(secs // 60)
                        secs_rem = int(secs % 60)
                        countdown = f"{mins}m {secs_rem}s"
                        msg = rule.message_template.format(name=m.name, value=countdown)
                        event = AlertEvent(
                            rule_name=rule.name,
                            severity=rule.severity.value,
                            message=msg,
                            suggested_action=rule.suggested_action,
                            triggered_at=now_iso,
                            snapshot_timestamp=snapshot.timestamp,
                        )
                        new_alerts.append(event)
                continue

            # Generic single-event handling
            msg = self._build_message(rule, snapshot)
            event = AlertEvent(
                rule_name=rule.name,
                severity=rule.severity.value,
                message=msg,
                suggested_action=rule.suggested_action,
                triggered_at=now_iso,
                snapshot_timestamp=snapshot.timestamp,
            )
            new_alerts.append(event)

        self._active_alerts = new_alerts
        self._alert_history.extend(new_alerts)

        if new_alerts:
            self._persist(new_alerts)

        return new_alerts

    # ------------------------------------------------------------------
    # Message builder
    # ------------------------------------------------------------------

    def _build_message(self, rule: AlertRule, snap: ExtendedSnapshot) -> str:
        """Renders the message_template with context-specific values."""
        try:
            if rule.name in ("ram_warn", "ram_critical"):
                return rule.message_template.format(value=snap.ram.available_gb)
            if rule.name == "cpu_critical":
                return rule.message_template.format(value=snap.cpu.total_percent)
            if rule.name == "disk_usage_high":
                # Report first offending disk
                for d in (snap.disks or []):
                    if d.percent > 90:
                        return rule.message_template.format(
                            mountpoint=d.mountpoint, value=d.percent
                        )
            # Generic: no substitution needed
            return rule.message_template
        except Exception:
            return rule.message_template

    # ------------------------------------------------------------------
    # Public query methods
    # ------------------------------------------------------------------

    def get_active_alerts(self) -> List[AlertEvent]:
        """Returns the alerts generated during the last evaluate() call."""
        return list(self._active_alerts)

    def get_alert_history(self, hours: int = 24) -> List[AlertEvent]:
        """
        Returns alerts from the in-memory history that were triggered
        within the last `hours` hours.
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
        result: List[AlertEvent] = []
        for event in self._alert_history:
            try:
                ts = datetime.fromisoformat(event.triggered_at)
                if ts >= cutoff:
                    result.append(event)
            except Exception:
                result.append(event)  # include if unparseable, safer
        return result

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, events: List[AlertEvent]) -> None:
        """
        Appends alert events to logs/alerts/alerts_YYYY-MM-DD.json.
        Creates the file (and parent directories) if they don't exist.
        Errors are silently swallowed to protect the main loop.
        """
        try:
            self._alert_log_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now().strftime("%Y-%m-%d")
            log_file = self._alert_log_dir / f"alerts_{date_str}.json"

            existing: list = []
            if log_file.exists():
                try:
                    existing = json.loads(log_file.read_text(encoding="utf-8"))
                    if not isinstance(existing, list):
                        existing = []
                except Exception:
                    existing = []

            existing.extend(asdict(e) for e in events)
            log_file.write_text(
                json.dumps(existing, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass  # Never crash the monitoring loop due to I/O issues
