"""Tests für abc_tools mit echten SheetSage2-Partituren (aus songs/*.txt, sonst eingebaute Beispiele).

Start:  .venv-yue2\\Scripts\\python.exe -m pytest tests  (oder direkt: python tests/test_abc_tools.py)
"""
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import abc_tools as at  # noqa: E402

SAMPLE = """X:1
T:
M:4/4
L:1/16
Q:1/4=103
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:G
% intro
V: Vocal
Z4|
V: Ins
Z|g4g4g4g4|g4g4g4g4|g4d'4d'8-|
% verse
V: Vocal
z4d2d2e3d3z2|z4e2de3g4z2|z4a2a2b2a2a4|e2^c2=c2d2e2g2g4|
V: Ins
Z4|
% chorus
V: Vocal
"G"b12bag2|"D/F#"a8z4b2a2|g8z4b2d'e'-|e'8-e'3ze'2d'd'-|
V: Ins
Z4|
"""

SAMPLE_B = """X:1
T:
M:2/4
L:1/32
Q:1/4=128
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:D#m
% verse
V: Vocal
^d4^f4^g8|^a8z8|
V: Ins
Z2|
% chorus
V: Vocal
^f8^g8|^a4b4^c'8|[K:B]B8c8|
V: Ins
Z2|
"""


def real_scores():
    scores = [SAMPLE, SAMPLE_B]
    for txt in sorted((ROOT / "songs").glob("*.txt")) + sorted((ROOT / "examples").glob("*.txt")):
        text = txt.read_text(encoding="utf-8", errors="replace")
        start = text.find("\nX:1")
        if start < 0:
            continue
        lines, body = [], text[start + 1:].split("\n")
        for line in body:
            if line.startswith("===") or line.startswith("---"):
                break
            lines.append(line)
        scores.append("\n".join(lines))
    return [at.parse_score(s) for s in scores]


def test_parse():
    s = at.parse_score(SAMPLE)
    assert [x.tag for x in s.sections] == ["Intro", "Verse", "Chorus"]
    assert s.key == at.Key("G", False) and s.unit == Fraction(1, 16) and s.tempo == 103
    assert s.sections[1].vocal_bars() == 4


def test_keys():
    assert at.Key.parse("D#m").fifths == 6
    assert at.Key.parse("Ab").fifths == -4
    assert at.Key.parse("Gb").fifths == -6
    assert at.Key.parse("Cm").fifths == -3
    assert at.Key.parse("G").relative() == at.Key("E", True)
    assert at.target_key_for(at.Key.parse("D#m"), at.Key.parse("G")) == at.Key("E", True)


def test_transpose_roundtrip_and_durations():
    for score in real_scores():
        for sec in score.sections:
            original = at.section_pitches(sec)
            durations = at.bar_durations(sec)
            for shift in (-5, -2, 1, 3, 6):
                dst = at.Key.from_pc(sec.start_key.pc + shift, sec.start_key.minor)
                lines, key = [], sec.start_key
                for line in sec.lines:
                    if line.startswith("V:"):
                        lines.append(line)
                        continue
                    new, key = at.transform_line(line, key, dst, shift)
                    lines.append(new)
                moved = at.Section(sec.name, lines, dst, sec.start_meter)
                got = at.section_pitches(moved)
                assert [p for p, _ in got] == [p + shift for p, _ in original], (sec.name, shift, dst)
                assert [d for _, d in got] == [d for _, d in original]
                assert at.bar_durations(moved) == durations


def test_unit_conversion():
    b = at.parse_score(SAMPLE_B)
    sec, shift, dst = at.adapt_section(b.sections[0], b.unit, Fraction(1, 16), at.Key("G", False))
    assert dst == at.Key("E", True)
    before = [d * b.unit for d in at.bar_durations(b.sections[0])]
    after = [d * Fraction(1, 16) for d in at.bar_durations(sec)]
    assert before == after  # gleiche absolute Taktdauer


def test_octave_shift():
    b = at.parse_score(SAMPLE_B)
    sec = b.sections[0]
    for octaves in (-1, 1):
        moved, shift, dst = at.adapt_section(sec, b.unit, b.unit, at.Key("G", False), octaves)
        base = at.semitone_shift(sec.start_key, dst)
        assert shift == base + 12 * octaves
        assert [p for p, _ in at.section_pitches(moved)] == [p + shift for p, _ in at.section_pitches(sec)]


def test_build_mashup():
    a, b = at.parse_score(SAMPLE), at.parse_score(SAMPLE_B)
    abc, info = at.build_mashup(a, b, ["A", "B", "B"])
    again = at.parse_score(abc)
    assert [s.name for s in again.sections] == ["intro", "verse", "chorus"]
    assert info["to"] == "Em" and "[K:Em]" in abc and "[M:2/4]" in abc
    # Kein Inline-Wechsel der Quelle (B) bleibt übrig – alles steht in der Zieltonart
    assert "[K:B]" not in abc
    for real in real_scores()[2:4]:
        for other in real_scores()[4:6]:
            choices = ["B" if i % 2 else "A" for i in range(len(real.sections))]
            abc, _ = at.build_mashup(real, other, choices)
            assert len(at.parse_score(abc).sections) == len(real.sections)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
