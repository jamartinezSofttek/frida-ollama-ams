# Herramientas y Estrategias de Ahorro de Tokens para AMS L3
## Integración Ollama + FRIDA – Guía Completa

---

## Presupuesto de Tokens FRIDA

```
Límite diario:          130,000 tokens
Tokens por consulta típica (sin optimizar):  3,000 – 8,000
Consultas posibles sin estrategia:           16 – 43 consultas/día

Tokens por consulta (con relay Ollama):      300 – 800
Consultas posibles con estrategia:           162 – 433 consultas/día

Objetivo: Usar FRIDA SOLO para tareas que requieren su capacidad superior.
          Ollama gestiona el 80-90% del trabajo preparatorio.
```

---

## Sección 1 – Kit de Herramientas para AMS L3

### 1.1 Ollama CLI (Core)

**Qué es:** Interfaz de línea de comandos para ejecutar modelos de IA localmente.

```bash
# Comandos esenciales
ollama list                          # Ver modelos instalados
ollama run phi3:mini                 # Iniciar chat interactivo
ollama run mistral:7b "tu pregunta"  # Query de una sola vez
ollama serve                         # Iniciar servidor API en background
ollama ps                            # Ver modelos actualmente en memoria
ollama stop mistral:7b               # Descargar modelo de RAM
ollama show mistral:7b               # Ver detalles del modelo

# Parámetros de rendimiento
ollama run mistral:7b --num-ctx 2048    # Limitar ventana de contexto (ahorra RAM)
ollama run phi3:mini --num-predict 500  # Limitar longitud de respuesta
```

**Cuándo usar:** Para todas las tareas preparatorias, análisis previo, generación de borradores, y pre-procesamiento de contexto antes de FRIDA.

---

### 1.2 Open WebUI (Interfaz Gráfica Local)

**Qué es:** Interfaz web tipo ChatGPT que se conecta a tu Ollama local. Permite historial de conversaciones, múltiples modelos, y carga de archivos.

**Instalación:**
```bash
# Opción 1: Con Docker (recomendado)
docker run -d -p 3000:8080 --add-host=host.docker.internal:host-gateway \
  -v open-webui:/app/backend/data --name open-webui --restart always \
  ghcr.io/open-webui/open-webui:main

# Opción 2: Con pip (sin Docker)
pip install open-webui
open-webui serve
```

**Acceso:** http://localhost:3000

**Ventajas para AMS L3:**
- Historial persistente de conversaciones por proyecto/incidente
- Posibilidad de cargar archivos de logs directamente
- Cambio rápido entre modelos en la misma interfaz
- Templates de prompts guardados (System Prompts)
- Exportar conversaciones como Markdown para documentación

**Configurar modelo por defecto:**
```
Settings → Models → Default Model: phi3:mini
(Para triaje rápido siempre disponible)
```

---

### 1.3 Process Hacker 2 (Monitor de Recursos)

**Qué es:** Alternativa avanzada al Task Manager de Windows, gratuita y open source.

**Descarga:** https://processhacker.sourceforge.io/

**Funcionalidades clave para Ollama:**
- Vista de árbol de procesos (identificar procesos padre → hijo)
- Columna de RAM física vs virtual (crítico para saber RAM real disponible)
- Terminar procesos del sistema protegidos con un clic
- Ver uso de CPU por núcleo (monitorear qué núcleos usa Ollama)
- Gráficas en tiempo real de RAM y CPU
- Buscar qué proceso usa un archivo específico

**Configuración recomendada:**
```
Ver → Columnas → Agregar: Working Set, Virtual Size, CPU, I/O Total
Ordenar por: Working Set (descendente)
```

---

### 1.4 PowerShell Scripts de Automatización

**Ubicación:** `scripts/` en este repositorio

#### Script 1: `cleanup_for_ollama.ps1`
```powershell
# ============================================
# cleanup_for_ollama.ps1
# Limpieza de procesos para liberar RAM
# Uso: .\scripts\cleanup_for_ollama.ps1 [-Aggressive]
# ============================================
param([switch]$Aggressive)

function Get-FreeRAM {
    return [math]::Round((Get-WmiObject Win32_OperatingSystem).FreePhysicalMemory/1KB, 0)
}

$ramBefore = Get-FreeRAM
Write-Host "=== OLLAMA CLEANUP SCRIPT ===" -ForegroundColor Cyan
Write-Host "RAM libre inicial: $ramBefore MB" -ForegroundColor Yellow

# Procesos siempre seguros para terminar
$safeProcs = @(
    "OneDriveSetup", "OfficeClickToRun", "MicrosoftEdgeUpdate",
    "GoogleUpdate", "WerFault", "CompatTelRunner",
    "Spotify", "Discord", "Steam", "AnyDesk", "TeamViewer", "Skype"
)

# Procesos adicionales en modo agresivo
$aggressiveProcs = @("Teams", "OneDrive", "Slack", "Zoom", "outlook")

$toKill = $safeProcs
if ($Aggressive) { $toKill += $aggressiveProcs }

foreach ($proc in $toKill) {
    $p = Get-Process -Name $proc -ErrorAction SilentlyContinue
    if ($p) {
        Stop-Process -Name $proc -Force -ErrorAction SilentlyContinue
        Write-Host "  ✓ Terminado: $proc" -ForegroundColor Green
    }
}

# Detener servicios de baja prioridad
$services = @("SysMain", "WSearch", "DiagTrack")
foreach ($svc in $services) {
    $s = Get-Service -Name $svc -ErrorAction SilentlyContinue
    if ($s -and $s.Status -eq "Running") {
        Stop-Service -Name $svc -Force -ErrorAction SilentlyContinue
        Write-Host "  ✓ Servicio detenido: $svc" -ForegroundColor Green
    }
}

Start-Sleep -Seconds 2
$ramAfter = Get-FreeRAM
$freed = $ramAfter - $ramBefore

Write-Host "`nRAM libre final:   $ramAfter MB" -ForegroundColor Green
Write-Host "RAM liberada:      $freed MB" -ForegroundColor Cyan

if ($ramAfter -gt 8000) {
    Write-Host "`n✅ Listo para modelos 7B+ (mistral, qwen2.5-coder)" -ForegroundColor Green
} elseif ($ramAfter -gt 4000) {
    Write-Host "`n⚡ Listo para modelos eficientes (phi3, llama3.2:3b)" -ForegroundColor Yellow
} else {
    Write-Host "`n⚠️  RAM limitada. Cerrar más aplicaciones manualmente." -ForegroundColor Red
}
```

#### Script 2: `check_system_for_ollama.ps1`
```powershell
# ============================================
# check_system_for_ollama.ps1
# Diagnóstico rápido del sistema pre-Ollama
# ============================================
$os = Get-WmiObject Win32_OperatingSystem
$freeRAM = [math]::Round($os.FreePhysicalMemory/1KB, 0)
$totalRAM = [math]::Round($os.TotalVisibleMemorySize/1KB, 0)
$freeGB = [math]::Round($freeRAM/1024, 1)
$cpuLoad = (Get-CimInstance Win32_Processor).LoadPercentage

Write-Host "╔══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     DIAGNÓSTICO PRE-OLLAMA AMS L3    ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host "RAM Libre:  $freeRAM MB ($freeGB GB)"
Write-Host "RAM Total:  $totalRAM MB"
Write-Host "Carga CPU:  $cpuLoad%"
Write-Host ""

# Modelos disponibles según RAM
$models = ollama list 2>$null
Write-Host "Modelos instalados:" -ForegroundColor Yellow
ollama list

Write-Host ""
if ($freeGB -ge 9) {
    Write-Host "✅ ÓPTIMO: codellama:13b-q4, mistral:7b-q8, qwen2.5-coder:14b" -ForegroundColor Green
} elseif ($freeGB -ge 5) {
    Write-Host "⚡ EFICIENTE: mistral:7b, qwen2.5-coder:7b, deepseek-coder:6.7b" -ForegroundColor Yellow
} elseif ($freeGB -ge 2.5) {
    Write-Host "🔵 LIGERO: phi3:mini, gemma:2b, llama3.2:3b" -ForegroundColor Blue
} else {
    Write-Host "❌ INSUFICIENTE: Ejecutar cleanup_for_ollama.ps1 primero" -ForegroundColor Red
}
```

#### Script 3: `restore_services.ps1`
```powershell
# ============================================
# restore_services.ps1
# Restaurar servicios después de usar Ollama
# ============================================
$services = @("SysMain", "WSearch", "DiagTrack")
foreach ($svc in $services) {
    Start-Service -Name $svc -ErrorAction SilentlyContinue
    Write-Host "✓ Servicio restaurado: $svc" -ForegroundColor Green
}

# Detener Ollama si no se necesita más
ollama stop phi3:mini 2>$null
ollama stop mistral:7b 2>$null
ollama stop qwen2.5-coder:7b 2>$null

Write-Host "`n✅ Sistema restaurado al estado normal." -ForegroundColor Green
```

---

### 1.5 ollama-python (Integración Programática)

**Instalación:**
```bash
pip install ollama
```

**Script base para AMS L3:**
```python
# ollama_ams_helper.py
import ollama
import sys

def analyze_log(log_content: str, model: str = "phi3:mini") -> str:
    """Analiza logs de producción y retorna clasificación."""
    prompt = f"""Analiza este log de producción y responde en formato JSON:
    {{
        "severidad": "CRITICO|ADVERTENCIA|INFORMATIVO|FALSO_POSITIVO",
        "componente_afectado": "nombre",
        "causa_probable": "descripcion breve",
        "accion_inmediata": "que hacer ahora"
    }}
    
    LOG:
    {log_content}"""
    
    response = ollama.generate(model=model, prompt=prompt)
    return response['response']

def condense_for_frida(context: str, model: str = "phi3:mini") -> str:
    """Condensa contexto largo para minimizar tokens en FRIDA."""
    prompt = f"""Eres un condensador técnico. Extrae SOLO la información esencial de este texto.
    Máximo 300 palabras. Mantén: errores específicos, valores numéricos, nombres de componentes.
    Elimina: timestamps repetidos, líneas duplicadas, metadatos irrelevantes.
    
    TEXTO:
    {context}"""
    
    response = ollama.generate(model=model, prompt=prompt)
    return response['response']

def generate_rca_draft(incident_data: dict, model: str = "mistral:7b") -> str:
    """Genera borrador de RCA a partir de datos del incidente."""
    prompt = f"""Genera un RCA ejecutivo profesional con estos datos:
    Incidente: {incident_data.get('title', 'N/A')}
    Duración: {incident_data.get('duration', 'N/A')}
    Sistemas: {incident_data.get('systems', 'N/A')}
    Causa raíz: {incident_data.get('root_cause', 'N/A')}
    Acciones tomadas: {incident_data.get('actions', 'N/A')}
    
    Formato: Markdown estructurado con secciones Executive Summary, Timeline, Root Cause, Prevention."""
    
    response = ollama.generate(model=model, prompt=prompt)
    return response['response']

if __name__ == "__main__":
    # Modo de uso rápido: python ollama_ams_helper.py condense "texto largo..."
    if len(sys.argv) > 2:
        action = sys.argv[1]
        content = sys.argv[2]
        
        if action == "condense":
            print(condense_for_frida(content))
        elif action == "analyze":
            print(analyze_log(content))
```

---

### 1.6 Herramientas de Monitoreo Complementarias

| Herramienta | Uso | Descarga |
|---|---|---|
| **Process Hacker 2** | Monitor avanzado de procesos y RAM | processhacker.sourceforge.io |
| **HWiNFO64** | Temperatura CPU/GPU, throttling | hwinfo.com |
| **GPU-Z** | Monitoreo GPU y VRAM (aunque sea iGPU) | techpowerup.com/gpuz |
| **RAMMap** | Análisis detallado de uso de RAM por tipo | docs.microsoft.com |
| **Windhawk** | Optimizaciones de Windows sin registry | windhawk.net |
| **NTLite** | Deshabilitar servicios Windows innecesarios | ntlite.com |

---

## Sección 2 – Estrategias de Ahorro de Tokens FRIDA

### 2.1 Jerarquía de Decisión: ¿Ollama o FRIDA?

```
┌─────────────────────────────────────────────────────────────────┐
│                 ÁRBOL DE DECISIÓN OLLAMA vs FRIDA               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ¿La tarea requiere información actualizada (post-2024)?        │
│  ├─ SÍ → FRIDA                                                  │
│  └─ NO → ¿Es una tarea con contexto muy largo (>2000 tokens)?  │
│           ├─ SÍ → Condensar con Ollama → luego FRIDA            │
│           └─ NO → ¿Requiere conocimiento especializado profundo?│
│                    ├─ SÍ → FRIDA                                │
│                    └─ NO → OLLAMA (local, gratis)               │
│                                                                  │
│  Tareas 100% para Ollama:                                       │
│  ✓ Análisis de logs y stack traces                              │
│  ✓ Generación de borradores (RCA, runbooks, CRs)               │
│  ✓ Code review y análisis de código                             │
│  ✓ Clasificación y triaje de incidentes                         │
│  ✓ Explicación de código legacy                                 │
│  ✓ Generación de scripts y comandos                             │
│  ✓ Resúmenes y condensación de contexto                         │
│                                                                  │
│  Tareas para FRIDA (después de preprocesar con Ollama):         │
│  ★ Arquitectura de solución compleja nueva                      │
│  ★ Decisiones de diseño con múltiples trade-offs               │
│  ★ Conocimiento de herramientas/frameworks específicos actuales │
│  ★ Validación final de análisis crítico (P1 escalado)           │
│  ★ Generación de código complejo de producción                  │
└─────────────────────────────────────────────────────────────────┘
```

---

### 2.2 Plantillas de Prompts Eficientes para FRIDA

Cuando sea necesario usar FRIDA, usar estas plantillas estructuradas que maximizan la información por token:

#### Template Universal AMS L3
```
CONTEXTO: [2-3 líneas máximo sobre el sistema y situación]
PROBLEMA: [1 oración clara del problema específico]
YA INTENTÉ: [Lista de 3-5 puntos de lo que ya se probó]
PREGUNTA: [La pregunta específica y concisa]
FORMATO ESPERADO: [Bullets / Código / Tabla / Párrafo]
```

#### Template para Análisis de Incidente (ya pre-procesado por Ollama)
```
INCIDENTE: [Título - ID - Prioridad]
RESUMEN TÉCNICO: [150 palabras del análisis de Ollama]
HIPÓTESIS DESCARTADAS: [Lo que ya se probó]
CONSULTA: ¿Qué otros vectores de causa raíz debería investigar?
```

#### Template para Revisión de Código Complejo
```
LENGUAJE: [Java/Python/.NET/etc]
CONTEXTO: [Qué hace este componente en 2 líneas]
ANÁLISIS PREVIO DE OLLAMA: [Resumen de lo que Ollama ya detectó]
CÓDIGO: [Solo el fragmento relevante, < 50 líneas]
PREGUNTA: [Específica sobre el código]
```

---

### 2.3 Asignación del Presupuesto Diario de Tokens

```
PRESUPUESTO TOTAL DIARIO: 130,000 tokens

Distribución recomendada:
┌��───────────────────────────────────────────────────┐
│ Reserva de emergencia (P1 críticos):    20,000 (15%)│
│ Análisis técnico complejo:              40,000 (31%)│
│ Code review y arquitectura:             30,000 (23%)│
│ Documentación y comunicaciones:         20,000 (15%)│
│ Buffer libre / aprendizaje:             20,000 (15%)│
└────────────────────────────────────────────────────┘

Reglas de uso:
1. NUNCA pegar logs o código sin condensar con Ollama primero
2. Reservar 20,000 tokens hasta final del turno (para emergencias)
3. Si el presupuesto baja de 30,000 tokens, cambiar a modo Ollama-only
4. Usar FRIDA en modo "una consulta bien preparada" vs. múltiples iteraciones
```

---

### 2.4 Biblioteca de Prompts Reutilizables AMS

Guardar en `prompts/` como archivos `.txt` para reutilizar sin reescribir:

```
prompts/
├── triage_incidente.txt
├── analisis_rca.txt
├── generar_runbook.txt
├── code_review_seguridad.txt
├── comunicado_cliente.txt
├── condensar_logs.txt
├── generar_change_request.txt
└── analizar_query_sql.txt
```

#### Ejemplo: `prompts/condensar_logs.txt`
```
Eres un condensador técnico especializado en logs de aplicaciones enterprise.
Tu tarea:
1. Identificar los eventos críticos y errores únicos (eliminar duplicados)
2. Ordenar cronológicamente los eventos importantes
3. Destacar: excepciones, timeouts, códigos de error HTTP 5xx, OOM, deadlocks
4. Ignorar: logs INFO rutinarios, health checks exitosos, métricas normales
5. Producir un resumen de máximo 200 palabras

Responde SOLO con el resumen, sin explicaciones adicionales.

LOGS:
[PEGAR AQUÍ]
```

---

### 2.5 Flujo de Trabajo Integrado Diario

```
┌─────────────────────────────────────────────────────────────────┐
│                  FLUJO DIARIO AMS L3 CON OLLAMA                 │
└─────────────────────────────────────────────────────────────────┘

08:00 – INICIO DE TURNO
  1. Ejecutar: .\scripts\check_system_for_ollama.ps1
  2. Ejecutar: .\scripts\cleanup_for_ollama.ps1
  3. Iniciar: ollama run phi3:mini  (modo triaje activo)

DURANTE EL TURNO – Flujo por tipo de tarea:

  ALERTA/INCIDENTE ENTRANTE:
  ├─ Paso 1: Pegar error en phi3:mini → clasificación inicial (< 15 seg)
  ├─ Paso 2: Si requiere análisis profundo → cambiar a mistral:7b
  ├─ Paso 3: Si hay código involucrado → cambiar a qwen2.5-coder:7b
  └─ Paso 4: Si necesitas FRIDA → condensar con Ollama primero

  REDACCIÓN DE DOCUMENTOS:
  ├─ Paso 1: Usar mistral:7b para generar borrador completo
  ├─ Paso 2: Revisar y ajustar el borrador manualmente
  └─ Paso 3: Si necesitas validación → enviar borrador resumido a FRIDA

  CONSULTA TÉCNICA COMPLEJA:
  ├─ Paso 1: Intentar con mistral:7b o qwen2.5-coder:7b
  ├─ Paso 2: Si Ollama no tiene la respuesta → preparar prompt para FRIDA
  ├─ Paso 3: Condensar contexto con Ollama (< 500 tokens)
  └─ Paso 4: Enviar a FRIDA con template estructurado

  VERIFICAR PRESUPUESTO (cada 2 horas):
  └─ Si < 30,000 tokens restantes → modo Ollama-only hasta final del turno

17:00/18:00 – FIN DE TURNO
  1. Exportar conversaciones importantes de Open WebUI
  2. Ejecutar: .\scripts\restore_services.ps1
  3. Registrar casos donde Ollama no fue suficiente (para mejorar estrategia)
```

---

## Sección 3 – Configuración Avanzada de Ollama

### 3.1 Variables de Entorno Clave

```powershell
# Configurar en PowerShell o en variables de entorno del sistema
$env:OLLAMA_NUM_THREAD = 8           # Hilos CPU (dejar 4 para el sistema)
$env:OLLAMA_MAX_LOADED_MODELS = 1    # Solo 1 modelo en RAM a la vez
$env:OLLAMA_KEEP_ALIVE = "10m"       # Descargar modelo de RAM tras 10 min inactivo
$env:OLLAMA_HOST = "0.0.0.0:11434"  # Escuchar en todas las interfaces (para Open WebUI)
$env:OLLAMA_MODELS = "D:\ollama_models"  # Mover modelos a disco con más espacio
```

**Configurar permanentemente:**
```powershell
# Agregar a variables de entorno del sistema (requiere reinicio de sesión)
[System.Environment]::SetEnvironmentVariable("OLLAMA_NUM_THREAD", "8", "User")
[System.Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "10m", "User")
[System.Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS", "1", "User")
```

### 3.2 Archivo Modelfile para Personalización AMS

```dockerfile
# ams_triage.modelfile
FROM phi3:mini

SYSTEM """Eres un asistente técnico especializado en Application Maintenance Engineering (AMS) L3.
Tu rol es analizar incidentes, clasificar errores, y proporcionar análisis técnico conciso.

Reglas de respuesta:
- Sé directo y técnico, sin explicaciones innecesarias
- Prioriza siempre la acción correctiva inmediata
- Clasifica la severidad como: CRÍTICO/ALTO/MEDIO/BAJO
- Formato preferido: puntos numerados o JSON estructurado
- Idioma: responde en el mismo idioma de la pregunta"""

PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER num_ctx 2048
```

```bash
# Crear modelo personalizado
ollama create ams-triage -f ams_triage.modelfile
ollama run ams-triage
```

---

## Sección 4 – Métricas de Éxito

### 4.1 KPIs de Optimización Semanal

Registrar semanalmente para medir el impacto de la estrategia:

| Métrica | Objetivo | Cómo medir |
|---|---|---|
| Tokens FRIDA consumidos/día | < 80,000 (margen 38%) | Dashboard FRIDA |
| % consultas resueltas con Ollama | > 70% | Registro manual |
| Tiempo promedio triaje inicial | < 2 minutos | Registro de incidentes |
| Borradores de RCA generados/sem | > 3 | Conteo de documentos |
| RAM libre antes de iniciar Ollama | > 6 GB | Script check_system |

### 4.2 Señales de que la Estrategia está Funcionando

✅ Terminas el turno con >30,000 tokens FRIDA restantes  
✅ El análisis inicial de incidentes toma < 5 minutos (vs. 20-30 min sin Ollama)  
✅ Los borradores de RCA/runbooks están listos antes de la reunión post-incidente  
✅ Menos interrupciones por "necesito consultar a FRIDA para esto"  
✅ El sistema responde normalmente mientras Ollama corre en background  

---

## Resumen de Referencia Rápida

```
╔═══════════════════════════════════════════════════════════════╗
║           CHEAT SHEET AMS L3 – OLLAMA + FRIDA                ║
╠═══════════════════════════════════════════════════════════════╣
║ TAREA                    │ HERRAMIENTA │ MODELO              ║
╠═══════════════════════════════════════════════════════════════╣
║ Triaje de alertas/logs   │ Ollama      │ phi3:mini           ║
║ Análisis RCA             │ Ollama      │ mistral:7b          ║
║ Code review / debugging  │ Ollama      │ qwen2.5-coder:7b    ║
║ Redacción runbooks/RCA   │ Ollama      │ mistral:7b          ║
║ Condensar para FRIDA     │ Ollama      │ phi3:mini           ║
║ Arquitectura compleja    │ FRIDA       │ N/A (post-Ollama)   ║
║ Decisiones críticas P1   │ FRIDA       │ N/A (post-Ollama)   ║
╠═══════════════════════════════════════════════════════════════╣
║ COMANDOS RÁPIDOS                                              ║
║ Limpieza:    .\scripts\cleanup_for_ollama.ps1               ║
║ Diagnóstico: .\scripts\check_system_for_ollama.ps1          ║
║ Triaje:      ollama run phi3:mini                            ║
║ Análisis:    ollama run mistral:7b                           ║
║ Código:      ollama run qwen2.5-coder:7b                    ║
║ Restaurar:   .\scripts\restore_services.ps1                 ║
╠═══════════════════════════════════════════════════════════════╣
║ REGLA DE ORO: Ollama primero, FRIDA solo para lo esencial   ║
╚═══════════════════════════════════════════════════════════════╝
```
