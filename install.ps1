# YuE2 Music Studio - Installation (Windows). Erkennt die Grafikkarte und startet den passenden Installer:
#   NVIDIA -> install_nvidia.ps1 (CUDA 12.8)      AMD Radeon -> install_amd.ps1 (ROCm 7.2.1)
# Aufruf:  powershell -ExecutionPolicy Bypass -File install.ps1  [-Vendor nvidia|amd] [-SkipSheetSage] [-SkipModels] [-DryRun]
param([ValidateSet("auto", "nvidia", "amd")][string]$Vendor = "auto",
      [switch]$SkipSheetSage, [switch]$SkipModels, [switch]$DryRun)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
. "$PSScriptRoot\install_common.ps1"

if ($Vendor -eq "auto") {
    $gpus = @(Get-GpuList)
    foreach ($g in $gpus) { Write-Host ("Gefunden: {0} ({1}, {2} GB)" -f $g.Name, $g.Vendor, $g.VramGB) }
    # Die Karte mit dem meisten Grafikspeicher entscheidet (eine integrierte Radeon neben einer NVIDIA-Karte zaehlt nicht).
    $best = $gpus | Where-Object { $_.Vendor -in @("nvidia", "amd") } | Sort-Object VramGB -Descending | Select-Object -First 1
    if (-not $best) { throw "Keine NVIDIA- oder AMD-Grafikkarte gefunden. Hersteller mit -Vendor nvidia|amd angeben." }
    $Vendor = $best.Vendor
}

$target = Join-Path $PSScriptRoot ("install_{0}.ps1" -f $Vendor)
Write-Host ("Starte {0} ..." -f (Split-Path $target -Leaf)) -ForegroundColor Green
$forward = @{ SkipSheetSage = $SkipSheetSage; SkipModels = $SkipModels; DryRun = $DryRun }
& $target @forward
