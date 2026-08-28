"""Tests des parties testables hors Mac."""

import subprocess
import tempfile
from pathlib import Path

from lecteur.extract import clean_text
from lecteur.segment import MAX_CHARS, font_size_for, segment
from lecteur.synthesize import assign_timings
from lecteur.segment import TextSegment
from lecteur.timeline import Meta, build
from lecteur.waveform import envelope


def test_clean_text():
    raw = "Le\u00a0texte avec espaces ins\u00e9cables.\nUne ligne coup\u00e9e\nau milieu.\n\nNouveau paragraphe."
    out = clean_text(raw)
    assert "\u00a0" not in out
    assert "ligne coupée au milieu" in out, out
    assert "\n\n" in out, "les paragraphes doivent survivre"
    print("  nettoyage OK")


def test_apostrophes():
    out = clean_text("L\u2019\u00e9lection et \u201cles urnes\u201d")
    assert "L'élection" in out and '"les urnes"' in out
    print("  apostrophes typographiques OK")


def test_segment_respects_limit():
    text = (
        "La révision de la liste électorale débutera le 15 septembre et se "
        "poursuivra jusqu'au 30 octobre sur toute l'étendue du territoire "
        "national. Chaque citoyen en âge de voter devra se présenter muni "
        "d'une pièce d'identité en cours de validité, sans exception aucune."
    )
    segs = segment(text)
    assert segs, "au moins un segment"
    trop_longs = [s for s in segs if len(s.text) > MAX_CHARS]
    assert not trop_longs, [s.text for s in trop_longs]
    rebuilt = " ".join(s.text for s in segs)
    assert "15 septembre" in rebuilt and "pièce d'identité" in rebuilt
    print(f"  découpage OK ({len(segs)} segments, max "
          f"{max(len(s.text) for s in segs)} car.)")


def test_no_word_lost():
    text = ("Le gouvernement annonce trois mesures. La première concerne "
            "les transports. La seconde vise le logement social urbain.")
    segs = segment(text)
    original = set(text.replace(".", "").split())
    rebuilt = set(" ".join(s.text for s in segs).replace(".", "").split())
    assert original == rebuilt, original ^ rebuilt
    print("  aucun mot perdu OK")


def test_very_long_sentence_without_punctuation():
    text = "mot " * 60  # 240 caractères sans aucune ponctuation
    segs = segment(text.strip())
    assert all(len(s.text) <= MAX_CHARS for s in segs), \
        [len(s.text) for s in segs]
    assert len(segs) >= 3
    print("  phrase sans ponctuation OK")


def test_font_tiers():
    assert font_size_for("a" * 40) == 70
    assert font_size_for("a" * 60) == 70
    assert font_size_for("a" * 61) == 60
    assert font_size_for("a" * 90) == 60
    assert font_size_for("a" * 120) == 52
    print("  paliers de police OK")


def test_timings():
    segs = [TextSegment(i, f"segment {i}") for i in range(3)]
    for s in segs:
        s.duration = 2.0
    assign_timings(segs, gap=0.5, lead_in=1.0)
    assert segs[0].start == 1.0
    assert segs[1].start == 3.5, segs[1].start
    assert segs[2].start == 6.0
    assert segs[2].end == 8.0
    print("  timings OK")


def test_envelope_follows_audio():
    """Une sinusoïde suivie d'un silence: l'enveloppe doit chuter."""
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "t.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi",
             "-i", "sine=frequency=300:duration=1:sample_rate=24000",
             "-af", "apad=pad_dur=1", "-t", "2", str(wav)],
            capture_output=True, check=True,
        )
        env = envelope(wav, fps=30)
        assert 55 <= len(env) <= 65, len(env)
        parle = sum(env[5:25]) / 20
        silence = sum(env[40:55]) / 15
        assert parle > silence * 2, f"parle={parle:.3f} silence={silence:.3f}"
        assert all(0.0 <= v <= 1.0 for v in env)
        print(f"  enveloppe OK (voix {parle:.2f} / silence {silence:.2f})")


def test_timeline_payload():
    segs = [TextSegment(i, f"texte {i}", font_size=70) for i in range(2)]
    for s in segs:
        s.duration = 2.0
    assign_timings(segs, gap=0.5, lead_in=1.0)
    payload = build(segs, Path("voix.wav"), [0.1] * 150, Meta(),
                    fps=30, total_duration=5.0)
    assert payload["durationInFrames"] == 150
    assert payload["segments"][0]["startFrame"] == 30
    assert payload["segments"][1]["startFrame"] == 105
    assert payload["theme"]["card"] == "#B65C10"
    print("  payload Remotion OK")


if __name__ == "__main__":
    for fn in [
        test_clean_text,
        test_apostrophes,
        test_segment_respects_limit,
        test_no_word_lost,
        test_very_long_sentence_without_punctuation,
        test_font_tiers,
        test_timings,
        test_envelope_follows_audio,
        test_timeline_payload,
    ]:
        fn()
    print("\nTous les tests passent.")
