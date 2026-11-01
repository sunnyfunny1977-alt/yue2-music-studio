# YuE2 Music Studio - optionale Cover-Funktion: FLUX.3 Image Klein (eigene Umgebung .venv-flux3 + Modell)
# Aufruf:  powershell -ExecutionPolicy Bypass -File install_cover.ps1  [-Variant fp8r|bf16] [-SkipModel] [-DryRun]
#   fp8r (Standard): Transformer 6.3 GB, laeuft auf jeder Karte (ohne fp8-Kerne wird pro Schritt nach bf16 gerechnet)
#   bf16:            Transformer 11.1 GB, etwas schneller auf Karten ohne fp8-Unterstuetzung, braucht mehr VRAM
# Download gesamt: ca. 15.5 GB (fp8r) bzw. 20.3 GB (bf16). Quelle: unsloth/flux-3-image-klein (ohne Login).
# Lizenz des Modells: FLUX Kommunity License (privat und fuer kleine Unternehmen kostenlos).
# Hinweis: Diese Datei ist bewusst reines ASCII (Windows PowerShell 5.1 liest UTF-8 ohne BOM als ANSI).
param([ValidateSet("fp8r", "bf16")][string]$Variant = "fp8r", [switch]$SkipModel, [switch]$DryRun)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
. "$PSScriptRoot\install_common.ps1"

$FPy = ".venv-flux3\Scripts\python.exe"
$Repo = "unsloth/flux-3-image-klein"
$ModelDir = "models/flux3-klein"
# Diffusers mit FLUX.3-Unterstuetzung (main-Branch, auf einen getesteten Commit festgelegt)
$Diffusers = "diffusers @ git+https://github.com/huggingface/diffusers.git@d42ebf9c6e0b"
$FluxDeps = @($Diffusers, "transformers==5.20.1", "accelerate==1.15.0", "safetensors==0.8.0",
              "huggingface-hub==2.2.0", "hf_xet", "pillow")
$Cu128 = "https://download.pytorch.org/whl/cu128"
$RocmRel = "https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1"
$RocmSdk = @(
    "$RocmRel/rocm_sdk_core-7.2.1-py3-none-win_amd64.whl",
    "$RocmRel/rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl",
    "$RocmRel/rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl",
    "$RocmRel/rocm-7.2.1.tar.gz"
)
$RocmTorch = @(
    "$RocmRel/torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl",
    "$RocmRel/torchvision-0.24.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl"
)

Write-Host "YuE2 Music Studio - Cover-Funktion (FLUX.3 Image Klein) installieren" -ForegroundColor Green
if (-not (Test-Path $Py)) {
    Write-Warning "YuE2 Music Studio ist noch nicht installiert. Bitte zuerst install.ps1 ausfuehren."
    if (-not $DryRun) { exit 1 }
}
Need uv "Installieren: winget install astral-sh.uv"
Need git "Installieren: winget install Git.Git"

$gpu = @(Get-GpuList | Where-Object { $_.Vendor -in @("nvidia", "amd") } | Sort-Object VramGB -Descending) | Select-Object -First 1
if (-not $gpu) {
    Write-Warning "Keine NVIDIA- oder AMD-Grafikkarte gefunden - FLUX.3 braucht eine GPU."
    if (-not $DryRun) { exit 1 }
    $gpu = [pscustomobject]@{ Name = "(DryRun)"; Vendor = "nvidia"; VramGB = 0 }
}
Write-Host ("Grafikkarte: {0} ({1} GB)" -f $gpu.Name, $gpu.VramGB)
if ($gpu.VramGB -gt 0 -and $gpu.VramGB -lt 22) {
    Write-Warning "Weniger als 22 GB VRAM: FLUX.3 laeuft mit CPU-Offload (langsamer)."
}

# ---------------------------------------------------------------- Umgebung (.venv-flux3, Python 3.12)
Step "FLUX-Umgebung (.venv-flux3, Python 3.12)"
if ($DryRun -or -not (Test-Path .venv-flux3)) { Run uv venv .venv-flux3 --python 3.12 }
if ($gpu.Vendor -eq "amd") {
    Write-Warning "AMD/ROCm: experimentell, nicht auf echter AMD-Hardware getestet."
    Run uv pip install --python $FPy @RocmSdk
    Run uv pip install --python $FPy @RocmTorch
} else {
    Run uv pip install --python $FPy "torch==2.10.0" "torchvision==0.25.0" --index-url $Cu128
}
Run uv pip install --python $FPy @FluxDeps
Run $FPy -c "import torch, diffusers, transformers; assert torch.cuda.is_available(), 'GPU nicht verfuegbar'; print('Torch', torch.__version__, '| diffusers', diffusers.__version__, '| transformers', transformers.__version__)"

# ---------------------------------------------------------------- Modell (nur die benoetigten Dateien)
if (-not $SkipModel) {
    Step "FLUX.3 Image Klein herunterladen ($Variant) - das dauert beim ersten Mal"
    $weights = if ($Variant -eq "fp8r") { "'variants/fp8r/*'" } else { "'transformer/*'" }
    $patterns = "['modular_model_index.json', 'LICENSE.md', 'NOTICE.md', 'README.md', 'text_encoder/*', 'vae/*', 'transformer/config.json', $weights]"
    Run $FPy -c "from huggingface_hub import snapshot_download; print(snapshot_download('$Repo', local_dir='$ModelDir', allow_patterns=$patterns))"
}

# ---------------------------------------------------------------- Selbsttest
Step "FLUX.3-Selbsttest (kleines Bild, 4 Schritte)"
Run $FPy flux_worker.py --selftest $ModelDir $Variant
Write-Host "`nFertig. Die Cover-Funktion erscheint nach dem Neustart von YuE2 Music Studio (start.bat)." -ForegroundColor Green
