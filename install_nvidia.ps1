# YuE2 Music Studio - Installation fuer NVIDIA-Grafikkarten (Windows, CUDA 12.8, z. B. RTX 30/40/50)
# Aufruf:  powershell -ExecutionPolicy Bypass -File install_nvidia.ps1  [-SkipSheetSage] [-SkipModels] [-DryRun]
param([switch]$SkipSheetSage, [switch]$SkipModels, [switch]$DryRun)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
. "$PSScriptRoot\install_common.ps1"

$Cu128 = "https://download.pytorch.org/whl/cu128"

Write-Host "YuE2 Music Studio - Installer fuer NVIDIA (CUDA 12.8)" -ForegroundColor Green
Test-Prerequisites

# ---------------------------------------------------------------- YuE2 + App (Python 3.12)
Step "YuE2-Umgebung (.venv-yue2, Python 3.12, CUDA)"
if ($DryRun -or -not (Test-Path .venv-yue2)) { Run uv venv .venv-yue2 --python 3.12 }
# Zuerst CUDA-12.8-Torch (inkl. Blackwell/sm_120), dann YuE2 - dessen Pin torch==2.10.0 ist damit erfuellt.
Run uv pip install --python $Py "torch==2.10.0" --index-url $Cu128
Run uv pip install --python $Py $YuESource
Run uv pip install --python $Py -r requirements-app.txt
Run $Py -c "import torch; assert torch.cuda.is_available() and torch.version.cuda, 'CUDA nicht verfuegbar'; print('Torch', torch.__version__, torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))"

# ---------------------------------------------------------------- SheetSage2 (Python 3.11, CUDA)
if (-not $SkipSheetSage) {
    Step "SheetSage2-Umgebung (.venv-sheetsage2, Python 3.11, CUDA) fuer Remakes"
    if ($DryRun -or -not (Test-Path .venv-sheetsage2)) { Run uv venv .venv-sheetsage2 --python 3.11 }
    Run uv pip install --python $SPy "torch==2.8.0" "torchaudio==2.8.0" --index-url $Cu128
    Install-SheetSageCommon
}

if (-not $SkipModels) { Install-Models }
Complete-Install
