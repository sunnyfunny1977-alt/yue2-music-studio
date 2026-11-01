"""Speichert einen generierten Song als MP3 oder FLAC plus Info-Textdatei (in der Oberflächensprache)."""
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from i18n import t
from lyrics_tools import fmt_duration, sanitize_filename

FORMATS = {"MP3": ".mp3", "FLAC": ".flac"}
LABEL_WIDTH = 18


def _write_mp3(audio, sr, target, bitrate="320"):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(t("err.ffmpeg_missing"))
    pcm = np.clip(audio, -1, 1)
    pcm = (pcm * 32767).astype("<i2")
    channels = 1 if pcm.ndim == 1 else pcm.shape[1]
    quality = ["-q:a", "0"] if str(bitrate).upper() == "V0" else ["-b:a", f"{int(bitrate)}k"]
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(sr), "-ac", str(channels),
           "-i", "pipe:0", "-codec:a", "libmp3lame", *quality, str(target)]
    proc = subprocess.run(cmd, input=pcm.tobytes(), capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(t("err.mp3_failed", e=proc.stderr.decode(errors="replace")))


def _format_text(path):
    """Formatzeile aus der Datei selbst, z. B. „MP3 – 48 kHz Stereo – 192 kbit/s“ oder „FLAC – … – 16 Bit“."""
    from audio_utils import describe_audio
    d = describe_audio(path)
    khz = f"{d.get('khz', 48):g}" if d else "48"
    if Path(path).suffix.lower() == ".mp3":
        return t("txt.fmt_mp3", khz=khz, kbps=d.get("kbps") or "?")
    return t("txt.fmt_flac", khz=khz, bits=d.get("bits") or "?")


def _row(key, value):
    return f"{t(key) + ':':<{LABEL_WIDTH}}{value}"


def _describe_source(tags):
    """„Titel – Interpret (Album, Jahr, Genre)“ aus den Tags des Original-Songs."""
    head = " – ".join(x for x in (tags.get("title"), tags.get("artist") or tags.get("album_artist")) if x)
    extra = ", ".join(x for x in (tags.get("album"), tags.get("year"), tags.get("genre")) if x)
    text = f"{head} ({extra})" if head and extra else head or extra
    return text or "-"


def build_info_text(info, audio_files, seconds):
    mode = info.get("mode", "new")
    cfg = info.get("cfg_scale")
    cfg_text = t("txt.cfg_default", v=info.get("cfg_default", "")) if cfg is None else cfg
    truncated = ", ".join(f"{t('trunc.' + k)}: {t('txt.yes') if v else t('txt.no')}"
                          for k, v in (info.get("truncated") or {}).items())
    formats = " | ".join(_format_text(f) for f in audio_files)
    lines = [
        _row("txt.title", info.get("title", "")),
        *([_row("txt.artist", info["artist"])] if info.get("artist") else []),
        *([_row("txt.album", info["album"])] if info.get("album") else []),
        _row("txt.files", ", ".join(f.name for f in audio_files)),
        _row("txt.saved", f"{datetime.now():%Y-%m-%d %H:%M:%S}"),
        _row("txt.created", info.get("created", "")),
        _row("txt.mode", t({"remake": "mode.remake_plain", "mashup": "mode.mashup_plain"}.get(mode, "mode.new_plain"))),
        _row("txt.length", f"{fmt_duration(seconds)} min ({seconds:.1f} s)"),
        _row("txt.format", formats),
        "",
        t("txt.sec_gen"),
        _row("txt.model", info.get("model", "")),
        _row("txt.vae", info.get("vae", "")),
        _row("txt.cot", info.get("cot", "")),
        _row("txt.seed", info.get("seed", "")),
        _row("txt.cfg", cfg_text),
        _row("txt.max_tokens", f"{info.get('max_tokens', '')} (≈ {int(info.get('max_tokens', 0)) // 25} s)"),
        _row("txt.truncated", truncated),
        _row("txt.render", f"{info.get('gen_seconds', 0):.0f} s"),
        _row("txt.gpu", (info.get("gpu") or "-") + (f" · {t('txt.lowvram')}" if info.get("low_vram") else "")),
        "",
        t("txt.sec_llm"),
        _row("txt.llm", info.get("llm_model", "")),
        _row("txt.language", info.get("language", "")),
        *([t("txt.concept"), info["concept"]] if info.get("concept") else []),
        t("txt.idea"),
        info.get("idea", "") or "-",
        "",
        t("txt.sec_style"),
        info.get("style", ""),
        "",
        t("txt.sec_lyrics"),
        info.get("lyrics", ""),
    ]
    if mode == "remake":
        lm = info.get("lyrics_mode")
        origin = info.get("lyrics_origin")
        source_text = t("txt.src_online", provider=origin["provider"], label=origin["label"]) if origin else t("txt.src_asr")
        lines += ["", t("txt.sec_source"),
                  _row("txt.source", info.get("source_file", "")),
                  _row("txt.original", _describe_source(info.get("source_tags") or {})),
                  _row("txt.lyrics_source", source_text),
                  _row("txt.lyrics_mode", t(f"lm.{lm}") if lm else ""),
                  "", t("txt.lyrics_online" if origin else "txt.transcript"), info.get("transcript", "") or "-",
                  "", t("txt.abc_used"), info.get("abc", "") or "-"]
    elif mode == "mashup":
        m = info.get("mashup") or {}
        lines += ["", t("txt.sec_mashup"),
                  _row("txt.mash_a", m.get("a", "")),
                  _row("txt.mash_b", m.get("b", "")),
                  _row("txt.mash_shift", m.get("shift", "")),
                  _row("txt.mash_plan", m.get("plan", "")),
                  "", t("txt.abc_used"), info.get("abc", "") or "-"]
    elif info.get("abc"):
        lines += ["", t("txt.abc_planned"), info["abc"]]
    return "\n".join(lines) + "\n"


def _split_cover(text):
    """Trennt einen vorhandenen Cover-Abschnitt (in beliebiger Oberflächensprache) vom Rest der Info-Datei."""
    from i18n import STRINGS
    heads = set(STRINGS["txt.sec_cover"])
    lines = text.rstrip("\n").split("\n")
    for i, line in enumerate(lines):
        if line.strip() in heads:
            return "\n".join(lines[:i]).rstrip("\n"), "\n".join(lines[i:])
    return "\n".join(lines), ""


def set_cover_section(text_file, jpg_name, size, model, seed, caption):
    """Schreibt bzw. ersetzt den Abschnitt „=== Cover ===“ am Ende der Info-TXT."""
    text_file = Path(text_file)
    body, _ = _split_cover(text_file.read_text(encoding="utf-8", errors="replace"))
    section = [t("txt.sec_cover"),
               _row("txt.cover_file", f"{jpg_name} ({size} × {size})"),
               _row("txt.cover_model", model),
               _row("txt.seed", seed),
               _row("txt.created", f"{datetime.now():%Y-%m-%d %H:%M:%S}"),
               t("txt.cover_prompt"),
               caption]
    text_file.write_text(body + "\n\n" + "\n".join(section) + "\n", encoding="utf-8")


def save_song(audio, sr, name, fmt, out_dir, info, overwrite=False, export=None):
    """Schreibt <Name>.<mp3|flac> und <Name>.txt. Gibt beide Pfade zurück.

    export: Einstellungen aus dem Reiter „Einstellungen“ (Bitrate, Bittiefe, Tags); Standard: gespeicherte Werte.
    """
    from settings import export_settings
    export = export or export_settings()
    if fmt not in FORMATS:
        raise ValueError(f"Unknown format: {fmt}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = sanitize_filename(name)
    audio_file = out_dir / f"{stem}{FORMATS[fmt]}"
    text_file = out_dir / f"{stem}.txt"
    if not overwrite:
        existing = [audio_file.name] if audio_file.exists() else []
        # Die TXT darf ersetzt werden, wenn sie zum selben Song gehört (z. B. erst MP3, dann FLAC).
        # Erkannt am Erstellungszeitpunkt – unabhängig von der Sprache der vorhandenen TXT.
        created = info.get("created", "")
        if text_file.exists() and not (created and created in text_file.read_text(encoding="utf-8", errors="replace")):
            existing.append(text_file.name)
        if existing:
            raise FileExistsError(t("err.exists", files=", ".join(existing)))
    if fmt == "FLAC":
        sf.write(audio_file, audio, sr, subtype="PCM_16" if int(export.get("flac_bits", 24)) == 16 else "PCM_24")
    else:
        _write_mp3(audio, sr, audio_file, export.get("mp3_bitrate", "320"))
    from audio_utils import write_tags
    try:
        write_tags(audio_file, {"title": info.get("title", name), "artist": info.get("artist", ""),
                                "album": info.get("album", ""), "genre": info.get("genre", ""),
                                "date": info.get("year", ""), "comment": info.get("comment", "")})
    except RuntimeError:
        pass  # Tags sind Komfort – der Song selbst ist gespeichert
    seconds = len(audio) / sr
    audio_files = [out_dir / f"{stem}{ext}" for ext in FORMATS.values() if (out_dir / f"{stem}{ext}").exists()]
    # Ein schon erstelltes Cover (z. B. erst MP3 mit Cover, dann zusätzlich FLAC) bleibt in der Info-Datei vermerkt.
    cover = _split_cover(text_file.read_text(encoding="utf-8", errors="replace"))[1] if text_file.exists() else ""
    text = build_info_text(info, audio_files, seconds)
    text_file.write_text(text + ("\n" + cover + "\n" if cover else ""), encoding="utf-8")
    return audio_file, text_file
