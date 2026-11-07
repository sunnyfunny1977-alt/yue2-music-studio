# shellcheck shell=bash disable=SC2034  # Variablen nutzen install.sh und install_cover.sh
# YuE2 Music Studio - gemeinsame Funktionen fuer install.sh und install_cover.sh (Linux, NVIDIA; per "source" geladen).

YUE_TAG="yue2-v0.1.6"
YUE_SOURCE="yue2-infer @ git+https://github.com/multimodal-art-projection/YuE.git@$YUE_TAG"
CU128="https://download.pytorch.org/whl/cu128"
PY=".venv-yue2/bin/python"
SPY=".venv-sheetsage2/bin/python"
MIN_DRIVER=570   # CUDA 12.8 (und RTX 50/Blackwell) braucht den NVIDIA-Treiber 570 oder neuer
DRY_RUN=${DRY_RUN:-0}

if [ -t 1 ]; then
    C_STEP=$'\e[36m'; C_OK=$'\e[32m'; C_WARN=$'\e[33m'; C_ERR=$'\e[31m'; C_DIM=$'\e[90m'; C_OFF=$'\e[0m'
else
    C_STEP=""; C_OK=""; C_WARN=""; C_ERR=""; C_DIM=""; C_OFF=""
fi

step() { printf '\n%s=== %s ===%s\n' "$C_STEP" "$1" "$C_OFF"; }
ok()   { printf '%s%s%s\n' "$C_OK" "$1" "$C_OFF"; }
warn() { printf '%sWARNUNG: %s%s\n' "$C_WARN" "$1" "$C_OFF" >&2; }
die()  { printf '%sFEHLER: %s%s\n' "$C_ERR" "$1" "$C_OFF" >&2; exit 1; }

# Befehl ausfuehren und bei Fehler abbrechen; im Probelauf (--dry-run) nur anzeigen.
run() {
    if [ "$DRY_RUN" = 1 ]; then
        printf '  %s[DryRun] %s%s\n' "$C_DIM" "$*" "$C_OFF"
        return 0
    fi
    "$@" || die "Fehlgeschlagen: $*"
}

# Fehlt ein Werkzeug, bricht die Installation ab (im Probelauf nur Warnung).
need() {
    command -v "$1" >/dev/null 2>&1 && return 0
    if [ "$DRY_RUN" = 1 ]; then warn "$1 nicht gefunden. $2"; else die "$1 nicht gefunden. $2"; fi
}

# Installationsbefehl fuer ein Systempaket passend zur Distribution.
pkg_hint() {
    if command -v apt-get >/dev/null 2>&1; then echo "Installieren: sudo apt install $1"
    elif command -v dnf >/dev/null 2>&1; then echo "Installieren: sudo dnf install $1 (ffmpeg unter Fedora aus RPM Fusion)"
    elif command -v pacman >/dev/null 2>&1; then echo "Installieren: sudo pacman -S $1"
    elif command -v zypper >/dev/null 2>&1; then echo "Installieren: sudo zypper install $1"
    else echo "Bitte $1 ueber die Paketverwaltung installieren."
    fi
}

check_system() {
    step "System pruefen"
    local os arch
    os=$(uname -s); arch=$(uname -m)
    if [ "$os" != "Linux" ]; then
        [ "$DRY_RUN" = 1 ] || die "Dieser Installer ist fuer Linux. Unter Windows bitte install.ps1 verwenden."
        warn "Kein Linux ($os) - Probelauf wird fortgesetzt."
    fi
    if [ "$arch" != "x86_64" ]; then
        warn "Architektur $arch: getestet ist nur x86_64. PyTorch fuer CUDA 12.8 gibt es auch fuer aarch64, YuE2 ist dort aber ungeprueft."
    fi
    ok "  $os $arch"
}

check_prerequisites() {
    step "Voraussetzungen pruefen"
    need uv "Installieren: curl -LsSf https://astral.sh/uv/install.sh | sh  (danach neues Terminal oeffnen)"
    need git "$(pkg_hint git)"
    need ffmpeg "$(pkg_hint ffmpeg)"
    need ffprobe "$(pkg_hint ffmpeg)"
    if ! command -v ollama >/dev/null 2>&1; then
        warn "Ollama nicht gefunden - Installieren: curl -fsSL https://ollama.com/install.sh | sh  (danach z. B. ollama pull qwen3.8:27b)"
    fi
}

# Setzt GPU_NAME und GPU_VRAM_GB (Karte mit dem meisten Grafikspeicher) und prueft den Treiber.
check_nvidia() {
    step "NVIDIA-Grafikkarte und Treiber pruefen"
    GPU_NAME="(unbekannt)"; GPU_VRAM_GB=0
    if ! command -v nvidia-smi >/dev/null 2>&1; then
        [ "$DRY_RUN" = 1 ] || die "nvidia-smi nicht gefunden - bitte den NVIDIA-Treiber $MIN_DRIVER oder neuer installieren (z. B. sudo ubuntu-drivers install)."
        warn "nvidia-smi nicht gefunden (Probelauf wird fortgesetzt)."
        return 0
    fi
    local line name mem driver major
    line=$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits | tr -d '\r' \
           | sort -t, -k2,2 -nr | head -n1)
    [ -n "$line" ] || die "nvidia-smi meldet keine Grafikkarte - Treiber pruefen."
    IFS=',' read -r name mem driver <<<"$line"
    name=$(echo "$name" | xargs); mem=$(echo "$mem" | xargs); driver=$(echo "$driver" | xargs)
    GPU_NAME=$name
    GPU_VRAM_GB=$(( (${mem%%.*} + 512) / 1024 ))
    ok "  Grafikkarte: $name  |  VRAM: $GPU_VRAM_GB GB  |  Treiber: $driver"
    major=${driver%%.*}
    if [ "${major:-0}" -lt "$MIN_DRIVER" ] 2>/dev/null; then
        [ "$DRY_RUN" = 1 ] || die "Treiber $driver ist zu alt: CUDA 12.8 braucht $MIN_DRIVER oder neuer."
        warn "Treiber $driver ist zu alt: CUDA 12.8 braucht $MIN_DRIVER oder neuer."
    fi
    if [ "$GPU_VRAM_GB" -lt 15 ]; then
        warn "Weniger als 16 GB VRAM - YuE2 wird hier sehr wahrscheinlich nicht laufen."
    elif [ "$GPU_VRAM_GB" -lt 22 ]; then
        warn "16-GB-Karte: YuE2 laeuft im experimentellen Sparmodus (langsamer, kuerzere Songs empfohlen)."
    fi
}

install_sheetsage() {
    step "SheetSage2-Umgebung (.venv-sheetsage2, Python 3.11, CUDA) fuer Remakes"
    if [ "$DRY_RUN" = 1 ] || [ ! -d .venv-sheetsage2 ]; then run uv venv .venv-sheetsage2 --python 3.11; fi
    run uv pip install --python "$SPY" "torch==2.8.0" "torchaudio==2.8.0" --index-url "$CU128"
    run uv pip install --python "$SPY" "huggingface-hub==0.36.0"
    if [ "$DRY_RUN" = 1 ] || [ ! -f models/SheetSage2/config.json ]; then
        run "$SPY" -c "from huggingface_hub import snapshot_download; snapshot_download('m-a-p/SheetSage2', local_dir='models/SheetSage2')"
    fi
    run uv pip install --python "$SPY" -r models/SheetSage2/requirements.txt soundfile hf_xet
    run "$SPY" -c "import torch; print('SheetSage2-Torch', torch.__version__, 'GPU:', torch.cuda.is_available())"
}

install_models() {
    step "Modelle herunterladen (YuE2-3B, YuE2-Vae, Whisper) - das dauert beim ersten Mal"
    run "$PY" -c "from yue2.storage import resolve_model; print(resolve_model('m-a-p/YuE2-3B')); print(resolve_model('m-a-p/YuE2-Vae'))"
    run "$PY" -c "from huggingface_hub import snapshot_download; snapshot_download('openai/whisper-large-v3-turbo', allow_patterns=['*.json','*.safetensors','*.txt'])"
}
