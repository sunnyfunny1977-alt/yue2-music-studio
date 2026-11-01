"""Audio mit ffmpeg dekodieren und Metadaten (Tags, Cover) mit ffprobe lesen – MP3, FLAC, WAV, M4A, OGG …"""
import base64
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

from i18n import t


def load_mono(path, sr):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(t("err.ffmpeg_missing"))
    cmd = [ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
           "-f", "f32le", "pipe:1"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(t("err.audio_read", e=proc.stderr.decode(errors="replace")[:300]))
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


# Tag-Namen verschiedener Formate (ID3, Vorbis, MP4) auf einheitliche Schlüssel abbilden.
_TAG_ALIASES = {
    "title": ("title",),
    "artist": ("artist", "performer"),
    "album": ("album",),
    "album_artist": ("album_artist", "albumartist", "album artist"),
    "year": ("date", "year", "originaldate", "tdrc", "tyer"),
    "genre": ("genre",),
    "track": ("track", "tracknumber"),
    "composer": ("composer",),
}


def replace_with_retry(tmp, target, attempts=20):
    """os.replace mit Wiederholung: Virenscanner, Windows-Suche oder Player sperren frische Dateien manchmal kurz."""
    import os
    import time
    for attempt in range(attempts):
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                Path(tmp).unlink(missing_ok=True)
                raise
            time.sleep(0.5)


def write_tags(path, tags):
    """Setzt Tags (title, artist, album, genre, date, comment) ohne Neu-Kodierung; leere Werte werden ausgelassen."""
    ffmpeg = shutil.which("ffmpeg")
    path = Path(path)
    values = {k: str(v).strip() for k, v in tags.items() if str(v or "").strip()}
    if not ffmpeg or not values:
        return
    tmp = path.with_name(f".{path.stem}.tags-tmp{path.suffix}")
    cmd = [ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(path), "-map", "0", "-c", "copy", "-map_metadata", "0"]
    for key, value in values.items():
        cmd += ["-metadata", f"{key}={value}"]
    if path.suffix.lower() == ".mp3":
        cmd += ["-id3v2_version", "3"]
    proc = subprocess.run(cmd + [str(tmp)], capture_output=True)
    if proc.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(proc.stderr.decode(errors="replace")[-400:])
    replace_with_retry(tmp, path)


def describe_audio(path):
    """Kurzbeschreibung des Formats aus der Datei selbst: (Codec, kHz, Kanäle, kbit/s, Bit)."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {}
    cmd = [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
           "stream=codec_name,sample_rate,channels,bit_rate,bits_per_raw_sample,sample_fmt:format=bit_rate",
           "-of", "json", str(path)]
    proc = subprocess.run(cmd, capture_output=True)
    try:
        data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
    except ValueError:
        return {}
    stream = (data.get("streams") or [{}])[0]
    bits = stream.get("bits_per_raw_sample")
    if not bits or bits == "0":
        bits = {"s16": 16, "s16p": 16, "s32": 32, "s32p": 32}.get(stream.get("sample_fmt", ""), "")
    rate = stream.get("bit_rate") or (data.get("format") or {}).get("bit_rate")
    return {"codec": stream.get("codec_name", ""), "khz": int(stream.get("sample_rate") or 0) / 1000,
            "channels": int(stream.get("channels") or 0), "kbps": round(int(rate) / 1000) if rate else 0,
            "bits": int(bits) if str(bits).isdigit() else 0}


def replace_with_retry(tmp, target, attempts=20):
    """os.replace mit Wiederholung: Virenscanner, Windows-Suche oder Player sperren frische Dateien manchmal kurz."""
    import os
    import time
    for attempt in range(attempts):
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                Path(tmp).unlink(missing_ok=True)
                raise
            time.sleep(0.5)


def write_tags(path, tags):
    """Setzt Tags (title, artist, album, genre, date, comment) ohne Neu-Kodierung; leere Werte werden ausgelassen."""
    ffmpeg = shutil.which("ffmpeg")
    path = Path(path)
    values = {k: str(v).strip() for k, v in tags.items() if str(v or "").strip()}
    if not ffmpeg or not values:
        return
    tmp = path.with_name(f".{path.stem}.tags-tmp{path.suffix}")
    cmd = [ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(path), "-map", "0", "-c", "copy", "-map_metadata", "0"]
    for key, value in values.items():
        cmd += ["-metadata", f"{key}={value}"]
    if path.suffix.lower() == ".mp3":
        cmd += ["-id3v2_version", "3"]
    proc = subprocess.run(cmd + [str(tmp)], capture_output=True)
    if proc.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(proc.stderr.decode(errors="replace")[-400:])
    replace_with_retry(tmp, path)


def describe_audio(path):
    """Kurzbeschreibung des Formats aus der Datei selbst: (Codec, kHz, Kanäle, kbit/s, Bit)."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {}
    cmd = [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
           "stream=codec_name,sample_rate,channels,bit_rate,bits_per_raw_sample,sample_fmt:format=bit_rate",
           "-of", "json", str(path)]
    proc = subprocess.run(cmd, capture_output=True)
    try:
        data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
    except ValueError:
        return {}
    stream = (data.get("streams") or [{}])[0]
    bits = stream.get("bits_per_raw_sample")
    if not bits or bits == "0":
        bits = {"s16": 16, "s16p": 16, "s32": 32, "s32p": 32}.get(stream.get("sample_fmt", ""), "")
    rate = stream.get("bit_rate") or (data.get("format") or {}).get("bit_rate")
    return {"codec": stream.get("codec_name", ""), "khz": int(stream.get("sample_rate") or 0) / 1000,
            "channels": int(stream.get("channels") or 0), "kbps": round(int(rate) / 1000) if rate else 0,
            "bits": int(bits) if str(bits).isdigit() else 0}


def read_tags(path):
    """Liest Titel, Interpret, Album usw. sowie technische Daten und ein eingebettetes Cover.

    Gibt ein Dict zurück; fehlende Felder fehlen einfach. Ohne ffprobe oder bei Fehlern: {}.
    """
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not path:
        return {}
    cmd = [ffprobe, "-v", "error", "-show_entries",
           "format=duration,bit_rate,format_name:format_tags:stream=index,codec_type,codec_name,sample_rate,"
           "channels,bit_rate:stream_tags:stream_disposition=attached_pic", "-of", "json", str(path)]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        return {}
    try:
        data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
    except ValueError:
        return {}
    fmt, streams = data.get("format", {}), data.get("streams", [])
    # Tags können am Container (MP3/FLAC/M4A) oder am Audio-Stream (OGG/Opus) hängen.
    raw = {}
    for stream in streams:
        if stream.get("codec_type") == "audio":
            raw.update({k.lower(): v for k, v in (stream.get("tags") or {}).items()})
    raw.update({k.lower(): v for k, v in (fmt.get("tags") or {}).items()})
    info = {}
    for key, aliases in _TAG_ALIASES.items():
        for alias in aliases:
            value = str(raw.get(alias, "")).strip()
            if value:
                info[key] = value
                break
    if "year" in info:
        info["year"] = info["year"][:4]
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    info["codec"] = (audio.get("codec_name") or fmt.get("format_name", "")).upper()
    if audio.get("sample_rate"):
        info["sample_rate"] = int(audio["sample_rate"])
    if audio.get("channels"):
        info["channels"] = int(audio["channels"])
    bitrate = audio.get("bit_rate") or fmt.get("bit_rate")
    if bitrate:
        info["bitrate_kbps"] = round(int(bitrate) / 1000)
    if fmt.get("duration"):
        info["duration"] = float(fmt["duration"])
    cover = next((s for s in streams if (s.get("disposition") or {}).get("attached_pic")), None)
    if cover is not None:
        info["cover"] = _read_cover(path, cover["index"])
        if not info["cover"]:
            info.pop("cover")
    return info


def _read_cover(path, stream_index):
    """Eingebettetes Cover als verkleinertes JPEG (data-URI) für die Anzeige."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return ""
    cmd = [ffmpeg, "-nostdin", "-v", "error", "-i", str(path), "-map", f"0:{stream_index}", "-frames:v", "1",
           "-vf", "scale=320:320:force_original_aspect_ratio=decrease", "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(proc.stdout).decode("ascii")
