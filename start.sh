#!/usr/bin/env bash
# YuE2 Music Studio starten (Linux). Danach im Browser: http://127.0.0.1:7860
cd "$(dirname "$(readlink -f "$0")")" || exit 1
if [ ! -x .venv-yue2/bin/python ]; then
    echo "Bitte zuerst den Installer ausfuehren:  ./install.sh" >&2
    exit 1
fi
export PYTHONUTF8=1
exec .venv-yue2/bin/python app.py
