# ============================================
# restore_services.ps1
# Restaurar servicios de Windows después de usar Ollama
# AMS L3 – Frida Code Copilot / Ollama Optimization
#
# Uso: .\scripts\restore_services.ps1
# ============================================

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║       RESTAURAR SERVICIOS – AMS L3           ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Descargar modelos Ollama de la RAM ──────────────────────────────────────
Write-Host "[ Descargando modelos Ollama de RAM... ]" -ForegroundColor Cyan
$ollamaAvailable = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaAvailable) {
    $modelsToStop = @("phi3:mini", "mistral:7b", "qwen2.5-coder:7b", "ams-triage")
    foreach ($m in $modelsToStop) {
        ollama stop $m 2>$null
    }
    Write-Host "  ✓ Modelos Ollama descargados de RAM" -ForegroundColor Green
} else {
    Write-Host "  (Ollama no disponible en PATH)" -ForegroundColor Gray
}

# ── Restaurar servicios de Windows ──────────────────────────────────────────
Write-Host ""
Write-Host "[ Restaurando servicios de Windows... ]" -ForegroundColor Cyan

$services = @(
    @{ Name = "SysMain";   Desc = "Superfetch / Prefetch" },
    @{ Name = "WSearch";   Desc = "Windows Search Indexer" },
    @{ Name = "DiagTrack"; Desc = "Telemetría de Windows" }
)

foreach ($svc in $services) {
    $s = Get-Service -Name $svc.Name -ErrorAction SilentlyContinue
    if ($s) {
        if ($s.Status -ne "Running") {
            Start-Service -Name $svc.Name -ErrorAction SilentlyContinue
            Write-Host "  ✓ Restaurado: $($svc.Name) ($($svc.Desc))" -ForegroundColor Green
        } else {
            Write-Host "  · Ya activo: $($svc.Name)" -ForegroundColor Gray
        }
    }
}

# ── Estado final del sistema ─────────────────────────────────────────────────
Write-Host ""
$freeRAM = [math]::Round((Get-WmiObject Win32_OperatingSystem).FreePhysicalMemory / 1KB, 0)
$freeGB  = [math]::Round($freeRAM / 1024, 1)
Write-Host "RAM libre ahora: $freeRAM MB ($freeGB GB)" -ForegroundColor White
Write-Host ""
Write-Host "✅ Sistema restaurado al estado normal." -ForegroundColor Green
Write-Host ""
