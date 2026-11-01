"""YuE2 Music Studio – Gradio-Oberfläche (Deutsch / English)."""
import atexit
import math
import os
import random
import shutil
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

# Temporäre Dateien (Vorschau-Audio) landen in einem eigenen Ordner, der beim Beenden gelöscht wird.
TEMP_DIR = Path(tempfile.mkdtemp(prefix="yue2_app_"))
os.environ["GRADIO_TEMP_DIR"] = str(TEMP_DIR)
atexit.register(shutil.rmtree, TEMP_DIR, ignore_errors=True)
atexit.register(lambda: __import__("cover").ENGINE.stop())

# Muss vor dem ersten CUDA-Zugriff gesetzt sein: Ohne Aufräumschwelle hortet PyTorchs Allocator beim
# VAE-Dekodieren bis zu ~28 GB ungenutzten Cache, obwohl nur 2–7 GB belegt sind.
for _var in ("PYTORCH_CUDA_ALLOC_CONF", "PYTORCH_HIP_ALLOC_CONF"):
    os.environ.setdefault(_var, "garbage_collection_threshold:0.6")

import gradio as gr  # noqa: E402
import soundfile as sf  # noqa: E402

import abc_tools as at  # noqa: E402
import cover  # noqa: E402
import gpu_info  # noqa: E402
import i18n  # noqa: E402
import library  # noqa: E402
import llm  # noqa: E402
import mashup  # noqa: E402
import settings  # noqa: E402
import sysmon  # noqa: E402
import ui_theme as ui  # noqa: E402
from exporter import save_song  # noqa: E402
from i18n import t  # noqa: E402
from lyrics_tools import (auto_max_seconds, estimate_seconds, fmt_duration, issues_text, lint,  # noqa: E402
                          normalize_lyrics, sanitize_filename, structure_hint, target_lines)
from settings import CONFIG, path, prompt  # noqa: E402
from yue_engine import ENGINE, SAMPLE_RATE, Cancelled  # noqa: E402

# Sprachneutrale Werte; die Anzeigenamen kommen aus i18n.
MODE_NEW, MODE_REMAKE = "new", "remake"
LYRIC_LANGS = ["auto", "German", "English", "Spanish", "French", "Italian", "Portuguese", "Dutch",
               "Turkish", "Polish", "Russian", "Greek", "Arabic", "Japanese", "Chinese", "Korean"]
# Zweite Sprache eines mehrsprachigen Songs und wo sie eingesetzt wird
MIX_USES = ["chorus", "bridge", "chorus_bridge", "lines", "idea"]
MIX_RULES = {
    "chorus": "every [Chorus] section (write each chorus repetition identically in {second}); "
              "all other sections stay in the main language",
    "bridge": "the [Bridge] section; all other sections stay in the main language",
    "chorus_bridge": "every [Chorus] and the [Bridge]; all other sections stay in the main language",
    "lines": "whole single lines mixed into the sections, mostly in the chorus (e.g. every second chorus line); "
             "about a quarter of all sung lines. Each line is either completely {second} or completely in the main "
             "language – never both languages inside one line",
    "idea": "the parts the song idea / user wish asks for; if it does not say, use it for every [Chorus]",
}
LYRICS_MODES = ["keep", "rewrite", "translate"]
COTS = ["full", "melody", "off"]


def mode_choices():
    return [(t("mode.new"), MODE_NEW), (t("mode.remake"), MODE_REMAKE)]


def lang_choices():
    return [(t(f"lang.{code}"), code) for code in LYRIC_LANGS]


def lmode_choices():
    return [(t(f"lm.{code}"), code) for code in LYRICS_MODES]


def cot_choices():
    return [(t(f"cot.{code}"), code) for code in COTS]


def lang2_choices():
    return [(t("lang.none"), "none")] + [(t(f"lang.{code}"), code) for code in LYRIC_LANGS[1:]]


def mix_choices():
    return [(t(f"mix.{code}"), code) for code in MIX_USES]


def lyric_language(code):
    return "" if code in (None, "", "auto") else code


def mix_instruction(main, second_code, use):
    """Zusatz für den Masterprompt bei zwei Sprachen; leer, wenn der Song einsprachig bleibt."""
    second = "" if second_code in (None, "", "none") else second_code
    if not second or second == main:
        return ""
    rule = MIX_RULES.get(use, MIX_RULES["chorus"]).format(second=second)
    return (f"Bilingual song: main language {main}, second language {second}. Use no third language.\n"
            f"Write in {second} (native script): {rule}.\n")


def mix_changed(second_code):
    return gr.update(interactive=second_code not in (None, "", "none"))


# ---------------------------------------------------------------- Hilfen

def gpu_status():
    """(Text, ok) für den Status-Chip, z. B. „RX 7900 XTX · 24 GB · ROCm“."""
    gpu = gpu_info.current()
    if gpu.vendor == "none":
        return t("chip.gpu_none"), False
    return f"{gpu.short_name} · {gpu.vram_gib:.0f} GB · {gpu.runtime}", True


def model_choices():
    """(Modelle, Vorauswahl, ok, Statustext)."""
    try:
        models = llm.list_models()
    except llm.OllamaError:
        return [], None, False, t("chip.ollama_err")
    default = CONFIG["ollama_default_model"]
    value = default if default in models else (models[0] if models else None)
    return models, value, True, t("chip.ollama_ok", n=len(models))


def hero_html():
    _, _, ok, text = model_choices()
    gpu_text, gpu_ok = gpu_status()
    return ui.hero(ok, text, gpu_text, gpu_ok, gpu_info.current().low_vram, cover.chip_text(), cover.available())


def refresh_models():
    models, value, _, _ = model_choices()
    return gr.update(choices=models, value=value), hero_html()


def require_model(model):
    if not model:
        raise gr.Error(t("err.no_model"))


def song_outputs(data, max_secs=None, auto_max=False):
    """Gemeinsame Ausgabe aller Erstellen-/Korrigieren-Aktionen."""
    # Manche Modelle maskieren Zeilenumbrüche doppelt – ein wörtliches „\n“ würde YuE2 sonst mitsingen.
    lyrics = normalize_lyrics(data["lyrics"].replace("\\n", "\n"))
    style = " ".join(data["style"].split())
    out = [data["title"], style, lyrics, data["language"], ui.lint_html(style, lyrics), data["title"]]
    if auto_max:
        max_secs = auto_max_seconds(lyrics, style)
    out.append(gr.update(value=max_secs) if max_secs else gr.update())
    out.append(data.get("concept", ""))
    return out


def concept_language():
    """Das Songkonzept schreibt Ollama in der Sprache der Oberfläche."""
    return "German" if i18n.get_lang() == "de" else "English"


# ---------------------------------------------------------------- Neuer Song

def create_new(idea, language_code, second_code, mix_use, target_secs, model, think):
    require_model(model)
    if not (idea or "").strip():
        raise gr.Error(t("err.no_idea"))
    lang = lyric_language(language_code)
    target_secs = int(target_secs)
    user = (f"Language for `concept`: {concept_language()}\n"
            f"Song idea: {idea.strip()}\n"
            f"Target language of the lyrics: {lang or 'the language the idea is written in'}\n"
            + mix_instruction(lang or "the language the idea is written in", second_code, mix_use) +
            f"Target length: about {target_secs} seconds ({fmt_duration(target_secs)} min)\n"
            f"Suggested structure: {structure_hint(target_secs)}\n"
            f"Aim for about {target_lines(target_secs)} sung lines in total (≈ 2 bars per line).")
    try:
        data = llm.chat_json(model, prompt("master_new.md"), user, think=think)
    except llm.OllamaError as e:
        raise gr.Error(str(e))
    return song_outputs(data, auto_max=True)


# ---------------------------------------------------------------- Remake

def load_source_info(audio_file):
    """Liest beim Laden eines Songs Titel, Interpret, Album, Cover usw. aus den Tags (MP3, FLAC, M4A …).

    Belegt außerdem die Felder der Online-Lyrics-Suche vor und setzt eine frühere Lyrics-Übernahme zurück.
    """
    reset = (gr.update(choices=[], value=None), None, None)
    if not audio_file:
        return ("", None, gr.update(), gr.update()) + reset
    from audio_utils import read_tags
    source = {"tags": read_tags(audio_file), "name": Path(audio_file).stem}
    tags = source["tags"]
    title = tags.get("title") or source["name"]
    artist = tags.get("artist") or tags.get("album_artist") or ""
    return (ui.track_card(tags, source["name"]), source, title, artist) + reset


def search_lyrics(title, artist, source):
    """Sucht den Originaltext online (LRCLIB). Treffer werden als Liste im State gehalten."""
    if not (title or "").strip():
        raise gr.Error(t("lyr.need_title"))
    import lyrics_online
    duration = ((source or {}).get("tags") or {}).get("duration")
    try:
        results = lyrics_online.search(title, artist, duration=duration)
    except lyrics_online.LyricsError as e:
        return gr.update(choices=[], value=None), [], ui.notice("err", t("lyr.failed_t"), ui.esc(e))
    if not results:
        return gr.update(choices=[], value=None), [], ui.notice("warn", t("lyr.none_t"), t("lyr.none_b"))
    choices = [(lyric_label(r), str(i)) for i, r in enumerate(results)]
    return gr.update(choices=choices, value="0"), results, ui.notice("ok", t("lyr.found", n=len(results)))


def lyric_label(r):
    album = f" · {r['album']}" if r["album"] else ""
    length = f" · {fmt_duration(r['duration'])}" if r["duration"] else ""
    return f"{r['title']} – {r['artist']}{album}{length}{' · ⏱ sync' if r['synced'] else ''}"


def use_lyrics(choice, results):
    """Übernimmt den gewählten Treffer in das Feld „Originaltext“ und merkt sich die Quelle."""
    if choice in (None, "") or not results:
        raise gr.Error(t("lyr.pick_first"))
    import lyrics_online
    r = results[int(choice)]
    label = f"{r['title']} – {r['artist']}" + (f" ({r['album']})" if r["album"] else "")
    source = {"provider": lyrics_online.PROVIDER, "id": r["id"], "label": label}
    lines = len([line for line in r["lyrics"].splitlines() if line.strip()])
    return r["lyrics"], source, ui.notice("ok", t("lyr.used_t"), ui.esc(t("lyr.used_b", lines=lines, label=label)))


def analyze_remake(audio_file, current_text, lyrics_source):
    if not audio_file:
        raise gr.Error(t("err.no_upload"))
    from melody import transcribe_melody
    from lyrics_asr import transcribe

    llm.unload()  # VRAM für SheetSage2 und Whisper freimachen
    if not ENGINE.unload():
        raise gr.Error(t("err.busy"))
    keep = gr.update()
    yield keep, keep, ui.notice("info", t("remake.step1"),
                                      t("remake.step1_sub_cpu" if gpu_info.current().is_amd else "remake.step1_sub")), keep, keep
    try:
        abc, warnings = transcribe_melody(audio_file)
    except RuntimeError as e:
        yield keep, keep, ui.notice("err", t("remake.melody_failed"), ui.esc(e)), keep, keep
        raise gr.Error(str(e))
    note = f"<br>{t('remake.hints')}: {ui.esc('; '.join(warnings)[:300])}" if warnings else ""
    if lyrics_source and (current_text or "").strip():
        # Originaltext stammt aus der Online-Suche – exakter als Spracherkennung, Whisper entfällt.
        text = keep
        note = f"<br>{t('remake.asr_skipped')}" + note
    else:
        yield abc, keep, ui.notice("info", t("remake.step2"), t("remake.melody_done") + note), keep, keep
        try:
            text = transcribe(audio_file)
        except Exception as e:
            yield keep, keep, ui.notice("err", t("remake.asr_failed"), ui.esc(e)), keep, keep
            raise gr.Error(t("err.whisper", e=e))
    from audio_utils import load_mono
    duration = len(load_mono(audio_file, 8000)) / 8000
    yield (abc, text, ui.notice("ok", t("remake.done", dur=fmt_duration(duration)), t("remake.done_sub") + note),
           gr.update(value=min(600, int(duration) + 30)), duration)


def create_remake(transcript, lyrics_mode, target_lang_code, second_code, mix_use, style_wish, abc, model,
                  src_duration, lyrics_source, think):
    require_model(model)
    if not (abc or "").strip():
        raise gr.Error(t("err.no_abc"))
    from melody import abc_header, abc_sections
    sections = abc_sections(abc)
    target = lyric_language(target_lang_code)
    if lyrics_mode == "translate" and not target:
        raise gr.Error(t("err.no_target_lang"))
    origin = ("online lyrics database (exact wording, no section tags)" if lyrics_source
              else "automatic speech recognition of the vocals (may contain recognition errors)")
    user = (f"Language for `concept`: {concept_language()}\n"
            f"Lyrics mode: {lyrics_mode}\n"
            + (f"Target language: {target}\n" if lyrics_mode == "translate" else "")
            + mix_instruction(target if lyrics_mode == "translate" else "the language of the original lyrics",
                              second_code, mix_use)
            + f"User wish for the new style / idea: {(style_wish or '').strip() or '(none)'}\n"
            f"Original song length: about {int(src_duration or 0)} seconds\n"
            f"Original score header (tempo, meter, key): {abc_header(abc) or 'unknown'}\n"
            f"Section order detected in the original melody: {' → '.join(sections) or 'unknown'}\n"
            f"Source of the original lyrics: {origin}\n\n"
            f"Original lyrics:\n{(transcript or '').strip() or '(no vocals recognised)'}")
    try:
        data = llm.chat_json(model, prompt("master_remake.md"), user, think=think)
    except llm.OllamaError as e:
        raise gr.Error(str(e))
    return song_outputs(data)


# ---------------------------------------------------------------- Korrektur

def check(style, lyrics):
    return ui.lint_html(style, lyrics) or ui.notice("warn", t("check.empty_t"), t("check.empty_b"))


def correct(concept, title, style, lyrics, request, model, think):
    require_model(model)
    if not (style or lyrics):
        raise gr.Error(t("err.nothing_to_correct"))
    user = (f"Correction request from the user: {(request or '').strip() or '(none – only fix rule violations)'}\n\n"
            f"Automatic check warnings:\n{issues_text(style, lyrics)}\n\n"
            f"Language for `concept`: {concept_language()}\n"
            f"Current concept: {(concept or '').strip() or '(none)'}\n\n"
            f"Current title: {title}\n\nCurrent style:\n{style}\n\nCurrent lyrics:\n{lyrics}")
    try:
        data = llm.chat_json(model, prompt("master_correct.md"), user, temperature=0.4, think=think)
    except llm.OllamaError as e:
        raise gr.Error(str(e))
    return song_outputs(data)


def normalize(style, lyrics):
    lyrics = normalize_lyrics(lyrics or "")
    return lyrics, ui.lint_html(style, lyrics)


# ---------------------------------------------------------------- Generierung

def generate(mode, concept, title, style, lyrics, language, cot, seed, random_seed, cfg, max_secs, abc,
             model, idea, style_wish, transcript, lyrics_mode, source_file, source_meta, lyrics_origin, mashup_meta=None):
    errors, _ = lint(style, lyrics)
    if errors:
        raise gr.Error(t("err.fix_first") + "\n" + "\n".join(errors[:5]))
    if mode == MODE_REMAKE:
        if not (abc or "").strip():
            raise gr.Error(t("err.remake_no_abc"))
        cot, use_abc = "melody", abc
    else:
        use_abc = None
        # Nach Bearbeiten/Korrigieren kann der Text länger geworden sein: Grenze nie unter den Bedarf fallen lassen,
        # sonst bricht YuE2 mitten im Song ab („Token-Limit erreicht“).
        max_secs = max(int(max_secs), auto_max_seconds(lyrics, style))
    seed = random.randrange(0, 2**31) if random_seed else int(seed or 0)
    cfg_scale = None if cfg is None or abs(float(cfg) - 1.0) < 1e-9 else float(cfg)

    llm.unload()  # Ollama-Modell aus dem VRAM werfen – YuE2 braucht ~22 GB
    box = {}

    def work():
        try:
            box["result"] = ENGINE.generate(style, lyrics, cot=cot, seed=seed, abc=use_abc,
                                            cfg_scale=cfg_scale, max_seconds=int(max_secs),
                                            expected_seconds=estimate_seconds(lyrics, style))
        except BaseException as e:  # an den UI-Thread weiterreichen
            box["error"] = e

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    while worker.is_alive():
        yield gr.update(), ui.progress_html(ENGINE.progress), gr.update(), seed
        worker.join(timeout=1.0)

    if "error" in box:
        e = box["error"]
        if isinstance(e, Cancelled):
            yield None, ui.notice("warn", t("gen.cancelled")), None, seed
            return
        yield gr.update(), ui.notice("err", t("gen.failed"), ui.esc(e)), gr.update(), seed
        raise gr.Error(f"{t('gen.failed')}: {e}")

    audio, meta = box["result"]
    preview = TEMP_DIR / f"preview_{int(time.time())}.flac"
    sf.write(preview, audio, SAMPLE_RATE, subtype="PCM_16")
    info = {
        **meta, "title": title, "language": language, "style": style, "lyrics": lyrics,
        "mode": mode, "created": f"{datetime.now():%Y-%m-%d %H:%M:%S}", "llm_model": model,
        "idea": idea if mode == MODE_NEW else style_wish, "concept": (concept or "").strip(),
    }
    if mode == MODE_REMAKE:
        tags = {k: v for k, v in ((source_meta or {}).get("tags") or {}).items() if k != "cover"}
        info.update(source_file=Path(source_file).name if source_file else "", transcript=transcript,
                    lyrics_mode=lyrics_mode, abc=abc, source_tags=tags, lyrics_origin=lyrics_origin)
        # Noten stammen aus dem Mashup-Bereich (unverändert) → als Mashup vermerken
        if mashup_meta and (abc or "").strip() == (mashup_meta.get("abc") or "").strip():
            info.update(mode="mashup", mashup=mashup_meta, idea=mashup_meta.get("idea", ""))
    result = {"audio": audio, "info": info, "meta": meta, "seed": seed, "title": title}
    yield str(preview), ui.result_html(title, meta, seed), result, seed


def cancel():
    ENGINE.cancel()
    return ui.notice("warn", t("cancel.t"), t("cancel.b"))


def unload_all():
    llm.unload()
    if not ENGINE.unload() or not cover.ENGINE.stop():
        return ui.notice("warn", t("unload.busy_t"), t("unload.busy_b"))
    return ui.notice("ok", t("unload.ok_t"), t("unload.ok_b"))


# ---------------------------------------------------------------- Speichern

def save(result, name, fmt, out_dir, overwrite, with_cover, model):
    if not result:
        raise gr.Error(t("err.no_song"))
    name = sanitize_filename(name or result["info"].get("title"))
    export = settings.export_settings()
    tags = {k: export.get(k, "") for k in ("artist", "album", "genre", "year", "comment")}
    info = {**result["info"], **tags, "title": name}
    folder = Path(out_dir or path("output_dir"))
    try:
        audio_file, text_file = save_song(result["audio"], SAMPLE_RATE, name, fmt, folder, info, overwrite=overwrite,
                                          export=export)
    except (FileExistsError, RuntimeError, OSError) as e:
        yield ui.notice("err", t("save.failed"), ui.esc(e))
        return
    library.remember_dir(folder)
    saved = ui.notice("ok", t("save.ok", name=name),
                      f"<code>{ui.esc(audio_file)}</code><br><code>{ui.esc(text_file)}</code>")
    if not (with_cover and cover.available()):
        try:  # vorhandenes Cover (z. B. vom MP3) auch in das neue Format übernehmen
            cover.embed_existing(audio_file, name, info.get("artist", ""))
        except RuntimeError as e:
            saved += ui.notice("warn", t("cover.failed"), ui.esc(e))
        yield saved
        return
    for status in run_cover(audio_file.parent, audio_file.stem, info, model):
        yield saved + status


# ---------------------------------------------------------------- Cover (optional, FLUX.3 Image Klein)

def cover_status_html(step, i=0, n=0):
    texts = {"prompt": t("cover.step_prompt"), "load": t("cover.step_load"),
             "render": t("cover.step_render", i=i, n=n), "embed": t("cover.step_embed")}
    pct = {"prompt": 8, "load": 20, "embed": 97}.get(step, 22 + 72 * (i / max(n, 1)))
    return (f'<div class="cover-prog"><div class="prog-head"><span class="prog-stage">{ui.esc(texts[step])}</span>'
            f'<span class="prog-pct">{pct:.0f} %</span></div><div class="prog-bar"><div class="prog-fill" '
            f'style="width:{pct:.1f}%"></div></div></div>')


def run_cover(folder, stem, info, model):
    """Erstellt das Cover im Hintergrund-Thread und liefert laufend Status-HTML (zuletzt Ergebnis/Fehler)."""
    if not cover.available():
        yield ui.notice("warn", t("cover.failed"), t("cover.missing"))
        return
    if ENGINE.busy:
        yield ui.notice("warn", t("cover.failed"), t("cover.busy_yue"))
        return
    if not model:
        yield ui.notice("err", t("cover.failed"), t("err.no_model"))
        return
    state, box = {"step": ("prompt",)}, {}

    def work():
        try:
            box["result"] = cover.make_cover(folder, stem, info, model,
                                             on_status=lambda *s: state.__setitem__("step", s))
        except BaseException as e:  # an den UI-Thread weiterreichen
            box["error"] = e

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    while worker.is_alive():
        yield cover_status_html(*state["step"])
        worker.join(timeout=0.5)
    if "error" in box:
        yield ui.notice("err", t("cover.failed"), ui.esc(box["error"]))
        return
    jpg, _caption, seed, embedded = box["result"]
    yield ui.notice("ok", t("cover.done_t"),
                    ui.esc(t("cover.done_b", file=jpg.name, formats=", ".join(embedded) or "–", seed=seed)))


# ---------------------------------------------------------------- Bibliothek

LIB_ORDERS = ["new", "title", "length"]
THUMB_DIR = TEMP_DIR / "thumbs"
SERVE_DIR = TEMP_DIR / "library"
ALLOWED_DIRS = [TEMP_DIR] + [d.resolve() for d in library.library_dirs()]


def lib_sort_choices():
    return [(t(f"lib.sort.{o}"), o) for o in LIB_ORDERS]


def served(file):
    """Gradio liefert nur Dateien aus erlaubten Ordnern aus; neue Ordner der laufenden Sitzung per Kopie."""
    file = Path(file).resolve()
    if any(file.is_relative_to(d) for d in ALLOWED_DIRS):
        return str(file)
    SERVE_DIR.mkdir(parents=True, exist_ok=True)
    target = SERVE_DIR / f"{abs(hash((str(file), file.stat().st_mtime))) % 10**12}{file.suffix}"
    if not target.exists():
        shutil.copy2(file, target)
    return str(target)


def library_view(query, order):
    """(Galerie-Einträge, Track-Liste, Zähler-HTML) für die aktuelle Suche/Sortierung."""
    all_tracks = library.scan()
    tracks = library.sort_filter(all_tracks, query, order)
    # Bildunterschrift zweizeilig: Titel, darunter Länge · Genre · BPM
    items = [(str(library.thumbnail(tr, THUMB_DIR)), f"{tr.title}\n{tr.summary()}" if tr.summary() else tr.title)
             for tr in tracks]
    if not all_tracks:
        count = ui.notice("info", t("lib.empty"))
    elif len(tracks) == len(all_tracks):
        count = f'<div class="lib-count">{ui.esc(t("lib.count", n=len(tracks)))}</div>'
    else:
        count = f'<div class="lib-count">{ui.esc(t("lib.count_filtered", n=len(tracks), total=len(all_tracks)))}</div>'
    return items, tracks, count


def refresh_library(query, order):
    items, tracks, count = library_view(query, order)
    return gr.update(value=items, selected_index=None), tracks, count


def cover_button(track):
    label = t("cover.btn_again") if track and track.jpg else t("cover.btn")
    return gr.update(value=label, interactive=bool(track) and cover.available())


def track_details(track):
    """Ausgaben der Detailkarte: Cover, Kopf, Player, Konzept, Idee, Style, Lyrics, Cover-Knopf."""
    if track is None:
        return (None, f'<div class="lib-pick">{ui.esc(t("lib.pick"))}</div>', None, "", "", "", "",
                cover_button(None))
    info = track.info
    image = served(track.jpg) if track.jpg else str(library.thumbnail(track, THUMB_DIR, size=512))
    audio = served(track.main_audio) if track.main_audio else None
    return (image, ui.track_head(track), audio, info.get("concept", ""), info.get("idea", ""),
            info.get("style", ""), info.get("lyrics", ""), cover_button(track))


def select_track(tracks, evt: gr.SelectData):
    track = tracks[evt.index] if tracks and evt.index is not None and evt.index < len(tracks) else None
    return (track, *track_details(track), "")


def library_cover(track, model, query, order):
    """Cover für den gewählten Song erstellen; danach Galerie und Detailkarte aktualisieren."""
    if track is None:
        raise gr.Error(t("lib.no_track"))
    keep = gr.update()
    for status in run_cover(track.folder, track.stem, {**track.info, "title": track.title}, model):
        yield status, keep, keep, keep, keep, keep, keep
    items, tracks, count = library_view(query, order)
    fresh = next((tr for tr in tracks if tr.id == track.id), track)
    image = served(fresh.jpg) if fresh.jpg else keep
    yield gr.update(), gr.update(value=items), tracks, fresh, image, cover_button(fresh), ui.track_head(fresh)


def _reused(track, what):
    return ui.notice("ok", t("lib.reused_t"), ui.esc(t("lib.reused_b", title=track.title, what=t(what))))


def reuse_all(track):
    """Alle Werte ins Studio: Titel, Konzept, Idee/Stilwunsch, Sprache, Style, Lyrics, Seed, CoT (+ Remake-Melodie)."""
    if track is None:
        raise gr.Error(t("lib.no_track"))
    info = track.info
    style, lyrics = info.get("style", ""), info.get("lyrics", "")
    remake = info.get("mode") in ("remake", "mashup") and bool(info.get("abc"))
    seed = info.get("seed")
    max_secs = (min(600, int(track.seconds) + 60) if remake and track.seconds
                else auto_max_seconds(lyrics, style))
    keep = gr.update()
    return (gr.update(selected="studio"),
            MODE_REMAKE if remake else MODE_NEW,
            keep if remake else info.get("idea", ""),        # idea
            info.get("idea", "") if remake else keep,         # style_wish
            info.get("abc", "") if remake else keep,          # abc
            info.get("lyrics_mode") or keep if remake else keep,
            info.get("concept", ""), track.title, style, lyrics, info.get("language", ""),
            ui.lint_html(style, lyrics), track.title, max_secs,
            seed if isinstance(seed, int) else keep, gr.update(value=not isinstance(seed, int)),
            info.get("cot") if info.get("cot") in COTS else keep,
            _reused(track, "lib.what_all_remake" if remake else "lib.what_all"))


def reuse_idea(track):
    if track is None:
        raise gr.Error(t("lib.no_track"))
    return (gr.update(selected="studio"), MODE_NEW, track.info.get("idea", ""), track.info.get("concept", ""),
            _reused(track, "lib.what_idea"))


def reuse_style(track, lyrics):
    if track is None:
        raise gr.Error(t("lib.no_track"))
    style = track.info.get("style", "")
    return gr.update(selected="studio"), style, ui.lint_html(style, lyrics), _reused(track, "lib.what_style")


def reuse_lyrics(track, style):
    if track is None:
        raise gr.Error(t("lib.no_track"))
    lyrics = track.info.get("lyrics", "")
    return gr.update(selected="studio"), lyrics, ui.lint_html(style, lyrics), _reused(track, "lib.what_lyrics")


# ---------------------------------------------------------------- Mashup

MAX_SLOTS = mashup.MAX_SLOTS
SLOT_PARTS = 5  # je Teil: Gruppe, Kopf, A/B-Schalter, Text, Noten


def _shift_text(info):
    n = int(info.get("semitones", 0) or 0)
    key = "mash.shift_up" if n > 0 else "mash.shift_down" if n < 0 else "mash.shift_none"
    return t(key, n=abs(n))


def _scores(state):
    return at.parse_score(state["a"]["abc"]), at.parse_score(state["b"]["abc"])


def _slot_section(state, slot, sa, sb, octave):
    if slot["source"] == "B" and slot["b_index"] is not None:
        return at.adapt_section(sb.sections[slot["b_index"]], sb.unit, sa.unit, sa.key, octave)[0]
    return sa.sections[slot["index"]]


def slot_views(state, sections=None):
    """Updates aller Teil-Karten: Sichtbarkeit, Kopf, A/B, Text, Noten (in dieser Reihenfolge, je MAX_SLOTS)."""
    slots = (state or {}).get("slots") or []
    groups, heads, radios, texts, staffs = [], [], [], [], []
    if slots:
        sa, sb = _scores(state)
        octave = at.best_octave(sa, sb)
    for i in range(MAX_SLOTS):
        if i < len(slots):
            s = slots[i]
            song = state["a"] if s["source"] == "A" else state["b"]
            groups.append(gr.update(visible=True))
            heads.append(ui.slot_head(i, s["tag"], s["source"], song["title"], s["b_index"] is not None,
                                      i in (state.get("stale") or [])))
            radios.append(gr.update(value=s["source"], interactive=s["b_index"] is not None))
            texts.append(gr.update(value="\n".join(sections[i])) if sections is not None else gr.update())
            staffs.append(ui.staff_html(at.vocal_abc(_slot_section(state, s, sa, sb, octave), sa), s["source"]))
        else:
            groups.append(gr.update(visible=False))
            heads.append("")
            radios.append(gr.update(value="A"))
            texts.append(gr.update(value="") if sections is not None else gr.update())
            staffs.append("")
    return groups + heads + radios + texts + staffs


def _keep_slots():
    return [gr.update()] * (MAX_SLOTS * SLOT_PARTS)


def _timeline(state):
    if not state or not state.get("slots"):
        return f'<div class="lyr-hint">{ui.esc(t("mash.empty"))}</div>'
    return ui.timeline_html(state["slots"], state["a"]["title"], state["b"]["title"])


def _texts_to_sections(state, texts):
    n = len((state or {}).get("slots") or [])
    return [[ln.strip() for ln in (texts[i] or "").splitlines() if ln.strip()] for i in range(n)]


class _Progress:
    """Gemeinsamer Fortschritt zwischen Hintergrund-Thread und Oberfläche."""

    def __init__(self, steps, expected):
        self.steps, self.expected = steps, expected  # erwartete Sekunden je Schritt (für die Zwischenanzeige)
        self.index, self.phase_start, self.start = 0, time.time(), time.time()
        self.think = self.write = 0
        self.write_expected = 0

    def go(self, index):
        self.index, self.phase_start = index, time.time()

    def llm(self, kind, chars):
        if kind == "think":
            self.think = chars
        else:
            self.write = chars

    def percent(self):
        n = len(self.steps)
        frac = 1 - math.exp(-(time.time() - self.phase_start) / max(self.expected[min(self.index, n - 1)], 1))
        if self.write and self.write_expected:  # Text wird geschrieben: echter Anteil statt Schätzung
            frac = max(frac, min(self.write / self.write_expected, 0.97))
        return 100 * (self.index + min(frac, 0.95)) / n

    def html(self, title):
        detail = ""
        if self.write:
            detail = t("mash.p_write_chars", n=self.write)
        elif self.think:
            detail = t("mash.p_think_chars", n=self.think)
        return ui.task_progress_html(title, self.steps, self.index, self.percent(), time.time() - self.start, detail)


def _run_with_progress(work, progress, title, out):
    """Führt work() im Hintergrund aus und liefert alle 0,5 s die Fortschrittsanzeige über out(html)."""
    box = {}

    def run():
        try:
            box["result"] = work()
        except BaseException as e:  # an den UI-Thread weiterreichen
            box["error"] = e

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    while worker.is_alive():
        yield out(progress.html(title))
        worker.join(timeout=0.5)
    if "error" in box:
        raise box["error"]
    box.setdefault("result", None)
    return box["result"]


def mash_analyze(file_a, file_b, text_a, src_a, text_b, src_b, state, model):
    """Beide Songs analysieren (SheetSage2 + Text), Ablauf von A bauen, KI schlägt A/B je Teil vor."""
    if not file_a or not file_b:
        raise gr.Error(t("mash.need_both"))
    require_model(model)
    llm.unload()
    if not ENGINE.unload():
        raise gr.Error(t("err.busy"))
    state = dict(state or {})
    keep = gr.update()
    songs = (("a", file_a, text_a, src_a, t("mash.song_a")), ("b", file_b, text_b, src_b, t("mash.song_b")))
    steps = [t(k, song=label) for _, _, _, _, label in songs for k in ("mash.p_melody", "mash.p_lyrics")]
    steps.append(t("mash.p_plan"))
    progress = _Progress(steps, [45, 15, 45, 15, 25])

    def work():
        for n, (key, path_, text, src, _label) in enumerate(songs):
            cached = state.get(key) or {}
            if cached.get("path") == path_ and cached.get("text_in") == (text or ""):
                continue  # schon analysiert
            progress.go(2 * n)
            song = mashup.analyze_song(path_, text, src,
                                       on_phase=lambda kind, n=n: progress.go(2 * n + (0 if kind == "melody" else 1)))
            song.update(path=path_, text_in=text or "")
            state[key] = song
        progress.go(4)
        sa, sb = _scores(state)
        return sa, sb, mashup.suggest_choices(model, state["a"], state["b"], sa, sb, on_progress=progress.llm)

    try:
        sa, sb, choices = yield from _run_with_progress(
            work, progress, t("mash.p_analyze"), lambda html: (state, html, keep, *_keep_slots()))
    except Exception as e:  # SheetSage2/Whisper/Ollama-Fehler verständlich anzeigen
        yield state, ui.notice("err", t("mash.failed"), ui.esc(e)), keep, *_keep_slots()
        raise gr.Error(str(e))
    llm.unload()
    state.update(slots=mashup.build_slots(sa, sb, choices), stale=[], sections=None, title="")
    _, shift = at.build_mashup(sa, sb, [s["source"] for s in state["slots"]])
    state["shift"] = shift
    body = t("mash.analyzed_b", n=len(state["slots"]), shift=_shift_text(shift),
             frm=shift.get("from", sb.key.name) if shift else sb.key.name,
             to=shift.get("to", sa.key.name) if shift else sa.key.name)
    yield state, ui.notice("ok", t("mash.analyzed_t"), ui.esc(body)), _timeline(state), *slot_views(state, [[]] * MAX_SLOTS)


def mash_switch(index, choice, state):
    """Teil umschalten: Farbe, Noten und Ablauf sofort, Text als veraltet markieren."""
    if not state or not state.get("slots") or index >= len(state["slots"]):
        return state, gr.update(), gr.update(), gr.update(), gr.update()
    state = dict(state)
    sa, sb = _scores(state)
    choices = [s["source"] for s in state["slots"]]
    choices[index] = choice
    state["slots"] = mashup.build_slots(sa, sb, choices)
    if state.get("sections") is not None and index not in state.get("stale", []):
        state["stale"] = sorted(set(state.get("stale", [])) | {index})
    s = state["slots"][index]
    song = state["a"] if s["source"] == "A" else state["b"]
    head = ui.slot_head(index, s["tag"], s["source"], song["title"], s["b_index"] is not None,
                        index in state.get("stale", []))
    staff = ui.staff_html(at.vocal_abc(_slot_section(state, s, sa, sb, at.best_octave(sa, sb)), sa), s["source"])
    return state, _timeline(state), head, staff, gr.update(visible=bool(state.get("stale")))


def _lyrics_job(state, style, language_code, model, texts, rewrite=None, request=None):
    """Gemeinsamer Ablauf für Erstellen, Neu-Erzeugen und Korrigieren (immer Denkmodus)."""
    if not state or not state.get("slots"):
        raise gr.Error(t("mash.need_analysis"))
    require_model(model)
    state = dict(state)
    current = _texts_to_sections(state, texts) if (rewrite or request) else None
    keep = gr.update()
    progress = _Progress([t("mash.p_think"), t("mash.p_typing")], [40, 30])
    # Erwartete Antwortlänge: ~45 Zeichen je Zeile plus JSON-Gerüst
    progress.write_expected = 45 * sum(s["lines"] for s in state["slots"]) + 300

    def on_llm(kind, chars):
        progress.llm(kind, chars)
        if kind == "write" and progress.index == 0:
            progress.go(1)

    def work():
        return mashup.write_lyrics(model, state["a"], state["b"], state["slots"], style, lyric_language(language_code),
                                   current, rewrite, request, tempo=_scores(state)[0].tempo, on_progress=on_llm)

    try:
        title, new_style, sections = yield from _run_with_progress(
            work, progress, t("mash.p_write"), lambda html: (state, keep, html, keep, *_keep_slots()))
    except llm.OllamaError as e:
        yield state, keep, ui.notice("err", t("mash.failed"), ui.esc(e)), keep, *_keep_slots()
        raise gr.Error(str(e))
    llm.unload()
    state.update(sections=sections, stale=[], title=title or state.get("title") or
                 f"{state['a']['title']} × {state['b']['title']}")
    style_out = style if (style or "").strip() else new_style
    yield (state, style_out, ui.notice("ok", t("mash.written_t"), t("mash.written_b")), gr.update(visible=False),
           *slot_views(state, sections))


def mash_write(state, style, language_code, model, *texts):
    yield from _lyrics_job(state, style, language_code, model, texts)


def mash_regen(state, style, language_code, model, *texts):
    yield from _lyrics_job(state, style, language_code, model, texts, rewrite=list((state or {}).get("stale") or []))


def mash_correct(state, request, style, language_code, model, *texts):
    if not (request or "").strip():
        raise gr.Error(t("err.nothing_to_correct"))
    yield from _lyrics_job(state, style, language_code, model, texts, request=request.strip())


def mash_suggest_style(state, model):
    """Style-Vorschlag für das Mashup (Denkmodus) aus Genre, Tempo und Texten beider Songs."""
    if not state or not state.get("slots"):
        raise gr.Error(t("mash.need_analysis"))
    require_model(model)
    sa, _ = _scores(state)
    system = ("You write the style prompt for the AI music model YuE2 for a mashup of two songs. Reply with JSON "
              "{\"style\": \"...\"}: one single line of comma-separated English descriptors, 10–30 words, in this "
              "order: language(s) of the lyrics → vocal (gender + timbre) → genre/subgenre that blends both songs → "
              "mood → tempo as NN BPM (use song A's tempo) → 3–5 concrete instruments → 1–2 production descriptors "
              "such as seamless mashup production. Never artist or song names.")
    user = "\n\n".join(
        f"Song {k.upper()}: {state[k]['title']} | genre tag: {state[k]['tags'].get('genre', 'unknown')}\n"
        f"Lyrics excerpt:\n{state[k]['lyrics'][:700]}" for k in ("a", "b")) + f"\n\nTempo of song A: {sa.tempo} BPM"
    try:
        data = llm.chat_json(model, system, user, schema={"type": "object", "properties": {"style": {"type": "string"}},
                                                          "required": ["style"]}, temperature=0.6, think=True)
    except llm.OllamaError as e:
        raise gr.Error(str(e))
    llm.unload()
    return " ".join(data.get("style", "").split())


def mash_send(state, style, *texts):
    """Kombinierte Noten, Text und Style ins Studio übernehmen."""
    if not state or not state.get("slots"):
        raise gr.Error(t("mash.need_analysis"))
    sections = _texts_to_sections(state, texts)
    sa, sb = _scores(state)
    abc, lyrics, info = mashup.assemble(sa, sb, state["slots"], sections)
    lyrics = normalize_lyrics(lyrics)
    style = " ".join((style or "").split())
    title = state.get("title") or f"{state['a']['title']} × {state['b']['title']}"
    plan = " · ".join(f"{s['tag']} {s['source']}" for s in state["slots"])
    describe = lambda s, score: (f"{s['title']}" + (f" – {s['artist']}" if s.get("artist") else "")
                                 + f" ({s['name']}) · {score.key.name} · {score.tempo} BPM")
    meta = {"abc": abc, "a": describe(state["a"], sa), "b": describe(state["b"], sb),
            "shift": f"{_shift_text(info['shift'])} ({info['shift'].get('from', '')} → {info['shift'].get('to', '')})"
                     if info["shift"] else _shift_text({}),
            "plan": plan, "idea": f"Mashup: {state['a']['title']} × {state['b']['title']}"}
    max_secs = min(600, int(info["seconds"] * 1.3) + 60)
    note = ui.notice("ok", t("mash.sent_t"), ui.esc(t("mash.sent_b", title=title)))
    return (gr.update(selected="studio"), MODE_REMAKE, abc, "", style, lyrics, title, title, "",
            ui.lint_html(style, lyrics), max_secs, meta, note)


# ---------------------------------------------------------------- Einstellungen (Export)

def mp3_choices():
    return [(f"{b} kbit/s", b) for b in settings.MP3_BITRATES if b != "V0"] + [(t("exp.mp3_v0"), "V0")]


def save_export_ui(mp3, flac, artist, album, genre, year, comment, cover_artist):
    settings.save_export(mp3_bitrate=str(mp3), flac_bits=int(flac), artist=(artist or "").strip(),
                         album=(album or "").strip(), genre=(genre or "").strip(), year=(year or "").strip(),
                         comment=(comment or "").strip(), artist_on_cover=bool(cover_artist))
    mp3_text = t("exp.mp3_v0") if str(mp3) == "V0" else f"{mp3} kbit/s"
    return ui.notice("ok", t("exp.saved_t"), ui.esc(t("exp.saved_b", fmt=f"MP3 {mp3_text} · FLAC {flac} Bit"
                                                       + (f" · {artist.strip()}" if (artist or "").strip() else ""))))


# ---------------------------------------------------------------- UI

def build_ui():
    models, model_value, _, _ = model_choices()
    registry = []  # (Komponente, {Eigenschaft: i18n-Schlüssel oder Funktion}) – wird beim Sprachwechsel neu befüllt

    def tr(component, **spec):
        registry.append((component, spec))
        return component

    with gr.Blocks(title="YuE2 Music Studio", theme=ui.THEME, css=ui.CSS, js=ui.FORCE_DARK_JS, fill_width=True,
                   head=ui.head_html(i18n.get_lang())) as demo:
        # --- Startdialog: Sprache wählen (nur beim allerersten Start)
        # Unsichtbar gebaut; on_load blendet ihn nur ein, solange noch keine Sprache gewählt wurde (kein Aufblitzen).
        with gr.Column(visible=False, elem_id="lang-modal") as modal:
            with gr.Column(elem_classes="modal-card"):
                gr.HTML(ui.modal_html(), elem_classes="html-slot")
                with gr.Row():
                    pick_de = gr.Button("Deutsch", variant="primary", elem_classes="lang-btn")
                    pick_en = gr.Button("English", variant="primary", elem_classes="lang-btn")

        # --- Kopfbereich mit Sprachumschalter oben rechts
        with gr.Row(elem_id="top-row"):
            hero = gr.HTML(hero_html(), elem_classes="html-slot")
            lang_switch = gr.Radio([("DE", "de"), ("EN", "en")], value=i18n.get_lang(), show_label=False,
                                   container=False, elem_id="lang-switch", elem_classes="seg", scale=0, min_width=110)
        language_state = gr.State("")
        mashup_meta = gr.State(None)  # gesetzt, wenn Noten/Text aus dem Mashup-Bereich übernommen wurden
        src_duration = gr.State(0)
        result_state = gr.State(None)
        source_info = gr.State(None)  # Tags des geladenen Original-Songs (Remake)
        lyric_results = gr.State([])  # Treffer der Online-Lyrics-Suche
        lyrics_source = gr.State(None)  # gesetzt, wenn der Originaltext aus der Online-Suche stammt

        with gr.Tabs(selected="studio", elem_id="main-tabs") as tabs:
          with gr.Tab(t("tab.studio"), id="studio") as tab_studio:
            tr(tab_studio, label="tab.studio")
            # Drei Spalten: Idee | Feinschliff | Generieren + Speichern (bricht auf schmalen Fenstern um)
            with gr.Row(equal_height=False, elem_id="main-row"):
                # ================= Spalte 1: Idee =================
                with gr.Column(scale=4, min_width=320):
                    with gr.Column(elem_classes="card"):
                        tr(gr.HTML(ui.step(1, "step1.title", "step1.sub")),
                           value=lambda: ui.step(1, "step1.title", "step1.sub"))
                        mode = tr(gr.Radio(mode_choices(), value=MODE_NEW, show_label=False, container=False,
                                           elem_id="mode-switch", elem_classes="seg"), choices=mode_choices)
                        with gr.Row(equal_height=True, elem_classes="model-row"):
                            model_dd = tr(gr.Dropdown(models, value=model_value, label=t("model.label"),
                                                      scale=5, min_width=160, elem_id="model-dd"),
                                          label="model.label")
                            refresh_btn = gr.Button("↻", scale=0, min_width=40, size="sm", elem_classes="icon-btn")
                        think = tr(gr.Checkbox(value=bool(CONFIG.get("ollama_think", True)), label=t("think.label"),
                                               container=False, elem_id="think-cb"), label="think.label")

                        # --- Neuer Song
                        with gr.Column(visible=True) as new_group:
                            idea = tr(gr.Textbox(label=t("idea.label"), lines=4, max_lines=8, elem_id="idea-box",
                                                 placeholder=t("idea.ph")), label="idea.label", placeholder="idea.ph")
                            with gr.Row():
                                language = tr(gr.Dropdown(lang_choices(), value="auto", label=t("language.label")),
                                              choices=lang_choices, label="language.label")
                                target_secs = tr(gr.Slider(60, 480, value=180, step=15, label=t("target.label")),
                                                 label="target.label")
                            with gr.Row():
                                language2 = tr(gr.Dropdown(lang2_choices(), value="none", label=t("lang2.label")),
                                               choices=lang2_choices, label="lang2.label")
                                mix_use = tr(gr.Dropdown(mix_choices(), value="chorus", label=t("mix.label"),
                                                         interactive=False),
                                               choices=mix_choices, label="mix.label")
                            create_new_btn = tr(gr.Button(t("create.btn"), variant="primary", elem_classes="create-btn"),
                                                value="create.btn")

                        # --- Remake
                        with gr.Column(visible=False) as remake_group:
                            source = tr(gr.Audio(label=t("source.label"), type="filepath", sources=["upload"],
                                                 waveform_options=ui.WAVEFORM), label="source.label")
                            track_box = gr.HTML(elem_classes="html-slot")
                            with gr.Accordion(t("lyr.acc"), open=False) as lyr_acc:
                                with gr.Row(equal_height=True):
                                    lyr_title = tr(gr.Textbox(label=t("lyr.title"), max_lines=1, min_width=120),
                                                   label="lyr.title")
                                    lyr_artist = tr(gr.Textbox(label=t("lyr.artist"), max_lines=1, min_width=120),
                                                    label="lyr.artist")
                                lyr_search_btn = tr(gr.Button(t("lyr.search_btn"), size="sm", variant="secondary"),
                                                    value="lyr.search_btn")
                                lyr_choice = tr(gr.Dropdown([], label=t("lyr.results"), elem_id="lyr-dd"),
                                                label="lyr.results")
                                lyr_use_btn = tr(gr.Button(t("lyr.use_btn"), size="sm", variant="primary"),
                                                 value="lyr.use_btn")
                                lyr_status = gr.HTML(elem_classes="html-slot")
                                lyr_hint = tr(gr.HTML(f'<div class="lyr-hint">{t("lyr.hint")}</div>'),
                                              value=lambda: f'<div class="lyr-hint">{t("lyr.hint")}</div>')
                            tr(lyr_acc, label="lyr.acc")
                            analyze_btn = tr(gr.Button(t("analyze.btn"), size="sm", variant="secondary",
                                                       elem_classes="ghost-btn"),
                                             value="analyze.btn")
                            remake_status = gr.HTML(elem_classes="html-slot")
                            transcript = tr(gr.Textbox(label=t("transcript.label"), lines=6, max_lines=12),
                                            label="transcript.label")
                            with gr.Accordion(t("abc.acc"), open=False) as abc_acc:
                                abc = gr.Textbox(lines=12, show_label=False)
                            tr(abc_acc, label="abc.acc")
                            lyrics_mode = tr(gr.Radio(lmode_choices(), value="keep", label=t("lmode.label"),
                                                      elem_classes="seg seg-sm"), choices=lmode_choices, label="lmode.label")
                            style_wish = tr(gr.Textbox(label=t("wish.label"), lines=2,
                                                       placeholder=t("wish.ph")), label="wish.label", placeholder="wish.ph")
                            remake_lang = tr(gr.Dropdown(lang_choices(), value="auto", label=t("rlang.label")),
                                             choices=lang_choices, label="rlang.label")
                            with gr.Row():
                                remake_lang2 = tr(gr.Dropdown(lang2_choices(), value="none", label=t("lang2.label")),
                                                  choices=lang2_choices, label="lang2.label")
                                remake_mix = tr(gr.Dropdown(mix_choices(), value="chorus", label=t("mix.label"),
                                                            interactive=False),
                                                  choices=mix_choices, label="mix.label")
                            create_remake_btn = tr(gr.Button(t("create.btn"), variant="primary", elem_classes="create-btn"),
                                                   value="create.btn")

                # ================= Spalte 2: Feinschliff =================
                with gr.Column(scale=5, min_width=400):
                    with gr.Column(elem_classes="card"):
                        tr(gr.HTML(ui.step(2, "step2.title", "step2.sub")),
                           value=lambda: ui.step(2, "step2.title", "step2.sub"))
                        concept = tr(gr.Textbox(label=t("concept.label"), lines=2, max_lines=5, elem_id="concept-box",
                                                placeholder=t("concept.ph")), label="concept.label", placeholder="concept.ph")
                        title = tr(gr.Textbox(label=t("title.label"), placeholder=t("title.ph")),
                                   label="title.label", placeholder="title.ph")
                        style = tr(gr.Textbox(label=t("style.label"), lines=2, elem_id="style-box", placeholder=t("style.ph")),
                                   label="style.label", placeholder="style.ph")
                        lyrics = tr(gr.Textbox(label=t("lyrics.label"), lines=14, max_lines=14, elem_id="lyrics-box",
                                               placeholder="[Verse]\n…\n\n[Chorus]\n…"), label="lyrics.label")
                        lint_box = gr.HTML(elem_classes="html-slot")
                        with gr.Row():
                            check_btn = tr(gr.Button(t("check.btn"), size="sm", min_width=100, elem_classes="ghost-btn"), value="check.btn")
                            normalize_btn = tr(gr.Button(t("normalize.btn"), size="sm", min_width=100, elem_classes="ghost-btn"),
                                               value="normalize.btn")
                        with gr.Row(equal_height=True, elem_classes="correct-row"):
                            correction = tr(gr.Textbox(label=t("correction.label"), scale=4, lines=2, max_lines=4,
                                                       placeholder=t("correction.ph")),
                                            label="correction.label", placeholder="correction.ph")
                            correct_btn = tr(gr.Button(t("correct.btn"), scale=0, min_width=180, size="sm",
                                                       variant="secondary"), value="correct.btn")

                # ================= Spalte 3: Generieren + Speichern =================
                with gr.Column(scale=4, min_width=320):
                    with gr.Column(elem_classes="card"):
                        tr(gr.HTML(ui.step(3, "step3.title", "step3.sub")),
                           value=lambda: ui.step(3, "step3.title", "step3.sub"))
                        gen_btn = tr(gr.Button(t("gen.btn"), variant="primary", elem_id="gen-btn"),
                                     value="gen.btn")
                        with gr.Row():
                            cancel_btn = tr(gr.Button(t("cancel.btn"), variant="stop", size="sm", min_width=100), value="cancel.btn")
                            unload_btn = tr(gr.Button(t("unload.btn"), size="sm", min_width=100, elem_classes="ghost-btn"),
                                            value="unload.btn")
                        gen_status = gr.HTML(ui.idle_html(), elem_id="gen-status", elem_classes="html-slot")
                        player = tr(gr.Audio(label=t("player.label"), type="filepath", interactive=False, elem_id="player",
                                             waveform_options=ui.WAVEFORM), label="player.label")
                        with gr.Accordion(t("adv.acc"), open=False) as adv_acc:
                            cot = tr(gr.Dropdown(cot_choices(), value="full", label=t("cot.label")),
                                     choices=cot_choices, label="cot.label")
                            max_secs = tr(gr.Slider(30, 600, value=180 if gpu_info.current().low_vram else 300, step=10,
                                                    label=t("max.label")), label="max.label")
                            with gr.Row():
                                seed = tr(gr.Number(value=831001, precision=0, label=t("seed.label"), min_width=120),
                                          label="seed.label")
                                cfg = tr(gr.Number(value=1.0, label=t("cfg.label"), minimum=0, maximum=20, min_width=120),
                                         label="cfg.label")
                            random_seed = tr(gr.Checkbox(value=True, label=t("random.label")), label="random.label")
                        tr(adv_acc, label="adv.acc")

                    with gr.Column(elem_classes="card"):
                        tr(gr.HTML(ui.step(4, "step4.title", "step4.sub")),
                           value=lambda: ui.step(4, "step4.title", "step4.sub"))
                        save_name = tr(gr.Textbox(label=t("savename.label"), placeholder=t("savename.ph")),
                                       label="savename.label", placeholder="savename.ph")
                        save_fmt = tr(gr.Radio(["MP3", "FLAC"], value="MP3", label=t("fmt.label"), elem_classes="seg seg-sm"),
                                      label="fmt.label")
                        save_dir = tr(gr.Textbox(value=str(path("output_dir")), label=t("savedir.label")),
                                      label="savedir.label")
                        overwrite = tr(gr.Checkbox(value=False, label=t("overwrite.label")), label="overwrite.label")
                        save_cover = tr(gr.Checkbox(value=False, label=t("cover.save_cb"), interactive=cover.available(),
                                                    info=None if cover.available() else t("cover.chip_off")),
                                        label="cover.save_cb")
                        save_btn = tr(gr.Button(t("save.btn"), variant="primary", elem_classes="create-btn"),
                                      value="save.btn")
                        save_box = gr.HTML(elem_classes="html-slot")



          # ================= Reiter Mashup =================
          with gr.Tab(t("tab.mashup"), id="mashup") as tab_mashup:
            tr(tab_mashup, label="tab.mashup")
            mash_state = gr.State(None)
            with gr.Row(equal_height=False, elem_classes="mash-songs"):
                with gr.Column(elem_classes="card song-a"):
                    tr(gr.HTML(ui.step(1, "mash.song_a", "mash.song_a_sub")),
                       value=lambda: ui.step(1, "mash.song_a", "mash.song_a_sub"))
                    mash_file_a = tr(gr.Audio(label=t("mash.upload"), type="filepath", sources=["upload"],
                                              waveform_options=ui.WAVEFORM), label="mash.upload")
                    mash_card_a = gr.HTML(elem_classes="html-slot")
                    mash_info_a = gr.State(None)  # Tags des Songs (Dauer für die Online-Suche)
                    mash_results_a = gr.State([])
                    with gr.Accordion(t("lyr.acc"), open=False) as mash_lyr_acc_a:
                        with gr.Row(equal_height=True):
                            mash_lyr_title_a = tr(gr.Textbox(label=t("lyr.title"), max_lines=1, min_width=120),
                                                    label="lyr.title")
                            mash_lyr_artist_a = tr(gr.Textbox(label=t("lyr.artist"), max_lines=1, min_width=120),
                                                     label="lyr.artist")
                        mash_lyr_search_a = tr(gr.Button(t("lyr.search_btn"), size="sm", variant="secondary"),
                                                 value="lyr.search_btn")
                        mash_lyr_choice_a = tr(gr.Dropdown([], label=t("lyr.results"), elem_id="lyr-dd-a"),
                                                 label="lyr.results")
                        mash_lyr_use_a = tr(gr.Button(t("lyr.use_btn"), size="sm", variant="primary"),
                                              value="lyr.use_btn")
                        mash_lyr_status_a = gr.HTML(elem_classes="html-slot")
                        tr(gr.HTML(f'<div class="lyr-hint">{t("lyr.hint")}</div>'),
                           value=lambda: f'<div class="lyr-hint">{t("lyr.hint")}</div>')
                    tr(mash_lyr_acc_a, label="lyr.acc")
                    mash_text_a = tr(gr.Textbox(label=t("mash.lyrics_label"), lines=4, max_lines=10),
                                     label="mash.lyrics_label")
                    mash_src_a = gr.State(None)
                with gr.Column(elem_classes="card song-b"):
                    tr(gr.HTML(ui.step(2, "mash.song_b", "mash.song_b_sub")),
                       value=lambda: ui.step(2, "mash.song_b", "mash.song_b_sub"))
                    mash_file_b = tr(gr.Audio(label=t("mash.upload"), type="filepath", sources=["upload"],
                                              waveform_options=ui.WAVEFORM), label="mash.upload")
                    mash_card_b = gr.HTML(elem_classes="html-slot")
                    mash_info_b = gr.State(None)  # Tags des Songs (Dauer für die Online-Suche)
                    mash_results_b = gr.State([])
                    with gr.Accordion(t("lyr.acc"), open=False) as mash_lyr_acc_b:
                        with gr.Row(equal_height=True):
                            mash_lyr_title_b = tr(gr.Textbox(label=t("lyr.title"), max_lines=1, min_width=120),
                                                    label="lyr.title")
                            mash_lyr_artist_b = tr(gr.Textbox(label=t("lyr.artist"), max_lines=1, min_width=120),
                                                     label="lyr.artist")
                        mash_lyr_search_b = tr(gr.Button(t("lyr.search_btn"), size="sm", variant="secondary"),
                                                 value="lyr.search_btn")
                        mash_lyr_choice_b = tr(gr.Dropdown([], label=t("lyr.results"), elem_id="lyr-dd-b"),
                                                 label="lyr.results")
                        mash_lyr_use_b = tr(gr.Button(t("lyr.use_btn"), size="sm", variant="primary"),
                                              value="lyr.use_btn")
                        mash_lyr_status_b = gr.HTML(elem_classes="html-slot")
                        tr(gr.HTML(f'<div class="lyr-hint">{t("lyr.hint")}</div>'),
                           value=lambda: f'<div class="lyr-hint">{t("lyr.hint")}</div>')
                    tr(mash_lyr_acc_b, label="lyr.acc")
                    mash_text_b = tr(gr.Textbox(label=t("mash.lyrics_label"), lines=4, max_lines=10),
                                     label="mash.lyrics_label")
                    mash_src_b = gr.State(None)
            with gr.Column(elem_classes="card"):
                tr(gr.HTML(ui.step(3, "mash.title", "mash.sub")), value=lambda: ui.step(3, "mash.title", "mash.sub"))
                mash_analyze_btn = tr(gr.Button(t("mash.analyze"), variant="primary", elem_classes="create-btn"),
                                      value="mash.analyze")
                mash_status = gr.HTML(elem_classes="html-slot")
                mash_timeline = gr.HTML(f'<div class="lyr-hint">{ui.esc(t("mash.empty"))}</div>', elem_classes="html-slot")
                with gr.Row(equal_height=True, elem_classes="model-row"):
                    mash_style = tr(gr.Textbox(label=t("mash.style"), placeholder=t("mash.style_ph"), lines=2, scale=5,
                                               elem_id="mash-style"), label="mash.style", placeholder="mash.style_ph")
                    mash_style_btn = tr(gr.Button(t("mash.style_ai"), size="sm", scale=0, min_width=170,
                                                  elem_classes="ghost-btn"), value="mash.style_ai")
                with gr.Row(equal_height=True, elem_classes="model-row"):
                    mash_lang = tr(gr.Dropdown(lang_choices(), value="auto", label=t("mash.language"), scale=2,
                                               min_width=180), choices=lang_choices, label="mash.language")
                    mash_write_btn = tr(gr.Button(t("mash.write"), variant="primary", scale=3, min_width=240),
                                        value="mash.write")
                slot_groups, slot_heads, slot_radios, slot_texts, slot_staffs = [], [], [], [], []
                for i in range(MAX_SLOTS):
                    with gr.Column(visible=False, elem_classes="mash-slot") as group:
                        with gr.Row(equal_height=True, elem_classes="slot-row"):
                            head = gr.HTML(elem_classes="html-slot")
                            radio = gr.Radio(["A", "B"], value="A", show_label=False, container=False, scale=0,
                                             min_width=110, elem_classes="seg seg-sm slot-ab")
                        text = tr(gr.Textbox(show_label=False, lines=3, max_lines=10, elem_classes="slot-text",
                                             placeholder=t("mash.lines_label")), placeholder="mash.lines_label")
                        staff = gr.HTML(elem_classes="html-slot")
                    slot_groups.append(group)
                    slot_heads.append(head)
                    slot_radios.append(radio)
                    slot_texts.append(text)
                    slot_staffs.append(staff)
                mash_regen_btn = tr(gr.Button(t("mash.regen"), variant="secondary", visible=False), value="mash.regen")
                with gr.Row(equal_height=True, elem_classes="correct-row"):
                    mash_request = tr(gr.Textbox(label=t("mash.correction"), placeholder=t("mash.correction_ph"),
                                                 lines=2, scale=4), label="mash.correction", placeholder="mash.correction_ph")
                    mash_correct_btn = tr(gr.Button(t("mash.correct"), size="sm", scale=0, min_width=180,
                                                    variant="secondary"), value="mash.correct")
                mash_send_btn = tr(gr.Button(t("mash.to_studio"), variant="primary", elem_classes="create-btn"),
                                   value="mash.to_studio")

          # ================= Reiter Bibliothek =================
          with gr.Tab(t("tab.library"), id="library") as tab_library:
            tr(tab_library, label="tab.library")
            lib_tracks = gr.State([])
            lib_track = gr.State(None)
            with gr.Row(equal_height=False, elem_id="lib-row"):
                with gr.Column(scale=7, min_width=380):
                    with gr.Column(elem_classes="card"):
                        tr(gr.HTML(ui.step(5, "lib.title", "lib.sub")), value=lambda: ui.step(5, "lib.title", "lib.sub"))
                        with gr.Row(equal_height=True, elem_classes="lib-tools"):
                            lib_query = tr(gr.Textbox(label=t("lib.search"), placeholder=t("lib.search_ph"), max_lines=1,
                                                      scale=4, min_width=160), label="lib.search", placeholder="lib.search_ph")
                            lib_order = tr(gr.Dropdown(lib_sort_choices(), value="new", label=t("lib.sort"), scale=2,
                                                       min_width=140), choices=lib_sort_choices, label="lib.sort")
                            lib_refresh = tr(gr.Button(t("lib.refresh"), size="sm", scale=1, min_width=110,
                                                       elem_classes="ghost-btn"), value="lib.refresh")
                        lib_count = gr.HTML(elem_classes="html-slot")
                        lib_gallery = tr(gr.Gallery(label=t("lib.gallery"), show_label=False, columns=4, height="auto",
                                                    object_fit="cover", allow_preview=False, elem_id="lib-gallery"),
                                         label="lib.gallery")
                with gr.Column(scale=5, min_width=340):
                    with gr.Column(elem_classes="card"):
                        lib_cover = gr.Image(type="filepath", interactive=False, show_label=False, container=False,
                                             height=300, elem_id="lib-cover", show_download_button=False,
                                             show_fullscreen_button=True)
                        lib_head = gr.HTML(f'<div class="lib-pick">{ui.esc(t("lib.pick"))}</div>', elem_classes="html-slot")
                        lib_player = tr(gr.Audio(label=t("lib.player"), type="filepath", interactive=False,
                                                 elem_id="lib-player", waveform_options=ui.WAVEFORM), label="lib.player")
                        with gr.Row(elem_classes="reuse-row"):
                            reuse_all_btn = tr(gr.Button(t("lib.reuse_all"), variant="primary", size="sm", min_width=150),
                                               value="lib.reuse_all")
                        with gr.Row(elem_classes="reuse-row"):
                            reuse_idea_btn = tr(gr.Button(t("lib.reuse_idea"), size="sm", min_width=80,
                                                          elem_classes="ghost-btn"), value="lib.reuse_idea")
                            reuse_style_btn = tr(gr.Button(t("lib.reuse_style"), size="sm", min_width=80,
                                                           elem_classes="ghost-btn"), value="lib.reuse_style")
                            reuse_lyrics_btn = tr(gr.Button(t("lib.reuse_lyrics"), size="sm", min_width=80,
                                                            elem_classes="ghost-btn"), value="lib.reuse_lyrics")
                        lib_cover_btn = gr.Button(t("cover.btn"), size="sm", interactive=False, elem_classes="ghost-btn")
                        lib_status = gr.HTML(elem_classes="html-slot")
                        lib_hint = tr(gr.HTML(), value=lambda: (f'<div class="lyr-hint">{t("lib.reuse_hint")}'
                                                                + ("" if cover.available() else f"<br>{t('cover.missing')}")
                                                                + "</div>"))
                        with gr.Accordion(t("lib.details"), open=False) as lib_acc:
                            lib_concept = tr(gr.Textbox(label=t("lib.concept"), lines=4, max_lines=8, interactive=False,
                                                        show_copy_button=True), label="lib.concept")
                            lib_idea = tr(gr.Textbox(label=t("lib.idea"), lines=3, max_lines=8, interactive=False,
                                                     show_copy_button=True), label="lib.idea")
                            lib_style = tr(gr.Textbox(label=t("lib.style"), lines=3, max_lines=6, interactive=False,
                                                      show_copy_button=True), label="lib.style")
                            lib_lyrics = tr(gr.Textbox(label=t("lib.lyrics"), lines=12, max_lines=24, interactive=False,
                                                       show_copy_button=True, elem_id="lib-lyrics"), label="lib.lyrics")
                        tr(lib_acc, label="lib.details")


          # ================= Reiter Einstellungen (Export) =================
          with gr.Tab(t("tab.settings"), id="settings") as tab_settings:
            tr(tab_settings, label="tab.settings")
            export = settings.export_settings()
            with gr.Row(equal_height=False, elem_id="settings-row"):
                with gr.Column(elem_classes="card", scale=1, min_width=340):
                    tr(gr.HTML(ui.step(6, "exp.title", "exp.sub")), value=lambda: ui.step(6, "exp.title", "exp.sub"))
                    exp_mp3 = tr(gr.Dropdown(mp3_choices(), value=str(export["mp3_bitrate"]), label=t("exp.mp3")),
                                 choices=mp3_choices, label="exp.mp3")
                    exp_flac = tr(gr.Radio([("16 Bit", 16), ("24 Bit", 24)], value=int(export["flac_bits"]),
                                           label=t("exp.flac"), elem_classes="seg seg-sm"), label="exp.flac")
                    exp_artist = tr(gr.Textbox(value=export["artist"], label=t("exp.artist"), placeholder=t("exp.artist_ph"),
                                               max_lines=1), label="exp.artist", placeholder="exp.artist_ph")
                    exp_cover_artist = tr(gr.Checkbox(value=bool(export["artist_on_cover"]), label=t("exp.cover_artist")),
                                          label="exp.cover_artist")
                    with gr.Row():
                        exp_album = tr(gr.Textbox(value=export["album"], label=t("exp.album"), max_lines=1),
                                       label="exp.album")
                        exp_genre = tr(gr.Textbox(value=export["genre"], label=t("exp.genre"), max_lines=1),
                                       label="exp.genre")
                    with gr.Row():
                        exp_year = tr(gr.Textbox(value=export["year"], label=t("exp.year"), max_lines=1, min_width=100),
                                      label="exp.year")
                        exp_comment = tr(gr.Textbox(value=export["comment"], label=t("exp.comment"), max_lines=1),
                                         label="exp.comment")
                    exp_save = tr(gr.Button(t("exp.save"), variant="primary", elem_classes="create-btn"), value="exp.save")
                    exp_status = gr.HTML(elem_classes="html-slot")
                with gr.Column(scale=1, min_width=10):
                    pass


        # --- Sprache anwenden: alle registrierten Texte plus dynamische Inhalte neu erzeugen
        translated = [component for component, _ in registry]
        dynamic = [hero, lint_box, gen_status, remake_status, save_box, track_box, lyr_status]

        def texts(style_text, lyrics_text, result, source):
            updates = []
            for _, spec in registry:
                updates.append(gr.update(**{prop: (src() if callable(src) else t(src)) for prop, src in spec.items()}))
            status = ui.result_html(result["title"], result["meta"], result["seed"]) if result else ui.idle_html()
            track = ui.track_card(source["tags"], source["name"]) if source else ""
            return updates + [hero_html(), ui.lint_html(style_text, lyrics_text), status, "", "", track, ""]

        def switch_language(lang, *inputs):
            i18n.set_lang(lang)
            return texts(*inputs)

        def pick_language(lang, *inputs):
            i18n.set_lang(lang)  # speichert die Wahl – der Dialog erscheint nicht wieder
            return [gr.update(visible=False), gr.update(value=lang)] + texts(*inputs)

        def on_load(*inputs):
            # Neu laden der Seite: aktuelle Sprache anwenden und Dialog nur beim ersten Start zeigen.
            return [gr.update(visible=i18n.is_first_start()), gr.update(value=i18n.get_lang())] + texts(*inputs)

        text_inputs = [style, lyrics, result_state, source_info]
        demo.load(on_load, inputs=text_inputs, outputs=[modal, lang_switch] + translated + dynamic,
                  show_progress="hidden")
        # .input statt .change: reagiert nur auf Klicks des Nutzers, nicht auf das programmatische Setzen beim Laden.
        lang_switch.input(switch_language, inputs=[lang_switch] + text_inputs, outputs=translated + dynamic,
                          show_progress="hidden")
        # Gradios eigene Texte (z. B. Upload-Hinweis) folgen der Sprache beim nächsten Laden (siehe ui.head_html).
        # Ohne laufende Arbeit (keine Eingaben, kein Song) kurz neu laden, damit auch Gradios Texte sofort wechseln.
        remember = """(l) => {
          try { localStorage.setItem('yue2_lang', l); } catch (e) {}
          const typed = ['#idea-box', '#style-box', '#lyrics-box'].some(
            (id) => (document.querySelector(id + ' textarea') || {}).value?.trim());
          // Geladener Original-Song (.track), generierter Song (.result) oder laufende Generierung zählen als Arbeit.
          const busy = typed || document.querySelector('.track, .result, .prog:not(.idle)');
          if (!busy) setTimeout(() => window.location.reload(), 700);
        }"""
        lang_switch.input(None, inputs=lang_switch, js=remember)
        picked = [modal, lang_switch] + translated + dynamic
        for button, code in ((pick_de, "de"), (pick_en, "en")):
            button.click(lambda *inputs, code=code: pick_language(code, *inputs), inputs=text_inputs,
                         outputs=picked, show_progress="hidden")
            button.click(None, js=f"() => {{ try {{ localStorage.setItem('yue2_lang', '{code}'); }} catch (e) {{}} }}")

        # --- Live-Systemanzeige im Kopfbereich: Werte alle 2 s holen, Balken per JavaScript animieren
        # Das Datenfeld bleibt eingebunden (per CSS versteckt); ein Beobachter in ui.SYSMON_JS liest es aus.
        sysmon_data = gr.Textbox(elem_id="sysmon-data", container=False, show_label=False)
        sysmon_timer = gr.Timer(2.0)
        sysmon_timer.tick(sysmon.snapshot_json, outputs=sysmon_data, show_progress="hidden", queue=False)

        # --- Events
        refresh_btn.click(refresh_models, outputs=[model_dd, hero])
        mode.change(lambda m: (gr.update(visible=m == MODE_NEW), gr.update(visible=m == MODE_REMAKE)),
                    inputs=mode, outputs=[new_group, remake_group])
        song_out = [title, style, lyrics, language_state, lint_box, save_name, max_secs, concept]
        create_new_btn.click(create_new, inputs=[idea, language, language2, mix_use, target_secs, model_dd, think],
                             outputs=song_out)
        language2.change(mix_changed, inputs=language2, outputs=mix_use, show_progress="hidden")
        remake_lang2.change(mix_changed, inputs=remake_lang2, outputs=remake_mix, show_progress="hidden")
        source.change(load_source_info, inputs=source,
                      outputs=[track_box, source_info, lyr_title, lyr_artist, lyr_choice, lyric_results, lyrics_source],
                      show_progress="hidden")
        lyr_search_btn.click(search_lyrics, inputs=[lyr_title, lyr_artist, source_info],
                             outputs=[lyr_choice, lyric_results, lyr_status])
        lyr_use_btn.click(use_lyrics, inputs=[lyr_choice, lyric_results], outputs=[transcript, lyrics_source, lyr_status])
        analyze_btn.click(analyze_remake, inputs=[source, transcript, lyrics_source],
                          outputs=[abc, transcript, remake_status, max_secs, src_duration], show_progress="hidden")
        create_remake_btn.click(create_remake,
                                inputs=[transcript, lyrics_mode, remake_lang, remake_lang2, remake_mix, style_wish, abc, model_dd, src_duration,
                                        lyrics_source, think],
                                outputs=song_out)
        check_btn.click(check, inputs=[style, lyrics], outputs=lint_box)
        normalize_btn.click(normalize, inputs=[style, lyrics], outputs=[lyrics, lint_box])
        correct_btn.click(correct, inputs=[concept, title, style, lyrics, correction, model_dd, think], outputs=song_out)
        title.change(lambda value: value, inputs=title, outputs=save_name)
        gen_event = gen_btn.click(generate,
                                  inputs=[mode, concept, title, style, lyrics, language_state, cot, seed, random_seed, cfg,
                                          max_secs, abc, model_dd, idea, style_wish, transcript, lyrics_mode, source,
                                          source_info, lyrics_source, mashup_meta],
                                  outputs=[player, gen_status, result_state, seed], show_progress="hidden")
        # ENGINE.cancel() stoppt YuE2 im Hintergrund-Thread, cancels= beendet den UI-Generator.
        cancel_btn.click(cancel, outputs=gen_status, cancels=[gen_event], queue=False)
        unload_btn.click(unload_all, outputs=gen_status)
        save_btn.click(save, inputs=[result_state, save_name, save_fmt, save_dir, overwrite, save_cover, model_dd],
                       outputs=save_box, show_progress="hidden")

        # --- Bibliothek
        lib_view_out = [lib_gallery, lib_tracks, lib_count]
        tab_library.select(refresh_library, inputs=[lib_query, lib_order], outputs=lib_view_out, show_progress="hidden")
        lib_refresh.click(refresh_library, inputs=[lib_query, lib_order], outputs=lib_view_out)
        lib_query.submit(refresh_library, inputs=[lib_query, lib_order], outputs=lib_view_out)
        lib_order.change(refresh_library, inputs=[lib_query, lib_order], outputs=lib_view_out, show_progress="hidden")
        detail_out = [lib_track, lib_cover, lib_head, lib_player, lib_concept, lib_idea, lib_style, lib_lyrics,
                      lib_cover_btn, lib_status]
        lib_gallery.select(select_track, inputs=lib_tracks, outputs=detail_out, show_progress="hidden")
        lib_cover_btn.click(library_cover, inputs=[lib_track, model_dd, lib_query, lib_order],
                            outputs=[lib_status, lib_gallery, lib_tracks, lib_track, lib_cover, lib_cover_btn, lib_head],
                            show_progress="hidden")
        reuse_all_btn.click(reuse_all, inputs=lib_track,
                            outputs=[tabs, mode, idea, style_wish, abc, lyrics_mode, concept, title, style, lyrics,
                                     language_state, lint_box, save_name, max_secs, seed, random_seed, cot, gen_status])
        reuse_idea_btn.click(reuse_idea, inputs=lib_track, outputs=[tabs, mode, idea, concept, gen_status])
        reuse_style_btn.click(reuse_style, inputs=[lib_track, lyrics], outputs=[tabs, style, lint_box, gen_status])
        reuse_lyrics_btn.click(reuse_lyrics, inputs=[lib_track, style], outputs=[tabs, lyrics, lint_box, gen_status])

        # --- Mashup
        slot_outputs = slot_groups + slot_heads + slot_radios + slot_texts + slot_staffs
        # Song A/B: Song-Karte + Vorbelegung der Online-Suche (wie im Remake), Online-Text übernehmen
        for f_in, card, info, l_title, l_artist, l_choice, l_results, src, text, l_search, l_use, l_status in (
                (mash_file_a, mash_card_a, mash_info_a, mash_lyr_title_a, mash_lyr_artist_a, mash_lyr_choice_a,
                 mash_results_a, mash_src_a, mash_text_a, mash_lyr_search_a, mash_lyr_use_a, mash_lyr_status_a),
                (mash_file_b, mash_card_b, mash_info_b, mash_lyr_title_b, mash_lyr_artist_b, mash_lyr_choice_b,
                 mash_results_b, mash_src_b, mash_text_b, mash_lyr_search_b, mash_lyr_use_b, mash_lyr_status_b)):
            f_in.change(load_source_info, inputs=f_in, outputs=[card, info, l_title, l_artist, l_choice, l_results, src],
                        show_progress="hidden")
            l_search.click(search_lyrics, inputs=[l_title, l_artist, info], outputs=[l_choice, l_results, l_status])
            l_use.click(use_lyrics, inputs=[l_choice, l_results], outputs=[text, src, l_status])
            # Eigener Text zählt als Originaltext (Whisper entfällt); ein übernommener Online-Text bleibt als Quelle
            text.input(lambda txt, current: (current or "manual") if (txt or "").strip() else None,
                       inputs=[text, src], outputs=src)
        mash_analyze_btn.click(mash_analyze,
                               inputs=[mash_file_a, mash_file_b, mash_text_a, mash_src_a, mash_text_b, mash_src_b,
                                       mash_state, model_dd],
                               outputs=[mash_state, mash_status, mash_timeline] + slot_outputs, show_progress="hidden")
        for i, radio in enumerate(slot_radios):
            radio.input(lambda choice, st, i=i: mash_switch(i, choice, st), inputs=[radio, mash_state],
                        outputs=[mash_state, mash_timeline, slot_heads[i], slot_staffs[i], mash_regen_btn],
                        show_progress="hidden")
        lyrics_out = [mash_state, mash_style, mash_status, mash_regen_btn] + slot_outputs
        mash_write_btn.click(mash_write, inputs=[mash_state, mash_style, mash_lang, model_dd] + slot_texts,
                             outputs=lyrics_out, show_progress="hidden")
        mash_regen_btn.click(mash_regen, inputs=[mash_state, mash_style, mash_lang, model_dd] + slot_texts,
                             outputs=lyrics_out, show_progress="hidden")
        mash_correct_btn.click(mash_correct, inputs=[mash_state, mash_request, mash_style, mash_lang, model_dd] + slot_texts,
                               outputs=lyrics_out, show_progress="hidden")
        mash_style_btn.click(mash_suggest_style, inputs=[mash_state, model_dd], outputs=mash_style)
        mash_send_btn.click(mash_send, inputs=[mash_state, mash_style] + slot_texts,
                            outputs=[tabs, mode, abc, transcript, style, lyrics, title, save_name, concept, lint_box,
                                     max_secs, mashup_meta, gen_status])

        # --- Einstellungen
        exp_save.click(save_export_ui, inputs=[exp_mp3, exp_flac, exp_artist, exp_album, exp_genre, exp_year,
                                               exp_comment, exp_cover_artist], outputs=exp_status)
    return demo


gr.set_static_paths(paths=[str(Path(__file__).resolve().parent / "static")])


if __name__ == "__main__":
    # Ein (minimales) I18n-Objekt lässt Gradio seine eigenen Texte nach dem Laden mit navigator.language
    # neu initialisieren – das head-Skript hat sie zu diesem Zeitpunkt bereits auf die gewählte Sprache gesetzt.
    gradio_i18n = gr.I18n(de={"app.name": "YuE2 Music Studio"}, en={"app.name": "YuE2 Music Studio"})
    build_ui().queue().launch(server_name="127.0.0.1", server_port=CONFIG["server_port"],
                              inbrowser=True, allowed_paths=[str(d) for d in ALLOWED_DIRS], i18n=gradio_i18n,
                              favicon_path=str(Path(__file__).resolve().parent / "static" / "favicon.png"))
