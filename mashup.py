"""Mashup aus zwei Songs: Analyse, Ablauf (A/B je Teil), Mashup-Text per KI (Denkmodus) und Übergabe ins Studio."""
import json
from pathlib import Path

import abc_tools as at
import llm
from settings import prompt

MAX_SLOTS = 24
SONG_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "style": {"type": "string"},
        "sections": {"type": "array", "items": {"type": "object", "properties": {
            "lines": {"type": "array", "items": {"type": "string"}}}, "required": ["lines"]}},
    },
    "required": ["title", "style", "sections"],
}
PLAN_SCHEMA = {"type": "object", "properties": {"choices": {"type": "array", "items": {"type": "string",
                                                                                        "enum": ["A", "B"]}}},
               "required": ["choices"]}


# --------------------------------------------------------------------------- Analyse eines Songs

def analyze_song(path, lyrics_text=None, lyrics_source=None, on_phase=None):
    """SheetSage2-Partitur, Text (Online-Text oder Whisper), Tags und Dauer eines Songs.

    on_phase("melody"|"lyrics") meldet den aktuellen Schritt (für die Fortschrittsanzeige)."""
    from audio_utils import load_mono, read_tags
    from lyrics_asr import transcribe
    from melody import transcribe_melody

    phase = on_phase or (lambda _p: None)
    phase("melody")
    abc, warnings = transcribe_melody(path)
    phase("lyrics")
    text = (lyrics_text or "").strip() if lyrics_source and (lyrics_text or "").strip() else transcribe(path)
    tags = {k: v for k, v in read_tags(path).items() if k != "cover"}
    duration = len(load_mono(path, 8000)) / 8000
    return {"name": Path(path).name, "title": tags.get("title") or Path(path).stem, "artist": tags.get("artist", ""),
            "tags": tags, "abc": abc, "lyrics": text, "lyrics_source": lyrics_source, "duration": duration,
            "warnings": warnings}


# --------------------------------------------------------------------------- Ablauf

def target_lines(bars):
    """Richtwert gesungener Zeilen aus den gesungenen Takten (etwa 2 Takte je Zeile)."""
    return 0 if bars == 0 else max(2, round(bars / 2))


def build_slots(score_a, score_b, choices=None):
    """Teile in der Reihenfolge von A mit Quelle (A/B), Takten und Zeilen-Richtwert."""
    slots = at.plan_slots(score_a, score_b)[:MAX_SLOTS]
    for i, slot in enumerate(slots):
        choice = (choices[i] if choices and i < len(choices) else "A")
        if slot["b_index"] is None:
            choice = "A"
        slot["source"] = choice
        sec = score_b.sections[slot["b_index"]] if choice == "B" else score_a.sections[slot["index"]]
        slot["bars"] = sec.total_bars()
        slot["meter"] = sec.start_meter
        slot["sung_bars"] = sec.vocal_bars()
        slot["lines"] = target_lines(slot["sung_bars"])
    return slots


def heuristic_choices(slots):
    """Ohne KI: Strophen aus A, Refrains/Pre-Chorus aus B, Bridge abwechselnd."""
    out = []
    for slot in slots:
        if slot["b_index"] is None:
            out.append("A")
        elif slot["tag"] in ("Chorus", "Pre-Chorus"):
            out.append("B")
        elif slot["tag"] == "Bridge":
            out.append("B" if slot["occurrence"] % 2 == 0 else "A")
        else:
            out.append("A")
    return out


def suggest_choices(model, a, b, score_a, score_b, on_progress=None):
    """KI-Vorschlag (Denkmodus) für A/B je Teil; bei Fehler die Heuristik."""
    slots = build_slots(score_a, score_b)
    desc = "\n".join(f"{i + 1}. {s['tag']} (A: {s['name']}; B has {'a matching ' + s['tag'] if s['b_index'] is not None else 'NO ' + s['tag']})"
                     for i, s in enumerate(slots))
    system = ("You are a mashup producer. For every section of song A's arrangement decide whether the melody and "
              "lyrics come from song A or song B, so the mashup has a clear dramaturgy: usually verses from one "
              "song, the big hooks/choruses from the other, contrast in the bridge, and both songs clearly present. "
              "Sections where B has no matching part must be A. Reply with JSON {\"choices\": [\"A\"|\"B\", ...]} "
              "with exactly one entry per section.")
    user = (f"Song A: {a.get('title')}\nSong B: {b.get('title')}\n\nSong A lyrics (excerpt):\n{a.get('lyrics', '')[:1500]}\n\n"
            f"Song B lyrics (excerpt):\n{b.get('lyrics', '')[:1500]}\n\nSections:\n{desc}")
    try:
        data = llm.chat_json(model, system, user, schema=PLAN_SCHEMA, temperature=0.4, think=True, raw=True,
                             on_progress=on_progress)
        choices = [c if c in ("A", "B") else "A" for c in data.get("choices", [])]
        if len(choices) == len(slots):
            return [c if s["b_index"] is not None else "A" for c, s in zip(choices, slots)]
    except (llm.OllamaError, ValueError, json.JSONDecodeError):
        pass
    return heuristic_choices(slots)


# --------------------------------------------------------------------------- Mashup-Text

def _plan_text(slots, a, b):
    rows = []
    for i, s in enumerate(slots):
        song = "A" if s["source"] == "A" else "B"
        title = a.get("title") if song == "A" else b.get("title")
        rows.append(f"{i + 1}. [{s['tag']}] source: song {song} ({title}), occurrence {s['occurrence'] + 1} of this "
                    f"section type, target sung lines: {s['lines']}")
    return "\n".join(rows)


def _user_message(slots, a, b, style, language, current=None, rewrite=None, request=None, tempo=None):
    parts = [f"Song A: {a.get('title')}\nOriginal lyrics of song A:\n{a.get('lyrics', '').strip() or '(none)'}",
             f"Song B: {b.get('title')}\nOriginal lyrics of song B:\n{b.get('lyrics', '').strip() or '(none)'}",
             f"Section plan:\n{_plan_text(slots, a, b)}",
             f"Target language: {language or 'keep each song’s original language'}",
             f"Tempo of song A (use it in the style): {tempo or 'unknown'} BPM",
             f"Style: {style.strip() if (style or '').strip() else '(empty – suggest one)'}"]
    if current:
        cur = "\n".join(f"{i + 1}. [{s['tag']}]\n" + "\n".join(lines) for i, (s, lines) in enumerate(zip(slots, current)))
        parts.append(f"Current mashup lyrics:\n{cur}")
    if rewrite:
        parts.append("Sections to rewrite (their source song changed): " + ", ".join(str(i + 1) for i in rewrite))
    if request:
        parts.append(f"Correction request from the user: {request}")
    return "\n\n".join(parts)


def _normalize(data, slots, fallback=None):
    sections = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(sections, list):
        raise llm.OllamaError("Mashup: unexpected answer from the model")
    out = []
    for i, slot in enumerate(slots):
        if i < len(sections) and isinstance(sections[i], dict):
            lines = [str(x).strip() for x in sections[i].get("lines", []) if str(x).strip()]
        else:
            lines = list(fallback[i]) if fallback and i < len(fallback) else []
        out.append(lines)
    return out


def write_lyrics(model, a, b, slots, style, language, current=None, rewrite=None, request=None, tempo=None,
                 on_progress=None):
    """Mashup-Text für alle Teile (oder nur die zu erneuernden) – immer im Denkmodus."""
    data = llm.chat_json(model, prompt("master_mashup.md"),
                         _user_message(slots, a, b, style, language, current, rewrite, request, tempo),
                         schema=SONG_SCHEMA, temperature=0.6, think=True, raw=True, on_progress=on_progress)
    sections = _normalize(data, slots, current)
    if rewrite and current:  # nur die gewünschten Teile übernehmen (plus die Übergangszeile davor)
        keep = set(range(len(slots))) - set(rewrite) - {i - 1 for i in rewrite}
        sections = [current[i] if i in keep else sections[i] for i in range(len(slots))]
    return str(data.get("title") or "").strip(), str(data.get("style") or "").strip(), sections


# --------------------------------------------------------------------------- Übergabe ins Studio

def assemble(score_a, score_b, slots, sections):
    """(abc, lyrics, info) für das Studio: kombinierte Noten und Text mit Sektions-Tags."""
    choices = [s["source"] for s in slots]
    abc, shift = at.build_mashup(at.Score(score_a.header, score_a.sections[:len(slots)], score_a.meter,
                                          score_a.unit, score_a.tempo, score_a.key), score_b, choices)
    blocks = []
    for slot, lines in zip(slots, sections):
        blocks.append(f"[{slot['tag']}]\n" + "\n".join(lines) if lines else f"[{slot['tag']}]\n")
    lyrics = "\n\n".join(b.rstrip("\n") for b in blocks).strip()
    seconds = sum(at.seconds(score_a, s["bars"], s.get("meter")) for s in slots)
    return abc, lyrics, {"shift": shift, "seconds": seconds}
