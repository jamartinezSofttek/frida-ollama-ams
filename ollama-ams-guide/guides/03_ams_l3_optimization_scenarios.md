# Escenarios de Optimización de Ollama para AMS L3
## Application Maintenance Engineer – Escenarios de Uso Avanzados

---

## Contexto del Rol AMS L3

Un Application Maintenance Engineer L3 en AMS gestiona diariamente:
- Triaje y resolución de incidentes P1/P2/P3
- Análisis de causa raíz (RCA) y documentación post-mortem
- Revisión de código en cambios de emergencia (hotfixes)
- Redacción de runbooks, procedimientos y change requests
- Comunicación técnica con clientes y equipos de desarrollo
- Monitoreo de aplicaciones y análisis de logs en producción

El uso de Ollama como asistente **local y sin costo de tokens** maximiza la productividad sin consumir el presupuesto diario de FRIDA (130,000 tokens/día).

---

## Escenario A – Modo Triaje de Incidentes

### Descripción
Mantener un modelo ligero **siempre activo en segundo plano** para análisis inmediato de errores, logs y mensajes de alerta. Respuesta en segundos, sin necesidad de abrir FRIDA.

### Trigger de activación
- Alerta entrante en monitoring (Dynatrace, Datadog, Splunk, etc.)
- Ticket P1/P2 creado en ServiceNow/Jira
- Error crítico en logs de producción

### Modelo recomendado
```
phi3:mini  (2.2 GB RAM)
```
*Razón: Bajo consumo, siempre disponible, suficiente para clasificación y análisis inicial.*

### Perfil de recursos
```
RAM consumida:    ~2.5 GB
CPU en reposo:    ~0% (modelo en caché, sin queries activas)
CPU en query:     ~60-80% por 5-15 segundos
Impacto laboral:  Mínimo — puede correr mientras se usa el navegador y VDI
```

### Flujo de trabajo
```
1. Iniciar modelo al comenzar turno:
   ollama run phi3:mini

2. Pegar el error/log directamente en el prompt:
   >>> Analiza este error de Java y dime: causa probable, componente afectado, prioridad sugerida:
   [PEGAR STACK TRACE AQUÍ]

3. Obtener clasificación inicial en < 15 segundos

4. Enrutar a equipo correcto o escalar si es P1
```

### Prompts plantilla para triaje
```
# Clasificación de severidad
"Clasifica este incidente como P1/P2/P3/P4 y justifica brevemente: [DESCRIPCIÓN]"

# Análisis de stack trace
"Identifica la causa raíz probable de este error. Lista: 1) causa, 2) componente, 3) siguiente acción:
[STACK TRACE]"

# Análisis de mensaje de log
"Este log muestra un problema. ¿Qué ocurrió y qué debo revisar primero?
[LOG LINES]"

# Identificación de patrón de error
"¿Este error es típico de problemas de: memoria, conexión BD, timeout de red, o lógica de negocio?
[ERROR MESSAGE]"
```

### Configuración de inicio automático
```powershell
# Agregar al perfil de PowerShell ($PROFILE) para iniciar con el turno
# Inicio silencioso de Ollama en background
Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
Write-Host "🟢 Ollama iniciado en background – Modelo de triaje disponible"
Write-Host "   Usar: ollama run phi3:mini"
```

---

## Escenario B – Modo Análisis Profundo (Deep RCA)

### Descripción
Para incidentes complejos que requieren **análisis técnico exhaustivo**: correlación de múltiples logs, identificación de patrones históricos, análisis de dependencias de sistema.

### Trigger de activación
- Incidente P1 sin causa raíz identificada en 30 minutos
- Incidente recurrente que requiere análisis de patrón
- Post-mortem de incidente crítico
- Investigación de degradación de performance

### Modelo recomendado
```
mistral:7b  (Q4_K_M, ~5 GB RAM)
```
*Razón: Excelente capacidad de razonamiento, síntesis de información compleja, generación de hipótesis.*

### Perfil de recursos
```
RAM consumida:    ~5.0 GB
CPU en query:     ~90-100% por 30-120 segundos
Impacto laboral:  Moderado — cerrar Teams, OneDrive, apps no críticas
Tiempo de carga:  ~15-25 segundos (primera vez)
```

### Protocolo de activación
```powershell
# 1. Ejecutar limpieza rápida
$procs = @("Teams", "OneDrive", "Spotify", "Discord", "Slack")
foreach ($p in $procs) { Stop-Process -Name $p -Force -ErrorAction SilentlyContinue }

# 2. Verificar RAM disponible
$freeGB = [math]::Round((Get-WmiObject Win32_OperatingSystem).FreePhysicalMemory/1MB, 1)
Write-Host "RAM libre para análisis: $freeGB GB"

# 3. Lanzar modelo de análisis
ollama run mistral:7b
```

### Flujo de análisis profundo
```
Paso 1 – Contexto del sistema
>>> "Tengo un sistema [NOMBRE] en [AMBIENTE]. Tecnologías: [STACK]. 
    El incidente ocurrió a las [HORA]. Síntoma: [DESCRIPCIÓN]"

Paso 2 – Análisis de logs
>>> "Analiza estos logs cronológicamente e identifica la secuencia de eventos que llevó al fallo:
    [LOGS]"

Paso 3 – Hipótesis de causa raíz
>>> "Basado en los logs anteriores, lista las 3 hipótesis más probables de causa raíz, 
    ordenadas por probabilidad. Para cada una, indica qué evidencia confirmaría o descartaría."

Paso 4 – Plan de remediación
>>> "Para la hipótesis #1, describe: 
    a) Pasos de remediación inmediata
    b) Fix permanente recomendado
    c) Validación de que el fix funcionó"

Paso 5 – Documentación RCA
>>> "Genera el borrador de RCA en formato ejecutivo con: 
    Timeline, Causa Raíz, Impacto, Acciones tomadas, Prevención futura"
```

---

## Escenario C – Modo Redacción de Documentación

### Descripción
Usar Ollama para **generar y refinar documentación técnica**: RCAs, runbooks, change requests, notas de reunión, comunicados a cliente. Reduce tiempo de redacción de 30-60 min a 5-10 min.

### Trigger de activación
- Post-incidente que requiere RCA formal
- Necesidad de runbook para procedimiento nuevo/modificado
- Change request para ServiceNow/ITSM
- Comunicado de impacto a cliente (en inglés o español)

### Modelo recomendado
```
mistral:7b  o  qwen2.5-coder:7b (para documentación técnica con código)
```

### Plantillas de documentación AMS

#### Template: RCA Ejecutivo
```
Prompt:
"Genera un RCA ejecutivo con los siguientes datos:
- Incidente: [ID/TÍTULO]
- Fecha/Hora inicio: [TIMESTAMP]
- Duración: [X minutos/horas]
- Sistemas afectados: [LISTA]
- Impacto al negocio: [DESCRIPCIÓN]
- Causa raíz identificada: [CAUSA]
- Acciones de remediación tomadas: [LISTA]
- Acciones preventivas: [LISTA]

Formato: Párrafos concisos, lenguaje técnico pero comprensible para management."
```

#### Template: Runbook de Procedimiento
```
Prompt:
"Crea un runbook técnico para el procedimiento: [NOMBRE DEL PROCEDIMIENTO]
Contexto: [DESCRIPCIÓN DEL SISTEMA]
Incluir:
1. Pre-requisitos y permisos necesarios
2. Pasos numerados con comandos exactos
3. Validaciones en cada paso crítico
4. Qué hacer si algo falla (rollback)
5. Criterios de éxito final
Formato: Markdown con bloques de código para todos los comandos."
```

#### Template: Change Request
```
Prompt:
"Redacta la descripción técnica para un Change Request con:
- Cambio a realizar: [DESCRIPCIÓN]
- Razón del cambio: [JUSTIFICACIÓN]
- Sistemas impactados: [LISTA]
- Riesgo identificado: [NIVEL Y DESCRIPCIÓN]
- Plan de rollback: [PASOS]
- Ventana de mantenimiento sugerida: [HORARIO]
Tono: Técnico, formal, orientado a aprobación de CAB."
```

#### Template: Comunicado a Cliente
```
Prompt:
"Redacta un comunicado profesional para el cliente sobre:
- Incidente: [DESCRIPCIÓN BREVE]
- Impacto experimentado: [QUÉ AFECTÓ AL USUARIO]
- Estado actual: [RESUELTO/EN PROGRESO]
- Causa (lenguaje no técnico): [EXPLICACIÓN SIMPLE]
- Próximos pasos: [ACCIONES]
Tono: Empático, profesional, sin jerga técnica."
```

### Perfil de recursos
```
RAM consumida:    ~5.0 GB
CPU en query:     ~80-90% durante generación (60-90 segundos)
Resultado típico: Borrador completo listo para revisión mínima
Ahorro de tiempo: 25-45 minutos por documento
```

---

## Escenario D – Modo Revisión de Código y Parches

### Descripción
Revisión técnica de código para **hotfixes y cambios de emergencia** en producción. Detectar bugs, vulnerabilidades, y problemas de rendimiento antes del deploy.

### Trigger de activación
- Hotfix urgente que requiere revisión rápida
- Code review de cambio de emergencia (P1/P2)
- Validación de script de automatización o parche de BD

### Modelo recomendado
```
qwen2.5-coder:7b  (especializado en código, ~5.2 GB RAM)
```
*Razón: Entrenado específicamente en código, mejor comprensión de patrones de bugs y seguridad.*

### Flujo de revisión
```
# Revisión de seguridad
>>> "Revisa este [LENGUAJE] desde perspectiva de seguridad. 
    Identifica: SQL injection, XSS, hardcoded credentials, permisos incorrectos:
    [CÓDIGO]"

# Revisión de lógica
>>> "Analiza esta función. ¿Tiene bugs, edge cases no manejados, o problemas de rendimiento?
    [CÓDIGO]"

# Revisión de impacto en BD
>>> "Este SQL se ejecutará en producción. ¿Hay riesgo de bloqueo de tablas, full scan, 
    o pérdida de datos? Sugiere optimizaciones:
    [SQL QUERY]"

# Revisión de script de bash/PowerShell
>>> "Revisa este script que se ejecutará en [N] servidores de producción.
    ¿Es seguro ejecutarlo? ¿Qué podría salir mal?
    [SCRIPT]"
```

### Perfil de recursos
```
RAM consumida:    ~5.2 GB
CPU en query:     ~85-95% durante análisis
Tiempo respuesta: 20-60 segundos (dependiendo del tamaño del código)
Valor agregado:   Segunda opinión técnica en segundos, sin esperar a otro L3
```

---

## Escenario E – Modo Relay de Ahorro de Tokens (FRIDA Bridge)

### Descripción
El escenario más crítico para el presupuesto diario: usar Ollama como **preprocesador y condensador** de contexto antes de enviar a FRIDA. En lugar de pegar 10,000 tokens de logs a FRIDA, Ollama los resume a 500 tokens con la información esencial.

### Problema que resuelve
```
SIN RELAY:
Usuario → FRIDA
[5,000 tokens de logs] + [500 tokens de pregunta] = 5,500 tokens consumidos

CON RELAY:
Usuario → Ollama (local, gratis) → resume a 500 tokens esenciales
Usuario → FRIDA
[500 tokens de resumen] + [200 tokens de pregunta] = 700 tokens consumidos

AHORRO: ~4,800 tokens por consulta (87% de reducción)
```

### Modelo recomendado
```
phi3:mini  o  mistral:7b  (según complejidad del contexto)
```

### Flujo de trabajo del relay

#### Paso 1 – Condensar contexto con Ollama
```
>>> "Eres un condensador técnico. Tu tarea es:
    1. Extraer SOLO la información técnicamente relevante de este texto
    2. Eliminar timestamps redundantes, líneas repetidas, y metadatos innecesarios
    3. Producir un resumen de máximo 300 palabras
    4. Mantener: errores específicos, valores numéricos clave, nombres de componentes
    
    TEXTO A CONDENSAR:
    [PEGAR LOGS / CONTEXTO LARGO]"
```

#### Paso 2 – Estructurar la pregunta para FRIDA
```
>>> "Ahora convierte este resumen en una pregunta técnica estructurada para un experto.
    La pregunta debe ser concisa, incluir el contexto mínimo necesario, y pedir
    una respuesta específica y accionable."
```

#### Paso 3 – Enviar a FRIDA solo el prompt optimizado
```
El resultado del Paso 2 es lo que va a FRIDA.
Típicamente: 200-400 tokens vs. 3,000-10,000 tokens originales.
```

### Calculadora de ahorro de tokens
```
Presupuesto diario FRIDA:     130,000 tokens
Consumo promedio sin relay:    5,000 tokens/consulta
Consultas posibles:            26 consultas/día

Consumo promedio con relay:    600 tokens/consulta  
Consultas posibles:            216 consultas/día

Multiplicador de eficiencia:   8.3x más consultas FRIDA por día
```

### Templates de condensación por tipo de tarea

| Tipo de contexto | Ratio compresión típico | Modelo recomendado |
|---|---|---|
| Stack traces (Java/Python) | 10:1 | phi3:mini |
| Logs de aplicación (1000+ líneas) | 20:1 | mistral:7b |
| Código fuente a revisar | 3:1 | qwen2.5-coder:7b |
| Emails/conversaciones técnicas | 8:1 | phi3:mini |
| Documentación técnica extensa | 15:1 | mistral:7b |
| Queries SQL complejas | 2:1 | qwen2.5-coder:7b |

---

## Escenario F – Modo Aprendizaje Asistido

### Descripción
Usar Ollama como **tutor técnico on-demand** para aprender tecnologías nuevas, entender código heredado (legacy), o prepararse para certificaciones — sin consumir tokens de FRIDA.

### Casos de uso
- Entender código legacy en lenguaje poco familiar
- Aprender una nueva tecnología en el contexto del sistema que mantienes
- Preparar documentación de arquitectura de un sistema desconocido
- Practicar troubleshooting de escenarios hipotéticos

### Prompts de aprendizaje
```
# Entender código legacy
>>> "Explícame qué hace este código como si yo no conociera [LENGUAJE].
    Luego indica qué partes son críticas y cuáles son deuda técnica:
    [CÓDIGO]"

# Aprender tecnología nueva
>>> "Soy ingeniero de mantenimiento y necesito entender [TECNOLOGÍA] 
    específicamente para: diagnosticar problemas, interpretar logs, y 
    aplicar fixes de emergencia. Dame un resumen práctico de 5 minutos."

# Preparar preguntas inteligentes para FRIDA
>>> "Voy a consultar con un experto sobre [TEMA]. 
    ¿Qué 5 preguntas técnicas específicas debería hacer para obtener 
    la información más valiosa posible?"
```

---

## Escenario G – Modo Monitoreo Inteligente de Alertas

### Descripción
Integrar Ollama con scripts de monitoreo para **análisis automático de alertas** antes de que lleguen al ingeniero. Pre-procesamiento de alertas para reducir ruido y priorizar.

### Arquitectura básica
```
Alerta entrante (email/webhook)
        ↓
Script PowerShell captura texto de alerta
        ↓
Envía a Ollama API (http://localhost:11434)
        ↓
Ollama clasifica: CRÍTICO / ADVERTENCIA / INFORMATIVO / FALSO POSITIVO
        ↓
Notificación al ingeniero con clasificación y análisis previo
```

### Script de integración básico
```powershell
# alert_analyzer.ps1
param([string]$AlertText)

$body = @{
    model = "phi3:mini"
    prompt = "Clasifica esta alerta de sistema como: CRÍTICO, ADVERTENCIA, INFORMATIVO, o FALSO_POSITIVO. 
              Responde SOLO en este formato JSON: 
              {`"clasificacion`": `"NIVEL`", `"componente`": `"NOMBRE`", `"accion_inmediata`": `"DESCRIPCIÓN`"}
              
              ALERTA: $AlertText"
    stream = $false
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:11434/api/generate" -Method POST -Body $body -ContentType "application/json"
$response.response
```

---

## Resumen de Escenarios por Impacto

| Escenario | Ahorro de tiempo | Ahorro de tokens FRIDA | Recurso RAM |
|---|---|---|---|
| A – Triaje de Incidentes | 10-20 min/incidente | 80-90% | 2.5 GB (siempre activo) |
| B – Deep RCA | 1-2 horas/RCA | 60-70% | 5.0 GB (bajo demanda) |
| C – Documentación | 30-45 min/doc | 70-85% | 5.0 GB (bajo demanda) |
| D – Code Review | 20-30 min/review | 50-60% | 5.2 GB (bajo demanda) |
| E – Token Relay | N/A | **85-92%** | 2.5-5.0 GB |
| F – Aprendizaje | Variable | 95-100% | 5.0 GB |
| G – Alertas Auto | 5-10 min/alerta | 95% | 2.5 GB (daemon) |

### Combinación óptima para un turno AMS L3 típico

```
Inicio de turno (siempre):
  → Escenario A activo: phi3:mini en background para triaje

Durante incidente:
  → Si es simple: Escenario A resuelve (phi3:mini)
  → Si es complejo: Activar Escenario B (mistral:7b)
  → Para código: Activar Escenario D (qwen2.5-coder:7b)

Post-incidente:
  → Escenario C para documentación (mistral:7b)
  → Escenario E para condensar antes de escalar a FRIDA

Cuando FRIDA es necesaria:
  → Siempre pasar por Escenario E primero
  → Solo enviar el prompt optimizado (200-500 tokens vs. miles)
```
