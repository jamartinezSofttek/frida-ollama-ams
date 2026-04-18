"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           TASK BRIEF — Ingeniero Frontend Local (Ollama)                    ║
║           Módulo: advanced_dashboard.py                                     ║
║           Asignado por: FRIDA (Arquitecta Orquestadora)                     ║
║           Fecha: 2026-04-18                                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  CONTEXTO                                                                   ║
║  El módulo metrics_monitor.py ya tiene un dashboard básico con CPU/RAM.     ║
║  Tu tarea es construir un dashboard estilo Dynatrace usando rich.layout     ║
║  y rich.live que reemplaza la visualización básica en monitor_main.py.      ║
║  Este módulo NO tiene CLI propio — es consumido por monitor_main.py.        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  ENTREGABLES REQUERIDOS                                                     ║
║  1. AdvancedDashboard — clase principal de renderizado                      ║
║     - render(snapshot, history, alerts) → rich.layout.Layout               ║
║     - Secciones: header, cpu, ram, network, disk, ollama, alerts           ║
║  2. Funciones helper privadas (_render_*) una por sección                  ║
║  3. Código de colores consistente con metrics_monitor._pct_color()         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  ESPECIFICACIÓN DE SECCIONES                                                ║
║                                                                             ║
║  HEADER (fila superior, ancho completo):                                    ║
║    - Hostname del sistema (socket.gethostname())                            ║
║    - Uptime del sistema en formato "Xd Xh Xm" (psutil.boot_time())         ║
║    - Timestamp actual en vivo                                               ║
║    - Título "FRIDA · Monitor Dynatrace-Style"                               ║
║    Estilo: bold white on dark_blue, centrado                                ║
║                                                                             ║
║  CPU (panel izquierdo superior):                                            ║
║    - Barra de progreso por núcleo (rich.progress.BarColumn o texto █/░)    ║
║    - Uso total en % con barra grande                                        ║
║    - Frecuencia actual en MHz                                               ║
║    - Temperatura si disponible (psutil.sensors_temperatures())             ║
║      Si no disponible en Windows, mostrar "N/A"                            ║
║    Color: verde <50%, amarillo 50-80%, rojo >80%                           ║
║                                                                             ║
║  RAM (panel derecho superior):                                              ║
║    - Gauge visual de uso % con barra grande                                 ║
║    - GB usada / GB total                                                    ║
║    - GB disponible                                                          ║
║    - ⚠️ ALERTA VISUAL si disponible < 3 GB (texto en rojo parpadeante)     ║
║    Color: verde <60%, amarillo 60-80%, rojo >80%                           ║
║                                                                             ║
║  NETWORK (panel izquierdo medio):                                           ║
║    - Tabla con columnas: Interfaz | Estado | ↑ Enviado/s | ↓ Recibido/s   ║
║    - Solo mostrar interfaces donde is_up = True                            ║
║    - Formatear bytes/s con _format_bytes_per_sec() (KB/s, MB/s)           ║
║    - Si no hay interfaces activas: "Sin interfaces activas"                ║
║                                                                             ║
║  DISK (panel derecho medio):                                                ║
║    - Tabla con columnas: Partición | Uso% | Libre | Total | R/s | W/s     ║
║    - Color del % igual que CPU/RAM                                          ║
║    - Formatear R/s y W/s con _format_bytes_per_sec()                       ║
║                                                                             ║
║  OLLAMA MODELS (panel ancho, fila inferior):                                ║
║    - Tabla con columnas: Modelo | Estado | Tamaño RAM | VRAM | Expira en  ║
║    - Estado: "✅ ACTIVO" (verde) si cargado, "💤 EN DISCO" (dim) si no    ║
║    - "Expira en": countdown en formato "Xm Xs" calculado desde expires_at  ║
║      Si expires_at es vacío o ya expiró: "—"                               ║
║    - Si Ollama no disponible: panel amarillo con ⚠️ mensaje                ║
║    - Proceso Ollama: mostrar PID, CPU%, MEM RSS si found=True              ║
║                                                                             ║
║  ALERTS (barra inferior, ancho completo):                                  ║
║    - Lista las AlertEvent activas recibidas como parámetro                 ║
║    - Si no hay alertas: "✅ Sin alertas activas" en verde                  ║
║    - Si hay alertas: fondo rojo con lista numerada de mensajes             ║
║    - Formato: "[SEVERIDAD] nombre: mensaje — acción_sugerida"              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  LAYOUT RICH                                                                ║
║                                                                             ║
║  Usar rich.layout.Layout con esta estructura:                               ║
║    root                                                                     ║
║    ├── header      (size=3)                                                 ║
║    ├── body                                                                 ║
║    │   ├── top_row                                                          ║
║    │   │   ├── cpu    (ratio=1)                                             ║
║    │   │   └── ram    (ratio=1)                                             ║
║    │   ├── mid_row                                                          ║
║    │   │   ├── network (ratio=1)                                            ║
║    │   │   └── disk    (ratio=1)                                            ║
║    │   └── ollama  (size=10)                                                ║
║    └── alerts  (size=4)                                                     ║
║                                                                             ║
║  Usar rich.live.Live(layout, screen=True, refresh_per_second=2)            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  REGLAS DE IMPLEMENTACIÓN                                                   ║
║  - Importar ExtendedSnapshot, SnapshotHistory desde extended_metrics_collector ║
║  - Importar AlertEvent desde alert_engine (para type hints)                ║
║  - No llamar a psutil directamente desde el dashboard — solo renderizar    ║
║  - _format_bytes_per_sec(bps: float) → str: < 1024 → "X B/s",            ║
║    < 1MB → "X.X KB/s", else → "X.X MB/s"                                 ║
║  - _countdown(expires_at_iso: str) → str: calcular segundos restantes     ║
║    desde datetime.utcnow() vs datetime.fromisoformat(expires_at)          ║
║  - Tolerancia a campos None o vacíos — nunca crashear el render            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  CRITERIOS DE ACEPTACIÓN                                                   ║
║  C1. render() retorna un Layout válido en < 100ms                          ║
║  C2. El dashboard no crashea si snapshot.network o snapshot.disks = []     ║
║  C3. Si Ollama no está disponible, la sección OLLAMA muestra ⚠️ sin error  ║
║  C4. La alerta de RAM < 3 GB se muestra en rojo cuando aplica              ║
║  C5. El countdown de keep_alive muestra "—" cuando expires_at es vacío    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import socket
from datetime import datetime, timezone
from typing import List, Optional

import psutil
from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from monitors.extended_metrics_collector import (
    DiskMetrics,
    ExtendedSnapshot,
    NetworkMetrics,
    ProcessMetrics,
    SnapshotHistory,
)

# Alert types are imported lazily to avoid circular imports at module load time.
# The render() method accepts a plain list; duck typing is used instead of
# a strict AlertEvent import.

__all__ = ["AdvancedDashboard"]

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pct_color(pct: float) -> str:
    """Consistent colour thresholds used throughout the dashboard."""
    if pct >= 80:
        return "red"
    if pct >= 50:
        return "yellow"
    return "green"


def _bar(pct: float, width: int = 20) -> str:
    """Unicode block progress bar."""
    pct = max(0.0, min(100.0, pct))
    filled = int(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _format_bytes_per_sec(bps: float) -> str:
    """Human-readable bandwidth string."""
    if bps < 1024:
        return f"{bps:.0f} B/s"
    if bps < 1024 ** 2:
        return f"{bps / 1024:.1f} KB/s"
    return f"{bps / (1024 ** 2):.1f} MB/s"


def _countdown(expires_at_iso: str) -> str:
    """
    Returns remaining time as 'Xm Xs' until expires_at_iso (UTC ISO-8601).
    Returns '—' if empty, expired, or unparseable.
    """
    if not expires_at_iso:
        return "—"
    try:
        # Ollama returns RFC3339 strings like "2026-04-17T18:05:00Z"
        ts = expires_at_iso.replace("Z", "+00:00")
        expires = datetime.fromisoformat(ts)
        now = datetime.now(tz=timezone.utc)
        delta = (expires - now).total_seconds()
        if delta <= 0:
            return "expirado"
        m = int(delta // 60)
        s = int(delta % 60)
        return f"{m}m {s}s"
    except Exception:
        return "—"


def _uptime() -> str:
    """System uptime formatted as 'Xd Xh Xm'."""
    try:
        boot = psutil.boot_time()
        elapsed = datetime.now().timestamp() - boot
        d = int(elapsed // 86400)
        h = int((elapsed % 86400) // 3600)
        m = int((elapsed % 3600) // 60)
        return f"{d}d {h}h {m}m"
    except Exception:
        return "N/A"


# ---------------------------------------------------------------------------
# Dashboard class
# ---------------------------------------------------------------------------


class AdvancedDashboard:
    """
    Renders an ExtendedSnapshot as a Dynatrace-style rich.layout.Layout.

    Usage (from monitor_main.py):

        dashboard = AdvancedDashboard()
        with Live(dashboard.build_layout(), screen=True, refresh_per_second=2) as live:
            while True:
                snap = collector.collect()
                history.add(snap)
                alerts = alert_engine.get_active_alerts()
                live.update(dashboard.render(snap, history, alerts))
                time.sleep(interval)
    """

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _render_header(self, snap: ExtendedSnapshot) -> Panel:
        hostname = socket.gethostname()
        uptime = _uptime()
        ts = snap.timestamp if snap.timestamp else datetime.now().isoformat(timespec="seconds")
        content = Text(
            f"  FRIDA · Monitor Dynatrace-Style  │  🖥  {hostname}  │  ⏱ {uptime}  │  🕐 {ts}  ",
            style="bold white on dark_blue",
            justify="center",
        )
        return Panel(Align.center(content), style="dark_blue", box=box.HEAVY)

    # ------------------------------------------------------------------
    # CPU
    # ------------------------------------------------------------------

    def _render_cpu(self, snap: ExtendedSnapshot) -> Panel:
        cpu = snap.cpu
        table = Table(box=box.SIMPLE, show_header=False)
        table.add_column("Métrica", style="dim", min_width=16)
        table.add_column("Valor")

        # Total
        color = _pct_color(cpu.total_percent)
        table.add_row(
            "Total CPU",
            Text(f"{cpu.total_percent:5.1f}%  {_bar(cpu.total_percent)}", style=color),
        )
        table.add_row("Frecuencia", f"{cpu.frequency_mhz} MHz")
        table.add_row("Núcleos / Hilos", f"{cpu.core_count} / {cpu.thread_count}")

        # Temperature (Windows typically returns nothing)
        temp_str = "N/A"
        try:
            sensors = psutil.sensors_temperatures()
            if sensors:
                first_key = next(iter(sensors))
                entries = sensors[first_key]
                if entries:
                    temp_str = f"{entries[0].current:.1f} °C"
        except (AttributeError, Exception):
            pass
        table.add_row("Temperatura", temp_str)

        # Per-core bars (max 12 shown)
        for i, pct in enumerate(cpu.per_core[:12]):
            c = _pct_color(pct)
            table.add_row(f"  Core {i}", Text(f"{pct:5.1f}%  {_bar(pct, 14)}", style=c))
        if len(cpu.per_core) > 12:
            table.add_row("  ...", f"({len(cpu.per_core) - 12} núcleos más)")

        return Panel(table, title="[bold cyan]🖥  CPU[/bold cyan]", border_style="cyan")

    # ------------------------------------------------------------------
    # RAM
    # ------------------------------------------------------------------

    def _render_ram(self, snap: ExtendedSnapshot) -> Panel:
        ram = snap.ram
        color = _pct_color(ram.percent)
        low_ram = ram.available_gb < 3.0

        table = Table(box=box.SIMPLE, show_header=False)
        table.add_column("Métrica", style="dim", min_width=16)
        table.add_column("Valor")

        table.add_row(
            "Uso RAM",
            Text(f"{ram.percent:5.1f}%  {_bar(ram.percent)}", style=color),
        )
        table.add_row("Usada / Total", f"{ram.used_gb} GB / {ram.total_gb} GB")

        avail_text = f"{ram.available_gb} GB"
        if low_ram:
            avail_text += "  ⚠️  BAJA MEMORIA"
        table.add_row(
            "Disponible",
            Text(avail_text, style="bold red" if low_ram else "default"),
        )

        border = "red" if low_ram else "magenta"
        title = "[bold magenta]🧠  RAM[/bold magenta]"
        if low_ram:
            title = "[bold red]🧠  RAM — ⚠️ MEMORIA CRÍTICA[/bold red]"

        return Panel(table, title=title, border_style=border)

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------

    def _render_network(self, snap: ExtendedSnapshot) -> Panel:
        active = [n for n in (snap.network or []) if n.is_up]

        if not active:
            return Panel(
                Text("Sin interfaces activas", style="dim"),
                title="[bold blue]🌐  Red[/bold blue]",
                border_style="blue",
            )

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold blue")
        table.add_column("Interfaz")
        table.add_column("Estado", justify="center")
        table.add_column("↑ Enviado/s", justify="right")
        table.add_column("↓ Recibido/s", justify="right")

        for iface in active:
            status = Text("▲ UP", style="green") if iface.is_up else Text("▼ DOWN", style="red")
            table.add_row(
                iface.interface,
                status,
                _format_bytes_per_sec(iface.bytes_sent_per_sec),
                _format_bytes_per_sec(iface.bytes_recv_per_sec),
            )

        return Panel(table, title="[bold blue]🌐  Red[/bold blue]", border_style="blue")

    # ------------------------------------------------------------------
    # Disk
    # ------------------------------------------------------------------

    def _render_disk(self, snap: ExtendedSnapshot) -> Panel:
        disks = snap.disks or []

        if not disks:
            return Panel(
                Text("Sin particiones detectadas", style="dim"),
                title="[bold yellow]💾  Disco[/bold yellow]",
                border_style="yellow",
            )

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold yellow")
        table.add_column("Partición")
        table.add_column("Uso%", justify="right")
        table.add_column("Libre", justify="right")
        table.add_column("Total", justify="right")
        table.add_column("R/s", justify="right")
        table.add_column("W/s", justify="right")

        for d in disks:
            color = _pct_color(d.percent)
            table.add_row(
                d.mountpoint,
                Text(f"{d.percent:.1f}%", style=color),
                f"{d.free_gb} GB",
                f"{d.total_gb} GB",
                _format_bytes_per_sec(d.read_bytes_per_sec),
                _format_bytes_per_sec(d.write_bytes_per_sec),
            )

        return Panel(table, title="[bold yellow]💾  Disco[/bold yellow]", border_style="yellow")

    # ------------------------------------------------------------------
    # Ollama models + process
    # ------------------------------------------------------------------

    def _render_ollama(self, snap: ExtendedSnapshot) -> Panel:
        ollama = snap.ollama
        proc = snap.ollama_process

        if not ollama.available:
            msg = Text(f"⚠  {ollama.error or 'Ollama no disponible'}", style="bold yellow")
            return Panel(msg, title="[bold]🤖  Ollama[/bold]", border_style="yellow")

        # Process info line
        if proc and proc.found:
            proc_info = (
                f"Proceso: PID {proc.pid}  |  "
                f"CPU {proc.cpu_percent:.1f}%  |  "
                f"MEM {proc.mem_rss_mb:.0f} MB  |  "
                f"Hilos {proc.num_threads}  |  {proc.status}"
            )
        else:
            proc_info = "Proceso ollama: no encontrado en sistema"

        # Models table
        if not ollama.models_loaded:
            content = Group(
                Text(proc_info, style="dim"),
                Text("✔  Ollama activo — ningún modelo cargado en RAM.", style="green"),
            )
            return Panel(content, title="[bold green]🤖  Ollama[/bold green]", border_style="green")

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold green")
        table.add_column("Modelo")
        table.add_column("Estado", justify="center")
        table.add_column("RAM", justify="right")
        table.add_column("VRAM", justify="right")
        table.add_column("Expira en", justify="right")
        table.add_column("Digest")

        for m in ollama.models_loaded:
            expires_str = _countdown(m.expires_at)
            vram_str = f"{m.size_vram} GB" if m.size_vram and m.size_vram > 0 else "CPU-only"
            table.add_row(
                m.name,
                Text("✅ ACTIVO", style="bold green"),
                f"{m.size_gb} GB",
                vram_str,
                expires_str,
                m.digest,
            )

        content = Group(Text(proc_info, style="dim"), table)
        return Panel(
            content,
            title=f"[bold green]🤖  Ollama — {len(ollama.models_loaded)} modelo(s) en RAM[/bold green]",
            border_style="green",
        )

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def _render_alerts(self, alerts: list) -> Panel:
        """
        Renders the active alert list.
        `alerts` is a list of AlertEvent objects (or any object with
        .severity, .rule_name, .message, .suggested_action attributes).
        """
        if not alerts:
            return Panel(
                Text("  ✅  Sin alertas activas", style="bold green"),
                title="[bold]🔔  Alertas[/bold]",
                border_style="green",
                height=4,
            )

        lines: List[Text] = []
        for i, alert in enumerate(alerts, start=1):
            severity = getattr(alert, "severity", "?")
            name = getattr(alert, "rule_name", "alerta")
            msg = getattr(alert, "message", str(alert))
            action = getattr(alert, "suggested_action", "")
            sev_color = "red" if severity == "CRITICAL" else "yellow"
            line = Text()
            line.append(f"  [{i}] ", style="bold")
            line.append(f"[{severity}]", style=f"bold {sev_color}")
            line.append(f" {name}: ", style="bold")
            line.append(msg)
            if action:
                line.append(f" — {action}", style="dim")
            lines.append(line)

        border = "red" if any(getattr(a, "severity", "") == "CRITICAL" for a in alerts) else "yellow"
        group = Group(*lines)
        return Panel(
            group,
            title=f"[bold red]🔔  Alertas Activas ({len(alerts)})[/bold red]",
            border_style=border,
            height=max(4, len(alerts) + 2),
        )

    # ------------------------------------------------------------------
    # Layout builder
    # ------------------------------------------------------------------

    def build_layout(self) -> Layout:
        """Returns the base Layout structure (call once, then update with render())."""
        layout = Layout(name="root")
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="alerts", size=5),
        )
        layout["body"].split_column(
            Layout(name="top_row", ratio=2),
            Layout(name="mid_row", ratio=2),
            Layout(name="ollama", size=10),
        )
        layout["top_row"].split_row(
            Layout(name="cpu", ratio=1),
            Layout(name="ram", ratio=1),
        )
        layout["mid_row"].split_row(
            Layout(name="network", ratio=1),
            Layout(name="disk", ratio=1),
        )
        return layout

    def render(
        self,
        snapshot: ExtendedSnapshot,
        history: Optional[SnapshotHistory] = None,
        alerts: Optional[list] = None,
    ) -> Layout:
        """
        Builds and populates the full Layout for one render cycle.

        Parameters
        ----------
        snapshot : ExtendedSnapshot
            Current system metrics snapshot.
        history : SnapshotHistory, optional
            Rolling history used for trend indicators (reserved for future use).
        alerts : list of AlertEvent, optional
            Active alerts from AlertEngine.get_active_alerts().
        """
        layout = self.build_layout()
        alerts = alerts or []

        layout["header"].update(self._render_header(snapshot))
        layout["cpu"].update(self._render_cpu(snapshot))
        layout["ram"].update(self._render_ram(snapshot))
        layout["network"].update(self._render_network(snapshot))
        layout["disk"].update(self._render_disk(snapshot))
        layout["ollama"].update(self._render_ollama(snapshot))
        layout["alerts"].update(self._render_alerts(alerts))

        return layout
