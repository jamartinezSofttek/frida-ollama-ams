"""
demo_simulada.py — FRIDA Orchestration Framework
Simulación visual completa de una sesión de orquestación multi-agente.
NO requiere Ollama corriendo. Todas las respuestas son pre-escritas y realistas.

Ejecutar:
    cd ollama-ams-guide/orchestration
    py demo_simulada.py
"""

import json
import time
import uuid
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich import box

console = Console()

# ─────────────────────────────────────────────────────────────────────────────
# TAREA DEL USUARIO (caso real P1 NullPointerException en PaymentService)
# ─────────────────────────────────────────────────────────────────────────────

USER_TASK = (
    "Tenemos un incidente P1 crítico en producción. "
    "El servicio de pagos está caído con el siguiente error:\n\n"
    "java.lang.NullPointerException\n"
    "    at com.empresa.PaymentService.processPayment(PaymentService.java:142)\n"
    "    at com.empresa.PaymentController.handleRequest(PaymentController.java:87)\n"
    "    at sun.reflect.NativeMethodAccessorImpl.invoke0(Native Method)\n\n"
    "Impacto: 500 transacciones por minuto fallando. "
    "Clientes reportando errores en checkout. "
    "Revisa el código, clasifica la severidad y genera el RCA."
)

SESSION_ID = str(uuid.uuid4())
TASK_START = datetime.now()

# ─────────────────────────────────────────────────────────────────────────────
# PAYLOADS JSON REALES que se envían a la API de Ollama
# ─────────────────────────────────────────────────────────────────────────────

PAYLOADS = {
    "architect": {
        "model": "mistral:7b",
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 1024},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres el Architect Agent del framework FRIDA AMS L3. "
                    "Descompón la tarea en máximo 4 subtareas especializadas. "
                    "Responde ÚNICAMENTE con JSON válido con este esquema:\n"
                    '{"subtasks": [{"type": "TRIAGE|CODE|ANALYSIS|DOCS", "task": "..."}]}'
                )
            },
            {
                "role": "user",
                "content": f"Tarea: {USER_TASK}"
            }
        ]
    },
    "triage": {
        "model": "phi3:mini",
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 512},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres el TRIAGE Engineer del framework FRIDA AMS L3. "
                    "Tu especialidad es clasificar la severidad de incidentes, "
                    "priorizar acciones y escalar correctamente. "
                    "Responde con estructura clara usando Markdown. "
                    "Sé conciso y directo. Máximo 400 palabras."
                )
            },
            {
                "role": "user",
                "content": (
                    "Clasifica este incidente y determina severidad, impacto y próximos pasos:\n\n"
                    "java.lang.NullPointerException at PaymentService.processPayment:142\n"
                    "500 transacciones/minuto fallando. Clientes sin poder pagar."
                )
            }
        ]
    },
    "code": {
        "model": "qwen2.5-coder:7b",
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 1024},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres el CODE Engineer del framework FRIDA AMS L3. "
                    "Tu especialidad es code review, debugging y análisis de stack traces. "
                    "Identifica la causa técnica exacta y proporciona el fix. "
                    "Usa bloques de código con syntax highlighting."
                )
            },
            {
                "role": "user",
                "content": (
                    "Analiza este stack trace Java y encuentra la causa raíz técnica:\n\n"
                    "java.lang.NullPointerException\n"
                    "    at com.empresa.PaymentService.processPayment(PaymentService.java:142)\n"
                    "    at com.empresa.PaymentController.handleRequest(PaymentController.java:87)\n\n"
                    "Línea 142 de PaymentService.java probablemente hace referencia a un objeto "
                    "no inicializado. Proporciona el análisis y el hotfix."
                )
            }
        ]
    },
    "analysis": {
        "model": "mistral:7b",
        "stream": False,
        "options": {"temperature": 0.4, "num_predict": 2048},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres el ANALYSIS Engineer del framework FRIDA AMS L3. "
                    "Tu especialidad es análisis de causa raíz, hipótesis sistémicas "
                    "y recomendaciones de largo plazo. "
                    "Estructura tu respuesta con hipótesis, evidencia y diagnóstico."
                )
            },
            {
                "role": "user",
                "content": (
                    "Realiza un análisis de causa raíz del incidente:\n\n"
                    "NullPointerException en PaymentService.processPayment:142\n"
                    "Afecta 500 tx/min. Servicio de pagos caído.\n\n"
                    "¿Cuál es la causa sistémica? ¿Cómo prevenir recurrencia?"
                )
            }
        ]
    },
    "docs": {
        "model": "mistral:7b",
        "stream": False,
        "options": {"temperature": 0.5, "num_predict": 1024},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Eres el DOCS Engineer del framework FRIDA AMS L3. "
                    "Tu especialidad es generar RCA ejecutivos, runbooks y comunicados. "
                    "Escribe en formato profesional listo para enviar a stakeholders."
                )
            },
            {
                "role": "user",
                "content": (
                    "Genera el RCA ejecutivo del siguiente incidente:\n\n"
                    "Servicio: PaymentService — Severidad: P1\n"
                    "Causa: NullPointerException en processPayment:142\n"
                    "Duración: ~8 minutos\n"
                    "Impacto: ~4.000 transacciones fallidas\n"
                    "Resolución: Deploy del hotfix v2.3.1"
                )
            }
        ]
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# RESPUESTAS SIMULADAS REALISTAS
# ─────────────────────────────────────────────────────────────────────────────

RESPONSES = {
    "architect": {
        "subtasks": [
            {"type": "TRIAGE",   "task": "Clasificar la severidad del incidente NullPointerException en PaymentService y determinar prioridad de respuesta."},
            {"type": "CODE",     "task": "Analizar el stack trace e identificar la causa técnica exacta en PaymentService.java:142, proporcionar hotfix."},
            {"type": "ANALYSIS", "task": "Realizar análisis de causa raíz sistémico y determinar cómo prevenir recurrencia del NPE en producción."},
            {"type": "DOCS",     "task": "Generar el RCA ejecutivo del incidente P1 del servicio de pagos para comunicar a stakeholders."},
        ]
    },
    "triage": """\
## 🚨 Clasificación de Incidente — TRIAGE

**Severidad:** P1 — CRÍTICO
**Estado:** ACTIVO — Requiere acción inmediata

---

### Clasificación

| Campo | Valor |
|-------|-------|
| **Tipo** | NullPointerException (NPE) en capa de negocio |
| **Servicio afectado** | PaymentService (core de pagos) |
| **Impacto** | 500 transacciones/minuto fallando |
| **Usuarios afectados** | Todos los clientes en proceso de checkout |
| **Severidad** | **P1 — Sistema crítico de negocio inoperativo** |

---

### Próximos pasos inmediatos

1. **[0-2 min]** Alertar al equipo de on-call y tech lead de PaymentService
2. **[2-5 min]** Activar runbook de incidente P1 en el canal #incidents
3. **[5-10 min]** Evaluar rollback a versión anterior mientras se investiga
4. **[10-15 min]** Comunicado a soporte para informar a clientes afectados

### Escalación recomendada

- **Equipo:** Backend + SRE
- **Stakeholders:** CTO, Product Manager de Pagos
- **SLA:** Resolución esperada en < 30 minutos
""",
    "code": """\
## 🔍 Análisis Técnico del Stack Trace

### Causa Raíz Técnica

La línea `PaymentService.java:142` indica que se está accediendo a un campo o
llamando a un método sobre un objeto que es `null` en tiempo de ejecución.

**Hipótesis principal:** El objeto `paymentMethod` o `customerAccount` no fue
inicializado antes de la llamada en `processPayment()`.

---

### Análisis del Stack Trace

```
java.lang.NullPointerException
    at com.empresa.PaymentService.processPayment(PaymentService.java:142)  ← ORIGEN
    at com.empresa.PaymentController.handleRequest(PaymentController.java:87)
```

La cadena de llamadas indica: `handleRequest` → `processPayment` → NPE.
El controlador no valida el objeto antes de pasarlo al servicio.

---

### Código defectuoso probable (línea ~142)

```java
// ❌ ANTES (problemático)
public PaymentResult processPayment(PaymentRequest request) {
    // línea 142: request.getPaymentMethod() puede ser null
    String methodCode = request.getPaymentMethod().getCode();  // NPE aquí
    return gateway.process(methodCode, request.getAmount());
}
```

### Hotfix recomendado

```java
// ✅ DESPUÉS (con validación)
public PaymentResult processPayment(PaymentRequest request) {
    if (request == null || request.getPaymentMethod() == null) {
        throw new IllegalArgumentException(
            "PaymentRequest o PaymentMethod no pueden ser null"
        );
    }
    String methodCode = request.getPaymentMethod().getCode();
    return gateway.process(methodCode, request.getAmount());
}
```

### También en el Controller (PaymentController.java:87)

```java
// ✅ Validar antes de llamar al servicio
if (paymentRequest == null || paymentRequest.getPaymentMethod() == null) {
    return ResponseEntity.badRequest()
        .body("PaymentMethod es requerido");
}
```

**Prioridad del fix:** Crítica — Deploy inmediato en rama `hotfix/pay-503-npe`
""",
    "analysis": """\
## 🔬 Análisis de Causa Raíz — PaymentService NPE

### Hipótesis Principal

**H1 (Confianza: ALTA):** Un cambio reciente en el cliente o en la API introdujo
un campo `paymentMethod` que puede llegar como `null` cuando el usuario abandona
el checkout en un estado intermedio. El servicio no tenía validación defensiva.

---

### Evidencia

- La NPE ocurre consistentemente en `processPayment:142`, no es aleatoria
- El patrón sugiere una condición de entrada específica (paymentMethod null)
- Impacto masivo (500 tx/min) indica que afecta el flujo principal, no un edge case
- PaymentController.java:87 no valida el payload antes de delegarlo al servicio

---

### Línea de tiempo probable

```
~T-7 días: Deploy de nueva versión del frontend con campo paymentMethod opcional
~T-0:     Ciertos usuarios completan checkout sin seleccionar método de pago
~T+0:     PaymentService recibe paymentMethod=null → NPE → 500 transacciones caen
```

---

### Diagnóstico Sistémico

El fallo revela **tres problemas de diseño**:

1. **Falta de validación en capa de servicio** — Los servicios deben ser robustos ante inputs inválidos
2. **Falta de contrato explícito API** — El campo no está marcado como `@NotNull` en el DTO
3. **Ausencia de tests de integración** para payloads con campos opcionales nulos

---

### Recomendaciones de Largo Plazo

1. **Inmediato:** Agregar `@NotNull @Valid` en `PaymentRequest.paymentMethod`
2. **Esta semana:** Implementar Bean Validation en toda la capa de servicio
3. **Este sprint:** Añadir tests parametrizados con payloads inválidos
4. **Este mes:** Revisar todos los DTOs de la capa de pagos con el mismo patrón
""",
    "docs": """\
## 📋 RCA Ejecutivo — Incidente P1 PaymentService

**Fecha:** 2026-04-21 | **Duración:** ~8 minutos | **Severidad:** P1

---

### Resumen Ejecutivo

El servicio de pagos estuvo inoperativo durante aproximadamente 8 minutos
debido a un error `NullPointerException` en la clase `PaymentService`.
Se estima un impacto de ~4.000 transacciones fallidas.

---

### Causa Raíz

Un campo `paymentMethod` sin validación en la capa de servicio provocó
un error crítico cuando llegaron solicitudes con ese campo vacío.
La ausencia de controles defensivos en `PaymentService.processPayment`
permitió que el error escalara al 100% del tráfico de pagos.

---

### Cronología

| Hora | Evento |
|------|--------|
| 14:22:01 | Primeras alertas de error en PaymentService |
| 14:22:15 | PagerDuty notifica al equipo on-call |
| 14:24:00 | Confirmación de incidente P1, apertura de war room |
| 14:27:30 | Identificación de la causa raíz (NPE en línea 142) |
| 14:29:45 | Deploy del hotfix v2.3.1 en producción |
| 14:30:12 | Servicio restaurado — tasa de error vuelve a 0% |

---

### Acciones Correctivas

- [x] **Inmediato:** Deploy hotfix v2.3.1 con validación de `paymentMethod`
- [ ] **Esta semana:** Agregar `@NotNull` en todos los DTOs de pagos
- [ ] **Este sprint:** Suite de tests para payloads con campos nulos
- [ ] **Este mes:** Revisión de contratos API en capa de servicios críticos

---

*Generado por FRIDA AMS L3 — Incident Management Framework*
"""
}

# ─────────────────────────────────────────────────────────────────────────────
# SCORES DEL RESPONSE EVALUATOR
# ─────────────────────────────────────────────────────────────────────────────

EVALUATIONS = {
    "TRIAGE": {
        "overall_score": 0.82,
        "criteria": {
            "completeness": 0.85, "structure": 0.90,
            "coherence": 0.80, "length": 0.85,
            "confidence": 1.00, "response_time": 0.90,
            "domain_markers": 0.95
        },
        "decision": "is_acceptable",
        "duration": 4.3
    },
    "CODE": {
        "overall_score": 0.88,
        "criteria": {
            "completeness": 0.90, "structure": 0.95,
            "coherence": 0.85, "length": 0.90,
            "confidence": 1.00, "response_time": 0.80,
            "domain_markers": 0.92
        },
        "decision": "is_acceptable",
        "duration": 9.1
    },
    "ANALYSIS": {
        "overall_score": 0.85,
        "criteria": {
            "completeness": 0.88, "structure": 0.85,
            "coherence": 0.90, "length": 0.88,
            "confidence": 0.60, "response_time": 0.85,
            "domain_markers": 0.90
        },
        "decision": "is_acceptable",
        "duration": 18.7
    },
    "DOCS": {
        "overall_score": 0.79,
        "criteria": {
            "completeness": 0.80, "structure": 0.88,
            "coherence": 0.78, "length": 0.80,
            "confidence": 0.60, "response_time": 0.88,
            "domain_markers": 0.85
        },
        "decision": "is_acceptable",
        "duration": 12.4
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DE DISPLAY
# ─────────────────────────────────────────────────────────────────────────────

def pause(seconds: float):
    time.sleep(seconds)

def show_json_payload(title: str, payload: dict, border_color: str = "cyan"):
    json_str = json.dumps(payload, indent=2, ensure_ascii=False)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False, word_wrap=True)
    console.print(Panel(syntax, title=f"[bold {border_color}]{title}[/]",
                        border_style=border_color, expand=False))

def show_response(title: str, text: str, border_color: str = "green"):
    console.print(Panel(text.strip(), title=f"[bold {border_color}]{title}[/]",
                        border_style=border_color, padding=(1, 2)))

def show_eval_scores(engineer_type: str, ev: dict):
    score = ev["overall_score"]
    color = "green" if score >= 0.65 else "yellow" if score >= 0.40 else "red"
    decision_icon = {"is_acceptable": "✅", "needs_human_review": "⚠️", "needs_escalation": "🚨"}

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold magenta")
    table.add_column("Criterio", style="cyan", no_wrap=True)
    table.add_column("Score", justify="right")
    table.add_column("Bar", min_width=20)

    for crit, val in ev["criteria"].items():
        bar_len = int(val * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        crit_color = "green" if val >= 0.65 else "yellow" if val >= 0.40 else "red"
        table.add_row(crit, f"[{crit_color}]{val:.2f}[/]", f"[{crit_color}]{bar}[/]")

    console.print(Panel(
        table,
        title=f"[bold {color}]ResponseEvaluator — {engineer_type} · Score: {score:.2f} "
              f"{decision_icon.get(ev['decision'], '')} {ev['decision'].upper()}[/]",
        border_style=color
    ))

# ─────────────────────────────────────────────────────────────────────────────
# DEMO PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def run_demo():
    console.clear()

    # ── HEADER ──────────────────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        "[bold white]FRIDA Orchestration Framework[/]\n"
        "[dim]AMS L3 — Multi-Agent Orchestration with Local Ollama Models[/]\n\n"
        "[yellow]⚡ DEMO SIMULADA[/] — Sin Ollama requerido · Respuestas pre-escritas realistas\n"
        f"[dim]Session: {SESSION_ID}[/]",
        border_style="bright_blue",
        expand=True
    ))
    pause(1.0)

    # ── TAREA DEL USUARIO ───────────────────────────────────────────────────
    console.print(Rule("[bold yellow]📨  TAREA RECIBIDA DEL USUARIO[/]"))
    console.print()
    console.print(Panel(
        USER_TASK,
        title="[bold yellow]Usuario → Orchestrator[/]",
        border_style="yellow",
        padding=(1, 2)
    ))
    pause(1.5)

    # ── FASE 1: ARCHITECT AGENT ─────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold magenta]🏗️  FASE 1 — ARCHITECT AGENT (mistral:7b)[/]"))
    console.print()
    console.print("[dim]El Orchestrator briefea al Architect Agent para descomponer la tarea...[/]")
    pause(0.8)

    show_json_payload(
        "📤 POST http://localhost:11434/api/chat  →  mistral:7b (Architect)",
        PAYLOADS["architect"],
        border_color="magenta"
    )
    pause(0.5)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold magenta]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Architect analizando tarea y generando plan...", total=None)
        time.sleep(3.2)

    console.print("[bold magenta]✓[/] Architect Agent respondió en [bold]3.2s[/]")
    pause(0.3)

    arch_json = json.dumps(RESPONSES["architect"], indent=2, ensure_ascii=False)
    arch_syntax = Syntax(arch_json, "json", theme="monokai", word_wrap=True)
    console.print(Panel(
        arch_syntax,
        title="[bold magenta]📥 Respuesta Architect Agent — Descomposición en 4 Subtareas[/]",
        border_style="magenta"
    ))
    pause(1.5)

    subtasks = RESPONSES["architect"]["subtasks"]
    table = Table(title="Plan de Ejecución", box=box.ROUNDED, border_style="bright_blue")
    table.add_column("#", style="dim", width=3)
    table.add_column("Tipo de Engineer", style="bold cyan")
    table.add_column("Modelo", style="yellow")
    table.add_column("Subtarea", style="white")

    model_map = {"TRIAGE": "phi3:mini", "CODE": "qwen2.5-coder:7b",
                 "ANALYSIS": "mistral:7b", "DOCS": "mistral:7b"}
    for i, st in enumerate(subtasks, 1):
        table.add_row(str(i), st["type"], model_map[st["type"]], st["task"][:70] + "...")

    console.print(table)
    pause(1.5)

    # ── FASE 2: ENGINEER AGENTS ─────────────────────────────────────────────
    engineers = [
        ("TRIAGE",   "phi3:mini",          "triage",   "🔴", "red"),
        ("CODE",     "qwen2.5-coder:7b",   "code",     "🟡", "yellow"),
        ("ANALYSIS", "mistral:7b",         "analysis", "🔵", "blue"),
        ("DOCS",     "mistral:7b",         "docs",     "🟢", "green"),
    ]

    console.print()
    console.print(Rule("[bold cyan]⚙️  FASE 2 — ENGINEER AGENTS EN EJECUCIÓN[/]"))

    for eng_type, model, key, icon, color in engineers:
        console.print()
        console.print(Rule(
            f"[bold {color}]{icon} Engineer: {eng_type}  ·  Modelo: {model}[/]",
            style=color
        ))
        pause(0.6)

        console.print(f"[dim]Orchestrator enviando brief a {eng_type} Engineer ({model})...[/]")
        pause(0.4)

        show_json_payload(
            f"📤 POST http://localhost:11434/api/chat  →  {model} ({eng_type} Engineer)",
            PAYLOADS[key],
            border_color=color
        )
        pause(0.4)

        duration = EVALUATIONS[eng_type]["duration"]
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[bold {color}]{{task.description}}"),
            BarColumn(bar_width=30),
            TimeElapsedColumn(),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task(
                f"{model} procesando · {eng_type} Engineer razonando...",
                total=100
            )
            steps = 20
            for _ in range(steps):
                time.sleep(duration / steps)
                progress.advance(task, 100 / steps)

        console.print(f"[bold {color}]✓[/] {eng_type} Engineer respondió en [bold]{duration}s[/]")
        pause(0.3)

        show_response(
            f"📥 Respuesta {eng_type} Engineer ({model})",
            RESPONSES[key],
            border_color=color
        )
        pause(0.5)

        console.print(f"[dim]ResponseEvaluator evaluando calidad de respuesta {eng_type}...[/]")
        pause(0.6)
        show_eval_scores(eng_type, EVALUATIONS[eng_type])
        pause(0.8)

    # ── FASE 3: SUMMARY FINAL ───────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold bright_white]📊  RESUMEN FINAL DE ORQUESTACIÓN[/]"))
    console.print()

    total_duration = sum(v["duration"] for v in EVALUATIONS.values()) + 3.2
    avg_score = sum(v["overall_score"] for v in EVALUATIONS.values()) / len(EVALUATIONS)

    summary_table = Table(box=box.ROUNDED, border_style="bright_white", show_header=True,
                          header_style="bold white")
    summary_table.add_column("Fase", style="bold cyan", no_wrap=True)
    summary_table.add_column("Modelo", style="yellow")
    summary_table.add_column("Score", justify="center")
    summary_table.add_column("Decisión", justify="center")
    summary_table.add_column("Tiempo", justify="right", style="dim")

    decision_icons = {"is_acceptable": "✅ ACCEPTABLE", "needs_human_review": "⚠️ REVIEW",
                      "needs_escalation": "🚨 ESCALATE"}

    summary_table.add_row(
        "🏗️  Architect", "mistral:7b", "—", "📋 4 subtareas", "3.2s"
    )
    for eng_type, model, _, _, _ in engineers:
        ev = EVALUATIONS[eng_type]
        score_color = "green" if ev["overall_score"] >= 0.65 else "yellow"
        summary_table.add_row(
            f"⚙️  {eng_type}",
            model,
            f"[{score_color}]{ev['overall_score']:.2f}[/]",
            decision_icons.get(ev["decision"], ev["decision"]),
            f"{ev['duration']}s"
        )

    console.print(summary_table)
    pause(0.8)

    final_summary = (
        "## Resumen del Incidente P1 — PaymentService NPE\n\n"
        "**Triage:** Severidad P1 confirmada. 500 tx/min afectadas. "
        "Escalación a equipo on-call y tech lead activada.\n\n"
        "**Code Review:** NPE en `PaymentService.java:142` por `paymentMethod=null`. "
        "Hotfix identificado: agregar validación defensiva antes del acceso.\n\n"
        "**Análisis:** Causa sistémica — falta de contrato `@NotNull` en DTO y "
        "ausencia de validación en capa de servicio. "
        "Deploy reciente del frontend introdujo campo opcional sin retro-compatibilidad.\n\n"
        "**RCA:** Documento ejecutivo generado, listo para stakeholders. "
        "Acciones correctivas inmediatas y de largo plazo definidas."
    )

    console.print(Panel(
        final_summary,
        title="[bold bright_white]📝 Summary del Orchestrator[/]",
        border_style="bright_white",
        padding=(1, 2)
    ))
    pause(0.5)

    # Métricas finales
    metrics_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    metrics_table.add_column("Key", style="dim")
    metrics_table.add_column("Value", style="bold")

    metrics_table.add_row("Session ID", SESSION_ID)
    metrics_table.add_row("Tarea recibida", TASK_START.strftime("%Y-%m-%d %H:%M:%S"))
    metrics_table.add_row("Subtareas ejecutadas", "4")
    metrics_table.add_row("Modelos usados", "phi3:mini, qwen2.5-coder:7b, mistral:7b")
    metrics_table.add_row("Duración total", f"{total_duration:.1f}s")
    metrics_table.add_row("Score promedio", f"{avg_score:.2f}")
    metrics_table.add_row("Decisión global", "✅ ALL ACCEPTABLE")
    metrics_table.add_row("Tokens estimados", "~3.800 tokens")
    metrics_table.add_row("Sesión guardada en", f"sessions/{SESSION_ID[:8]}.json")

    console.print(Panel(
        metrics_table,
        title="[bold bright_cyan]📈 Métricas de Sesión[/]",
        border_style="bright_cyan"
    ))
    pause(0.5)

    console.print()
    console.print(Panel(
        "[bold green]✅  Demo completada exitosamente.[/]\n\n"
        "[white]Para ejecutar con Ollama real:[/]\n"
        "[dim]  cd ollama-ams-guide/orchestration[/]\n"
        "[cyan]  py cli/main.py[/]\n\n"
        "[white]Para tests sin Ollama:[/]\n"
        "[dim]  cd ollama-ams-guide/orchestration[/]\n"
        "[cyan]  py -m pytest tests/test_pipeline.py -v[/]",
        border_style="green",
        padding=(1, 2)
    ))
    console.print()


if __name__ == "__main__":
    run_demo()
