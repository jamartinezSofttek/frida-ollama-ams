"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           TASK BRIEF — Ingeniero de Integración Local (Ollama)             ║
║           Módulo: monitor_main.py                                           ║
║           Asignado por: FRIDA (Arquitecta Orquestadora)                     ║
║           Fecha: 2026-04-18                                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  CONTEXTO                                                                   ║
║  Este es el punto de entrada principal del sistema de monitoreo             ║
║  Dynatrace-style. Orquesta los tres módulos anteriores:                     ║
║    - ExtendedMetricsCollector  (extended_metrics_collector.py)              ║
║    - AdvancedDashboard         (advanced_dashboard.py)                      ║
║    - AlertEngine               (alert_engine.py)                            ║
║  También mantiene retrocompatibilidad: si se usa --legacy, delega en       ║
║  metrics_monitor.py original (MetricsDashboard).                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  ARGUMENTOS CLI                                                             ║
║    --interval N     Segundos entre snapshots (default: 5)                  ║
║    --export         Exportar snapshots a JSON/CSV en logs/metrics/          ║
║    --url URL        URL base de Ollama (default: http://localhost:11434)    ║
║    --alert-log DIR  Directorio de logs de alertas (default: logs/alerts)   ║
║    --no-dashboard   Modo headless: solo exportar, sin dashboard rich        ║
║    --once           Captura única, imprime JSON y sale                      ║
║    --legacy         Usar el dashboard original metrics_monitor.py           ║
║    --log-dir DIR    Directorio de métricas exportadas (default: logs/metrics)║
╠══════════════════════════════════════════════════════════════════════════════╣
║  LOOP PRINCIPAL                                                             ║
║  1. Inicializar ExtendedMetricsCollector, AdvancedDashboard, AlertEngine   ║
║     y SnapshotHistory                                                       ║
║  2. Entrar en Live(screen=True, refresh_per_second=2) si no es headless    ║
║  3. Cada iteración:                                                         ║
║     a. snap = collector.collect()                                           ║
║     b. history.add(snap)                                                    ║
║     c. alerts = engine.evaluate(snap)                                      ║
║     d. layout = dashboard.render(snap, history, alerts)                    ║
║     e. live.update(layout)    [si no headless]                             ║
║     f. _export_snapshot(snap) [si --export]                                ║
║     g. time.sleep(interval)                                                 ║
║  4. Ctrl+C → imprimir resumen final de sesión                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  RESUMEN FINAL DE SESIÓN (al salir con Ctrl+C):                            ║
║    - Duración total de la sesión (HH:MM:SS)                                ║
║    - Total de snapshots capturados                                          ║
║    - Total de alertas disparadas                                            ║
║    - Tendencias finales: cpu_trend() y ram_trend() del historial           ║
║    - Si --export: ruta donde se guardaron los archivos                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  MODO --once                                                                ║
║    - Capturar un único snapshot                                             ║
║    - Evaluar alertas                                                        ║
║    - Imprimir JSON con snapshot + alerts a stdout                          ║
║    - Salir con código 0                                                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  MODO --no-dashboard (headless)                                             ║
║    - Sin rich.live ni rich.layout                                           ║
║    - Cada ciclo: collect → evaluate → export (si --export)                 ║
║    - Imprimir una línea de log por ciclo:                                  ║
║      [HH:MM:SS] CPU:X% RAM:X% Alertas:N Snapshots:N                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  CRITERIOS DE ACEPTACIÓN                                                   ║
║  C1. python -m monitors.monitor_main arranca sin errores                   ║
║  C2. Ctrl+C imprime resumen en lugar de traceback                          ║
║  C3. --once imprime JSON válido y sale                                     ║
║  C4. --no-dashboard funciona sin terminal interactiva (útil en CI/scripts) ║
║  C5. --legacy delega completamente en MetricsDashboard del módulo original ║
║  C6. --export genera archivos en logs/metrics/YYYY-MM-DD/                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from monitors.advanced_dashboard import AdvancedDashboard
from monitors.alert_engine import AlertEngine, AlertEvent
from monitors.extended_metrics_collector import (
    ExtendedMetricsCollector,
    ExtendedSnapshot,
    SnapshotHistory,
)

console = Console()


# ---------------------------------------------------------------------------
# Export helpers (mirror of metrics_monitor but for ExtendedSnapshot)
# ---------------------------------------------------------------------------


def _export_snapshot(snap: ExtendedSnapshot, log_dir: Path) -> None:
    """Exports the snapshot to JSON (append) and CSV (append) under log_dir/YYYY-MM-DD/."""
    try:
        date_dir = log_dir / datetime.now().strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)

        # --- JSON -----------------------------------------------------------
        json_file = date_dir / "metrics.json"
        records: list = []
        if json_file.exists():
            try:
                records = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception:
                records = []
        records.append(asdict(snap))
        json_file.write_text(
            json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # --- CSV ------------------------------------------------------------
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
                    "net_interfaces", "disk_partitions",
                    "ollama_process_found", "ollama_process_cpu_pct",
                ])
            models_json = json.dumps(
                [asdict(m) for m in snap.ollama.models_loaded], ensure_ascii=False
            )
            net_json = json.dumps(
                [asdict(n) for n in snap.network], ensure_ascii=False
            )
            disk_json = json.dumps(
                [asdict(d) for d in snap.disks], ensure_ascii=False
            )
            writer.writerow([
                snap.timestamp,
                snap.cpu.total_percent, snap.cpu.frequency_mhz, snap.cpu.core_count,
                snap.ram.total_gb, snap.ram.used_gb, snap.ram.available_gb, snap.ram.percent,
                snap.ollama.available, models_json,
                net_json, disk_json,
                snap.ollama_process.found,
                snap.ollama_process.cpu_percent,
            ])
    except Exception:
        pass  # Export errors must never crash the monitor


# ---------------------------------------------------------------------------
# Session summary
# ---------------------------------------------------------------------------


def _print_summary(
    start_time: datetime,
    snapshot_count: int,
    alert_count: int,
    history: SnapshotHistory,
    export: bool,
    log_dir: Path,
) -> None:
    elapsed = datetime.now(tz=timezone.utc) - start_time
    total_s = int(elapsed.total_seconds())
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60

    cpu_t = history.cpu_trend()
    ram_t = history.ram_trend()

    table = Table(title="📊  Resumen de Sesión FRIDA Monitor", show_header=False)
    table.add_column("Métrica", style="dim")
    table.add_column("Valor", style="bold")

    table.add_row("Duración", f"{h:02d}:{m:02d}:{s:02d}")
    table.add_row("Snapshots capturados", str(snapshot_count))
    table.add_row("Alertas disparadas", str(alert_count))
    table.add_row(
        "CPU (avg / max / min)",
        f"{cpu_t['avg']}% / {cpu_t['max']}% / {cpu_t['min']}%",
    )
    table.add_row(
        "RAM (avg / max / min)",
        f"{ram_t['avg']}% / {ram_t['max']}% / {ram_t['min']}%",
    )
    if export:
        table.add_row("Exportado en", str(log_dir.resolve()))

    console.print()
    console.print(table)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m monitors.monitor_main",
        description="Monitor de métricas Dynatrace-style para Ollama AMS L3.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=5,
        metavar="SEG",
        help="Segundos entre actualizaciones.",
    )
    parser.add_argument(
        "--export", "-e",
        action="store_true",
        help="Exportar snapshots a JSON/CSV en --log-dir.",
    )
    parser.add_argument(
        "--url", "-u",
        default="http://localhost:11434",
        metavar="URL",
        help="URL base del servidor Ollama.",
    )
    parser.add_argument(
        "--alert-log",
        default="logs/alerts",
        metavar="DIR",
        help="Directorio para logs de alertas JSON.",
    )
    parser.add_argument(
        "--log-dir",
        default="logs/metrics",
        metavar="DIR",
        help="Directorio para exportación de métricas.",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Modo headless: exportar métricas sin dashboard visual.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Capturar una sola muestra, imprimir JSON y salir.",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Usar el dashboard original metrics_monitor.py en lugar del Dynatrace-style.",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def _run_legacy(args: argparse.Namespace) -> None:
    """Delegates entirely to the original MetricsDashboard."""
    from monitors.metrics_monitor import MetricsCollector, MetricsDashboard

    collector = MetricsCollector(ollama_url=args.url)
    dashboard = MetricsDashboard(
        collector=collector,
        interval=args.interval,
        export=args.export,
        log_dir=args.log_dir,
    )
    dashboard.run()


def _run_once(args: argparse.Namespace) -> None:
    """Collect one snapshot, evaluate alerts, print JSON and exit."""
    collector = ExtendedMetricsCollector(ollama_url=args.url)
    engine = AlertEngine(alert_log_dir=args.alert_log)

    snap = collector.collect()
    alerts = engine.evaluate(snap)

    output = {
        "snapshot": asdict(snap),
        "alerts": [asdict(a) for a in alerts],
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


def _run_headless(args: argparse.Namespace) -> None:
    """No dashboard — prints a one-liner per cycle; useful for scripting/CI."""
    collector = ExtendedMetricsCollector(ollama_url=args.url)
    engine = AlertEngine(alert_log_dir=args.alert_log)
    history = SnapshotHistory(maxlen=60)
    log_dir = Path(args.log_dir)

    start_time = datetime.now(tz=timezone.utc)
    snapshot_count = 0
    total_alerts = 0

    console.print(
        "[dim]Modo headless activo. Ctrl+C para detener y ver resumen.[/dim]"
    )

    try:
        while True:
            snap = collector.collect()
            history.add(snap)
            alerts = engine.evaluate(snap)
            snapshot_count += 1
            total_alerts += len(alerts)

            if args.export:
                _export_snapshot(snap, log_dir)

            ts = datetime.now().strftime("%H:%M:%S")
            alert_tag = (
                f"[red]Alertas:{len(alerts)}[/red]" if alerts
                else f"[green]Alertas:0[/green]"
            )
            console.print(
                f"[dim]{ts}[/dim]  "
                f"CPU:[cyan]{snap.cpu.total_percent:.1f}%[/cyan]  "
                f"RAM:[cyan]{snap.ram.percent:.1f}%[/cyan]  "
                f"{alert_tag}  "
                f"Snapshots:{snapshot_count}"
            )
            time.sleep(args.interval)

    except KeyboardInterrupt:
        console.print("\n[yellow]Monitor headless detenido.[/yellow]")
        _print_summary(start_time, snapshot_count, total_alerts, history, args.export, log_dir)


def _run_dashboard(args: argparse.Namespace) -> None:
    """Full Dynatrace-style live dashboard."""
    collector = ExtendedMetricsCollector(ollama_url=args.url)
    dashboard = AdvancedDashboard()
    engine = AlertEngine(alert_log_dir=args.alert_log)
    history = SnapshotHistory(maxlen=60)
    log_dir = Path(args.log_dir)

    start_time = datetime.now(tz=timezone.utc)
    snapshot_count = 0
    total_alerts = 0

    if args.export:
        log_dir.mkdir(parents=True, exist_ok=True)

    try:
        # First snapshot to initialise the layout before entering Live
        initial_snap = collector.collect()
        history.add(initial_snap)
        initial_alerts = engine.evaluate(initial_snap)
        snapshot_count += 1
        total_alerts += len(initial_alerts)
        initial_layout = dashboard.render(initial_snap, history, initial_alerts)

        with Live(initial_layout, console=console, screen=True, refresh_per_second=2) as live:
            while True:
                time.sleep(args.interval)

                snap = collector.collect()
                history.add(snap)
                alerts = engine.evaluate(snap)
                snapshot_count += 1
                total_alerts += len(alerts)

                layout = dashboard.render(snap, history, alerts)
                live.update(layout)

                if args.export:
                    _export_snapshot(snap, log_dir)

    except KeyboardInterrupt:
        console.print("\n[yellow]Monitor detenido por el usuario.[/yellow]")
        _print_summary(start_time, snapshot_count, total_alerts, history, args.export, log_dir)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv=None) -> None:
    args = _parse_args(argv)

    if args.legacy:
        _run_legacy(args)
        return

    if args.once:
        _run_once(args)
        return

    if args.no_dashboard:
        _run_headless(args)
        return

    _run_dashboard(args)


if __name__ == "__main__":
    main()
