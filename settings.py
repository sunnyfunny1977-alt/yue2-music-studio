"""Lädt config.json und löst relative Pfade gegen den Projektordner auf."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROMPTS = ROOT / "prompts"

with (ROOT / "config.json").open(encoding="utf-8") as f:
    CONFIG = json.load(f)


def path(key):
    """Pfad aus der Konfiguration; relative Angaben gelten ab dem Projektordner."""
    p = Path(CONFIG[key])
    return p if p.is_absolute() else ROOT / p


def prompt(name):
    return (PROMPTS / name).read_text(encoding="utf-8")


# Persönliche Einstellungen (z. B. Oberflächensprache) – werden von der App selbst geschrieben.
USER_FILE = ROOT / "user_settings.json"


def load_user():
    try:
        return json.loads(USER_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def save_user(**values):
    data = {**load_user(), **values}
    USER_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# Export (Reiter „Einstellungen“): Qualität und Tags für gespeicherte MP3/FLAC
MP3_BITRATES = ["128", "192", "256", "320", "V0"]
FLAC_BITS = [16, 24]
EXPORT_DEFAULTS = {"mp3_bitrate": "320", "flac_bits": 24, "artist": "", "album": "", "genre": "", "year": "",
                   "comment": "YuE2 Music Studio", "artist_on_cover": True}


def export_settings():
    data = {**EXPORT_DEFAULTS, **(load_user().get("export") or {})}
    if str(data["mp3_bitrate"]) not in MP3_BITRATES:
        data["mp3_bitrate"] = EXPORT_DEFAULTS["mp3_bitrate"]
    if int(data.get("flac_bits") or 24) not in FLAC_BITS:
        data["flac_bits"] = 24
    return data


def save_export(**values):
    save_user(export={**export_settings(), **values})
