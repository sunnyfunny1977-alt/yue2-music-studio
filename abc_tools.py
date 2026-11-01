"""Werkzeuge für SheetSage2-Partituren (ABC): Teile zerlegen, transponieren, Notenlängen umrechnen, Mashups bauen.

Unterstützt das ABC-Format, das SheetSage2 schreibt: Kopf (X/T/M/L/Q/V/K), Teile als „% name“-Kommentar,
je Teil abwechselnd „V: Vocal“ und „V: Ins“ mit Taktzeilen. Noten mit Vorzeichen (^ _ =), Oktavzeichen (' ,),
Längen (2, 3/2, /2), Pausen (z, x, Z), Haltebögen (-), Akkordsymbole ("Dm7"), Inline-Felder ([K:G]).
"""
import re
from dataclasses import dataclass, field
from fractions import Fraction

LETTERS = "CDEFGAB"
NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SHARP_ORDER, FLAT_ORDER = "FCGDAEB", "BEADGCF"
MAJOR_FIFTHS = {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7,
                "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5, "Gb": -6, "Cb": -7}
PC_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
PC_NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


# --------------------------------------------------------------------------- Tonarten

@dataclass(frozen=True)
class Key:
    tonic: str   # z. B. "G", "D#", "Ab"
    minor: bool

    @classmethod
    def parse(cls, text):
        m = re.match(r"\s*([A-Ga-g])([#b]?)\s*(m|min|minor|maj|major)?\b", text or "C")
        if not m:
            return cls("C", False)
        return cls(m.group(1).upper() + m.group(2), (m.group(3) or "").lower() in ("m", "min", "minor"))

    @property
    def name(self):
        return self.tonic + ("m" if self.minor else "")

    @property
    def pc(self):
        return (NATURAL[self.tonic[0]] + {"#": 1, "b": -1}.get(self.tonic[1:], 0)) % 12

    @property
    def letter_index(self):
        return LETTERS.index(self.tonic[0])

    @property
    def fifths(self):
        if not self.minor and self.tonic in MAJOR_FIFTHS:
            return MAJOR_FIFTHS[self.tonic]
        major_pc = (self.pc + 3) % 12 if self.minor else self.pc
        # Schreibweise der parallelen Dur-Tonart passend zum Vorzeichen der Moll-Tonart wählen
        candidates = [name for name, f in MAJOR_FIFTHS.items() if (NATURAL[name[0]] + {"#": 1, "b": -1}.get(name[1:], 0)) % 12 == major_pc]
        if self.minor and "#" in self.tonic:
            candidates.sort(key=lambda n: -MAJOR_FIFTHS[n])
        elif self.minor and "b" in self.tonic[1:]:
            candidates.sort(key=lambda n: MAJOR_FIFTHS[n])
        else:
            candidates.sort(key=lambda n: abs(MAJOR_FIFTHS[n]))
        return MAJOR_FIFTHS[candidates[0]]

    def signature(self):
        """Vorzeichen je Notenbuchstabe (+1 Kreuz, −1 B)."""
        f = self.fifths
        sig = {letter: 0 for letter in LETTERS}
        for letter in (SHARP_ORDER[:f] if f > 0 else FLAT_ORDER[:-f]):
            sig[letter] = 1 if f > 0 else -1
        return sig

    def relative(self):
        """Paralleltonart (Dur ↔ Moll)."""
        shift = -3 if not self.minor else 3
        return Key.from_pc((self.pc + shift) % 12, not self.minor, prefer_flats=self.fifths < 0)

    @classmethod
    def from_pc(cls, pc, minor, prefer_flats=False):
        names = PC_NAMES_FLAT if prefer_flats else PC_NAMES_SHARP
        return cls(names[pc % 12], minor)


def target_key_for(src, target):
    """Zieltonart für Song B: Tonart von A bei gleichem Tongeschlecht, sonst deren Paralleltonart."""
    return target if src.minor == target.minor else target.relative()


def semitone_shift(src, dst):
    """Kleinste Verschiebung (−6 … +5 Halbtöne) von src nach dst."""
    d = (dst.pc - src.pc) % 12
    return d - 12 if d > 6 else d


# --------------------------------------------------------------------------- Partitur zerlegen

SECTION_TAGS = {"intro": "Intro", "verse": "Verse", "pre-chorus": "Pre-Chorus", "prechorus": "Pre-Chorus",
                "chorus": "Chorus", "refrain": "Chorus", "bridge": "Bridge", "outro": "Outro",
                "instrumental": "Interlude", "interlude": "Interlude", "solo": "Interlude", "break": "Interlude",
                "inst": "Interlude"}


def section_tag(name):
    key = name.strip().lower()
    for word, tag in SECTION_TAGS.items():
        if key.startswith(word):
            return tag
    return "Verse"


@dataclass
class Section:
    name: str                       # wie in der Partitur, z. B. "chorus"
    lines: list = field(default_factory=list)  # Rohzeilen ohne „% name“
    start_key: Key = None
    start_meter: str = ""

    @property
    def tag(self):
        return section_tag(self.name)

    def voice_lines(self, voice="Vocal"):
        out, current = [], None
        for line in self.lines:
            if line.startswith("V:"):
                current = line[2:].strip().split()[0] if line[2:].strip() else None
                continue
            if current == voice and line.strip():
                out.append(line)
        return out

    def vocal_bars(self):
        """Takte der Gesangsstimme mit gesungenen Noten (ohne reine Pausen)."""
        bars = [b for line in self.voice_lines("Vocal") for b in line.split("|") if b.strip()]
        return sum(1 for b in bars if re.search(r"[A-Ga-g]", re.sub(r'"[^"]*"|\[[A-Za-z]:[^\]]*\]', "", b)))

    def total_bars(self):
        n = 0
        for line in self.voice_lines("Vocal"):
            for b in line.split("|"):
                b = b.strip()
                if not b:
                    continue
                m = re.fullmatch(r"Z(\d*)", b)
                n += int(m.group(1) or 1) if m else 1
        return n


@dataclass
class Score:
    header: list
    sections: list
    meter: str
    unit: Fraction
    tempo: int
    key: Key

    def abc(self):
        out = list(self.header)
        for s in self.sections:
            out.append(f"% {s.name}")
            out.extend(s.lines)
        return "\n".join(out) + "\n"

    def of_type(self, tag):
        return [s for s in self.sections if s.tag == tag]


def _field(header, name, default=""):
    for line in header:
        if line.startswith(name + ":"):
            return line[len(name) + 1:].strip()
    return default


def parse_score(abc):
    lines = [ln.rstrip() for ln in (abc or "").replace("\r\n", "\n").split("\n")]
    header, i = [], 0
    while i < len(lines):
        header.append(lines[i])
        if lines[i].startswith("K:"):
            i += 1
            break
        i += 1
    meter = _field(header, "M", "4/4")
    unit_text = _field(header, "L", "1/8")
    unit = Fraction(unit_text) if re.fullmatch(r"\d+/\d+", unit_text) else Fraction(1, 8)
    q = re.search(r"=\s*(\d+)", _field(header, "Q", "1/4=120"))
    key = Key.parse(_field(header, "K", "C"))
    sections, current = [], None
    cur_key, cur_meter = key, meter
    for line in lines[i:]:
        m = re.match(r"^%\s*([A-Za-z][\w -]*)$", line.strip())
        if m:
            current = Section(m.group(1).strip(), [], cur_key, cur_meter)
            sections.append(current)
            continue
        if not line.strip():
            continue
        if current is None:  # Takte vor dem ersten Teil
            current = Section("intro", [], cur_key, cur_meter)
            sections.append(current)
        current.lines.append(line)
        for kind, value in re.findall(r"\[([KM]):([^\]]*)\]", line):
            if kind == "K":
                cur_key = Key.parse(value)
            else:
                cur_meter = value.strip()
    return Score(header, sections, meter, unit, int(q.group(1)) if q else 120, key)


# --------------------------------------------------------------------------- Tokenisierung der Taktzeilen

_TOKEN = re.compile(
    r'(?P<chord>"[^"]*")'
    r'|(?P<field>\[[A-Za-z]:[^\]]*\])'
    r'|(?P<note>(?P<acc>\^\^|\^|__|_|=)?(?P<letter>[A-Ga-g])(?P<oct>[\',]*)(?P<len>\d*/?\d*))'
    r'|(?P<rest>(?P<rtype>[zx])(?P<rlen>\d*/?\d*))'
    r'|(?P<mrest>Z\d*)'
    r'|(?P<bar>\|)'
    r'|(?P<other>.)', re.S)


def _parse_len(text):
    if not text:
        return Fraction(1)
    if "/" in text:
        num, _, den = text.partition("/")
        return Fraction(int(num) if num else 1, int(den) if den else 2)
    return Fraction(int(text))


def _fmt_len(value):
    value = Fraction(value)
    if value == 1:
        return ""
    if value.denominator == 1:
        return str(value.numerator)
    if value.numerator == 1:
        return f"/{value.denominator}"
    return f"{value.numerator}/{value.denominator}"


def _midi(letter, octave_marks, accidental_offset):
    base = 60 + (12 if letter.islower() else 0) + NATURAL[letter.upper()]
    base += 12 * octave_marks.count("'") - 12 * octave_marks.count(",")
    return base + accidental_offset


def _abs_step(letter, octave_marks):
    """Absolute diatonische Stufe (C4 = 28)."""
    octave = 4 + (1 if letter.islower() else 0) + octave_marks.count("'") - octave_marks.count(",")
    return octave * 7 + LETTERS.index(letter.upper())


def _spell(abs_step):
    octave, idx = divmod(abs_step, 7)
    letter = LETTERS[idx]
    if octave >= 5:
        return letter.lower() + "'" * (octave - 5)
    return letter + "," * (4 - octave)


ACC = {"^^": 2, "^": 1, "=": 0, "_": -1, "__": -2}
ACC_TEXT = {2: "^^", 1: "^", 0: "=", -1: "_", -2: "__"}


def _transpose_chord_symbol(symbol, semitones, prefer_flats):
    def shift(match):
        root = match.group(0)
        pc = (NATURAL[root[0]] + {"#": 1, "b": -1}.get(root[1:], 0) + semitones) % 12
        return (PC_NAMES_FLAT if prefer_flats else PC_NAMES_SHARP)[pc]
    inner = symbol[1:-1]
    inner = re.sub(r"^[A-G][#b]?", shift, inner)
    inner = re.sub(r"(?<=/)[A-G][#b]?", shift, inner)
    return f'"{inner}"'


def transform_line(line, src_key, dst_key=None, semitones=0, unit_factor=Fraction(1), octaves=0):
    """Transponiert eine Taktzeile von src_key nach dst_key und skaliert Notenlängen.

    Gibt (neue Zeile, Tonart am Zeilenende in der Quelle) zurück. Inline-[K:]-Felder der Quelle werden
    ausgewertet und – wenn transponiert wird – entfernt (die Ausgabe steht komplett in dst_key).
    """
    transposing = dst_key is not None and (semitones or octaves or dst_key != src_key)
    dst = dst_key or src_key
    diatonic = 0
    if transposing:
        diatonic = (dst.letter_index - src_key.letter_index) % 7
        # Richtung passend zur Halbtonverschiebung wählen
        if semitones < 0 and diatonic:
            diatonic -= 7
        diatonic += 7 * octaves
    semitones += 12 * octaves
    src_sig, dst_sig = src_key.signature(), dst.signature()
    src_bar, dst_bar = {}, {}  # Vorzeichen, die bis zum Taktende gelten: (Buchstabe, Oktave) → Versatz
    prefer_flats = dst.fifths < 0
    out = []
    for m in _TOKEN.finditer(line):
        kind = m.lastgroup
        if kind in ("acc", "letter", "oct", "len", "rtype", "rlen"):
            kind = "note" if m.group("note") else "rest"
        if m.group("chord"):
            text = m.group("chord")
            out.append(_transpose_chord_symbol(text, semitones, prefer_flats) if transposing else text)
        elif m.group("field"):
            text = m.group("field")
            km = re.fullmatch(r"\[K:([^\]]*)\]", text)
            if km:
                src_key = Key.parse(km.group(1))
                src_sig = src_key.signature()
                if transposing:
                    continue  # Ausgabe bleibt in der Zieltonart
            out.append(text)
        elif m.group("note"):
            acc, letter, octs, length = m.group("acc"), m.group("letter"), m.group("oct"), m.group("len")
            new_len = _fmt_len(_parse_len(length) * unit_factor) if unit_factor != 1 else length
            if not transposing:
                out.append((acc or "") + letter + octs + new_len)
                continue
            pos = (letter.upper(), _abs_step(letter, octs))
            if acc:
                src_bar[pos] = ACC[acc]
            offset = src_bar.get(pos, src_sig[letter.upper()])
            pitch = _midi(letter, octs, offset) + semitones
            step = _abs_step(letter, octs) + diatonic
            new_letter = LETTERS[step % 7]
            natural = _midi(_spell(step)[0], _spell(step)[1:], 0)
            need = pitch - natural
            if abs(need) > 2:  # unpassende Schreibweise – enharmonisch umdeuten
                step += 1 if need > 0 else -1
                new_letter = LETTERS[step % 7]
                natural = _midi(_spell(step)[0], _spell(step)[1:], 0)
                need = pitch - natural
            dpos = (new_letter, step)
            current = dst_bar.get(dpos, dst_sig[new_letter])
            text = _spell(step)
            if need != current:
                text = ACC_TEXT[need] + text
                dst_bar[dpos] = need
            out.append(text + new_len)
        elif m.group("rest"):
            length = m.group("rlen")
            out.append(m.group("rtype") + (_fmt_len(_parse_len(length) * unit_factor) if unit_factor != 1 else length))
        elif m.group("bar"):
            src_bar.clear()
            dst_bar.clear()
            out.append("|")
        else:
            out.append(m.group(0))
    return "".join(out), src_key


def section_pitches(section, key=None):
    """Alle Tonhöhen (MIDI) und Längen eines Teils in Reihenfolge – für Tests und Vergleiche."""
    out = []
    src_key = key or section.start_key
    for line in section.lines:
        if line.startswith("V:"):
            continue
        sig, bar = src_key.signature(), {}
        for m in _TOKEN.finditer(line):
            if m.group("field"):
                km = re.fullmatch(r"\[K:([^\]]*)\]", m.group("field"))
                if km:
                    src_key = Key.parse(km.group(1))
                    sig = src_key.signature()
            elif m.group("note"):
                acc, letter, octs = m.group("acc"), m.group("letter"), m.group("oct")
                pos = (letter.upper(), _abs_step(letter, octs))
                if acc:
                    bar[pos] = ACC[acc]
                out.append((_midi(letter, octs, bar.get(pos, sig[letter.upper()])), _parse_len(m.group("len"))))
            elif m.group("bar"):
                bar = {}
    return out


def vocal_pitches(section):
    """Tonhöhen (MIDI) nur der Gesangsstimme."""
    only = Section(section.name, [], section.start_key, section.start_meter)
    current = None
    for line in section.lines:
        if line.startswith("V:"):
            current = line[2:].strip().split()[0] if line[2:].strip() else None
            continue
        if current == "Vocal":
            only.lines.append(line)
    return [p for p, _ in section_pitches(only)]


def mean_vocal_pitch(sections):
    pitches = [p for s in sections for p in vocal_pitches(s)]
    return sum(pitches) / len(pitches) if pitches else None


def bar_durations(section):
    """Dauer jedes Takts (in Notenlängen-Einheiten) für jede Stimme – für Tests."""
    out = []
    for line in section.lines:
        if line.startswith("V:"):
            continue
        for bar in line.split("|"):
            total = Fraction(0)
            for m in _TOKEN.finditer(bar):
                if m.group("note"):
                    total += _parse_len(m.group("len"))
                elif m.group("rest"):
                    total += _parse_len(m.group("rlen"))
            if bar.strip():
                out.append(total)
    return out


def adapt_section(section, src_unit, dst_unit, dst_key, octaves=0):
    """Kopie eines Teils von Song B in Tonart und Notenlänge von Song A (optional um Oktaven verschoben)."""
    shift = semitone_shift(section.start_key, target_key_for(section.start_key, dst_key))
    dst = target_key_for(section.start_key, dst_key)
    factor = Fraction(src_unit) / Fraction(dst_unit)
    lines, key = [], section.start_key
    for line in section.lines:
        if line.startswith("V:"):
            lines.append(line)
            continue
        new, key = transform_line(line, key, dst, shift, factor, octaves)
        lines.append(new)
    return Section(section.name, lines, dst, section.start_meter), shift + 12 * octaves, dst


def best_octave(score_a, score_b):
    """Oktave für Song B, deren Gesangslage nach der Transposition der von A am nächsten liegt."""
    mean_a, mean_b = mean_vocal_pitch(score_a.sections), mean_vocal_pitch(score_b.sections)
    if mean_a is None or mean_b is None:
        return 0
    shift = semitone_shift(score_b.key, target_key_for(score_b.key, score_a.key))
    return min((-1, 0, 1), key=lambda o: abs(mean_b + shift + 12 * o - mean_a))


# --------------------------------------------------------------------------- Mashup

def match_b_section(score_b, tag, occurrence):
    """Teil gleichen Typs aus Song B (n-tes Vorkommen, sonst das letzte); None, wenn B den Typ nicht hat."""
    same = score_b.of_type(tag)
    if not same:
        return None
    return same[min(occurrence, len(same) - 1)]


def plan_slots(score_a, score_b):
    """Ablauf von Song A mit der jeweils passenden Stelle in Song B (oder None)."""
    slots, seen = [], {}
    for idx, sec in enumerate(score_a.sections):
        occ = seen.get(sec.tag, 0)
        seen[sec.tag] = occ + 1
        b = match_b_section(score_b, sec.tag, occ) if score_b else None
        slots.append({"index": idx, "tag": sec.tag, "name": sec.name, "occurrence": occ,
                      "b_index": score_b.sections.index(b) if b is not None else None})
    return slots


def _with_inline(lines, fields):
    """Setzt Inline-Felder (z. B. [K:G][M:4/4]) an den Anfang jeder Taktzeile direkt nach einem V:-Wechsel."""
    if not fields:
        return list(lines)
    out, after_voice = [], True
    for line in lines:
        if line.startswith("V:"):
            out.append(line)
            after_voice = True
            continue
        out.append(fields + line if after_voice else line)
        after_voice = False
    return out


def build_mashup(score_a, score_b, choices):
    """Kombinierte Partitur: Ablauf von A, je Teil die Noten aus A oder (angeglichen) aus B.

    choices: Liste "A"/"B" je Teil von A. Gibt (abc, info) zurück; info enthält Transposition von B.
    """
    slots = plan_slots(score_a, score_b)
    sections, shift_info = [], {}
    octave = best_octave(score_a, score_b) if score_b else 0
    prev_key, prev_meter = score_a.key, score_a.meter
    for slot, choice in zip(slots, choices):
        if choice == "B" and slot["b_index"] is not None:
            src = score_b.sections[slot["b_index"]]
            sec, shift, dst = adapt_section(src, score_b.unit, score_a.unit, score_a.key, octave)
            shift_info = {"semitones": shift, "from": score_b.key.name, "to": dst.name}
            key, meter = dst, src.start_meter
        else:
            sec = score_a.sections[slot["index"]]
            key, meter = sec.start_key, sec.start_meter
        fields = ""
        if key != prev_key:
            fields += f"[K:{key.name}]"
        if meter != prev_meter:
            fields += f"[M:{meter}]"
        sections.append(Section(sec.name, _with_inline(sec.lines, fields), key, meter))
        # Tonart am Teilende (Inline-Wechsel innerhalb von A-Teilen berücksichtigen)
        prev_key = key
        for line in sec.lines:
            for k in re.findall(r"\[K:([^\]]*)\]", line):
                prev_key = Key.parse(k)
        prev_meter = meter
    score = Score(score_a.header, sections, score_a.meter, score_a.unit, score_a.tempo, score_a.key)
    return score.abc(), shift_info


def vocal_abc(section, score, color=None):
    """Kleine eigenständige ABC nur mit der Gesangsstimme eines Teils (für die Notenanzeige)."""
    # Alle Gesangszeilen zu einer Musikzeile verbinden – abcjs bricht dann selbst sinnvoll um.
    bars = " ".join(line.strip().rstrip("|") + "|" for line in section.voice_lines("Vocal") if line.strip())
    head = ["X:1", f"M:{section.start_meter or score.meter}", f"L:{score.unit.numerator}/{score.unit.denominator}",
            f"K:{(section.start_key or score.key).name}"]
    return "\n".join(head + [bars]) if bars else ""


def seconds(score, bars, meter=None):
    """Dauer von n Takten (im angegebenen Takt) im Tempo der Partitur."""
    num, _, den = (meter or score.meter or "4/4").partition("/")
    beats = int(num) * 4 / int(den or 4)
    return bars * beats * 60 / max(score.tempo, 30)
