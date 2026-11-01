"""Optionale Cover-Erstellung mit FLUX.3 Image Klein (eigene venv .venv-flux3, Worker-Prozess flux_worker.py)."""
import json
import os
import random
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import gpu_info
import llm
from i18n import t
from settings import CONFIG, ROOT, path, prompt

COVER_EXT = ".jpg"


# --------------------------------------------------------------------------- Installation erkennen

def model_dir():
    return path("flux_model_dir")


def variant():
    """fp8r (kleinerer Transformer) oder bf16 – je nachdem, was install_cover.ps1 geladen hat."""
    choice = CONFIG.get("flux_variant", "auto")
    has_fp8 = (model_dir() / "variants" / "fp8r" / "model.safetensors").exists()
    has_bf16 = any((model_dir() / "transformer").glob("*.safetensors"))
    if choice == "fp8r" or (choice == "auto" and has_fp8):
        return "fp8r" if has_fp8 else ""
    return "bf16" if has_bf16 else ""


def available():
    return (path("flux_python").exists() and (model_dir() / "text_encoder" / "config.json").exists()
            and (model_dir() / "vae" / "config.json").exists() and bool(variant()))


def chip_text():
    return t("cover.chip_ok", v=variant()) if available() else t("cover.chip_off")


# --------------------------------------------------------------------------- Worker

class CoverEngine:
    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()
        self._log = Path(tempfile.gettempdir()) / "yue2_flux_worker.log"

    @property
    def busy(self):
        return self._lock.locked()

    def _start(self):
        if self._proc and self._proc.poll() is None:
            return
        env = {**os.environ, "PYTHONUTF8": "1", "FLUX_MODEL_DIR": str(model_dir()), "FLUX_VARIANT": variant(),
               "FLUX_LOW_VRAM": "1" if gpu_info.current().low_vram else "0"}
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._logfile = self._log.open("a", encoding="utf-8")
        self._proc = subprocess.Popen([str(path("flux_python")), str(ROOT / "flux_worker.py")], cwd=ROOT, env=env,
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._logfile,
                                      text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=flags)
        msg = self._read()
        if not msg.get("ready"):
            raise RuntimeError(t("cover.worker_failed", log=self._log))

    def _read(self):
        while True:
            line = self._proc.stdout.readline()
            if not line:  # Worker beendet
                self._proc = None
                raise RuntimeError(t("cover.worker_failed", log=self._log))
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue

    def render(self, caption, seed, out, on_progress=None):
        if not self._lock.acquire(blocking=False):
            raise RuntimeError(t("cover.busy_self"))
        try:
            self._start()
            size = int(CONFIG.get("cover_render_size", 1024))
            job = {"cmd": "render", "prompt": caption, "seed": int(seed), "width": size, "height": size,
                   "steps": int(CONFIG.get("cover_steps", 16)), "out": str(out)}
            self._proc.stdin.write(json.dumps(job, ensure_ascii=False) + "\n")
            self._proc.stdin.flush()
            while True:
                msg = self._read()
                if "progress" in msg:
                    if on_progress:
                        on_progress(msg["progress"], msg["total"])
                    continue
                if msg.get("error"):
                    raise RuntimeError(msg["error"])
                return msg
        finally:
            self._lock.release()

    def stop(self):
        """Beendet den Worker (VRAM und RAM frei). Liefert False, solange ein Cover entsteht."""
        if not self._lock.acquire(blocking=False):
            return False
        try:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.stdin.write('{"cmd": "quit"}\n')
                    self._proc.stdin.flush()
                    self._proc.wait(timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    self._proc.kill()
            self._proc = None
            return True
        finally:
            self._lock.release()


ENGINE = CoverEngine()


# --------------------------------------------------------------------------- Prompt (Ollama als Upsampler)

def _upsampler_prompt():
    text = prompt("flux3_upsampler_t2i.md")
    return "\n".join(line for line in text.splitlines() if not line.startswith("<!--")).strip()


def cover_request(title, style, concept, lyrics, artist=""):
    """Kurzer Bildwunsch, den Ollama mit dem offiziellen FLUX.3-Upsampler-Prompt zur Bildbeschreibung ausbaut."""
    sung = [ln.strip() for ln in (lyrics or "").splitlines() if ln.strip() and not ln.strip().startswith("[")]
    excerpt = " / ".join(dict.fromkeys(sung))[:900]
    return (
        "TARGET CANVAS: 1:1\n"
        f"Square album cover artwork for the song \"{title}\".\n"
        f"Music style: {style or 'unknown'}\n"
        + (f"Song concept: {concept}\n" if concept else "")
        + f"Key lyrics: {excerpt or '(instrumental)'}\n\n"
        "Design an original, striking album cover that shows the song's central image, story and mood in one "
        "clear motif. Pick an artistic medium and color palette that fit the genre and mood (for example "
        "illustration, painting, graphic design or photography). The artwork fills the whole square canvas: "
        "no border, no frame, no vinyl or CD mockup, no hands holding it.\n"
        + (_text_rule_artist(title, artist) if artist else
           f"Render exactly one piece of text: the song title \"{title}\" as large, clearly legible typography that "
           "belongs to the design, placed in the upper third of the cover (players and libraries overlay the lower "
           "edge); describe its font style and color. Write the title exactly as given, letter by letter. No other "
           "words, letters, numbers, artist names, logos, labels or watermarks anywhere.")
    )


def _text_rule_artist(title, artist):
    return (f"Render exactly two pieces of text and nothing else: the song title \"{title}\" as large, clearly "
            "legible typography in the upper third of the cover, and the artist name "
            f"\"{artist}\" in smaller, matching typography on its own line directly above or below the title "
            "(still in the upper half – players and libraries overlay the lower edge). Describe font style and color "
            "of both. Write both exactly as given, letter by letter. No other words, letters, numbers, logos, "
            "labels or watermarks anywhere.")


def _title_sentence(title):
    return (f" Across the upper third of the cover, the title \"{title}\" is written in large, bold, clearly legible "
            "letters that contrast strongly with the background.")


def cover_caption(model, title, style, concept, lyrics, artist=""):
    if not model:
        raise RuntimeError(t("err.no_model"))
    caption = llm.chat_text(model, _upsampler_prompt(), cover_request(title, style, concept, lyrics, artist),
                            temperature=0.7)
    caption = caption.strip().strip('"').strip()
    if not caption:
        raise RuntimeError(t("cover.no_caption"))
    # Das Sprachmodell lässt den Schriftzug gelegentlich weg – ohne Titel in Anführungszeichen malt FLUX keinen.
    if f'"{title}"'.lower() not in caption.lower():
        caption += _title_sentence(title)
    if artist and f'"{artist}"'.lower() not in caption.lower():
        caption += (f" Directly below the title, the artist name \"{artist}\" is written in smaller, clearly "
                    "legible letters in the same style.")
    return caption


def cover_artist(info):
    """Künstler fürs Cover: aus dem Song (TXT/Tags), sonst aus den Einstellungen – sofern gewünscht."""
    from settings import export_settings
    export = export_settings()
    if not export.get("artist_on_cover", True):
        return ""
    return (info.get("artist") or export.get("artist") or "").strip()


# --------------------------------------------------------------------------- Bild speichern und einbetten

def _embed(audio, cover_jpg, title, artist=""):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(t("err.ffmpeg_missing"))
    tmp = audio.with_name(f".{audio.stem}.cover-tmp{audio.suffix}")
    cmd = [ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(audio), "-i", str(cover_jpg),
           "-map", "0:a", "-map", "1:0", "-c", "copy", "-map_metadata", "0",
           "-metadata:s:v", "title=Album cover", "-metadata:s:v", "comment=Cover (front)",
           "-disposition:v:0", "attached_pic"]
    if title:
        cmd += ["-metadata", f"title={title}"]
    if artist:
        cmd += ["-metadata", f"artist={artist}"]
    if audio.suffix.lower() == ".mp3":
        cmd += ["-id3v2_version", "3"]
    proc = subprocess.run(cmd + [str(tmp)], capture_output=True)
    if proc.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(t("cover.embed_failed", file=audio.name, e=proc.stderr.decode(errors="replace")[-400:]))
    from audio_utils import replace_with_retry
    replace_with_retry(tmp, audio)


def embed_existing(audio_file, title="", artist=""):
    """Bettet ein schon vorhandenes <Name>.jpg in eine neu gespeicherte Audiodatei ein (z. B. FLAC nach MP3)."""
    audio_file = Path(audio_file)
    jpg = audio_file.with_suffix(COVER_EXT)
    if jpg.exists():
        _embed(audio_file, jpg, title, artist)
        return True
    return False


def make_cover(folder, stem, info, model, seed=None, on_status=None):
    """Erzeugt <stem>.jpg (512²), bettet es in <stem>.mp3/.flac ein und vermerkt es in <stem>.txt.

    info: Titel, Style, Konzept, Lyrics. Gibt (jpg, caption, seed) zurück.
    """
    from PIL import Image
    from exporter import set_cover_section

    status = on_status or (lambda *_: None)
    folder = Path(folder)
    title = info.get("title") or stem
    seed = random.randrange(0, 2**31) if seed is None else int(seed)

    status("prompt")
    artist = cover_artist(info)
    caption = cover_caption(model, title, info.get("style", ""), info.get("concept", ""), info.get("lyrics", ""),
                            artist)
    llm.unload(model)  # VRAM für FLUX frei machen

    status("load")
    with tempfile.TemporaryDirectory(prefix="yue2_cover_") as tmp:
        png = Path(tmp) / "cover.png"
        result = ENGINE.render(caption, seed, png, on_progress=lambda i, n: status("render", i, n))
        size = int(CONFIG.get("cover_size", 512))
        jpg = folder / f"{stem}{COVER_EXT}"
        with Image.open(png) as img:
            img.convert("RGB").resize((size, size), Image.LANCZOS).save(jpg, quality=92, optimize=True)

    status("embed")
    embedded = []
    for ext in (".mp3", ".flac"):
        audio = folder / f"{stem}{ext}"
        if audio.exists():
            _embed(audio, jpg, title, info.get("artist", ""))
            embedded.append(ext[1:].upper())
    txt = folder / f"{stem}.txt"
    if txt.exists():
        set_cover_section(txt, jpg.name, size, f"FLUX.3 Image Klein ({variant()}, {result.get('mode', '')})",
                          seed, caption)
    return jpg, caption, seed, embedded
