"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           TASK BRIEF — Ingeniero Backend Local (Ollama)                     ║
║           Módulo: extended_metrics_collector.py                             ║
║           Asignado por: FRIDA (Arquitecta Orquestadora)                     ║
║           Fecha: 2026-04-18                                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  CONTEXTO                                                                   ║
║  El módulo metrics_monitor.py ya captura CPU, RAM y modelos Ollama.         ║
║  Tu tarea es extender esa base con 4 fuentes adicionales de datos sin       ║
║  romper la interfaz existente: hereda o importa MetricsSnapshot y           ║
║  MetricsCollector, no los reemplaces.                                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  ENTREGABLES REQUERIDOS                                                     ║
║  1. NetworkMetrics  — dataclass con métricas de red por interfaz            ║
║  2. DiskMetrics     — dataclass con uso y velocidad por partición           ║
║  3. ProcessMetrics  — dataclass con info del proceso ollama.exe             ║
║  4. ExtendedSnapshot — dataclass que extiende MetricsSnapshot               ║
║  5. ExtendedMetricsCollector — clase que hereda MetricsCollector            ║
║     y añade collect_network(), collect_disk(), collect_process_ollama()     ║
║     y collect() → ExtendedSnapshot                                          ║
║  6. SnapshotHistory — clase que guarda los últimos 60 snapshots             ║
║     y calcula tendencias: avg, max, min para cpu.total_percent y            ║
║     ram.percent                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  ESPECIFICACIÓN TÉCNICA                                                     ║
║                                                                             ║
║  NetworkMetrics:                                                            ║
║    interface: str          — nombre de la interfaz (e.g. "Ethernet")       ║
║    bytes_sent: int         — bytes totales enviados (acumulado psutil)      ║
║    bytes_recv: int         — bytes totales recibidos                        ║
║    bytes_sent_per_sec: float — calculado como delta vs snapshot anterior    ║
║    bytes_recv_per_sec: float — calculado como delta vs snapshot anterior    ║
║    is_up: bool             — interfaz activa                                ║
║                                                                             ║
║  DiskMetrics:                                                               ║
║    mountpoint: str         — ruta de la partición (e.g. "C:\\")             ║
║    total_gb: float                                                          ║
║    used_gb: float                                                           ║
║    free_gb: float                                                           ║
║    percent: float                                                           ║
║    read_bytes_per_sec: float  — delta vs snapshot anterior                  ║
║    write_bytes_per_sec: float — delta vs snapshot anterior                  ║
║                                                                             ║
║  ProcessMetrics:                                                            ║
║    pid: int                                                                 ║
║    name: str               — "ollama.exe" o "ollama"                       ║
║    cpu_percent: float      — uso CPU del proceso                            ║
║    mem_rss_mb: float       — RSS en MB                                     ║
║    num_threads: int                                                         ║
║    status: str             — "running" / "sleeping" / "not_found"          ║
║    found: bool                                                              ║
║                                                                             ║
║  ExtendedSnapshot(MetricsSnapshot):                                         ║
║    network: List[NetworkMetrics]                                            ║
║    disks: List[DiskMetrics]                                                 ║
║    ollama_process: ProcessMetrics                                           ║
║                                                                             ║
║  SnapshotHistory:                                                           ║
║    __init__(maxlen=60)                                                      ║
║    add(snapshot: ExtendedSnapshot)                                          ║
║    cpu_trend() → dict con avg, max, min de cpu.total_percent               ║
║    ram_trend() → dict con avg, max, min de ram.percent                     ║
║    latest() → ExtendedSnapshot | None                                      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  REGLAS DE IMPLEMENTACIÓN                                                   ║
║  - Usa psutil.net_io_counters(pernic=True) para red                        ║
║  - Usa psutil.disk_partitions() + disk_usage() para disco                  ║
║  - Usa psutil.disk_io_counters(perdisk=True) para I/O velocidades          ║
║  - Usa psutil.process_iter(['pid','name','cpu_percent','memory_info',       ║
║    'num_threads','status']) para encontrar ollama                           ║
║  - Los deltas de red/disco requieren el timestamp del snapshot anterior;   ║
║    el collector debe guardar self._last_net y self._last_disk internamente ║
║  - Si Ollama no está corriendo, ProcessMetrics.found = False               ║
║  - No lanzar excepciones al usuario; capturar todo y retornar valores 0    ║
║  - Todas las divisiones deben protegerse contra ZeroDivisionError          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  CRITERIOS DE ACEPTACIÓN                                                   ║
║  C1. collect() retorna ExtendedSnapshot en < 3 segundos                    ║
║  C2. Si Ollama no corre, ProcessMetrics.found = False sin excepción        ║
║  C3. bytes_per_sec es 0.0 en el primer snapshot (sin delta previo)         ║
║  C4. SnapshotHistory.cpu_trend() retorna {'avg':0,'max':0,'min':0}         ║
║      cuando el historial está vacío                                         ║
║  C5. ExtendedSnapshot es serializable con dataclasses.asdict()             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from statistics import mean
from typing import Dict, List, Optional

import psutil

# Re-exportamos los dataclasses base para que los consumidores importen desde
# este módulo sin necesidad de conocer metrics_monitor.
from monitors.metrics_monitor import (
    CpuMetrics,
    MetricsCollector,
    MetricsSnapshot,
    OllamaMetrics,
    RamMetrics,
)

__all__ = [
    "NetworkMetrics",
    "DiskMetrics",
    "ProcessMetrics",
    "ExtendedSnapshot",
    "ExtendedMetricsCollector",
    "SnapshotHistory",
]


# ---------------------------------------------------------------------------
# Dataclasses extendidos
# ---------------------------------------------------------------------------


@dataclass
class NetworkMetrics:
    """Métricas de una interfaz de red."""

    interface: str
    bytes_sent: int
    bytes_recv: int
    bytes_sent_per_sec: float = 0.0
    bytes_recv_per_sec: float = 0.0
    is_up: bool = True


@dataclass
class DiskMetrics:
    """Métricas de una partición de disco."""

    mountpoint: str
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float
    read_bytes_per_sec: float = 0.0
    write_bytes_per_sec: float = 0.0


@dataclass
class ProcessMetrics:
    """Métricas del proceso ollama (o cualquier proceso objetivo)."""

    pid: int = 0
    name: str = ""
    cpu_percent: float = 0.0
    mem_rss_mb: float = 0.0
    num_threads: int = 0
    status: str = "not_found"
    found: bool = False


@dataclass
class ExtendedSnapshot(MetricsSnapshot):
    """Snapshot extendido que incluye red, disco y proceso Ollama."""

    # NOTA: MetricsSnapshot ya tiene: timestamp, cpu, ram, ollama
    # Los campos nuevos deben tener default_factory para mantener compatibilidad
    network: List[NetworkMetrics] = field(default_factory=list)
    disks: List[DiskMetrics] = field(default_factory=list)
    ollama_process: ProcessMetrics = field(default_factory=ProcessMetrics)


# ---------------------------------------------------------------------------
# Colector extendido
# ---------------------------------------------------------------------------


class ExtendedMetricsCollector(MetricsCollector):
    """
    Extiende MetricsCollector con captura de red, disco y proceso Ollama.

    Los deltas de velocidad (bytes/s) se calculan automáticamente entre
    llamadas sucesivas a collect(). El primer snapshot siempre tendrá 0.0
    en los campos *_per_sec.
    """

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        super().__init__(ollama_url=ollama_url)

        # Estado interno para calcular deltas
        self._last_net_time: float = 0.0
        self._last_net: Dict[str, tuple] = {}   # {iface: (bytes_sent, bytes_recv)}

        self._last_disk_time: float = 0.0
        self._last_disk: Dict[str, tuple] = {}  # {dev: (read_bytes, write_bytes)}

    # ------------------------------------------------------------------
    # Red
    # ------------------------------------------------------------------

    def collect_network(self) -> List[NetworkMetrics]:
        """
        Retorna métricas de cada interfaz de red activa.
        Los bytes_per_sec son 0.0 si no hay snapshot anterior.

        Usa: psutil.net_io_counters(pernic=True)
             psutil.net_if_stats() para is_up
        """
        result: List[NetworkMetrics] = []
        now = time.monotonic()

        try:
            counters = psutil.net_io_counters(pernic=True)
            stats = psutil.net_if_stats()
            elapsed = now - self._last_net_time if self._last_net_time else 0.0

            for iface, cnt in counters.items():
                sent_ps = 0.0
                recv_ps = 0.0
                if elapsed > 0 and iface in self._last_net:
                    prev_sent, prev_recv = self._last_net[iface]
                    sent_ps = max(0.0, (cnt.bytes_sent - prev_sent) / elapsed)
                    recv_ps = max(0.0, (cnt.bytes_recv - prev_recv) / elapsed)

                is_up = stats[iface].isup if iface in stats else True
                result.append(NetworkMetrics(
                    interface=iface,
                    bytes_sent=cnt.bytes_sent,
                    bytes_recv=cnt.bytes_recv,
                    bytes_sent_per_sec=round(sent_ps, 1),
                    bytes_recv_per_sec=round(recv_ps, 1),
                    is_up=is_up,
                ))

            # Actualizar estado
            self._last_net = {
                iface: (cnt.bytes_sent, cnt.bytes_recv)
                for iface, cnt in counters.items()
            }
            self._last_net_time = now

        except Exception:
            pass  # Nunca propagar errores al consumidor

        return result

    # ------------------------------------------------------------------
    # Disco
    # ------------------------------------------------------------------

    def collect_disk(self) -> List[DiskMetrics]:
        """
        Retorna métricas de cada partición montada.

        Usa: psutil.disk_partitions()
             psutil.disk_usage(mountpoint)
             psutil.disk_io_counters(perdisk=True)
        """
        result: List[DiskMetrics] = []
        now = time.monotonic()
        gb = 1024 ** 3
        elapsed = now - self._last_disk_time if self._last_disk_time else 0.0

        try:
            io_all = psutil.disk_io_counters(perdisk=True) or {}
        except Exception:
            io_all = {}

        new_disk_state: Dict[str, tuple] = {}

        try:
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                except PermissionError:
                    continue

                # Calcular I/O velocidades usando el device físico
                dev = part.device.replace("\\\\", "").replace("\\", "").replace("/", "")
                read_ps = 0.0
                write_ps = 0.0

                # Buscar coincidencia de dispositivo en io_all (Windows/Linux)
                matched_key = next(
                    (k for k in io_all if dev.lower().startswith(k.lower()) or
                     k.lower().startswith(dev.lower())),
                    None,
                )
                if matched_key:
                    io = io_all[matched_key]
                    new_disk_state[matched_key] = (io.read_bytes, io.write_bytes)
                    if elapsed > 0 and matched_key in self._last_disk:
                        pr, pw = self._last_disk[matched_key]
                        read_ps = max(0.0, (io.read_bytes - pr) / elapsed)
                        write_ps = max(0.0, (io.write_bytes - pw) / elapsed)

                result.append(DiskMetrics(
                    mountpoint=part.mountpoint,
                    total_gb=round(usage.total / gb, 2),
                    used_gb=round(usage.used / gb, 2),
                    free_gb=round(usage.free / gb, 2),
                    percent=usage.percent,
                    read_bytes_per_sec=round(read_ps, 1),
                    write_bytes_per_sec=round(write_ps, 1),
                ))

            self._last_disk = new_disk_state
            self._last_disk_time = now

        except Exception:
            pass

        return result

    # ------------------------------------------------------------------
    # Proceso Ollama
    # ------------------------------------------------------------------

    def collect_process_ollama(self) -> ProcessMetrics:
        """
        Busca el proceso ollama.exe (Windows) u ollama (Linux/Mac)
        y retorna sus métricas.

        Si no se encuentra, retorna ProcessMetrics(found=False).
        Usa: psutil.process_iter()
        """
        target_names = {"ollama.exe", "ollama"}
        try:
            for proc in psutil.process_iter(
                attrs=["pid", "name", "cpu_percent", "memory_info", "num_threads", "status"]
            ):
                info = proc.info
                if info.get("name", "").lower() in target_names:
                    mem = info.get("memory_info")
                    return ProcessMetrics(
                        pid=info.get("pid", 0),
                        name=info.get("name", ""),
                        cpu_percent=info.get("cpu_percent") or 0.0,
                        mem_rss_mb=round((mem.rss / (1024 ** 2)) if mem else 0.0, 2),
                        num_threads=info.get("num_threads") or 0,
                        status=info.get("status", "unknown"),
                        found=True,
                    )
        except Exception:
            pass

        return ProcessMetrics(status="not_found", found=False)

    # ------------------------------------------------------------------
    # Snapshot extendido
    # ------------------------------------------------------------------

    def collect(self) -> ExtendedSnapshot:  # type: ignore[override]
        """
        Recolecta un ExtendedSnapshot completo.
        Llama a todos los sub-colectores y combina los resultados.
        Tiempo objetivo: < 3 segundos en hardware de referencia.
        """
        base = super().collect()  # MetricsSnapshot
        return ExtendedSnapshot(
            timestamp=base.timestamp,
            cpu=base.cpu,
            ram=base.ram,
            ollama=base.ollama,
            network=self.collect_network(),
            disks=self.collect_disk(),
            ollama_process=self.collect_process_ollama(),
        )


# ---------------------------------------------------------------------------
# Historial de snapshots con tendencias
# ---------------------------------------------------------------------------


class SnapshotHistory:
    """
    Mantiene un historial circular de hasta `maxlen` ExtendedSnapshot
    y calcula tendencias básicas sobre CPU y RAM.
    """

    def __init__(self, maxlen: int = 60):
        self._history: deque[ExtendedSnapshot] = deque(maxlen=maxlen)

    def add(self, snapshot: ExtendedSnapshot) -> None:
        self._history.append(snapshot)

    def _empty_trend(self) -> dict:
        return {"avg": 0.0, "max": 0.0, "min": 0.0, "samples": 0}

    def cpu_trend(self) -> dict:
        """Tendencia de cpu.total_percent sobre el historial."""
        if not self._history:
            return self._empty_trend()
        values = [s.cpu.total_percent for s in self._history]
        return {
            "avg": round(mean(values), 2),
            "max": round(max(values), 2),
            "min": round(min(values), 2),
            "samples": len(values),
        }

    def ram_trend(self) -> dict:
        """Tendencia de ram.percent sobre el historial."""
        if not self._history:
            return self._empty_trend()
        values = [s.ram.percent for s in self._history]
        return {
            "avg": round(mean(values), 2),
            "max": round(max(values), 2),
            "min": round(min(values), 2),
            "samples": len(values),
        }

    def latest(self) -> Optional[ExtendedSnapshot]:
        """Retorna el snapshot más reciente o None si el historial está vacío."""
        return self._history[-1] if self._history else None

    def __len__(self) -> int:
        return len(self._history)
