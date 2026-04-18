# Análisis de Estado del Sistema y Matriz de Factibilidad de Modelos
## AMS L3 – Selección de Modelos según Recursos Disponibles

---

## Sistema de Referencia

| Componente | Valor |
|---|---|
| CPU | AMD Ryzen 5 7530U – 6c/12t @ 2.0–4.5 GHz |
| RAM Total | 15.7 GB |
| RAM esperada post-limpieza | **8–10 GB libres** |
| GPU/VRAM | AMD Radeon iGPU – 512 MB (sin aceleración efectiva) |
| Modo de inferencia | **CPU-only** |
| Almacenamiento | SSD recomendado para swap de modelos |

> **Principio clave en CPU-only:** El modelo completo debe caber en RAM. Si no cabe en RAM, el sistema usa swap (disco), lo que degrada el rendimiento drásticamente. Siempre verificar RAM libre **antes** de lanzar un modelo.

---

## Checklist de Análisis del Sistema (Pre-Ejecución)

Ejecutar antes de elegir qué modelo usar:

```powershell
# Script de diagnóstico rápido pre-Ollama
$os = Get-WmiObject Win32_OperatingSystem
$freeRAM_MB = [math]::Round($os.FreePhysicalMemory / 1KB, 0)
$totalRAM_MB = [math]::Round($os.TotalVisibleMemorySize / 1KB, 0)
$usedRAM_MB = $totalRAM_MB - $freeRAM_MB
$freeRAM_GB = [math]::Round($freeRAM_MB / 1024, 1)

$cpu = Get-WmiObject Win32_Processor
$cpuLoad = (Get-CimInstance Win32_Processor).LoadPercentage

Write-Host "========== DIAGNÓSTICO PRE-OLLAMA =========="
Write-Host "RAM Libre:    $freeRAM_MB MB ($freeRAM_GB GB)"
Write-Host "RAM Usada:    $usedRAM_MB MB"
Write-Host "RAM Total:    $totalRAM_MB MB"
Write-Host "Carga CPU:    $cpuLoad%"
Write-Host ""

# Recomendación automática de escenario
if ($freeRAM_GB -ge 8) {
    Write-Host "✅ ESCENARIO: MÁXIMO RENDIMIENTO (>8 GB libres)"
    Write-Host "   → Puedes ejecutar modelos 13B-Q4 o 7B-Q8"
} elseif ($freeRAM_GB -ge 5) {
    Write-Host "⚡ ESCENARIO: EFICIENTE (5-8 GB libres)"
    Write-Host "   → Modelos 7B-Q4/Q5 o 3B-Q8 recomendados"
} elseif ($freeRAM_GB -ge 2.5) {
    Write-Host "⚠️  ESCENARIO: LIGERO (2.5-5 GB libres)"
    Write-Host "   → Solo modelos ligeros: phi3:mini, tinyllama, gemma:2b"
} else {
    Write-Host "❌ RECURSOS INSUFICIENTES (<2.5 GB libres)"
    Write-Host "   → Ejecutar limpieza primero: .\\scripts\\cleanup_for_ollama.ps1"
}
```

---

## Guía de Cuantización: Q4 vs Q5 vs Q8

| Cuantización | Tamaño relativo | Calidad | RAM típica (7B) | Uso recomendado |
|---|---|---|---|---|
| **Q2** | Muy pequeño | Baja | ~2.5 GB | Solo emergencias, baja calidad |
| **Q4_K_M** | Pequeño | Buena (recomendada) | ~4.1 GB | Balance óptimo rendimiento/calidad |
| **Q5_K_M** | Medio | Muy buena | ~4.8 GB | Cuando hay RAM suficiente |
| **Q6_K** | Medio-alto | Excelente | ~5.5 GB | Cerca de calidad completa |
| **Q8_0** | Grande | Casi perfecta | ~7.2 GB | Máxima calidad, requiere más RAM |
| **FP16** | Completo | Perfecta | ~14 GB | Impracticable en este sistema |

> **Regla de oro para este sistema:** Usar siempre **Q4_K_M** como base. Subir a Q5 si hay >7 GB libres. Nunca usar Q8 para modelos 7B salvo que tengas 10+ GB libres.

---

## Escenario 1 – Modelos Ligeros (Mínimo Consumo de Recursos)

**Condición:** RAM libre < 5 GB, o necesitas respuesta ultrarrápida, o tienes Ollama en segundo plano.

### Modelos recomendados

| Modelo | Tamaño | RAM necesaria | Velocidad (tokens/s)* | Mejor para |
|---|---|---|---|---|
| `phi3:mini` | 2.2 GB | ~2.5 GB | 20–35 t/s | Q&A rápido, resúmenes cortos, código simple |
| `tinyllama:1.1b` | 0.6 GB | ~1.0 GB | 40–60 t/s | Clasificación, tareas muy simples |
| `gemma:2b` | 1.5 GB | ~2.0 GB | 25–40 t/s | Razonamiento ligero, explicaciones |
| `qwen2:1.5b` | 0.9 GB | ~1.3 GB | 35–50 t/s | Multilingüe ligero (soporte español) |
| `codegemma:2b` | 1.6 GB | ~2.1 GB | 25–35 t/s | Completado de código, snippets rápidos |

*Velocidades estimadas en Ryzen 5 7530U con carga baja.

### Comandos de instalación
```bash
ollama pull phi3:mini
ollama pull tinyllama:1.1b
ollama pull gemma:2b
ollama pull qwen2:1.5b
ollama pull codegemma:2b
```

### Casos de uso en AMS L3
- Parsear rápidamente un mensaje de error y sugerir código de estado HTTP
- Clasificar tickets: `P1/P2/P3/P4` basado en descripción
- Responder preguntas básicas sobre sintaxis SQL/Bash
- Pre-filtrar logs: ¿es este error crítico o informativo?
- Generar líneas de comando básicas sin documentación externa

### Perfil de recurso
```
RAM usada por modelo:  ~2–3 GB
RAM libre para OS:     ~6–8 GB
Impacto en trabajo:    Mínimo (puede correr en background)
Latencia primera resp: 3–8 segundos
```

---

## Escenario 2 – Modelos Potentes pero Eficientes

**Condición:** RAM libre 5–9 GB. Balance entre calidad y disponibilidad del sistema.

### Modelos recomendados

| Modelo | Tamaño | RAM necesaria | Cuantización recomendada | Mejor para |
|---|---|---|---|---|
| `mistral:7b` | 4.4 GB | ~5.0 GB | Q4_K_M (incluida) | Razonamiento general, análisis, RCA |
| `qwen2.5-coder:7b` | 4.7 GB | ~5.2 GB | Q4_K_M (incluida) | Code review, debugging, scripts |
| `llama3.2:3b` | 2.0 GB | ~2.5 GB | Q4_K_M | Chat rápido con alta calidad |
| `deepseek-coder:6.7b` | 3.8 GB | ~4.5 GB | Q4_K_M | Código de producción, análisis técnico |
| `codellama:7b` | 3.8 GB | ~4.5 GB | Q4_K_M | Completado de código, refactoring |
| `neural-chat:7b` | 4.1 GB | ~4.8 GB | Q4_K_M | Diálogo técnico, documentación |

### Comandos de instalación
```bash
ollama pull mistral:7b
ollama pull qwen2.5-coder:7b
ollama pull llama3.2:3b
ollama pull deepseek-coder:6.7b
ollama pull codellama:7b
```

### Casos de uso en AMS L3
- Análisis de root cause en incidentes (RCA completo)
- Revisión de código de cambios en producción (change requests)
- Generación de runbooks y procedimientos detallados
- Análisis de stack traces complejos (Java, Python, .NET)
- Redacción de RFCs y propuestas de cambio técnico
- Consultas complejas SQL con optimización de queries

### Perfil de recurso
```
RAM usada por modelo:  ~4.5–5.5 GB
RAM libre para OS:     ~4–5 GB (post-limpieza)
Impacto en trabajo:    Moderado (cerrar apps pesadas previo a uso)
Latencia primera resp: 8–20 segundos
Velocidad generación:  8–15 tokens/segundo
```

### Configuración óptima para este escenario
```bash
# Establecer número de hilos para optimizar en Ryzen 5 7530U (12 hilos lógicos)
# Ollama usa todos los hilos disponibles por defecto
# Para equilibrio sistema/modelo, limitar a 8 hilos:
$env:OLLAMA_NUM_THREAD = 8    # PowerShell
# o en .env de Ollama:
# OLLAMA_NUM_THREAD=8
```

---

## Escenario 3 – Modelos de Máximo Rendimiento (Al Límite)

**Condición:** RAM libre >9 GB (después de limpieza agresiva), sistema dedicado a la tarea, sin multitarea.

> ⚠️ **Advertencia:** Estos modelos consumirán la mayor parte de la RAM del sistema. Cerrar **todas** las aplicaciones no esenciales antes de ejecutar. El sistema puede volverse lento durante la inferencia.

### Modelos recomendados

| Modelo | Tamaño en disco | RAM necesaria | Cuantización | Viabilidad en 15.7 GB |
|---|---|---|---|---|
| `mistral:7b-q8` | 7.7 GB | ~8.5 GB | Q8_0 | ✅ Viable post-limpieza agresiva |
| `codellama:13b-q4` | 7.4 GB | ~8.0 GB | Q4_K_M | ✅ Viable con >9 GB libres |
| `deepseek-coder:33b-q2` | 20 GB | ~22 GB | Q2_K | ❌ NO viable (excede RAM total) |
| `llama3:70b-q4` | 40 GB | ~43 GB | Q4_K_M | ❌ NO viable (requiere >40 GB RAM) |
| `codellama:34b-q4` | 19 GB | ~21 GB | Q4_K_M | ❌ NO viable en este sistema |
| `qwen2.5-coder:14b-q4` | 8.9 GB | ~9.5 GB | Q4_K_M | ⚠️ Límite (requiere limpieza total) |
| `mixtral:8x7b-q2` | 15 GB | ~16 GB | Q2_K | ❌ Excede RAM disponible |

### Modelos realistas al límite para este sistema específico

| Modelo | Tamaño | RAM necesaria | Notas |
|---|---|---|---|
| `mistral:7b` (Q8) | 7.7 GB | ~8.5 GB | Máxima calidad de 7B |
| `codellama:13b` (Q4_K_M) | 7.4 GB | ~8.0 GB | Mejor modelo de código posible |
| `qwen2.5-coder:14b` (Q4_K_M) | 8.9 GB | ~9.5 GB | Requiere limpieza total del sistema |

### Procedimiento para ejecutar modelos al límite
```powershell
# 1. Ejecutar limpieza agresiva
.\\scripts\\cleanup_for_ollama.ps1 -Aggressive

# 2. Verificar que hay al menos 9 GB libres
$freeGB = [math]::Round((Get-WmiObject Win32_OperatingSystem).FreePhysicalMemory/1MB, 1)
Write-Host "RAM libre: $freeGB GB"

# 3. Aumentar memoria virtual (swap) como respaldo
# Panel de Control → Sistema → Configuración avanzada → Rendimiento → Memoria virtual
# Recomendar: 16 GB de archivo de paginación en SSD

# 4. Ejecutar modelo con prioridad alta
ollama run codellama:13b
```

---

## Matriz Consolidada de Decisión

```
┌─────────────────────────────────────────────────────────────────┐
│              MATRIZ DE SELECCIÓN DE MODELO OLLAMA               │
│                  Sistema: Ryzen 5 7530U / 15.7 GB               │
├─────────────────┬───────────────────────────────────────────────┤
│ RAM Libre        │ Modelo recomendado                            │
├─────────────────┼───────────────────────────────────────────────┤
│ < 2.5 GB        │ ❌ Limpiar primero                            │
│ 2.5 – 3.5 GB    │ tinyllama:1.1b, qwen2:1.5b                   │
│ 3.5 – 5.0 GB    │ phi3:mini, gemma:2b, llama3.2:3b             │
│ 5.0 – 6.5 GB    │ mistral:7b, qwen2.5-coder:7b (Q4)           │
│ 6.5 – 8.0 GB    │ mistral:7b (Q5), deepseek-coder:6.7b        │
│ 8.0 – 9.0 GB    │ mistral:7b (Q8), codellama:13b (Q4)         │
│ > 9.0 GB        │ qwen2.5-coder:14b (Q4), codellama:13b (Q5)  │
└─────────────────┴───────────────────────────────────────────────┘
```

---

## Modelos Ya Instalados en este Sistema

| Modelo | Escenario | Estado |
|---|---|---|
| `phi3:mini` | Ligero | ✅ Instalado |
| `qwen2.5-coder:7b` | Eficiente | ✅ Instalado |
| `mistral:7b` | Eficiente / Máximo | ✅ Instalado |

---

## Notas Finales sobre CPU-Only en AMD Ryzen 5 7530U

1. **Sin aceleración GPU:** Todo el procesamiento ocurre en CPU. La velocidad de generación es 5–10x más lenta que con GPU dedicada.
2. **Calor y throttling:** El Ryzen 5 7530U puede hacer throttling después de 10–15 minutos de carga sostenida. Usar un cooler pad o asegurar ventilación.
3. **AVX2/AVX512:** Ollama aprovecha instrucciones vectoriales del CPU. El Ryzen 5 7530U soporta AVX2, lo cual mejora la velocidad de inferencia.
4. **Modelo preloaded:** Una vez cargado en RAM, el modelo permanece en memoria entre llamadas. No cerrar Ollama entre queries para evitar recargas costosas.
5. **Context window:** Mantener el contexto (num_ctx) en 2048–4096 tokens para modelos 7B en este sistema. Ventanas más grandes aumentan drásticamente el uso de RAM.

```bash
# Ejecutar con contexto reducido para conservar RAM
ollama run mistral:7b --num-ctx 2048
```
