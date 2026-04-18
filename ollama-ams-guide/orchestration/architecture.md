# Arquitectura Multi-Agente: Architect-Engineer con Ollama
## AMS L3 – Framework de Orquestación Local

---

## Visión General

```
┌────────────────────────────────────────────────────────────────────┐
│                    USUARIO (AMS L3 Engineer)                       │
│                  "Analiza este incidente P1..."                     │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│                    ARCHITECT AGENT (Orchestrator)                   │
│              Modelo: mistral:7b  o  phi3:mini                      │
│                                                                     │
│  1. Analiza la tarea del usuario                                    │
│  2. La descompone en subtareas especializadas                       │
│  3. Asigna cada subtarea al modelo más apropiado                    │
│  4. Recopila y agrega las respuestas                                │
│  5. Genera respuesta consolidada                                     │
└───────┬──────────────────────┬─────────────────────┬───────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
┌──────────────┐   ┌───────────────────┐   ┌────────────────────┐
│ ENGINEER #1  │   │   ENGINEER #2     │   │   ENGINEER #3      │
│ phi3:mini    │   │ qwen2.5-coder:7b  │   │  mistral:7b        │
│              │   │                   │   │                    │
│ Triaje y     │   │ Code review,      │   │ Análisis profundo, │
│ clasificación│   │ debugging,        │   │ RCA, documentación │
│ de errores   │   │ scripts           │   │                    │
└──────────────┘   └───────────────────┘   └────────────────────┘
        │                      │                      │
        └──────────────────────┴──────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  RESULTADO AGREGADO  │
                    │  Respuesta final al  │
                    │  usuario             │
                    └────────────────────���─���
```

---

## Roles del Sistema

### Architect Agent (Orquestador)

**Responsabilidades:**
- Recibir la tarea de alto nivel del usuario
- Analizar la complejidad y tipo de tarea
- Descomponer en subtareas atómicas y especializadas
- Asignar cada subtarea al engineer model más apropiado
- Gestionar el flujo de resultados entre engineers
- Agregar y sintetizar las respuestas parciales
- Entregar respuesta consolidada y coherente

**Prompt de sistema del Architect:**
```
Eres el Architect Agent de un sistema multi-agente de AMS L3.
Tu rol es:
1. Analizar la tarea recibida
2. Dividirla en subtareas especializadas (máximo 4)
3. Especificar qué tipo de agente debe manejar cada subtarea
4. Los tipos de agentes disponibles son: TRIAGE, CODE, ANALYSIS, DOCS
5. Responder SIEMPRE en JSON con la estructura de descomposición

Formato de respuesta:
{
  "tarea_original": "descripción",
  "subtareas": [
    {
      "id": 1,
      "tipo": "TRIAGE|CODE|ANALYSIS|DOCS",
      "descripcion": "qué debe hacer",
      "input": "datos de entrada para este agente",
      "modelo": "phi3:mini|qwen2.5-coder:7b|mistral:7b"
    }
  ]
}
```

### Engineer Agents (Especialistas)

| Tipo | Modelo | Especialidad | RAM |
|---|---|---|---|
| `TRIAGE` | `phi3:mini` | Clasificación, análisis inicial de errores, priorización | ~2.5 GB |
| `CODE` | `qwen2.5-coder:7b` | Code review, debugging, generación de scripts | ~5.2 GB |
| `ANALYSIS` | `mistral:7b` | Análisis profundo, hipótesis, razonamiento técnico | ~5.0 GB |
| `DOCS` | `mistral:7b` | Redacción de RCA, runbooks, comunicados | ~5.0 GB |

---

## Protocolo de Comunicación

### Formato de Asignación de Tarea (Architect → Engineer)
```json
{
  "task_id": "uuid",
  "engineer_type": "CODE",
  "model": "qwen2.5-coder:7b",
  "system_prompt": "Eres un experto en code review...",
  "user_prompt": "Revisa este código Python...",
  "context": "contexto adicional relevante",
  "max_tokens": 500,
  "temperature": 0.1
}
```

### Formato de Respuesta (Engineer → Architect)
```json
{
  "task_id": "uuid",
  "engineer_type": "CODE",
  "model_used": "qwen2.5-coder:7b",
  "result": "texto de la respuesta",
  "confidence": "HIGH|MEDIUM|LOW",
  "tokens_used": 342,
  "duration_seconds": 15.3
}
```

### Formato de Respuesta Agregada (Architect → Usuario)
```json
{
  "session_id": "uuid",
  "original_task": "descripción de la tarea",
  "subtasks_executed": 3,
  "results": {
    "summary": "respuesta consolidada principal",
    "details": [
      { "type": "TRIAGE", "finding": "..." },
      { "type": "CODE", "finding": "..." },
      { "type": "ANALYSIS", "finding": "..." }
    ]
  },
  "total_duration_seconds": 45.2,
  "models_used": ["phi3:mini", "qwen2.5-coder:7b"]
}
```

---

## Flujos de Trabajo por Tipo de Tarea

### Flujo 1: Análisis de Incidente
```
Usuario: "Analiza este stack trace de Java y propón solución"
    ↓
Architect descompone en:
  1. TRIAGE (phi3:mini)    → Clasifica severidad y componente
  2. ANALYSIS (mistral:7b) → Identifica causa raíz probable
  3. CODE (qwen2.5-coder)  → Propone fix de código
    ↓
Architect agrega los 3 resultados
    ↓
Respuesta final: Severidad + Causa + Fix en un solo mensaje
```

### Flujo 2: Code Review de Emergencia
```
Usuario: "Revisa este hotfix antes del deploy"
    ↓
Architect descompone en:
  1. CODE (qwen2.5-coder)  → Revisión de lógica y bugs
  2. CODE (qwen2.5-coder)  → Revisión de seguridad
  3. DOCS (mistral:7b)     → Genera comentarios de deploy
    ↓
Respuesta final: Aprobado/Rechazado + Issues + Notas de deploy
```

### Flujo 3: Generación de Documentación
```
Usuario: "Genera el RCA de este incidente"
    ↓
Architect descompone en:
  1. TRIAGE (phi3:mini)    → Extrae datos clave del incidente
  2. ANALYSIS (mistral:7b) → Análisis de causa raíz
  3. DOCS (mistral:7b)     → Redacta el RCA formal
    ↓
Respuesta final: Documento RCA completo en Markdown
```

---

## Consideraciones de Memoria y Contexto

### Gestión de Contexto por Engineer
- Cada engineer recibe **solo el contexto necesario** para su subtarea
- El architect **no pasa el contexto completo** a todos los engineers
- Esto permite usar modelos ligeros (phi3:mini) para subtareas simples sin cargar contexto pesado

### Límites de Ventana de Contexto
| Modelo | num_ctx recomendado | RAM extra por contexto |
|---|---|---|
| `phi3:mini` | 2048 tokens | ~0.2 GB |
| `qwen2.5-coder:7b` | 4096 tokens | ~0.5 GB |
| `mistral:7b` | 4096 tokens | ~0.5 GB |

### Estrategia de Carga de Modelos
- Con RAM limitada (~8-10 GB libres), **no cargar todos los modelos simultáneamente**
- El orquestador ejecuta subtareas **secuencialmente** por defecto
- Modo paralelo disponible solo si hay >12 GB libres
- Usar `OLLAMA_KEEP_ALIVE=5m` para liberar RAM entre subtareas

---

## Feedback Loops y Manejo de Errores

### Bucle de Validación
```
Engineer produce resultado
    ↓
Architect valida: ¿el resultado responde la subtarea?
    ├─ SÍ → continuar al siguiente engineer
    └─ NO → reintentar con prompt mejorado (máx 2 reintentos)
              └─ Si sigue fallando → marcar como "LOW CONFIDENCE"
                  y continuar con advertencia
```

### Degradación Elegante
- Si un engineer falla o timeout: continuar con los demás y marcar subtarea como incompleta
- Si el architect no puede descomponer: ejecutar como tarea simple con el modelo más apropiado
- Si hay RAM insuficiente: reducir al modelo más ligero disponible

---

## Implementación: Archivos del Sistema

```
orchestration/
├── architecture.md          ← Este archivo (diseño)
├── orchestrator.py          ← Motor principal de orquestación
├── config.yaml              ← Configuración de modelos y routing
├── agents/
│   ├── architect.py         ← Lógica del Architect Agent
│   └── engineer.py          ← Lógica de los Engineer Agents
├── memory/
│   └── session_store.py     ← Almacenamiento de sesiones
└── cli/
    └── main.py              ← Interfaz de línea de comandos
```
