# Guía de Limpieza de Procesos en Windows 11 para Optimizar Ollama
## AMS L3 – Liberación de Recursos del Sistema

---

## Resumen del Sistema Detectado

| Componente | Detalle |
|---|---|
| OS | Windows 11 Enterprise (Build 26200) |
| CPU | AMD Ryzen 5 7530U – 6 núcleos / 12 hilos |
| RAM Total | 15.7 GB |
| GPU | AMD Radeon iGPU (512 MB dedicados, sin VRAM discreta) |
| Modo de inferencia | **CPU-only** (sin aceleración GPU discreta) |

> **Nota crítica:** La GPU integrada no dispone de VRAM suficiente para acelerar modelos. Toda la inferencia se ejecuta en CPU + RAM del sistema. Liberar RAM es la acción de mayor impacto.

---

## Paso 0 – Verificación del Estado Antes de la Limpieza

Ejecutar el siguiente comando en PowerShell para registrar el punto de partida:

```powershell
# Estado inicial del sistema
Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 20 Name, @{N='RAM_MB';E={[math]::Round($_.WorkingSet/1MB,1)}}, CPU | Format-Table -AutoSize
Write-Host "`nRAM disponible: $([math]::Round((Get-WmiObject Win32_OperatingSystem).FreePhysicalMemory/1KB,0)) MB"
Write-Host "RAM total: $([math]::Round((Get-WmiObject Win32_OperatingSystem).TotalVisibleMemorySize/1KB,0)) MB"
```

Anotar el valor de "RAM disponible" antes y después de la limpieza.

---

## Paso 1 – Identificar Procesos por Consumo de Recursos

### 1.1 Ver procesos ordenados por RAM (PowerShell)
```powershell
Get-Process | Where-Object {$_.WorkingSet -gt 50MB} |
  Sort-Object WorkingSet -Descending |
  Select-Object Name, Id, @{N='RAM_MB';E={[math]::Round($_.WorkingSet/1MB,1)}}, @{N='CPU_s';E={[math]::Round($_.CPU,1)}} |
  Format-Table -AutoSize
```

### 1.2 Ver procesos ordenados por CPU (PowerShell)
```powershell
Get-Process | Sort-Object CPU -Descending | Select-Object -First 15 Name, Id, CPU | Format-Table -AutoSize
```

### 1.3 Ver con Task Manager (GUI)
- `Ctrl+Shift+Esc` → pestaña **Procesos** → clic en columna **Memoria** para ordenar descendente
- Ver también **Detalles** para ver el PID exacto

### 1.4 Herramienta recomendada: Process Hacker 2
- Descarga gratuita: https://processhacker.sourceforge.io/
- Ventaja: muestra árbol de procesos, uso de RAM física vs virtual, y permite terminar procesos del sistema con un clic

---

## Paso 2 – Categorías de Procesos Seguros para Terminar

> **NUNCA terminar:** procesos VDI (Citrix Workspace, VMware Horizon, RDP, Horizon Client), navegadores web activos, antivirus corporativo, agentes de seguridad (CrowdStrike, SentinelOne, Carbon Black), ni servicios del sistema críticos (lsass, winlogon, csrss, svchost de red).

### ✅ Categoría A – Agentes de Actualización Automática (TERMINAR SEGUROS)

| Proceso | Descripción | Acción |
|---|---|---|
| `OneDriveSetup.exe` | Actualizador de OneDrive | Terminar |
| `OfficeClickToRun.exe` | Actualizaciones de Office | Terminar |
| `MicrosoftEdgeUpdate.exe` | Actualizador de Edge | Terminar |
| `GoogleUpdate.exe` | Actualizador de Chrome/Google | Terminar |
| `SoftwareDistribution` (wuauclt) | Windows Update en background | Pausar |
| `Teams.exe` (si no se usa) | Microsoft Teams | Terminar |
| `OneDrive.exe` | Sincronización OneDrive | Terminar temporalmente |

### ✅ Categoría B – Telemetría y Diagnóstico (TERMINAR SEGUROS)

| Proceso | Descripción | Acción |
|---|---|---|
| `DiagTrack` service | Telemetría de Windows | Detener servicio |
| `WerFault.exe` | Error reporting | Terminar |
| `CompatTelRunner.exe` | Compatibilidad telemetría | Terminar |
| `SearchIndexer.exe` | Indexación de búsqueda | Detener temporalmente |
| `SysMain` (Superfetch) | Precarga de apps | Detener temporalmente |

### ✅ Categoría C – Apps en System Tray No Esenciales

| Proceso | Descripción | Acción |
|---|---|---|
| `Spotify.exe` | Reproductor de música | Terminar |
| `Discord.exe` | Chat de voz/texto | Terminar |
| `Slack.exe` | Mensajería (si no se usa activamente) | Terminar |
| `Zoom.exe` | Videollamadas (si no hay reunión activa) | Terminar |
| `AnyDesk.exe` / `TeamViewer.exe` | Control remoto | Terminar |
| `Skype.exe` | Mensajería (legacy) | Terminar |
| `Steam.exe` | Plataforma gaming | Terminar |

### ✅ Categoría D – Herramientas de Desarrollo No Activas

| Proceso | Descripción | Acción |
|---|---|---|
| `node.exe` (procesos inactivos) | Node.js servers detenidos | Terminar |
| `java.exe` (IDEs inactivos) | JVM de IDEs no usados | Terminar |
| `python.exe` (scripts inactivos) | Scripts Python detenidos | Terminar |
| `docker.exe` / containers | Docker si no se usa | Pausar/detener |
| IDEs adicionales abiertos | VS Code adicional, IntelliJ, Eclipse | Cerrar |

### ✅ Categoría E – Servicios Windows a Detener Temporalmente

```powershell
# Detener servicios seguros temporalmente
Stop-Service -Name "SysMain" -Force    # Superfetch/prefetch
Stop-Service -Name "WSearch" -Force    # Windows Search Indexer
Stop-Service -Name "DiagTrack" -Force  # Telemetría
Stop-Service -Name "wuauserv" -Force   # Windows Update (solo temporalmente)
```

---

## Paso 3 – Procedimiento de Limpieza Paso a Paso

### 3.1 Limpieza Rápida (5 minutos) – Uso del Script Automatizado

Ejecutar el script `cleanup_for_ollama.ps1` ubicado en la carpeta `scripts/`:

```powershell
# Ejecutar como usuario normal (sin requerir admin para la mayoría)
.\scripts\cleanup_for_ollama.ps1
```

El script realiza automáticamente:
1. Snapshot del estado actual (RAM/CPU)
2. Terminación de procesos no esenciales de las Categorías A, B, C
3. Detención de servicios de baja prioridad
4. Snapshot del estado post-limpieza
5. Reporte de MB liberados

### 3.2 Limpieza Manual Detallada

#### Paso 3.2.1 – Terminar procesos de actualización automática
```powershell
$processesToKill = @(
    "OneDriveSetup", "OfficeClickToRun", "MicrosoftEdgeUpdate",
    "GoogleUpdate", "Teams", "OneDrive", "Spotify", "Discord",
    "Slack", "Zoom", "AnyDesk", "TeamViewer", "Skype", "Steam",
    "WerFault", "CompatTelRunner"
)
foreach ($proc in $processesToKill) {
    $p = Get-Process -Name $proc -ErrorAction SilentlyContinue
    if ($p) {
        Stop-Process -Name $proc -Force
        Write-Host "Terminado: $proc"
    }
}
```

#### Paso 3.2.2 – Detener servicios de baja prioridad
```powershell
$servicesToStop = @("SysMain", "WSearch", "DiagTrack", "PrintSpooler")
foreach ($svc in $servicesToStop) {
    $s = Get-Service -Name $svc -ErrorAction SilentlyContinue
    if ($s -and $s.Status -eq "Running") {
        Stop-Service -Name $svc -Force -ErrorAction SilentlyContinue
        Write-Host "Servicio detenido: $svc"
    }
}
```

#### Paso 3.2.3 – Limpiar memoria en caché (requiere admin)
```powershell
# Forzar garbage collection de memoria disponible
[System.GC]::Collect()
[System.GC]::WaitForPendingFinalizers()
```

#### Paso 3.2.4 – Ajustar prioridad de Ollama (requiere que Ollama esté corriendo)
```powershell
# Dar alta prioridad al proceso de Ollama
$ollamaProcess = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if ($ollamaProcess) {
    $ollamaProcess.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::High
    Write-Host "Prioridad de Ollama ajustada a Alta"
}
```

---

## Paso 4 – Verificación Post-Limpieza

```powershell
# Comparar antes y después
$freeRAM = [math]::Round((Get-WmiObject Win32_OperatingSystem).FreePhysicalMemory/1KB, 0)
$totalRAM = [math]::Round((Get-WmiObject Win32_OperatingSystem).TotalVisibleMemorySize/1KB, 0)
$usedRAM = $totalRAM - $freeRAM
$pctFree = [math]::Round(($freeRAM / $totalRAM) * 100, 1)

Write-Host "`n====== ESTADO POST-LIMPIEZA ======"
Write-Host "RAM Total:      $totalRAM MB"
Write-Host "RAM Usada:      $usedRAM MB"
Write-Host "RAM Libre:      $freeRAM MB ($pctFree%)"

if ($freeRAM -gt 8000) {
    Write-Host "`n✅ ESTADO: ÓPTIMO – Puedes correr modelos 7B sin problema"
} elseif ($freeRAM -gt 5000) {
    Write-Host "`n⚠️ ESTADO: ACEPTABLE – Modelos 7B con cuantización Q4"
} elseif ($freeRAM -gt 2500) {
    Write-Host "`n⚠️ ESTADO: LIMITADO – Solo modelos ligeros (phi3:mini, etc.)"
} else {
    Write-Host "`n❌ ESTADO: INSUFICIENTE ��� Cierra más aplicaciones antes de usar Ollama"
}
```

---

## Paso 5 – Restaurar el Estado Normal

Al terminar de usar Ollama, restaurar los servicios detenidos:

```powershell
# Restaurar servicios
Start-Service -Name "SysMain" -ErrorAction SilentlyContinue
Start-Service -Name "WSearch" -ErrorAction SilentlyContinue
Start-Service -Name "DiagTrack" -ErrorAction SilentlyContinue
Write-Host "Servicios restaurados."
```

---

## Tabla de Ahorro de RAM Estimado por Categoría

| Categoría | Procesos típicos | RAM liberada estimada |
|---|---|---|
| Agentes de actualización | OneDrive, Office Updates, Edge Update | 200–400 MB |
| Telemetría + indexación | DiagTrack, WSearch, SysMain | 300–600 MB |
| Apps de comunicación | Teams, Slack, Discord, Zoom | 500–1500 MB |
| Herramientas de dev inactivas | Docker, Node, IDEs extra | 500–2000 MB |
| **Total estimado** | | **1.5 – 4.5 GB** |

> Con 15.7 GB de RAM y liberación típica de 2-3 GB adicionales, se puede contar con **8-10 GB libres** para Ollama después de la limpieza.
