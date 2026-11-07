#!/usr/bin/env bash
# YuE2 Music Studio - optionale Cover-Funktion fuer Linux/NVIDIA: FLUX.3 Image Klein (Umgebung .venv-flux3 + Modell)
# Aufruf:  ./install_cover.sh  [--variant fp8r|bf16] [--skip-model] [--dry-run]
#   fp8r (Standard): Transformer 6.3 GB, laeuft auf jeder Karte (ohne fp8-Kerne wird pro Schritt nach bf16 gerechnet)
#   bf16:            Transformer 11.1 GB, etwas schneller auf Karten ohne fp8-Unterstuetzung, braucht mehr VRAM
# Download gesamt: ca. 15.5 GB (fp8r) bzw. 20.3 GB (bf16). Quelle: unsloth/flux-3-image-klein (ohne Login).
# Lizenz des Modells: FLUX Kommunity License (privat und fuer kleine Unternehmen kostenlos).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

VARIANT=fp8r; SKIP_MODEL=0; DRY_RUN=0
while [ $# -gt 0 ]; do
    case "$1" in
        --variant) VARIANT=${2:-}; shift ;;
        --variant=*) VARIANT=${1#*=} ;;
        --skip-model) SKIP_MODEL=1 ;;
        --dry-run) DRY_RUN=1 ;;
        -h|--help) sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unbekannte Option: $1 (siehe --help)" >&2; exit 2 ;;
    esac
    shift
done
case "$VARIANT" in fp8r|bf16) ;; *) echo "--variant muss fp8r oder bf16 sein." >&2; exit 2 ;; esac
# shellcheck source=install_common.sh
source ./install_common.sh

FPY=".venv-flux3/bin/python"
REPO="unsloth/flux-3-image-klein"
MODEL_DIR="models/flux3-klein"
# Diffusers mit FLUX.3-Unterstuetzung (main-Branch, auf einen getesteten Commit festgelegt)
FLUX_DEPS=("diffusers @ git+https://github.com/huggingface/diffusers.git@d42ebf9c6e0b" "transformers==5.20.1"
           "accelerate==1.15.0" "safetensors==0.8.0" "huggingface-hub==2.2.0" "hf_xet" "pillow")

ok "YuE2 Music Studio - Cover-Funktion (FLUX.3 Image Klein) fuer Linux/NVIDIA installieren"
if [ ! -x "$PY" ]; then
    warn "YuE2 Music Studio ist noch nicht installiert. Bitte zuerst ./install.sh ausfuehren."
    [ "$DRY_RUN" = 1 ] || exit 1
fi
check_system
need uv "Installieren: curl -LsSf https://astral.sh/uv/install.sh | sh"
need git "$(pkg_hint git)"
check_nvidia
if [ "$GPU_VRAM_GB" -gt 0 ] && [ "$GPU_VRAM_GB" -lt 22 ]; then
    warn "Weniger als 22 GB VRAM: FLUX.3 laeuft mit CPU-Offload (langsamer)."
fi

# ---------------------------------------------------------------- Umgebung (.venv-flux3, Python 3.12)
step "FLUX-Umgebung (.venv-flux3, Python 3.12)"
if [ "$DRY_RUN" = 1 ] || [ ! -d .venv-flux3 ]; then run uv venv .venv-flux3 --python 3.12; fi
run uv pip install --python "$FPY" "torch==2.10.0" "torchvision==0.25.0" --index-url "$CU128"
run uv pip install --python "$FPY" "${FLUX_DEPS[@]}"
run "$FPY" -c "import torch, diffusers, transformers; assert torch.cuda.is_available(), 'GPU nicht verfuegbar'; print('Torch', torch.__version__, '| diffusers', diffusers.__version__, '| transformers', transformers.__version__)"

# ---------------------------------------------------------------- Modell (nur die benoetigten Dateien)
if [ "$SKIP_MODEL" = 0 ]; then
    step "FLUX.3 Image Klein herunterladen ($VARIANT) - das dauert beim ersten Mal"
    if [ "$VARIANT" = fp8r ]; then weights="'variants/fp8r/*'"; else weights="'transformer/*'"; fi
    patterns="['modular_model_index.json', 'LICENSE.md', 'NOTICE.md', 'README.md', 'text_encoder/*', 'vae/*', 'transformer/config.json', $weights]"
    run "$FPY" -c "from huggingface_hub import snapshot_download; print(snapshot_download('$REPO', local_dir='$MODEL_DIR', allow_patterns=$patterns))"
fi

# ---------------------------------------------------------------- Selbsttest
step "FLUX.3-Selbsttest (kleines Bild, 4 Schritte)"
run "$FPY" flux_worker.py --selftest "$MODEL_DIR" "$VARIANT"
ok ""
ok "Fertig. Die Cover-Funktion erscheint nach dem Neustart von YuE2 Music Studio (./start.sh)."
