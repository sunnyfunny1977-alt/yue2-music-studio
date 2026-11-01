"""Bibliothek: findet gespeicherte Songs, liest ihre Info-TXT (Deutsch oder Englisch) und baut Vorschaubilder."""
import hashlib
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from i18n import STRINGS
from lyrics_tools import fmt_duration, style_bpm
from settings import load_user, path, save_user

AUDIO_EXTS = (".flac", ".mp3")  # Reihenfolge = bevorzugte Datei für den Player

# --------------------------------------------------------------------------- Info-TXT lesen

# Zeilen „Label:   Wert“ in beiden Sprachen → Feldname
_ROW_KEYS = {
    "txt.title": "title", "txt.files": "files", "txt.saved": "saved", "txt.created": "created",
    "txt.mode": "mode", "txt.length": "length", "txt.format": "format", "txt.model": "model",
    "txt.vae": "vae", "txt.cot": "cot", "txt.seed": "seed", "txt.cfg": "cfg", "txt.max_tokens": "max_tokens",
    "txt.truncated": "truncated", "txt.render": "render", "txt.gpu": "gpu", "txt.llm": "llm",
    "txt.language": "language", "txt.source": "source", "txt.original": "original",
    "txt.lyrics_source": "lyrics_source", "txt.lyrics_mode": "lyrics_mode",
    "txt.cover_file": "cover_file", "txt.cover_model": "cover_model", "txt.artist": "artist", "txt.album": "album",
    "txt.mash_a": "mash_a", "txt.mash_b": "mash_b", "txt.mash_shift": "mash_shift", "txt.mash_plan": "mash_plan",
}
# Überschriften, nach denen ein Textblock folgt (bis zur nächsten Überschrift)
_BLOCK_KEYS = {
    "txt.concept": "concept", "txt.idea": "idea", "txt.sec_style": "style", "txt.sec_lyrics": "lyrics",
    "txt.lyrics_online": "original_lyrics", "txt.transcript": "original_lyrics", "txt.abc_used": "abc",
    "txt.abc_planned": "abc", "txt.cover_prompt": "cover_prompt",
}
# Abschnitte mit „Label: Wert“-Zeilen; der Präfix trennt gleichnamige Felder (z. B. Seed von Song und Cover)
_SECTION_KEYS = {"txt.sec_gen": "", "txt.sec_llm": "", "txt.sec_source": "", "txt.sec_cover": "cover_",
                 "txt.sec_mashup": ""}


def _labels(keys):
    out = {}
    for key, name in keys.items():
        for text in STRINGS.get(key, ()):
            out[text.strip().rstrip(":").strip().lower()] = name
    return out


_ROWS, _BLOCKS, _SECTIONS = _labels(_ROW_KEYS), _labels(_BLOCK_KEYS), _labels(_SECTION_KEYS)
_ROW_RE = re.compile(r"^([^:\n]{1,40}):\s+(.*)$")
_MODES = {text.lower(): mode for key, mode in (("mode.new_plain", "new"), ("mode.remake_plain", "remake"),
                                               ("mode.mashup_plain", "mashup")) for text in STRINGS[key]}
_LYRICS_MODES = {text.lower(): code for code in ("keep", "rewrite", "translate") for text in STRINGS[f"lm.{code}"]}


def parse_info_txt(text):
    """Liest eine von exporter.build_info_text geschriebene Info-Datei (beliebige Oberflächensprache)."""
    info, blocks = {}, {}
    block, prefix = None, ""
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        head = line.rstrip(":").strip().lower()
        if line and head in _SECTIONS:
            block, prefix = None, _SECTIONS[head]
            continue
        if line and head in _BLOCKS:
            block = _BLOCKS[head]
            blocks.setdefault(block, [])
            continue
        if line.startswith("===") and line.endswith("==="):  # unbekannter Abschnitt
            block, prefix = None, ""
            continue
        if block:
            blocks[block].append(raw.rstrip())
            continue
        m = _ROW_RE.match(line)
        if m and m.group(1).strip().lower() in _ROWS:
            name = _ROWS[m.group(1).strip().lower()]
            info[name if name.startswith(prefix) else prefix + name] = m.group(2).strip()
    for name, lines in blocks.items():
        value = "\n".join(lines).strip()
        if value and value != "-":
            info[name] = value
    # Normalisieren
    info["mode"] = _MODES.get(info.get("mode", "").lower(), "new")
    if "lyrics_mode" in info:
        info["lyrics_mode"] = _LYRICS_MODES.get(info["lyrics_mode"].lower(), "")
    m = re.search(r"\(([\d.]+)\s*s\)", info.get("length", ""))
    if m:
        info["seconds"] = float(m.group(1))
    for key in ("seed", "cover_seed"):
        if str(info.get(key, "")).lstrip("-").isdigit():
            info[key] = int(info[key])
    return info


# --------------------------------------------------------------------------- Songs finden

@dataclass
class Track:
    stem: str
    folder: Path
    audio: dict = field(default_factory=dict)  # Endung → Pfad
    txt: Path | None = None
    jpg: Path | None = None
    info: dict = field(default_factory=dict)

    @property
    def id(self):
        return str(self.folder / self.stem)

    @property
    def title(self):
        return self.info.get("title") or self.stem

    @property
    def seconds(self):
        return float(self.info.get("seconds") or 0)

    @property
    def main_audio(self):
        return next((self.audio[e] for e in AUDIO_EXTS if e in self.audio), None)

    @property
    def created(self):
        for key in ("created", "saved"):
            try:
                return datetime.strptime(self.info.get(key, ""), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        files = [p for p in (*self.audio.values(), self.txt) if p]
        return datetime.fromtimestamp(max(p.stat().st_mtime for p in files)) if files else datetime.min

    def genre(self):
        """Genre aus dem Style: der erste Eintrag nach Sprache(n) und Stimme."""
        items = [x.strip() for x in self.info.get("style", "").split(",") if x.strip()]
        if items and len(items[0].split()) > 1:  # frei formulierter Style ohne Sprache vorn: Anfang kürzen
            words = items[0].split()
            return " ".join(words[:4]) + (" …" if len(words) > 4 else "")
        for i, item in enumerate(items):
            if re.search(r"vocal|voice|singer|choir|rap|duet", item, re.I):
                return items[i + 1] if i + 1 < len(items) else ""
        return items[1] if len(items) > 1 else ""

    def bpm(self):
        style = self.info.get("style", "")
        return style_bpm(style) if re.search(r"\d\s*BPM", style, re.I) else None

    def summary(self):
        """Kurzinfo unter dem Tracknamen, z. B. „3:18 · reggae · 78 BPM“."""
        parts = [fmt_duration(self.seconds)] if self.seconds else []
        if self.genre():
            parts.append(self.genre())
        if self.bpm():
            parts.append(f"{self.bpm()} BPM")
        return " · ".join(parts)

    def search_text(self):
        return " ".join(str(self.info.get(k, "")) for k in ("title", "style", "lyrics", "idea", "concept")).lower() \
            + " " + self.stem.lower()


def library_dirs():
    """Standard-Ausgabeordner plus jeder Ordner, in den schon gespeichert wurde."""
    dirs = [path("output_dir")] + [Path(p) for p in load_user().get("library_dirs", [])]
    seen, out = set(), []
    for d in dirs:
        key = str(d.resolve()).lower() if d.exists() else str(d).lower()
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def remember_dir(folder):
    folder = Path(folder).resolve()
    known = load_user().get("library_dirs", [])
    if str(folder) not in known and folder != path("output_dir").resolve():
        save_user(library_dirs=known + [str(folder)])


def scan(dirs=None):
    tracks = {}
    for folder in dirs or library_dirs():
        if not folder.is_dir():
            continue
        for f in folder.iterdir():
            ext = f.suffix.lower()
            if ext not in AUDIO_EXTS + (".txt", ".jpg"):
                continue
            track = tracks.setdefault(str(folder / f.stem).lower(), Track(f.stem, folder))
            if ext == ".txt":
                track.txt = f
            elif ext == ".jpg":
                track.jpg = f
            else:
                track.audio[ext] = f
    result = []
    for track in tracks.values():
        if not track.audio:  # TXT oder Bild ohne Song – kein Eintrag
            continue
        if track.txt:
            try:
                track.info = parse_info_txt(track.txt.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                track.info = {}
        if not track.info.get("seconds") or not track.info.get("title"):
            from audio_utils import read_tags
            tags = read_tags(track.main_audio)
            track.info.setdefault("title", tags.get("title") or track.stem)
            if tags.get("duration"):
                track.info.setdefault("seconds", tags["duration"])
        result.append(track)
    return result


def sort_filter(tracks, query="", order="new"):
    words = [w for w in (query or "").lower().split() if w]
    tracks = [tr for tr in tracks if all(w in tr.search_text() for w in words)]
    if order == "title":
        return sorted(tracks, key=lambda tr: tr.title.lower())
    if order == "length":
        return sorted(tracks, key=lambda tr: tr.seconds, reverse=True)
    return sorted(tracks, key=lambda tr: tr.created, reverse=True)


# --------------------------------------------------------------------------- Vorschaubilder

def _font(size):
    from PIL import ImageFont
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def placeholder(title, target, size=512):
    """Platzhalter-Cover in den App-Farben (Verlauf violett → cyan) mit dem Songtitel."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            k = (x + y) / (2 * size)
            px[x, y] = (int(76 + (8 - 76) * k), int(29 + (145 - 29) * k), int(149 + (178 - 149) * k))
    draw = ImageDraw.Draw(img)
    # Equalizer-Balken wie im Logo
    bars = [0.4, 0.9, 0.6, 1.0, 0.5]
    w, gap, base = size // 22, size // 30, int(size * 0.42)
    x0 = (size - (len(bars) * w + (len(bars) - 1) * gap)) // 2
    for i, h in enumerate(bars):
        top = base - int(h * size * 0.22)
        draw.rounded_rectangle([x0 + i * (w + gap), top, x0 + i * (w + gap) + w, base], radius=w // 2,
                               fill=(255, 255, 255))
    # Titel umbrechen und zentrieren
    font = _font(size // 11)
    words, lines, line = title.split(), [], ""
    for word in words:
        test = f"{line} {word}".strip()
        if draw.textlength(test, font=font) <= size * 0.84 or not line:
            line = test
        else:
            lines.append(line)
            line = word
    lines.append(line)
    y = int(size * 0.55)
    for text in lines[:3]:
        draw.text((size / 2, y), text, font=font, fill=(255, 255, 255), anchor="ma")
        y += int(size / 11 * 1.25)
    img.save(target, quality=90)
    return target


def thumbnail(track, cache_dir, size=320):
    """Vorschaubild: <Name>.jpg, sonst eingebettetes Cover, sonst Platzhalter. Gecacht nach Änderungszeit."""
    from PIL import Image
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    sources = [p for p in (track.jpg, track.main_audio) if p]
    stamp = "-".join(str(int(p.stat().st_mtime)) for p in sources)
    key = hashlib.md5(f"{track.id}|{stamp}|{size}".encode("utf-8")).hexdigest()[:16]
    target = cache_dir / f"thumb_{key}.jpg"
    if target.exists():
        return target
    if track.jpg:
        with Image.open(track.jpg) as img:
            img.convert("RGB").resize((size, size), Image.LANCZOS).save(target, quality=90)
        return target
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg and track.main_audio:
        cmd = [ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(track.main_audio), "-map", "0:v:0?", "-frames:v",
               "1", "-vf", f"scale={size}:{size}", str(target)]
        if subprocess.run(cmd, capture_output=True).returncode == 0 and target.exists() and target.stat().st_size:
            return target
    return placeholder(track.title, target, size)
