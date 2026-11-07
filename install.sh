#!/usr/bin/env bash
# YuE2 Music Studio - Installation fuer Linux mit NVIDIA-Grafikkarte (CUDA 12.8, z. B. RTX 30/40/50)
# Aufruf:  ./install.sh  [--skip-sheetsage] [--skip-models] [--dry-run]
#   --skip-sheetsage  ohne Remake-Funktion (keine SheetSage2-Umgebung)
#   --skip-models     Modelle erst beim ersten Start laden
#   --dry-run         nur anzeigen, was installiert wuerde
# Voraussetzungen: NVIDIA-Treiber 570 oder neuer, uv, git, ffmpeg; Ollama fuer Lyrics und Style.
# Unter Windows bitte install.ps1 verwenden.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

SKIP_SHEETSAGE=0; SKIP_MODELS=0; DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --skip-sheetsage) SKIP_SHEETSAGE=1 ;;
        --skip-models) SKIP_MODELS=1 ;;
        --dry-run) DRY_RUN=1 ;;
        -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unbekannte Option: $arg (siehe --help)" >&2; exit 2 ;;
    esac
done
# shellcheck source=install_common.sh
source ./install_common.sh

ok "YuE2 Music Studio - Installer fuer Linux mit NVIDIA (CUDA 12.8)"
check_system
check_prerequisites
check_nvidia

# ---------------------------------------------------------------- YuE2 + App (Python 3.12)
step "YuE2-Umgebung (.venv-yue2, Python 3.12, CUDA)"
if [ "$DRY_RUN" = 1 ] || [ ! -d .venv-yue2 ]; then run uv venv .venv-yue2 --python 3.12; fi
# Zuerst CUDA-12.8-Torch (inkl. Blackwell/sm_120), dann YuE2 - dessen Pin torch==2.10.0 ist damit erfuellt.
run uv pip install --python "$PY" "torch==2.10.0" --index-url "$CU128"
run uv pip install --python "$PY" "$YUE_SOURCE"
run uv pip install --python "$PY" -r requirements-app.txt
run "$PY" -c "import torch; assert torch.cuda.is_available() and torch.version.cuda, 'CUDA nicht verfuegbar'; print('Torch', torch.__version__, torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))"

# ---------------------------------------------------------------- SheetSage2 (Python 3.11, CUDA)
if [ "$SKIP_SHEETSAGE" = 0 ]; then install_sheetsage; fi
if [ "$SKIP_MODELS" = 0 ]; then install_models; fi

step "YuE2-Selbsttest"
run .venv-yue2/bin/yue2 doctor
chmod +x start.sh install_cover.sh 2>/dev/null || true
ok ""
ok "Fertig. Start mit: ./start.sh"
ok "Optional: Cover-Funktion (FLUX.3) mit ./install_cover.sh nachinstallieren."
