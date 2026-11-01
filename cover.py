"""Optionale Cover-Erstellung mit FLUX.3 Image Klein (eigene venv .venv-flux3, Worker-Prozess flux_worker.py)."""
import json
import os
import random
import re
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


# Remakes und Mashups tragen wie Remix-Singles einen Zusatz auf dem Cover.
EDITIONS = {"remake": "REMAKE", "mashup": "MASHUP"}

# Bildansatz und Schriftanordnung werden je Cover (über den Seed) gewählt – sonst landet das Sprachmodell
# fast immer bei „Szene unten, Titel mittig darüber“.
APPROACHES = [
    "a close-up photographic portrait of the singer or band (matching the voice in the music style), dramatic "
    "studio or available light, the face or silhouette filling most of the frame",
    "a cinematic scene from the song's story, framed like a film still with a strong focal point",
    "a minimal graphic design: one symbolic object or shape on a bold flat color field with generous negative space",
    "a painted or illustrated artwork in a distinctive art style that suits the genre",
    "a surreal photo montage that turns the song's central metaphor into one striking, unexpected image",
    "a typographic cover where the title lettering itself is the hero visual, supported by a simple image or texture",
]
MASHUP_APPROACH = ("a fused composition that merges two visual worlds – one for each source song – into a single "
                   "image, for example a diagonal split, a double exposure or a torn-paper collage")
LAYOUTS = [
    "the title large and centered across the top",
    "the title set flush left in the top-left area like an editorial magazine cover",
    "the title as a huge wordmark spanning the full width along the top edge",
    "the title stacked over two or three lines in the upper left with tight leading",
]


def cover_edition(info):
    return EDITIONS.get((info.get("mode") or "").lower(), "")


def mashup_sources(info):
    """„Titel – Interpret“ von Song A und B (aus dem Generieren oder aus der Info-TXT)."""
    meta = info.get("mashup") or {}
    pair = [meta.get("a") or info.get("mash_a") or "", meta.get("b") or info.get("mash_b") or ""]
    # „Titel – Interpret (datei.mp3) · Tonart · BPM“ → „Titel – Interpret“
    return [re.sub(r"\s*\([^()]*\)\s*$", "", p.split(" · ")[0]).strip() for p in pair if p.strip()]


def cover_request(title, style, concept, lyrics, artist="", edition="", sources=(), seed=0):
    """Kurzer Bildwunsch, den Ollama mit dem offiziellen FLUX.3-Upsampler-Prompt zur Bildbeschreibung ausbaut."""
    sung = [ln.strip() for ln in (lyrics or "").splitlines() if ln.strip() and not ln.strip().startswith("[")]
    excerpt = " / ".join(dict.fromkeys(sung))[:900]
    rng = random.Random(seed)
    approach = rng.choice(APPROACHES)
    layout = rng.choice(LAYOUTS)
    kind = {"REMAKE": "remake single", "MASHUP": "mashup single"}.get(edition, "single")
    if edition == "MASHUP" and len(sources) == 2:
        approach = MASHUP_APPROACH
        origin = (f"This mashup blends two songs: {sources[0]} and {sources[1]}. Use them only as inspiration for "
                  "the two visual worlds – never write their titles or artists on the cover.\n")
    elif edition == "REMAKE":
        origin = "This is a reimagined new version of an existing song, so give it a fresh, contemporary look.\n"
    else:
        origin = ""
    return (
        "TARGET CANVAS: 1:1\n"
        f"Official cover art for the {kind} \"{title}\"" + (f" by {artist}" if artist else "") + ".\n"
        f"Music style: {style or 'unknown'}\n"
        + (f"Song concept: {concept}\n" if concept else "")
        + f"Key lyrics: {excerpt or '(instrumental)'}\n"
        + origin + "\n"
        "Design it like a professionally released record cover from a label, the kind shown on streaming services "
        "and vinyl sleeves – bold, iconic and recognizable even as a small thumbnail, not a generic stock image. "
        f"Visual approach: {approach}. Follow the cover conventions of the genre (synthwave: neon chrome lettering "
        "and retro sunsets; folk: warm analog film photo and hand-lettered type; metal: dark detailed illustration "
        "and a band-logo wordmark; hip-hop: flash photography and heavy sans-serif; pop: glossy studio portrait and "
        "clean bold type; classical: fine art and elegant serif). High production value, print-quality finish, film "
        "grain or paper texture where it fits. The artwork fills the whole square canvas: no border, no frame, no "
        "vinyl or CD mockup, no hands holding it, no streaming app interface.\n"
        + _text_rule(title, artist, edition, layout)
    )


def _text_rule(title, artist, edition, layout=LAYOUTS[0]):
    texts = [f"the song title \"{title}\" as the dominant cover typography (a display font or custom wordmark that "
             f"belongs to the design) in the upper third, with {layout}"]
    if artist:
        texts.append(f"the artist name \"{artist}\" in smaller, matching typography on its own line directly above "
                     "or below the title, set like an artist logo on a real release")
    if edition:
        texts.append(f"the version tag \"{edition}\" as a bold, high-contrast sticker, badge or banner in a top "
                     "corner – capital letters about a third of the title's letter height, clearly legible even in a "
                     "small thumbnail, like the remix label on a single cover")
    count = ("exactly one piece", "exactly two pieces", "exactly three pieces")[len(texts) - 1]
    return (f"Render {count} of text and nothing else: " + "; ".join(texts) + ". Keep all text in the upper half "
            "(players and libraries overlay the lower edge). Describe font style and color of each text. Write "
            "every text exactly as given, letter by letter. No other words, letters, numbers, logos, record label "
            "marks, parental advisory labels, barcodes or watermarks anywhere.")


def _title_sentence(title):
    return (f" Across the upper third of the cover, the title \"{title}\" is written in large, bold, clearly legible "
            "letters that contrast strongly with the background.")


def cover_caption(model, title, style, concept, lyrics, artist="", edition="", sources=(), seed=0):
    if not model:
        raise RuntimeError(t("err.no_model"))
    caption = llm.chat_text(model, _upsampler_prompt(),
                            cover_request(title, style, concept, lyrics, artist, edition, sources, seed),
                            temperature=0.7)
    caption = caption.strip().strip('"').strip()
    if not caption:
        raise RuntimeError(t("cover.no_caption"))
    # Das Sprachmodell lässt Schriftzüge gelegentlich weg – ohne Text in Anführungszeichen malt FLUX keinen.
    if f'"{title}"'.lower() not in caption.lower():
        caption += _title_sentence(title)
    if artist and f'"{artist}"'.lower() not in caption.lower():
        caption += (f" Directly below the title, the artist name \"{artist}\" is written in smaller, clearly "
                    "legible letters in the same style.")
    if edition and f'"{edition}"'.lower() not in caption.lower():
        caption += (f" In the top right corner, a bold high-contrast badge reads \"{edition}\" in clearly legible "
                    "capital letters.")
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
                            artist, cover_edition(info), mashup_sources(info), seed)
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
