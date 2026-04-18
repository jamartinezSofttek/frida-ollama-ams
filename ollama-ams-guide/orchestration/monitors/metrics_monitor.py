"""
metrics_monitor.py — Real-time system and Ollama metrics monitor.

Usage:
    python -m monitors.metrics_monitor
    python -m monitors.metrics_monitor --interval 3 --export --url http://localhost:11434
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import psutil
import requests
from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CpuMetrics:
    total_percent: float
    per_core: List[float]
    frequency_mhz: float
    core_count: int
    thread_count: int


@dataclass
class RamMetrics:
    total_gb: float
    used_gb: float
    available_gb: float
    percent: float


@dataclass
class OllamaModel:
    name: str
    size_gb: float
    digest: str
    expires_at: str          # ISO-8601 string from Ollama
    size_vram: float = 0.0   # VRAM occupied (bytes → GB)


@dataclass
class OllamaMetrics:
    available: bool
    models_loaded: List[OllamaModel] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class MetricsSnapshot:
    timestamp: str
    cpu: CpuMetrics
    ram: RamMetrics
    ollama: OllamaMetrics


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

class MetricsCollector:
    """Collects a MetricsSnapshot from the local system and Ollama."""

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url.rstrip("/")
        self._ps_url = f"{self.ollama_url}/api/ps"

    # --- CPU ----------------------------------------------------------------

    def collect_cpu(self) -> CpuMetrics:
        per_core = psutil.cpu_percent(percpu=True, interval=0.2)
        total = psutil.cpu_percent(interval=None)
        freq = psutil.cpu_freq()
        freq_mhz = freq.current if freq else 0.0
        return CpuMetrics(
            total_percent=total,
            per_core=per_core,
            frequency_mhz=round(freq_mhz, 1),
            core_count=psutil.cpu_count(logical=False) or 1,
            thread_count=psutil.cpu_count(logical=True) or 1,
        )

    # --- RAM ----------------------------------------------------------------

    def collect_ram(self) -> RamMetrics:
        vm = psutil.virtual_memory()
        gb = 1024 ** 3
        return RamMetrics(
            total_gb=round(vm.total / gb, 2),
            used_gb=round(vm.used / gb, 2),
            available_gb=round(vm.available / gb, 2),
            percent=vm.percent,
        )

    # --- Ollama -------------------------------------------------------------

    def collect_ollama(self) -> OllamaMetrics:
        try:
            resp = requests.get(self._ps_url, timeout=(3, 10))
            resp.raise_for_status()
            data = resp.json()
            models_raw = data.get("models") or []
            models = []
            for m in models_raw:
                size_bytes = m.get("size", 0)
                vram_bytes = m.get("size_vram", 0)
                models.append(OllamaModel(
                    name=m.get("name", "unknown"),
                    size_gb=round(size_bytes / (1024 ** 3), 2),
                    digest=m.get("digest", "")[:12],
                    expires_at=m.get("expires_at", ""),
                    size_vram=round(vram_bytes / (1024 ** 3), 3),
                ))
            return OllamaMetrics(available=True, models_loaded=models)
        except requests.exceptions.ConnectionError:
            return OllamaMetrics(available=False, error="Ollama no disponible (conexión rechazada)")
        except requests.exceptions.Timeout:
            return OllamaMetrics(available=False, error="Timeout al conectar con Ollama")
        except Exception as exc:
            return OllamaMetrics(available=False, error=str(exc))

    # --- Snapshot -----------------------------------------------------------

    def collect(self) -> MetricsSnapshot:
        return MetricsSnapshot(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            cpu=self.collect_cpu(),
            ram=self.collect_ram(),
            ollama=self.collect_ollama(),
        )


# ---------------------------------------------------------------------------
# Helpers — color thresholds
# ---------------------------------------------------------------------------

def _pct_color(pct: float) -> str:
    if pct >= 85:
        return "red"
    if pct >= 60:
        return "yellow"
    return "green"


def _bar(pct: float, width: int = 20) -> str:
    filled = int(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class MetricsDashboard:
    """Renders a live terminal dashboard and optionally exports metrics."""

    def __init__(
        self,
        collector: MetricsCollector,
        interval: int = 5,
        export: bool = False,
        log_dir: str = "logs/metrics",
    ):
        self.collector = collector
        self.interval = interval
        self.export = export
        self.log_dir = Path(log_dir)

    # --- Rendering ----------------------------------------------------------

    def _render_cpu(self, cpu: CpuMetrics) -> Panel:
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
        table.add_column("Métrica", style="dim")
        table.add_column("Valor")

        color = _pct_color(cpu.total_percent)
        table.add_row("Total CPU",
                      Text(f"{cpu.total_percent:5.1f}%  {_bar(cpu.total_percent)}", style=color))
        table.add_row("Frecuencia", f"{cpu.frequency_mhz} MHz")
        table.add_row("Núcleos / Hilos", f"{cpu.core_count} / {cpu.thread_count}")

        # Per-core mini-bars (up to 6 shown)
        for i, pct in enumerate(cpu.per_core[:6]):
            c = _pct_color(pct)
            table.add_row(f"  Core {i}", Text(f"{pct:5.1f}%  {_bar(pct, 12)}", style=c))
        if len(cpu.per_core) > 6:
            table.add_row("  ...", f"({len(cpu.per_core) - 6} cores más)")

        return Panel(table, title="[bold]🖥  CPU[/bold]", border_style="cyan")

    def _render_ram(self, ram: RamMetrics) -> Panel:
        table = Table(box=box.SIMPLE, show_header=False)
        table.add_column("Métrica", style="dim")
        table.add_column("Valor")

        color = _pct_color(ram.percent)
        table.add_row("Uso",
                      Text(f"{ram.percent:5.1f}%  {_bar(ram.percent)}", style=color))
        table.add_row("Usada / Total", f"{ram.used_gb} GB / {ram.total_gb} GB")
        table.add_row("Disponible", f"{ram.available_gb} GB")

        return Panel(table, title="[bold]🧠  RAM[/bold]", border_style="magenta")

    def _render_ollama(self, ollama: OllamaMetrics) -> Panel:
        if not ollama.available:
            msg = Text(f"⚠  {ollama.error}", style="yellow")
            return Panel(msg, title="[bold]🤖  Ollama[/bold]", border_style="yellow")

        if not ollama.models_loaded:
            msg = Text("✔  Ollama activo — ningún modelo cargado en memoria.", style="green")
            return Panel(msg, title="[bold]🤖  Ollama[/bold]", border_style="green")

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold green")
        table.add_column("Modelo")
        table.add_column("Tamaño", justify="right")
        table.add_column("VRAM", justify="right")
        table.add_column("Expira (keep_alive)")
        table.add_column("Digest")

        for m in ollama.models_loaded:
            expires = m.expires_at[:19].replace("T", " ") if m.expires_at else "—"
            table.add_row(
                m.name,
                f"{m.size_gb} GB",
                f"{m.size_vram} GB" if m.size_vram else "CPU",
                expires,
                m.digest,
            )

        return Panel(table, title=f"[bold]🤖  Ollama — {len(ollama.models_loaded)} modelo(s)[/bold]",
                     border_style="green")

    def _build_layout(self, snap: MetricsSnapshot) -> Panel:
        header = Text(
            f"  FRIDA · Monitor de Métricas Ollama  ·  {snap.timestamp}  ·  Intervalo: {self.interval}s",
            style="bold white on dark_blue",
            justify="center",
        )
        top = Columns([self._render_cpu(snap.cpu), self._render_ram(snap.ram)], equal=True)
        footer_text = "[dim]Ctrl+C para salir[/dim]"
        if self.export:
            footer_text += f"  |  Exportando a [cyan]{self.log_dir}[/cyan]"

        from rich.align import Align
        return Panel(
            Align.center(header),
            subtitle=footer_text,
        )

    def _render_full(self, snap: MetricsSnapshot):
        from rich.console import Group
        header = Text(
            f"  FRIDA · Monitor Ollama  ·  {snap.timestamp}  ·  cada {self.interval}s",
            style="bold white on dark_blue",
            justify="center",
        )
        footer = "[dim]Ctrl+C para salir[/dim]"
        if self.export:
            footer += f"  |  Exportando → [cyan]{self.log_dir}[/cyan]"
        return Panel(
            Group(
                header,
                Columns([self._render_cpu(snap.cpu), self._render_ram(snap.ram)], equal=True),
                self._render_ollama(snap.ollama),
            ),
            subtitle=footer,
            border_style="blue",
        )

    # --- Export -------------------------------------------------------------

    def _export_snapshot(self, snap: MetricsSnapshot) -> None:
        date_dir = self.log_dir / datetime.now().strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)

        # JSON
        json_file = date_dir / "metrics.json"
        records: list = []
        if json_file.exists():
            try:
                records = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception:
                records = []
        records.append(asdict(snap))
        json_file.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

        # CSV
        csv_file = date_dir / "metrics.csv"
        write_header = not csv_file.exists()
        with open(csv_file, "a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            if write_header:
                writer.writerow([
                    "timestamp",
                    "cpu_total_pct", "cpu_freq_mhz", "cpu_cores",
                    "ram_total_gb", "ram_used_gb", "ram_avail_gb", "ram_pct",
                    "ollama_available", "ollama_models_json",
                ])
            models_json = json.dumps(
                [asdict(m) for m in snap.ollama.models_loaded], ensure_ascii=False
            )
            writer.writerow([
                snap.timestamp,
                snap.cpu.total_percent, snap.cpu.frequency_mhz, snap.cpu.core_count,
                snap.ram.total_gb, snap.ram.used_gb, snap.ram.available_gb, snap.ram.percent,
                snap.ollama.available, models_json,
            ])

    # --- Main loop ----------------------------------------------------------

    def run(self) -> None:
        if self.export:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            console.print(f"[dim]Exportando métricas en: {self.log_dir.resolve()}[/dim]")

        try:
            with Live(console=console, refresh_per_second=1, screen=True) as live:
                while True:
                    snap = self.collector.collect()
                    live.update(self._render_full(snap))
                    if self.export:
                        self._export_snapshot(snap)
                    time.sleep(self.interval)
        except KeyboardInterrupt:
            console.print("\n[yellow]Monitor detenido por el usuario.[/yellow]")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Monitor de métricas en tiempo real para Ollama y el sistema.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=5,
        metavar="SEG",
        help="Intervalo de actualización en segundos.",
    )
    parser.add_argument(
        "--export", "-e",
        action="store_true",
        help="Exportar snapshots a JSON y CSV en logs/metrics/.",
    )
    parser.add_argument(
        "--url", "-u",
        default="http://localhost:11434",
        metavar="URL",
        help="URL base de Ollama.",
    )
    parser.add_argument(
        "--log-dir",
        default="logs/metrics",
        metavar="DIR",
        help="Directorio de exportación.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Tomar una sola muestra, imprimir JSON y salir (útil para scripts).",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    collector = MetricsCollector(ollama_url=args.url)

    if args.once:
        snap = collector.collect()
        print(json.dumps(asdict(snap), indent=2, ensure_ascii=False))
        return

    dashboard = MetricsDashboard(
        collector=collector,
        interval=args.interval,
        export=args.export,
        log_dir=args.log_dir,
    )
    dashboard.run()


if __name__ == "__main__":
    main()
