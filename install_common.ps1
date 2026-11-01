# YuE2 Music Studio - gemeinsame Funktionen fuer install_nvidia.ps1 und install_amd.ps1 (per Dot-Sourcing geladen).
# Hinweis: Diese Datei ist bewusst reines ASCII (Windows PowerShell 5.1 liest UTF-8 ohne BOM als ANSI).

$YuETag = "yue2-v0.1.6"
$YuESource = "yue2-infer @ git+https://github.com/multimodal-art-projection/YuE.git@$YuETag"
$Py = ".venv-yue2\Scripts\python.exe"
$SPy = ".venv-sheetsage2\Scripts\python.exe"
if (-not (Get-Variable -Name DryRun -Scope Script -ErrorAction SilentlyContinue)) { $script:DryRun = $false }

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        if ($script:DryRun) { Write-Warning "$cmd nicht gefunden. $hint"; return }
        throw "$cmd nicht gefunden. $hint"
    }
}

# Native Tools schreiben Fortschritt nach stderr; massgeblich ist nur der Exit-Code.
# Im Probelauf (-DryRun) wird der Befehl nur angezeigt.
function Run {
    if ($script:DryRun) { Write-Host ("  [DryRun] " + ($args -join " ")) -ForegroundColor DarkGray; return }
    $ErrorActionPreference = "Continue"
    & $args[0] $args[1..($args.Length - 1)]
    if ($LASTEXITCODE -ne 0) { throw "Fehlgeschlagen: $args" }
}

function Test-Prerequisites {
    Step "Voraussetzungen pruefen"
    Need uv "Installieren: winget install astral-sh.uv"
    Need ffmpeg "Installieren: winget install Gyan.FFmpeg"
    Need git "Installieren: winget install Git.Git"
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { Write-Warning "Ollama nicht gefunden - https://ollama.com" }
}

# Grafikkarten mit Hersteller und echtem VRAM (Win32_VideoController meldet hoechstens 4 GB,
# deshalb wird qwMemorySize aus der Registry gelesen).
function Get-GpuList {
    $classKey = "HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    $memory = @{}
    Get-ChildItem $classKey -ErrorAction SilentlyContinue | ForEach-Object {
        $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
        if ($p -and $p.DriverDesc -and $p."HardwareInformation.qwMemorySize") {
            $memory[$p.DriverDesc] = [double]$p."HardwareInformation.qwMemorySize"
        }
    }
    Get-CimInstance Win32_VideoController | ForEach-Object {
        $bytes = if ($memory.ContainsKey($_.Name)) { $memory[$_.Name] } else { [double]$_.AdapterRAM }
        $vendor = if ($_.Name -match "NVIDIA") { "nvidia" } elseif ($_.Name -match "AMD|Radeon") { "amd" } else { "other" }
        [pscustomobject]@{ Name = $_.Name; Vendor = $vendor; VramGB = [math]::Round($bytes / 1GB, 1); Driver = $_.DriverVersion }
    }
}

function Install-SheetSageCommon {
    # Erwartet eine vorhandene .venv-sheetsage2 mit installiertem torch/torchaudio.
    Run uv pip install --python $SPy "huggingface-hub==0.36.0"
    if ($script:DryRun -or -not (Test-Path models\SheetSage2\config.json)) {
        Run $SPy -c "from huggingface_hub import snapshot_download; snapshot_download('m-a-p/SheetSage2', local_dir='models/SheetSage2')"
    }
    Run uv pip install --python $SPy -r models\SheetSage2\requirements.txt soundfile hf_xet
    Run $SPy -c "import torch; print('SheetSage2-Torch', torch.__version__, 'GPU:', torch.cuda.is_available())"
}

function Install-Models {
    Step "Modelle herunterladen (YuE2-3B, YuE2-Vae, Whisper) - das dauert beim ersten Mal"
    Run $Py -c "from yue2.storage import resolve_model; print(resolve_model('m-a-p/YuE2-3B')); print(resolve_model('m-a-p/YuE2-Vae'))"
    Run $Py -c "from huggingface_hub import snapshot_download; snapshot_download('openai/whisper-large-v3-turbo', allow_patterns=['*.json','*.safetensors','*.txt'])"
}

function Complete-Install {
    Step "YuE2-Selbsttest"
    if ($script:DryRun) { Write-Host "  [DryRun] .venv-yue2\Scripts\yue2.exe doctor" -ForegroundColor DarkGray }
    else { & .venv-yue2\Scripts\yue2.exe doctor }
    Write-Host "`nFertig. Start mit: start.bat" -ForegroundColor Green
}
