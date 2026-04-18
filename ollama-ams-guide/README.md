# 🧠 FRIDA Orchestration Framework — Ollama AMS L3

> **FRIDA** actúa como **arquitecta orquestadora**: analiza el hardware disponible, decide qué modelos de IA descargar y cómo asignar tareas a agentes especializados, minimizando el gasto de tokens y maximizando el rendimiento local.

---

## 📋 Tabla de Contenidos

1. [Rol de FRIDA como Orquestadora](#1-rol-de-frida-como-orquestadora)
2. [Sistema de Referencia](#2-sistema-de-referencia)
3. [Arquitectura Técnica](#3-arquitectura-técnica)
4. [Roles de Agentes](#4-roles-de-agentes)
5. [Modelos Instalados y Selección](#5-modelos-instalados-y-selección)
6. [Estructura del Repositorio](#6-estructura-del-repositorio)
7. [Inicio Rápido](#7-inicio-rápido)
8. [Instalación y Dependencias](#8-instalación-y-dependencias)
9. [CLI — Referencia Completa](#9-cli--referencia-completa)
10. [Tarea #1 para Ingenieros: Monitor de Métricas en Tiempo Real](#10-tarea-1-para-ingenieros-monitor-de-métricas-en-tiempo-real)
11. [Escenarios de Uso AMS L3](#11-escenarios-de-uso-ams-l3)
12. [Estrategia de Tokens FRIDA](#12-estrategia-de-tokens-frida)
13. [Flujo de Trabajo Iterativo y Registro de Decisiones (ADR)](#13-flujo-de-trabajo-iterativo-y-registro-de-decisiones-adr)
14. [Publicar en GitHub](#14-publicar-en-github)
15. [Comandos de Referencia Rápida](#15-comandos-de-referencia-rápida)

---

## 1. Rol de FRIDA como Orquestadora

FRIDA no es solo un asistente de IA — es la **arquitecta del sistema**. Su responsabilidad es:

### 🔍 Inspección de Hardware Antes de Actuar

Antes de descargar o ejecutar cualquier modelo, FRIDA evalúa el entorno:

```
┌─────────────────────────────────────────────────────────────┐
│  FRIDA Hardware Assessment (al inicio de cada sesión)       │
├─────────────────────────────────────────────────────────────┤
│  1. CPU cores disponibles   → decide paralelismo            │
│  2. RAM libre               → filtra modelos viables        │
│  3. VRAM GPU                → determina modo CPU vs GPU     │
│  4. Espacio en disco        → valida si hay espacio pull    │
│  5. Modelos ya descargados  → evita re-descargas            │
└─────────────────────────────────────────────────────────────┘
```

### 🎯 Toma de Decisiones sobre Modelos

FRIDA sigue esta lógica para decidir qué modelo usar:

```
RAM libre < 2.5 GB  →  ❌ Ejecutar cleanup_for_ollama.ps1 primero
RAM libre 2.5–4.5 GB  →  ✅ phi3:mini  (ligero)
RAM libre 4.5–6.5 GB  →  ✅ mistral:7b o qwen2.5-coder:7b  (eficiente)
RAM libre > 6.5 GB    →  ✅ modelos grandes o múltiples agentes  (potente)
```

### 💰 Ahorro de Tokens de FRIDA

FRIDA usa modelos locales como **filtro previo** antes de consultar a FRIDA (la IA cloud):

```
Tarea compleja → Ollama procesa localmente → FRIDA recibe solo el resumen
                                                    ↑
                              Ahorro: 80–92% de tokens por consulta
```

**Regla de Oro:** Ollama primero → FRIDA solo para decisiones críticas o conocimiento especializado que los modelos locales no pueden resolver.

---

## 2. Sistema de Referencia

| Componente | Especificación |
|---|---|
| OS | Windows 11 Enterprise (Build 26200) |
| CPU | AMD Ryzen 5 7530U — 6 núcleos / 12 hilos |
| RAM | 15.7 GB total (~2.5–6 GB libres post-cleanup) |
| GPU | AMD Radeon iGPU (512 MB VRAM — inferencia CPU-only) |
| Ollama | v0.21.0 |
| Presupuesto FRIDA | 130,000 tokens/día |

---

## 3. Arquitectura Técnica

### Diagrama de Flujo de Orquestación

```
┌──────────────────────────────────────────────────────────────────────┐
│                        USUARIO (AMS L3)                              │
│              "Analiza este stack trace de Java"                       │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    CLI (cli/main.py)                                  │
│   Parsea comando → carga config.yaml → invoca Orchestrator           │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (orchestrator.py)                      │
│                                                                      │
│   1. Carga contexto de sesión (session_store.py)                     │
│   2. Evalúa RAM disponible                                           │
│   3. Llama al Architect Agent (si RAM > 3 GB)                        │
│      o usa keyword routing (si RAM < 3 GB)                           │
└────────────┬─────────────────────────────────────┬───────────────────┘
             │                                     │
             ▼                                     ▼
┌────────────────────────┐           ┌─────────────────────────────────┐
│  ARCHITECT AGENT       │           │  KEYWORD ROUTER (router.py)     │
│  (architect.py)        │           │  Fallback sin LLM               │
│                        │           │                                 │
│  Modelo: phi3:mini     │           │  Detecta: error/código/RCA/doc  │
│  Descompone la tarea   │           │  Asigna engineer tipo directo   │
│  en subtareas JSON     │           └────────────────┬────────────────┘
└────────────┬───────────┘                            │
             │                                        │
             └────────────────────┬───────────────────┘
                                  │
                                  ▼
              ┌───────────────────────────────────────┐
              │         ENGINEER AGENTS               │
              │         (engineer.py)                 │
              ├───────────────────────────────────────┤
              │  TRIAGE   → phi3:mini                 │
              │  CODE     → qwen2.5-coder:7b          │
              │  ANALYSIS → mistral:7b                │
              │  DOCS     → mistral:7b                │
              └───────────────────────────────────────┘
                                  │
                                  ▼
              ┌───────────────────────────────────────┐
              │      AGGREGATOR + SESSION STORE       │
              │  Consolida resultados → guarda turno  │
              ���  �� exporta a Markdown si se solicita  │
              └───────────────────────────────────────┘
                                  │
                                  ▼
              ┌───────────────────────────────────────┐
              │           USUARIO                     │
              │  Resultado consolidado + confianza    │
              └───────────────────────────────────────┘
```

### Protocolo de Comunicación Architect → Engineer

```json
{
  "subtask_id": "uuid",
  "engineer_type": "TRIAGE | CODE | ANALYSIS | DOCS",
  "model": "phi3:mini",
  "system_prompt": "Eres un experto en...",
  "user_prompt": "Analiza el siguiente...",
  "context": "Historial relevante de sesión...",
  "max_tokens": 500,
  "temperature": 0.1,
  "num_ctx": 2048
}
```

---

## 4. Roles de Agentes

| Agente | Archivo | Modelo | Responsabilidad |
|---|---|---|---|
| **Architect** | `agents/architect.py` | `phi3:mini` | Descompone tareas complejas en subtareas JSON asignables a engineers |
| **TRIAGE Engineer** | `agents/engineer.py` | `phi3:mini` | Clasificación de incidentes, triaje P1/P2, respuestas rápidas |
| **CODE Engineer** | `agents/engineer.py` | `qwen2.5-coder:7b` | Code review, debugging, análisis de stack traces, scripts |
| **ANALYSIS Engineer** | `agents/engineer.py` | `mistral:7b` | RCA profundo, análisis de logs, diagnóstico de performance |
| **DOCS Engineer** | `agents/engineer.py` | `mistral:7b` | Generación de RCAs, runbooks, change requests, documentación |

### Routing Automático por Palabras Clave

El `router.py` detecta el tipo de tarea automáticamente:

| Keywords detectadas | Engineer asignado |
|---|---|
| `error`, `excepción`, `stack trace`, `falla`, `crítico`, `P1`, `alerta` | `TRIAGE` |
| `código`, `script`, `python`, `java`, `bug`, `función`, `refactor`, `fix` | `CODE` |
| `causa raíz`, `análisis`, `rendimiento`, `diagnóstico`, `log`, `latencia` | `ANALYSIS` |
| `documenta`, `RCA`, `runbook`, `procedimiento`, `reporte`, `postmortem` | `DOCS` |

---

## 5. Modelos Instalados y Selección

### Modelos Disponibles

| Modelo | Tamaño | RAM necesaria | Velocidad (CPU) | Uso principal |
|---|---|---|---|---|
| `phi3:mini` | 2.2 GB | ~2.5 GB | ⚡ Rápido (5–10s) | Triaje, Q&A rápido, clasificación, Architect |
| `qwen2.5-coder:7b` | 4.7 GB | ~5.2 GB | 🔄 Medio (15–25s) | Code review, debugging, scripts |
| `mistral:7b` | 4.4 GB | ~5.0 GB | 🔄 Medio (15–25s) | RCA, documentación, análisis profundo |

### Selección según RAM Disponible

| RAM Libre | Modelo recomendado | Escenario |
|---|---|---|
| < 2.5 GB | ❌ Ejecutar cleanup primero | — |
| 2.5 – 4.5 GB | `phi3:mini` | Ligero |
| 4.5 – 6.5 GB | `mistral:7b` o `qwen2.5-coder:7b` | Eficiente |
| 6.5 – 9.0 GB | `mistral:7b` (Q8) | Potente |
| > 9.0 GB | Múltiples modelos simultáneos | Al límite |

### Agregar un Nuevo Modelo

```powershell
# 1. Verificar RAM disponible
.\\scripts\\check_system_for_ollama.ps1

# 2. Descargar el modelo
ollama pull llama3:8b

# 3. Asignar en config.yaml
#    agents > engineers > CODE > model: "llama3:8b"

# 4. Reiniciar el CLI
```

---

## 6. Estructura del Repositorio

```
ollama-ams-guide/
│
├── README.md                                  ← Este archivo (arquitectura + guía completa)
│
├── guides/                                    ← Guías detalladas en Markdown
│   ├── 01_process_cleanup_windows.md          ← Limpieza de procesos Windows paso a paso
│   ├── 02_model_feasibility_matrix.md         ← Qué modelos usar según tu RAM disponible
│   ├── 03_ams_l3_optimization_scenarios.md    ← 7 escenarios de uso AMS L3 avanzados
│   └── 04_tools_and_token_strategies.md       ← Herramientas y ahorro de tokens FRIDA
│
├── scripts/                                   ← PowerShell automation scripts
│   ├── cleanup_for_ollama.ps1                 ← Libera RAM antes de iniciar Ollama
│   ├── check_system_for_ollama.ps1            ← Diagnóstico del sistema (CPU/RAM/disco)
│   └── restore_services.ps1                  ← Restaura servicios al estado normal
│
├── prompts/                                   ← Plantillas de prompts reutilizables
│   ├── triage_incidente.txt                   ← Triaje y clasificación de incidentes
│   ├── condensar_logs.txt                     ← Comprimir logs para ahorrar tokens FRIDA
│   └── generar_rca.txt                        ← Generar borrador de RCA ejecutivo
│
└── orchestration/                             ← Framework Architect-Engineer (Python)
    │
    ├── architecture.md                        ← Diseño del sistema multi-agente (detallado)
    ├── config.yaml                            ← Configuración central (modelos, routing, memoria)
    ├── orchestrator.py                        ← Motor principal de orquestación
    ├── router.py                              ← Enrutamiento por palabras clave (fallback)
    ├── requirements.txt                       ← Dependencias Python
    │
    ├── agents/                                ← Agentes de IA
    │   ├── __init__.py
    │   ├── architect.py                       ← Agente descompositor de tareas (LLM)
    │   └── engineer.py                        ← Agente ejecutor especializado por tipo
    │
    ├── memory/                                ← Gestión de sesiones y contexto
    │   ├── __init__.py
    │   └── session_store.py                   ← Almacenamiento JSON de historial de sesiones
    │
    ├── monitors/                              ← [NUEVA] Módulos de monitoreo del sistema
    │   └── metrics_monitor.py                 ← Monitor de métricas CPU/RAM/Ollama (Tarea #1)
    │
    ├── cli/                                   ← Interfaz de línea de comandos
    │   ├── __init__.py
    │   └── main.py                            ← CLI con argparse + rich
    │
    └── tests/                                 ← Suite de pruebas
        └── test_pipeline.py                   ← Tests unitarios y end-to-end
```

---

## 7. Inicio Rápido

### Paso 1: Preparar el sistema

```powershell
# Diagnóstico completo del sistema
.\\scripts\\check_system_for_ollama.ps1

# Liberar RAM (limpieza estándar — cierra apps no esenciales)
.\\scripts\\cleanup_for_ollama.ps1

# Liberar RAM (limpieza agresiva — máximo rendimiento)
.\\scripts\\cleanup_for_ollama.ps1 -Aggressive
```

### Paso 2: Iniciar Ollama

```powershell
# ⚠️ Ejecutar en una terminal SEPARADA y dejar corriendo
ollama serve
```

### Paso 3: Usar el CLI del Framework

```powershell
cd ollama-ams-guide\\orchestration

# Consulta única
python cli/main.py query "Analiza este stack trace de Java y determina la causa raíz"

# Sesión interactiva (recomendado para turnos de trabajo)
python cli/main.py chat

# Leer tarea desde archivo de texto
python cli/main.py file ..\\prompts\\triage_incidente.txt

# Ver sesiones guardadas
python cli/main.py sessions

# Exportar sesión a Markdown
python cli/main.py export <session_id> --output resultado.md
```

### Paso 4: Uso Directo de Modelos (sin framework)

```powershell
ollama run phi3:mini           # Triaje rápido (~2.5 GB RAM)
ollama run mistral:7b          # Análisis profundo (~5.0 GB RAM)
ollama run qwen2.5-coder:7b   # Code review (~5.2 GB RAM)
```

### Paso 5: Al Terminar el Turno

```powershell
.\\scripts\\restore_services.ps1
```

---

## 8. Instalación y Dependencias

```powershell
cd ollama-ams-guide\\orchestration
pip install -r requirements.txt
```

| Paquete | Versión mínima | Uso |
|---|---|---|
| `requests` | >=2.31.0 | Comunicación HTTP con Ollama API |
| `PyYAML` | >=6.0 | Lectura de config.yaml |
| `rich` | >=13.0 | CLI con colores, tablas y panels |
| `psutil` | >=5.9.0 | Métricas de CPU y RAM (metrics_monitor) |

---

## 9. CLI — Referencia Completa

### Comandos disponibles

| Comando | Descripción | Ejemplo |
|---|---|---|
| `query` | Ejecuta una tarea única | `python cli/main.py query "analiza este error"` |
| `chat` | Sesión interactiva multi-turno | `python cli/main.py chat` |
| `file` | Ejecuta tarea desde archivo .txt | `python cli/main.py file tarea.txt` |
| `sessions` | Lista sesiones guardadas | `python cli/main.py sessions` |
| `export` | Exporta sesión a Markdown | `python cli/main.py export <id>` |
| `route` | Analiza enrutamiento sin ejecutar | `python cli/main.py route "analiza código"` |

### Opciones Globales

| Opción | Descripción |
|---|---|
| `--config PATH` | Ruta al config.yaml (default: auto-detectado) |
| `--verbose / -v` | Muestra detalles por subtarea en la salida |
| `--no-architect` | Salta el LLM de descomposición, usa keywords directamente |
| `--json` | Salida en formato JSON estructurado |

### Comandos Internos del Modo `chat`

| Comando | Acción |
|---|---|
| `/exit` o `/salir` | Termina la sesión (guardada automáticamente) |
| `/sesion` | Muestra el ID de la sesión actual |
| `/limpiar` | Limpia la pantalla |
| `/export [ruta]` | Exporta la sesión actual a Markdown |

### Memoria de Conversación

Las sesiones se guardan automáticamente en:

```
~/.ollama_ams/sessions/<session_id>.json
```

- **TTL automático:** 72 horas sin acceso → eliminación automática
- **Límite:** 50 sesiones simultáneas (configurable en `config.yaml`)
- **Contexto:** Los últimos 3 turnos se incluyen en cada nueva consulta

---

## 10. Tarea #1 para Ingenieros: Monitor de Métricas en Tiempo Real

### 🎯 Objetivo

Crear un módulo Python (`monitors/metrics_monitor.py`) que monitoree en tiempo real:

1. **CPU:** uso por núcleo y total
2. **RAM:** total, usada, disponible y porcentaje
3. **Actividad de modelos Ollama:** modelos cargados en RAM, tokens/seg, duración de inferencia, estado keep_alive

Este monitor permite al equipo AMS L3 saber **exactamente qué recursos consume cada modelo** antes y durante la ejecución, evitando sorpresas de memoria y permitiendo decisiones informadas sobre qué modelo usar.

### 📊 Métricas a Capturar

#### CPU (via `psutil`)

| Métrica | Descripción | Ejemplo |
|---|---|---|
| `cpu_percent_total` | Uso global de CPU % | `34.2` |
| `cpu_percent_per_core` | Uso % por núcleo lógico | `[45.1, 12.3, 67.8, ...]` |
| `cpu_freq_mhz` | Frecuencia actual en MHz | `2100` |
| `cpu_cores` | Núcleos físicos / lógicos | `6 / 12` |

#### RAM (via `psutil`)

| Métrica | Descripción | Ejemplo |
|---|---|---|
| `ram_total_gb` | RAM total del sistema | `15.7` |
| `ram_used_gb` | RAM actualmente en uso | `11.2` |
| `ram_available_gb` | RAM disponible ahora | `4.5` |
| `ram_percent` | Porcentaje de uso | `71.3` |

#### Actividad de Modelos Ollama (via `GET /api/ps`)

| Métrica | Descripción | Ejemplo |
|---|---|---|
| `model_name` | Nombre del modelo activo | `mistral:7b` |
| `model_size_gb` | Tamaño del modelo en RAM | `4.4` |
| `expires_at` | Timestamp de expiración keep_alive | `2026-04-17T18:05:00Z` |
| `size_vram` | VRAM usada (0 en CPU-only) | `0` |
| `is_loaded` | Modelo en RAM ahora mismo | `true` |

### 📤 Formato de Salida

#### JSON Estructurado (para exportación/integración)

```json
{
  "timestamp": "2026-04-17T17:45:00.123456",
  "cpu": {
    "total_percent": 34.2,
    "per_core_percent": [45.1, 12.3, 67.8, 23.4, 55.6, 31.2,
                          44.9, 11.1, 66.7, 22.3, 54.5, 30.1],
    "freq_mhz": 2100,
    "cores_physical": 6,
    "cores_logical": 12
  },
  "ram": {
    "total_gb": 15.7,
    "used_gb": 11.2,
    "available_gb": 4.5,
    "percent": 71.3
  },
  "ollama": {
    "server_reachable": true,
    "models_loaded": [
      {
        "name": "mistral:7b",
        "size_gb": 4.4,
        "expires_at": "2026-04-17T18:05:00Z",
        "size_vram": 0,
        "is_loaded": true
      }
    ]
  }
}
```

#### Dashboard Visual en Terminal (via `rich`)

```
┌─────────────────────────────────────────────────────────────────┐
│           🖥️  OLLAMA METRICS MONITOR  │  2026-04-17 17:45:00    │
├────────────────────────┬────────────────────────────────────────┤
│  CPU TOTAL             │  ████████░░░░░░░░░░  34.2%             │
│  Núcleo 1              │  ██████████░░░░░░░░  45.1%  [verde]    │
│  Núcleo 2              │  ██░░░░░░░░░░░░░░░░  12.3%  [verde]    │
│  Núcleo 3              │  █████████████░░░░░  67.8%  [amarillo] │
│  Frecuencia            │  2100 MHz                              │
├────────────────────────┼────────────────────────────────────────┤
│  RAM Total             │  15.7 GB                               │
│  RAM Usada             │  11.2 GB  ██████████████░░  71.3%      │
│  RAM Disponible        │  4.5 GB   [amarillo ⚠️]                │
├────────────────────────┼────────────────────────────────────────┤
│  🤖 OLLAMA MODELS      │                                        │
│  mistral:7b            │  ✅ ACTIVO  │  4.4 GB RAM  │  CPU-only  │
│  Expira en             │  20 minutos                            │
│  phi3:mini             │  💤 EN DISCO (no cargado)              │
└────────────────────────┴────────────────────────────────────────┘
  [Actualización cada 5s]  │  Exportando a: logs/metrics/  │  Ctrl+C para salir
```

**Código de colores:**
- 🟢 Verde: CPU < 50% / RAM < 60%
- 🟡 Amarillo: CPU 50–80% / RAM 60–80%
- 🔴 Rojo: CPU > 80% / RAM > 80% → ⚠️ Alerta: considerar cleanup

### 🏗️ Especificación Técnica del Módulo

#### Interfaz Pública de `metrics_monitor.py`

```python
# Clase principal de recolección de métricas
class MetricsCollector:
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        ...

    def collect(self) -> MetricsSnapshot:
        """Recolecta un snapshot completo de métricas en el momento actual."""
        ...

    def collect_cpu(self) -> CPUMetrics:
        """Métricas de CPU via psutil."""
        ...

    def collect_ram(self) -> RAMMetrics:
        """Métricas de RAM via psutil."""
        ...

    def collect_ollama(self) -> OllamaMetrics:
        """Estado de modelos via GET /api/ps de Ollama."""
        ...


# Clase de visualización en terminal
class MetricsDashboard:
    def __init__(self, collector: MetricsCollector, interval_seconds: int = 5):
        ...

    def start(self, export: bool = False, export_dir: str = "logs/metrics/"):
        """Inicia el dashboard en tiempo real con rich.live."""
        ...

    def export_snapshot(self, snapshot: MetricsSnapshot, export_dir: str):
        """Exporta el snapshot actual a JSON y CSV."""
        ...


# Punto de entrada CLI
# python -m monitors.metrics_monitor --interval 5 --export --url http://localhost:11434
```

#### Dataclasses de Métricas

```python
@dataclass
class CPUMetrics:
    total_percent: float
    per_core_percent: list[float]
    freq_mhz: float
    cores_physical: int
    cores_logical: int

@dataclass
class RAMMetrics:
    total_gb: float
    used_gb: float
    available_gb: float
    percent: float

@dataclass
class OllamaModelInfo:
    name: str
    size_gb: float
    expires_at: str
    size_vram: int
    is_loaded: bool

@dataclass
class OllamaMetrics:
    server_reachable: bool
    models_loaded: list[OllamaModelInfo]

@dataclass
class MetricsSnapshot:
    timestamp: str       # ISO8601
    cpu: CPUMetrics
    ram: RAMMetrics
    ollama: OllamaMetrics
```

### ✅ Criterios de Aceptación

| Criterio | Descripción |
|---|---|
| **C1** | `collect()` retorna un `MetricsSnapshot` completo en < 2 segundos |
| **C2** | El dashboard se actualiza cada N segundos (configurable con `--interval`) |
| **C3** | Cuando Ollama no está disponible, `ollama.server_reachable = False` y el dashboard muestra `⚠️ Ollama no disponible` sin crashear |
| **C4** | Los colores cambian correctamente según los umbrales (verde/amarillo/rojo) |
| **C5** | La exportación genera archivos válidos en `logs/metrics/YYYY-MM-DD/metrics_HH-MM-SS.json` y `.csv` |
| **C6** | El módulo funciona como CLI: `python -m monitors.metrics_monitor --interval 3 --export` |
| **C7** | No consume más de 2% de CPU adicional por el monitoreo en sí |

### 🔧 Argumentos CLI del Monitor

```powershell
# Uso básico (actualiza cada 5 segundos, sin exportar)
python -m monitors.metrics_monitor

# Con exportación a JSON/CSV
python -m monitors.metrics_monitor --export

# Intervalo personalizado (cada 10 segundos)
python -m monitors.metrics_monitor --interval 10

# Apuntar a Ollama en otro host
python -m monitors.metrics_monitor --url http://192.168.1.100:11434

# Combinado
python -m monitors.metrics_monitor --interval 3 --export --url http://localhost:11434
```

---

## 11. Tarea #2 para Ingenieros: Response Evaluator y Quality Scoring

### 🎯 Objetivo

Crear un módulo Python (`orchestration/evaluators/response_evaluator.py`) que califique automáticamente la calidad de cada respuesta de engineer, asignando un **confidence score** (0–1) basado en criterios heurísticos y opcionales métricas de similaridad semántica.

**Propósito:** Permitir al usuario saber qué respuestas son confiables (✅ 0.8+) y cuáles necesitan revisión humana (⚠️ < 0.6) o escalación a FRIDA.

### 📊 Criterios de Evaluación

| Criterio | Peso | Descripción |
|---|---|---|
| **Completitud** | 20% | ¿La respuesta aborda todos los puntos de la pregunta? |
| **Estructura** | 15% | ¿Tiene encabezados, listas, formato claro? |
| **Coherencia** | 20% | ¿Las ideas están conectadas lógicamente? |
| **Longitud** | 10% | ¿Tiene suficiente detalle sin ser excesiva? |
| **Confianza del Modelo** | 15% | ¿El modelo reportó high/medium/low confidence? |
| **Tiempo de Respuesta** | 10% | ¿Se completó en tiempo razonable (<30s para 7B)? |
| **Marcadores de Dominio** | 10% | ¿Contiene vocabulario técnico esperado para la tarea? |

### 🏗️ Especificación Técnica

```python
@dataclass
class ResponseEvaluation:
    engineer_result_id: str
    overall_score: float         # 0.0–1.0
    completeness: float
    structure: float
    coherence: float
    length_score: float
    confidence_weight: float
    response_time_score: float
    domain_markers: float
    is_acceptable: bool          # score >= 0.7
    needs_human_review: bool     # 0.5 <= score < 0.7
    needs_escalation: bool       # score < 0.5
    reasoning: str               # Explicación en texto

class ResponseEvaluator:
    def __init__(self, engineer_type: str, model: str):
        ...
    
    def evaluate(self, result: EngineerResult) -> ResponseEvaluation:
        """Califica una respuesta completa."""
        ...
    
    def quick_score(self, text: str, engineer_type: str) -> float:
        """Puntuación rápida sin LLM (heurística)."""
        ...
```

### ✅ Criterios de Aceptación

| Criterio | Descripción |
|---|---|
| **C1** | El evaluador calcula un score 0.0–1.0 en < 500ms |
| **C2** | Detecta respuestas incompletas (score < 0.5) con 85%+ de precisión |
| **C3** | Reporta reasoning en texto plano entendible por AMS L3 |
| **C4** | Integrable con `EngineerResult` sin cambios al código existente |
| **C5** | Exportable a JSON en los logs de sesión |

### 📝 Campos a Añadir en el Orchestrator

```yaml
# En orchestration/orchestrator.py
result = EngineerResult(...)
evaluation = evaluator.evaluate(result)
result.evaluation = evaluation
```

---

## 12. Escenarios de Uso AMS L3

| # | Tarea | Estado | Fecha | Responsable |
|---|---|---|---|---|
| 1 | Inspección de hardware y setup inicial | ✅ Completado | 2026-04-17 | FRIDA |
| 2 | Scripts de cleanup y diagnóstico | ✅ Completado | 2026-04-17 | FRIDA |
| 3 | Guías de modelos y escenarios AMS L3 | ✅ Completado | 2026-04-17 | FRIDA |
| 4 | Framework Architect-Engineer (Python) | ✅ Completado | 2026-04-17 | FRIDA |
| 5 | CLI con memoria de sesiones | ✅ Completado | 2026-04-17 | FRIDA |
| 6 | README de arquitectura completo | ✅ Completado | 2026-04-17 | FRIDA |
| 7 | Monitor de métricas (`metrics_monitor.py`) | ✅ Completado | 2026-04-17 | Ingenieros |
| 8 | **Response Evaluator (`response_evaluator.py`)** | ⏳ Pendiente | — | Ingenieros |
| 9 | Tests end-to-end del pipeline | ⏳ Pendiente | — | Ingenieros |
| 10 | Publicación en GitHub | ⏳ Pendiente | — | AMS L3 |

---

## 13. Escenarios de Uso AMS L3

| Escenario | Trigger | Modelo | Ahorro tokens FRIDA |
|---|---|---|---|
| **A – Triaje** | Alerta entrante, ticket P1/P2 | `phi3:mini` | 80–90% |
| **B – Deep RCA** | Incidente complejo, post-mortem | `mistral:7b` | 60–70% |
| **C – Documentación** | RCA, runbook, change request | `mistral:7b` | 70–85% |
| **D  Code Review** | Hotfix, script de producción | `qwen2.5-coder:7b` | 50–60% |
| **E – Token Relay** | Consulta con contexto largo | `phi3:mini` + FRIDA | **85–92%** |
| **F – Aprendizaje** | Código legacy, nueva tecnología | `mistral:7b` | 95–100% |
| **G – Monitor Auto** | Script de monitoreo continuo | `phi3:mini` (API) | 95% |

> Detalles completos en: `guides/03_ams_l3_optimization_scenarios.md`

---

## 14. Estrategia de Tokens FRIDA

```
Presupuesto diario: 130,000 tokens

REGLA DE ORO: Ollama primero → FRIDA solo para lo esencial

Flujo obligatorio para cualquier consulta a FRIDA:
1. Condensar contexto con Ollama (phi3:mini)         → usa 0 tokens FRIDA
2. Estructurar pregunta con template                  → prompt < 500 tokens
3. Enviar a FRIDA solo el prompt optimizado           → ahorra 85–92%

Resultado: hasta 8x más consultas FRIDA por día
```

### Distribución Recomendada del Presupuesto Diario

| Tipo de Consulta | Tokens/consulta | Consultas/día | Total |
|---|---|---|---|
| Triajes locales (Ollama) | 0 | ilimitado | 0 |
| Preguntas FRIDA simples | ~500 | 50 | 25,000 |
| Análisis FRIDA complejos | ~2,000 | 20 | 40,000 |
| RCA con contexto largo | ~5,000 | 5 | 25,000 |
| **Reserva de emergencia** | — | — | **40,000** |
| **TOTAL** | | | **130,000** |

> Ver plantillas en: `prompts/`
> Ver estrategia completa en: `guides/04_tools_and_token_strategies.md`

---

## 15. Flujo de Trabajo Iterativo y Registro de Decisiones (ADR)

### Proceso Iterativo

```
Tarea recibida
     │
     ▼
[FRIDA analiza] → ¿Hardware suficiente? → No → cleanup_for_ollama.ps1
     │                                            │
     │ Sí                                         ▼
     ▼                                    [Retry con phi3:mini]
[Architect descompone]
     │
     ▼
[Engineers ejecutan] → Resultado parcial
     │                        │
     ▼                        ▼
[Aggregator consolida] ← [Revisión humana]
     │
     ▼
[Sesión guardada en memory/]
     │
     ▼
[Próxima tarea usa contexto anterior]
```

### Registro de Decisiones Arquitectónicas (ADR)

#### ADR-001: Elección de Ollama como Backend de Inferencia Local

- **Fecha:** 2026-04-17
- **Estado:** Aceptado
- **Contexto:** Se necesita un backend de IA que funcione offline, sin costos por token, en un equipo con AMD Ryzen 5 7530U y 15.7 GB RAM sin GPU dedicada.
- **Decisión:** Usar Ollama v0.21.0 con modelos cuantizados (Q4/Q5).
- **Justificación:** API HTTP estándar, soporte de múltiples modelos, keep_alive configurable, compatible con Python via requests, sin dependencias de GPU.
- **Consecuencias:** Inferencia CPU-only (~15–25s para 7B). Aceptable para uso AMS L3 donde la latencia no es crítica al segundo.

#### ADR-002: Framework Architect-Engineer

- **Fecha:** 2026-04-17
- **Estado:** Aceptado
- **Contexto:** Tareas AMS L3 son heterogéneas (triaje, análisis, código, documentación). Un único modelo generalista desperdicia recursos.
- **Decisión:** Patrón Architect-Engineer con routing por tipo de tarea.
- **Justificación:** Cada engineer usa el modelo óptimo para su dominio. El Architect usa el modelo más ligero (phi3:mini) para no consumir RAM extra en la coordinación.
- **Consecuencias:** Mayor complejidad de código, compensada por mejor calidad de respuesta y menor consumo total de RAM por sesión.

#### ADR-003: Memoria de Sesión Basada en Archivos JSON

- **Fecha:** 2026-04-17
- **Estado:** Aceptado
- **Contexto:** Se necesita persistencia de contexto entre turnos de trabajo sin base de datos.
- **Decisión:** Archivos JSON en `~/.ollama_ams/sessions/` con TTL de 72 horas.
- **Justificación:** Sin dependencias adicionales, portátil, exportable a Markdown, inspecciona con cualquier editor de texto.
- **Consecuencias:** No apto para múltiples usuarios simultáneos. Aceptable para uso individual AMS L3.

### Tabla de Tareas del Proyecto

| # | Tarea | Estado | Fecha | Responsable |
|---|---|---|---|---|
| 1 | Inspección de hardware y setup inicial | ✅ Completado | 2026-04-17 | FRIDA |
| 2 | Scripts de cleanup y diagnóstico | ✅ Completado | 2026-04-17 | FRIDA |
| 3 | Guías de modelos y escenarios AMS L3 | ✅ Completado | 2026-04-17 | FRIDA |
| 4 | Framework Architect-Engineer (Python) | ✅ Completado | 2026-04-17 | FRIDA |
| 5 | CLI con memoria de sesiones | ✅ Completado | 2026-04-17 | FRIDA |
| 6 | README de arquitectura completo | ✅ Completado | 2026-04-17 | FRIDA |
| 7 | **Monitor de métricas (`metrics_monitor.py`)** | ✅ Completado | 2026-04-17 | Ingenieros |
| 8 | Tests end-to-end del pipeline | ⏳ Pendiente | — | Ingenieros |
| 9 | Publicación en GitHub | ⏳ Pendiente | — | AMS L3 |

### Convenciones de Commits

```
feat: nueva funcionalidad
fix: corrección de bug
docs: cambios en documentación
refactor: refactorización sin cambio funcional
test: añadir o modificar tests
chore: mantenimiento (dependencias, config)

Ejemplo: feat(monitor): add CPU per-core metrics collection
```

### Convenciones de Ramas

```
main          → código estable y documentado
dev           → integración de features
feature/XXX   → desarrollo de una funcionalidad específica
fix/XXX       → corrección de bug específico

Ejemplo: feature/metrics-monitor
```

---

## 16. Publicar en GitHub

### Pasos para Publicar el Repositorio

```powershell
# 1. Navegar al directorio raíz del proyecto
cd c:\Users\ja.martinez\Documents\FRIDA\Proyectos\Ollama

# 2. Inicializar Git (si no está inicializado)
git init

# 3. Añadir todos los archivos al staging
git add .

# 4. Primer commit con mensaje semántico
git commit -m "feat: initial FRIDA Orchestration Framework for AMS L3"

# 5. Crear repositorio en GitHub (desde la web o GitHub CLI)
# Opción A: GitHub CLI
gh repo create frida-ollama-ams --private --description "FRIDA Orchestration Framework for AMS L3 — local AI with Ollama"

# Opción B: Crear manualmente en github.com y copiar la URL

# 6. Añadir el remoto
git remote add origin https://github.com/<tu-usuario>/frida-ollama-ams.git

# 7. Push inicial
git branch -M main
git push -u origin main
```

### .gitignore Recomendado

El archivo `.gitignore` ya existe en la raíz del proyecto. Verificar que incluya:

```
__pycache__/
*.py[cod]
*.egg-info/
.env
*.log
logs/metrics/
~/.ollama_ams/
```

### Commits Subsiguientes

```powershell
# Después de completar cada tarea:
git add .
git commit -m "feat(monitor): implement MetricsCollector with CPU and RAM via psutil"
git push

# Para una corrección:
git add .
git commit -m "fix(router): handle empty keyword list without exception"
git push
```

### Tags de Versión

```powershell
# Al completar un milestone:
git tag -a v1.0.0 -m "Release v1.0.0: complete Architect-Engineer framework with CLI"
git push origin v1.0.0
```

---

## 17. Comandos de Referencia Rápida

```powershell
# ─── Sistema ───────────────────────────────────────────────────────────────
.\scripts\check_system_for_ollama.ps1           # Diagnóstico
.\scripts\cleanup_for_ollama.ps1                # Limpieza estándar
.\scripts\cleanup_for_ollama.ps1 -Aggressive    # Limpieza máxima
.\scripts\restore_services.ps1                  # Restaurar al finalizar

# ─── Ollama (servidor) ─────────────────────────────────────────────────────
ollama serve                                    # Iniciar servidor (terminal separada)
ollama list                                     # Ver modelos instalados
ollama ps                                       # Ver modelos activos en RAM
ollama stop mistral:7b                          # Liberar RAM de un modelo
ollama pull llama3:8b                           # Descargar nuevo modelo

# ─── Monitor de Métricas ───────────────────────────────────────────────────
cd ollama-ams-guide\orchestration
python -m monitors.metrics_monitor              # Dashboard en tiempo real
python -m monitors.metrics_monitor --export     # Con exportación JSON/CSV
python -m monitors.metrics_monitor --interval 3 # Actualización cada 3s

# ─── CLI del Framework ─────────────────────────────────────────────────────
cd ollama-ams-guide\orchestration
python cli/main.py query "tu tarea aquí"        # Consulta única
python cli/main.py chat                         # Sesión interactiva
python cli/main.py chat --session <id>          # Retomar sesión
python cli/main.py file tarea.txt               # Desde archivo
python cli/main.py sessions                     # Listar sesiones
python cli/main.py export <id>                  # Exportar sesión
python cli/main.py route "analiza código"       # Ver routing sin ejecutar
python cli/main.py --no-architect query "..."   # Modo rápido (sin LLM)

# ─── Modelos directos (sin framework) ─────────────────────────────────────
ollama run phi3:mini                            # Triaje (2.5 GB RAM)
ollama run mistral:7b                           # Análisis (5.0 GB RAM)
ollama run qwen2.5-coder:7b                    # Código (5.2 GB RAM)

# ─── Git ───────────────────────────────────────────────────────────────────
git status                                      # Ver estado del repo
git add .                                       # Añadir todos los cambios
git commit -m "feat: descripción del cambio"    # Commit semántico
git push                                        # Publicar en GitHub
```

---

> 📌 **Notas Importantes:**
>
> - ⚠️ **CPU-Only:** Inferencia 5–10x más lenta que con GPU dedicada. Planificar 10–30s para modelos 7B.
> - ⚠️ **VDI y Navegador:** Los scripts de limpieza **NUNCA** terminan procesos de VDI ni el navegador principal.
> - ⚠️ **Servidor Ollama:** Ejecutar `ollama serve` manualmente en una terminal separada antes de usar el CLI.
> - 💡 **Modelo preloaded:** Una vez cargado en RAM, el modelo permanece disponible entre queries. No cerrar la terminal de Ollama.
> - 💡 **Sesiones persistentes:** Usar `--session <id>` para retomar conversaciones del turno anterior.
> - 💡 **Modo rápido:** Usar `--no-architect` cuando la RAM disponible sea < 4 GB.
