# YuE2 Music Studio - Installation fuer AMD-Radeon-Grafikkarten (Windows 11, ROCm 7.2.1)
# Aufruf:  powershell -ExecutionPolicy Bypass -File install_amd.ps1  [-SkipSheetSage] [-SkipModels] [-DryRun]
#
# Voraussetzungen laut AMD (ROCm 7.2.1 fuer Windows):
#   - Windows 11, AMD-Grafiktreiber (Adrenalin) 26.2.2 oder neuer
#   - Radeon RX 7000/9000, Radeon AI PRO R9700, Radeon PRO W7800/W7900 (gfx1100/1101/1200/1201)
#   - YuE2 braucht 24 GB VRAM; 16-GB-Karten laufen im experimentellen Sparmodus
param([switch]$SkipSheetSage, [switch]$SkipModels, [switch]$DryRun)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
. "$PSScriptRoot\install_common.ps1"

# AMD stellt PyTorch fuer Windows nur als direkte Wheels bereit (nur Python 3.12).
$RocmRel = "https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1"
$RocmSdk = @(
    "$RocmRel/rocm_sdk_core-7.2.1-py3-none-win_amd64.whl",
    "$RocmRel/rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl",
    "$RocmRel/rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl",
    "$RocmRel/rocm-7.2.1.tar.gz"
)
$RocmTorch = @(
    "$RocmRel/torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl",
    "$RocmRel/torchaudio-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl",
    "$RocmRel/torchvision-0.24.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl"
)
# yue2-infer pinnt torch==2.10.0 (CUDA). Deshalb ohne Abhaengigkeiten installieren
# und die uebrigen Pins von yue2-infer 0.1.6 einzeln nachziehen.
$YuEDeps = @("transformers==4.57.6", "huggingface-hub==0.36.2", "safetensors==0.7.0", "tiktoken==0.12.0",
             "numpy==2.2.6", "soundfile==0.13.1", "accelerate==1.13.0")
$CpuIndex = "https://download.pytorch.org/whl/cpu"

Write-Host "YuE2 Music Studio - Installer fuer AMD Radeon (ROCm 7.2.1)" -ForegroundColor Green
Test-Prerequisites

# ---------------------------------------------------------------- System pruefen
Step "AMD-Grafikkarte und Windows pruefen"
$build = [Environment]::OSVersion.Version.Build
if ($build -lt 22000) { Write-Warning "ROCm fuer Windows unterstuetzt nur Windows 11 (gefunden: Build $build)." }
$amd = @(Get-GpuList | Where-Object { $_.Vendor -eq "amd" } | Sort-Object VramGB -Descending)
if ($amd.Count -eq 0) {
    if (-not $DryRun) { throw "Keine AMD-Radeon-Grafikkarte gefunden. Fuer NVIDIA bitte install_nvidia.ps1 verwenden." }
    Write-Warning "Keine AMD-Grafikkarte gefunden (Probelauf wird fortgesetzt)."
} else {
    $gpu = $amd[0]
    Write-Host ("  Grafikkarte: {0}  |  VRAM: {1} GB  |  Treiber: {2}" -f $gpu.Name, $gpu.VramGB, $gpu.Driver)
    if ($gpu.VramGB -lt 15) {
        Write-Warning "Weniger als 16 GB VRAM - YuE2 wird hier sehr wahrscheinlich nicht laufen."
    } elseif ($gpu.VramGB -lt 22) {
        Write-Warning "16-GB-Karte: YuE2 laeuft im experimentellen Sparmodus (langsamer, kuerzere Songs empfohlen)."
    }
}
Write-Host "  Benoetigt: AMD-Grafiktreiber (Adrenalin) 26.2.2 oder neuer." -ForegroundColor Yellow
Write-Host "  Bei Problemen: Smart App Control deaktivieren und das Visual C++ 2015-2022 Redistributable installieren." -ForegroundColor Yellow

# ---------------------------------------------------------------- YuE2 + App (Python 3.12, ROCm)
Step "YuE2-Umgebung (.venv-yue2, Python 3.12, ROCm 7.2.1)"
if ($DryRun -or -not (Test-Path .venv-yue2)) { Run uv venv .venv-yue2 --python 3.12 }
Run uv pip install --python $Py @RocmSdk
# torch, torchaudio und torchvision in EINEM Aufruf - sonst ersetzt der Installer torch durch die CPU-Version.
Run uv pip install --python $Py @RocmTorch
Run uv pip install --python $Py --no-deps $YuESource
Run uv pip install --python $Py @YuEDeps
Run uv pip install --python $Py -r requirements-app.txt
Run $Py -c "import torch; assert torch.version.hip, 'Kein ROCm-PyTorch installiert'; assert torch.cuda.is_available(), 'AMD-GPU nicht verfuegbar - Treiber pruefen'; print('Torch', torch.__version__, 'HIP', torch.version.hip, torch.cuda.get_device_name(0), 'BF16:', torch.cuda.is_bf16_supported())"

# ---------------------------------------------------------------- SheetSage2 (Python 3.11, CPU)
# SheetSage2 pinnt torch 2.8 und numpy 1.24 (kein Python 3.12) - dafuer gibt es keine ROCm-Wheels.
# Die Melodie-Analyse fuer Remakes laeuft daher auf der CPU (zuverlaessig, aber langsamer).
if (-not $SkipSheetSage) {
    Step "SheetSage2-Umgebung (.venv-sheetsage2, Python 3.11, CPU) fuer Remakes"
    if ($DryRun -or -not (Test-Path .venv-sheetsage2)) { Run uv venv .venv-sheetsage2 --python 3.11 }
    Run uv pip install --python $SPy "torch==2.8.0" "torchaudio==2.8.0" --index-url $CpuIndex
    Install-SheetSageCommon
}

if (-not $SkipModels) { Install-Models }
Complete-Install
