# ============================================
# cleanup_for_ollama.ps1
# Limpieza de procesos para liberar RAM antes de usar Ollama
# AMS L3 – Frida Code Copilot / Ollama Optimization
#
# Uso:
#   .\scripts\cleanup_for_ollama.ps1            # Limpieza estándar
#   .\scripts\cleanup_for_ollama.ps1 -Aggressive # Limpieza agresiva (cierra Teams, Outlook, etc.)
# ============================================

param(
    [switch]$Aggressive,
    [switch]$Quiet
)

function Get-FreeRAM {
    return [math]::Round((Get-WmiObject Win32_OperatingSystem).FreePhysicalMemory / 1KB, 0)
}

function Write-Status {
    param([string]$Message, [string]$Color = "White")
    if (-not $Quiet) {
        Write-Host $Message -ForegroundColor $Color
    }
}

# ── Estado inicial ───────────────────────────────────────────────────────────
$ramBefore = Get-FreeRAM
Write-Status "`n╔══════════════════════════════════════════╗" "Cyan"
Write-Status "║       OLLAMA CLEANUP SCRIPT – AMS L3     ║" "Cyan"
Write-Status "╚══════════════════════════════════════════╝" "Cyan"
Write-Status "RAM libre al inicio: $ramBefore MB" "Yellow"
if ($Aggressive) {
    Write-Status "Modo: AGRESIVO (cerrando Teams, Outlook, Slack, Zoom)" "Red"
} else {
    Write-Status "Modo: ESTÁNDAR (apps no críticas)" "Green"
}
Write-Status ""

# ── Procesos siempre seguros para terminar ───────────────────────────────────
$safeProcs = @(
    "OneDriveSetup",
    "OfficeClickToRun",
    "MicrosoftEdgeUpdate",
    "GoogleUpdate",
    "WerFault",
    "WerFaultSecure",
    "CompatTelRunner",
    "Spotify",
    "Discord",
    "Steam",
    "AnyDesk",
    "TeamViewer",
    "TeamViewer_Service",
    "Skype",
    "SearchIndexer"
)

# ── Procesos adicionales en modo agresivo ────────────────────────────────────
# NOTA: Excluye VDI (Citrix, VMware Horizon, RDP) y el navegador principal
$aggressiveProcs = @(
    "Teams",
    "ms-teams",
    "OneDrive",
    "Slack",
    "slack",
    "Zoom",
    "CiscoCollabHost",
    "Webex",
    "outlook"
)

$toKill = $safeProcs
if ($Aggressive) {
    $toKill += $aggressiveProcs
}

# ── Terminar procesos ────────────────────────────────────────────────────────
Write-Status "[ Terminando procesos no esenciales... ]" "Cyan"
$killed = 0
foreach ($proc in $toKill) {
    $p = Get-Process -Name $proc -ErrorAction SilentlyContinue
    if ($p) {
        Stop-Process -Name $proc -Force -ErrorAction SilentlyContinue
        Write-Status "  ✓ Terminado: $proc ($([math]::Round($p.WorkingSet/1MB,0)) MB)" "Green"
        $killed++
    }
}

if ($killed -eq 0) {
    Write-Status "  (ningún proceso de la lista estaba ejecutándose)" "Gray"
}

# ── Detener servicios de baja prioridad ─────────────────────────────────────
Write-Status "`n[ Deteniendo servicios de baja prioridad... ]" "Cyan"
$services = @(
    @{ Name = "SysMain";   Desc = "Superfetch / Prefetch" },
    @{ Name = "WSearch";   Desc = "Windows Search Indexer" },
    @{ Name = "DiagTrack"; Desc = "Telemetría de Windows" }
)

foreach ($svc in $services) {
    $s = Get-Service -Name $svc.Name -ErrorAction SilentlyContinue
    if ($s -and $s.Status -eq "Running") {
        Stop-Service -Name $svc.Name -Force -ErrorAction SilentlyContinue
        Write-Status "  ✓ Detenido: $($svc.Name) ($($svc.Desc))" "Green"
    }
}

# ── Esperar liberación de memoria ────────────────────────────────────────────
Start-Sleep -Seconds 3

# ── Estado final ─────────────────────────────────────────────────────────────
$ramAfter  = Get-FreeRAM
$freed     = $ramAfter - $ramBefore
$freeGB    = [math]::Round($ramAfter / 1024, 1)

Write-Status "`n╔══════════════════════════════════════════╗" "Cyan"
Write-Status "║             RESULTADO                    ║" "Cyan"
Write-Status "╚══════════════════════════════════════════╝" "Cyan"
Write-Status "RAM libre final:  $ramAfter MB ($freeGB GB)"
Write-Status "RAM liberada:     $freed MB" "Cyan"
Write-Status ""

if ($freeGB -ge 9) {
    Write-Status "✅ ÓPTIMO – Puedes usar: codellama:13b, mistral:7b-q8, qwen2.5-coder:14b" "Green"
} elseif ($freeGB -ge 5) {
    Write-Status "⚡ EFICIENTE – Puedes usar: mistral:7b, qwen2.5-coder:7b, deepseek-coder:6.7b" "Yellow"
} elseif ($freeGB -ge 2.5) {
    Write-Status "🔵 LIGERO – Solo modelos pequeños: phi3:mini, gemma:2b, llama3.2:3b" "Blue"
} else {
    Write-Status "❌ INSUFICIENTE – Cierra más aplicaciones manualmente antes de usar Ollama" "Red"
}

Write-Status "`nInicia Ollama con: ollama run phi3:mini" "White"
