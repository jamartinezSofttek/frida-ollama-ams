# FRIDA Orchestration Framework

> **AMS L3 — Multi-Agent Orchestration with Local Ollama Models**

Framework de orquestación multi-agente para análisis de incidentes, code review, generación de RCA y monitoreo de sistemas, diseñado para ejecutarse completamente en local con modelos Ollama.

---

## Tabla de Contenidos

1. [Arquitectura](#arquitectura)
2. [Estructura del Repositorio](#estructura-del-repositorio)
3. [Roles del Sistema](#roles-del-sistema)
4. [Instalación y Requisitos](#instalación-y-requisitos)
5. [Uso](#uso)
6. [Monitor de Métricas](#monitor-de-métricas)
7. [Response Evaluator](#response-evaluator)
8. [Tests](#tests)
9. [Tabla de Tareas del Proyecto](#tabla-de-tareas-del-proyecto)
10. [Registro de Decisiones](#registro-de-decisiones)

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                  USUARIO (AMS L3 Engineer)                      │
│                "Analiza este incidente P1..."                    │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                  ORCHESTRATOR (orchestrator.py)                  │
│  - Gestiona el ciclo completo de la tarea                       │
│  - Invoca al Architect Agent para descomposición                │
│  - Coordina Engineers y recopila resultados                     │
│  - Almacena sesión en SessionStore                              │
│  - Ejecuta ResponseEvaluator sobre cada resultado               │
└───────┬──────────────────┬────────────────────┬─────────────────┘
        │                  │                    │
        ▼                  ▼                    ▼
┌──────────────┐  ┌────────────────┐  ┌─────────────────────┐
│ ARCHITECT    │  │   TASK ROUTER  │  │   SESSION STORE     │
│ AGENT        │  │   (router.py)  │  │   (memory/)         │
│              │  │                │  │                     │
│ Descompone   │  │ Enruta tareas  │  │ Persiste historial  │
│ tareas en    │  │ por keywords   │  │ de conversaciones   │
│ subtareas    │  │ al engineer    │  │ en JSON             │
│ JSON         │  │ correcto       │  │                     │
└──────────────┘  └────────────────┘  └─────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ENGINEER AGENTS (agents/engineer.py)          │
├───────────────┬────────────────────┬─────────────────────────────┤
│  TRIAGE       │  CODE              │  ANALYSIS / DOCS            │
│  phi3:mini    │  qwen2.5-coder:7b  │  mistral:7b                 │
│               │                    │                             │
│ Clasificación │ Code review,       │ Análisis profundo,          │
│ severidad,    │ debugging,         │ RCA, runbooks,              │
│ priorización  │ scripts            │ hipótesis                   │
└───────────────┴────────────────────┴─────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│              RESPONSE EVALUATOR (evaluators/)                    │
│  Scoring heurístico multi-criterio:                             │
│  completeness · structure · coherence · length                  │
│  confidence · response_time · domain_markers                    │
│  → is_acceptable / needs_human_review / needs_escalation        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Estructura del Repositorio

```
orchestration/
├── README.md                        ← Este archivo
├── architecture.md                  ← Diseño detallado de la arquitectura
├── orchestrator.py                  ← Motor principal de orquestación
├── router.py                        ← Enrutamiento por keywords
├── config.yaml                      ← Configuración de modelos y routing
├── requirements.txt                 ← Dependencias Python
│
├── agents/
│   ├── __init__.py
│   ├── architect.py                 ← Architect Agent (descomposición de tareas)
│   └── engineer.py                  ← Engineer Agents (TRIAGE/CODE/ANALYSIS/DOCS)
│
├── memory/
│   ├── __init__.py
│   └── session_store.py             ← Persistencia de sesiones en JSON
│
├── evaluators/
│   ├── __init__.py
│   └── response_evaluator.py        ← Quality scoring heurístico
│
├── monitors/
│   ├── __init__.py
│   ├── metrics_monitor.py           ← Monitor básico de CPU/RAM/Ollama
│   ├── extended_metrics_collector.py ← Métricas extendidas (disco, red, GPU)
│   ├── advanced_dashboard.py        ← Dashboard rich en terminal
│   ├── alert_engine.py              ← Motor de alertas con umbrales
│   └── monitor_main.py              ← Punto de entrada del monitor Dynatrace-style
│
├── cli/
│   ├── __init__.py
│   └── main.py                      ← CLI interactivo
│
└── tests/
    ├── __init__.py
    └── test_pipeline.py             ← Tests unitarios e integración E2E
```

---

## Roles del Sistema

### Architect Agent
- Recibe la tarea de alto nivel del usuario
- La descompone en subtareas especializadas (máximo 4) en formato JSON
- Asigna cada subtarea al engineer más apropiado según el tipo

### Task Router
- Enrutamiento basado en keywords sin llamada a LLM (rápido y determinista)
- Tipos: `TRIAGE`, `CODE`, `ANALYSIS`, `DOCS`
- Método `route()` devuelve `RoutingDecision` con `engineer_type`, `model`, `confidence` y `reason`

### Engineer Agents

| Tipo | Modelo | Especialidad | RAM ~|
|------|--------|--------------|------|
| `TRIAGE` | `phi3:mini` | Clasificación de severidad, priorización | 2.5 GB |
| `CODE` | `qwen2.5-coder:7b` | Code review, debugging, scripts | 5.2 GB |
| `ANALYSIS` | `mistral:7b` | Análisis profundo, hipótesis, causa raíz | 5.0 GB |
| `DOCS` | `mistral:7b` | RCA, runbooks, comunicados ejecutivos | 5.0 GB |

### Session Store
- Persiste el historial de conversaciones en archivos JSON
- Soporta múltiples sesiones concurrentes con TTL configurable
- Exporta sesiones a Markdown

### Response Evaluator
- Evalúa la calidad de la respuesta de cada engineer sin llamar a otro LLM
- 7 criterios heurísticos con pesos configurables
- Decisión final: `is_acceptable` / `needs_human_review` / `needs_escalation`

---

## Instalación y Requisitos

```bash
# 1. Instalar dependencias
cd ollama-ams-guide/orchestration
pip install -r requirements.txt

# 2. Verificar que Ollama está corriendo
ollama list

# 3. Modelos recomendados
ollama pull phi3:mini
ollama pull qwen2.5-coder:7b
ollama pull mistral:7b
```

**requirements.txt incluye:**
- `requests` — comunicación con API Ollama
- `pyyaml` — lectura de config.yaml
- `psutil` — métricas de sistema
- `rich` — dashboard en terminal
- `pytest` — ejecución de tests

---

## Uso

### CLI Interactivo

```bash
cd ollama-ams-guide/orchestration
py cli/main.py
```

### Como módulo Python

```python
from orchestrator import Orchestrator

orch = Orchestrator(config_path="config.yaml")
result = orch.run(
    task="Analiza este stack trace: java.lang.NullPointerException at PaymentService.java:142",
    use_architect_llm=True,   # False = routing directo por keywords (más rápido)
    session_id=None,           # None = nueva sesión automática
)

print(result.summary)
print(f"Duración: {result.total_duration_seconds:.1f}s")
print(f"Modelos usados: {result.models_used}")
```

### Serializar resultado a JSON

```python
from orchestrator import Orchestrator

json_str = Orchestrator.result_to_json(result)
```

---

## Monitor de Métricas

Monitor Dynatrace-style con dashboard en terminal, alertas configurables y exportación de datos.

```bash
# Monitor básico (snapshot único)
py monitors/metrics_monitor.py

# Monitor continuo con dashboard rich
py monitors/monitor_main.py

# Opciones avanzadas
py monitors/monitor_main.py --interval 5 --export metrics.json
```

**Métricas capturadas:**
- CPU: uso por núcleo, frecuencia, temperatura (si disponible)
- RAM: total, usada, disponible, porcentaje
- Disco: uso, velocidad de lectura/escritura
- Red: bytes enviados/recibidos
- Ollama: modelos cargados, VRAM usada, disponibilidad de la API

---

## Response Evaluator

Evalúa la calidad de las respuestas de los engineers con 7 criterios heurísticos:

| Criterio | Peso | Descripción |
|----------|------|-------------|
| `completeness` | 20% | Longitud y ausencia de truncado |
| `structure` | 20% | Markdown, headers, listas, código |
| `coherence` | 15% | Conectores lógicos y cohesión |
| `length` | 15% | Rango ideal según tipo de engineer |
| `confidence` | 10% | Nivel de confianza declarado |
| `response_time` | 10% | Penaliza respuestas lentas |
| `domain_markers` | 10% | Vocabulario específico del dominio |

**Umbrales de decisión:**
- `≥ 0.65` → `is_acceptable` ✅
- `0.40–0.65` → `needs_human_review` ⚠️
- `< 0.40` → `needs_escalation` 🚨

```python
from evaluators.response_evaluator import ResponseEvaluator

ev = ResponseEvaluator(engineer_type="ANALYSIS", model="mistral:7b")
evaluation = ev.evaluate(engineer_result)
print(f"Score: {evaluation.overall_score:.2f}")
print(f"Decisión: {evaluation.decision}")
print(evaluation.to_dict())
```

---

## Tests

### Ejecutar todos los tests (sin Ollama)

```bash
cd ollama-ams-guide/orchestration
py -m pytest tests/test_pipeline.py -v
```

### Ejecutar solo tests rápidos (excluir live)

```bash
py -m pytest tests/test_pipeline.py -v -k "not Live"
```

### Ejecutar tests live (requiere Ollama corriendo)

```bash
py -m pytest tests/test_pipeline.py -v --live
```

### Ejecutar un grupo específico de tests

```bash
# Solo tests del Router
py -m pytest tests/test_pipeline.py -v -k "TestTaskRouter"

# Solo tests del SessionStore
py -m pytest tests/test_pipeline.py -v -k "TestSessionStore"

# Solo tests del ResponseEvaluator
py -m pytest tests/test_pipeline.py -v -k "TestResponseEvaluator"

# Solo tests del MetricsCollector
py -m pytest tests/test_pipeline.py -v -k "TestMetricsCollector"
```

### Cobertura de tests

| Clase de test | Módulo cubierto | Requiere Ollama |
|---------------|-----------------|-----------------|
| `TestTaskRouter` | `router.py` | ❌ No |
| `TestSessionStore` | `memory/session_store.py` | ❌ No |
| `TestResponseEvaluator` | `evaluators/response_evaluator.py` | ❌ No |
| `TestMetricsCollector` | `monitors/metrics_monitor.py` | ❌ No (mock psutil/requests) |
| `TestConfig` | `config.yaml` | ❌ No |
| `TestResultSerialization` | `orchestrator.py` | ❌ No |
| `TestLivePipeline` | Pipeline completo E2E | ✅ Sí (`--live`) |

---

## Tabla de Tareas del Proyecto

| # | Tarea | Estado | Módulo |
|---|-------|--------|--------|
| 1 | Monitor básico de métricas CPU/RAM/Ollama | ✅ Completado | `monitors/metrics_monitor.py` |
| 2 | Architect Agent + Task Router + Engineer Agents | ✅ Completado | `agents/`, `router.py` |
| 3 | Session Store (persistencia de conversaciones) | ✅ Completado | `memory/session_store.py` |
| 4 | Orchestrator (motor de orquestación) | ✅ Completado | `orchestrator.py` |
| 5 | CLI interactivo | ✅ Completado | `cli/main.py` |
| 6 | Monitor Dynatrace-style (dashboard + alertas) | ✅ Completado | `monitors/` |
| 7 | Response Evaluator (quality scoring heurístico) | ✅ Completado | `evaluators/response_evaluator.py` |
| 8 | Tests End-to-End del pipeline | ✅ Completado | `tests/test_pipeline.py` |

---

## Registro de Decisiones

### ADR-001: Routing por keywords vs LLM
**Decisión:** El `TaskRouter` usa matching por keywords ponderadas en lugar de llamar a un LLM para clasificar.  
**Razón:** Más rápido (< 1ms), determinista, sin coste de tokens, y suficientemente preciso para los 4 tipos de engineer.  
**Trade-off:** Menor flexibilidad para tareas ambiguas. Mitigado con `route_multi()` y modo `use_architect_llm=True`.

### ADR-002: Ejecución secuencial por defecto
**Decisión:** El orquestador ejecuta subtareas en secuencia, no en paralelo.  
**Razón:** Con RAM limitada (~8-10 GB libres), cargar múltiples modelos simultáneamente causa swapping.  
**Trade-off:** Mayor latencia total. Modo paralelo disponible con `execution.mode: parallel` en `config.yaml` si RAM > 12 GB.

### ADR-003: Evaluación heurística sin LLM juez
**Decisión:** El `ResponseEvaluator` usa heurísticas (longitud, Markdown, keywords de dominio) en lugar de un LLM juez.  
**Razón:** Evita el problema del "juez sesgado", elimina latencia adicional y no consume tokens extra.  
**Trade-off:** El scoring es menos semántico. Para producción, se puede combinar con validación humana en los casos `needs_human_review`.

### ADR-004: Tests sin dependencia de Ollama
**Decisión:** Todos los tests unitarios usan `unittest.mock` para simular llamadas a Ollama y psutil.  
**Razón:** Los tests deben poder correr en CI/CD sin infraestructura de modelos.  
**Trade-off:** Los tests live (`--live`) se marcan como skipped por defecto y requieren flag explícito.

---

## Contribución

Este proyecto sigue el flujo de trabajo iterativo del FRIDA Orchestration Framework:

1. **Planificación:** El Architect Agent descompone la tarea en subtareas
2. **Implementación:** Cada Engineer implementa su subtarea especializada
3. **Evaluación:** El ResponseEvaluator valora la calidad de cada resultado
4. **Sesión:** El SessionStore persiste el historial para contexto futuro
5. **Tests:** Cada módulo nuevo debe tener cobertura en `tests/test_pipeline.py`
