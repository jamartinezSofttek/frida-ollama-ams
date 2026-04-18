# ============================================
# check_system_for_ollama.ps1
# Diagnóstico rápido del sistema pre-Ollama
# AMS L3 – Frida Code Copilot / Ollama Optimization
#
# Uso: .\scripts\check_system_for_ollama.ps1
# ============================================

$os        = Get-WmiObject Win32_OperatingSystem
$freeRAM   = [math]::Round($os.FreePhysicalMemory / 1KB, 0)
$totalRAM  = [math]::Round($os.TotalVisibleMemorySize / 1KB, 0)
$usedRAM   = $totalRAM - $freeRAM
$freeGB    = [math]::Round($freeRAM / 1024, 1)
$usedPct   = [math]::Round(($usedRAM / $totalRAM) * 100, 1)
$cpuLoad   = (Get-CimInstance Win32_Processor).LoadPercentage

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║       DIAGNÓSTICO PRE-OLLAMA – AMS L3        ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  RAM Libre:  $freeRAM MB  ($freeGB GB)"
Write-Host "  RAM Usada:  $usedRAM MB  ($usedPct%)"
Write-Host "  RAM Total:  $totalRAM MB"
Write-Host "  Carga CPU:  $cpuLoad%"
Write-Host ""

# ── Top 10 procesos por consumo de RAM ──────────────────────────────────────
Write-Host "── Top 10 procesos por RAM ────────────────────────────────────────" -ForegroundColor DarkCyan
Get-Process |
    Where-Object { $_.WorkingSet -gt 30MB } |
    Sort-Object WorkingSet -Descending |
    Select-Object -First 10 Name,
        @{N='RAM_MB'; E={[math]::Round($_.WorkingSet/1MB,1)}},
        @{N='CPU_s';  E={[math]::Round($_.CPU,1)}} |
    Format-Table -AutoSize
Write-Host ""

# ── Modelos Ollama instalados ───────────────────────────────────────────────
Write-Host "── Modelos Ollama instalados ──────────────────────────────────────" -ForegroundColor DarkCyan
$ollamaAvailable = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaAvailable) {
    ollama list
} else {
    Write-Host "  ⚠️  Ollama no encontrado en PATH. Verificar instalación." -ForegroundColor Red
}
Write-Host ""

# ── Recomendación de modelo según RAM disponible ────────────────────────────
Write-Host "── Recomendación de modelo ────────────────────────────────────────" -ForegroundColor DarkCyan

if ($freeGB -ge 9) {
    Write-Host "  ✅ ÓPTIMO ($freeGB GB libres)" -ForegroundColor Green
    Write-Host "     → Modelos disponibles:"
    Write-Host "       codellama:13b (Q4_K_M)   – Mejor modelo de código"
    Write-Host "       mistral:7b (Q8)           – Máxima calidad 7B"
    Write-Host "       qwen2.5-coder:14b (Q4)    – Código avanzado"
} elseif ($freeGB -ge 5) {
    Write-Host "  ⚡ EFICIENTE ($freeGB GB libres)" -ForegroundColor Yellow
    Write-Host "     → Modelos disponibles:"
    Write-Host "       mistral:7b       – Análisis y RCA"
    Write-Host "       qwen2.5-coder:7b – Code review y debugging"
    Write-Host "       deepseek-coder:6.7b – Código de producción"
} elseif ($freeGB -ge 2.5) {
    Write-Host "  🔵 LIGERO ($freeGB GB libres)" -ForegroundColor Blue
    Write-Host "     → Modelos disponibles:"
    Write-Host "       phi3:mini   – Triaje y Q&A rápido"
    Write-Host "       gemma:2b    – Razonamiento ligero"
    Write-Host "       llama3.2:3b – Chat de alta calidad"
} else {
    Write-Host "  ❌ INSUFICIENTE ($freeGB GB libres)" -ForegroundColor Red
    Write-Host "     → Ejecutar limpieza primero:"
    Write-Host "       .\scripts\cleanup_for_ollama.ps1"
}

Write-Host ""
Write-Host "── Sugerencia de acción ───────────────────────────────────────────" -ForegroundColor DarkCyan

if ($cpuLoad -gt 80) {
    Write-Host "  ⚠️  CPU al $cpuLoad% – Esperar a que baje antes de iniciar Ollama" -ForegroundColor Red
} elseif ($freeGB -lt 4) {
    Write-Host "  💡 Ejecutar: .\scripts\cleanup_for_ollama.ps1" -ForegroundColor Yellow
} else {
    Write-Host "  💡 Sistema listo. Iniciar con:" -ForegroundColor Green
    if ($freeGB -ge 5) {
        Write-Host "     ollama run mistral:7b" -ForegroundColor White
    } else {
        Write-Host "     ollama run phi3:mini" -ForegroundColor White
    }
}
Write-Host ""
