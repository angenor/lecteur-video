"""Synthèse française segment par segment (Voxtral TTS / MLX).

Contrairement au projet de doublage, ici il n'y a pas de timeline imposée:
c'est la durée réelle de chaque segment audio qui DÉFINIT le timing de la
vidéo. Pas de time-stretch, donc, et pas de risque de débordement.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from .segment import TextSegment

SAMPLE_RATE = 24_000
DEFAULT_MODEL = "mlx-community/Voxtral-4B-TTS-2603-mlx-bf16"
VOICES = {"female": "fr_female", "male": "fr_male"}

SAMPLES_PER_FRAME = 1920      # une frame du codec = 80 ms à 24 kHz
CHARS_PER_SECOND = 12.0       # débit de parole française, estimation prudente
LENGTH_SAFETY = 3.0           # marge tolérée au-delà de la durée attendue
MIN_FRAMES = 120              # plancher, pour les segments très courts
MODEL_MAX_FRAMES = 4096       # plafond du modèle
RETRY_TEMPERATURES = (0.8, 0.4, 0.15)
DRIFT_FACTOR = 1.8            # au-delà, la voix a dérivé

GAP_BETWEEN = 0.28  # respiration entre deux segments, en secondes
LEAD_IN = 0.6       # silence avant le premier mot
TAIL = 1.2          # silence final, laisse la dernière carte à l'écran


class SynthesisError(RuntimeError):
    pass


def _load_model(model_id: str):
    try:
        from mlx_audio.tts.utils import load
    except ImportError as exc:
        raise SynthesisError(
            "mlx-audio manquant: pip install -U mlx-audio  (Apple Silicon)"
        ) from exc
    return load(model_id)


def _expected_duration(text: str) -> float:
    """Durée de lecture plausible du texte, en secondes."""
    return len(text) / CHARS_PER_SECOND + 1.0


def _frame_budget(text: str) -> int:
    """Nombre maximal de frames audio autorisé pour ce texte.

    Le modèle accumule toutes les frames puis les décode d'un bloc. Une
    génération qui n'émet jamais son token de fin court donc jusqu'au plafond
    du modèle et fait exploser la mémoire Metal (28 Go observés à 4096
    frames, soit 5 min d'audio pour une phrase de 6 secondes). On borne le
    budget à trois fois la durée attendue du texte.
    """
    budget = int(
        _expected_duration(text) * LENGTH_SAFETY * SAMPLE_RATE / SAMPLES_PER_FRAME
    )
    return max(MIN_FRAMES, min(budget, MODEL_MAX_FRAMES))


def _has_drifted(text: str, duration: float) -> bool:
    """Vrai si l'audio dure trop longtemps pour son texte.

    Le modèle part parfois en roue libre: il ajoute des chuchotements et des
    apartés adressés à un tiers avant de conclure. Le symptôme mesurable est
    un débit effondré — 4 à 6 caractères par seconde au lieu des 11 à 21
    d'une lecture saine. Se fier au seul plafond de frames ne suffit pas: une
    dérive peut s'arrêter juste en dessous.
    """
    return duration > _expected_duration(text) * DRIFT_FACTOR


def _generate_one(model, text: str, voice: str) -> np.ndarray:
    budget = _frame_budget(text)
    shortest: np.ndarray | None = None

    for temperature in RETRY_TEMPERATURES:
        chunks: list[np.ndarray] = []
        for result in model.generate(
            text=text, voice=voice, max_tokens=budget, temperature=temperature
        ):
            chunks.append(np.asarray(result.audio, dtype=np.float32))
        if not chunks:
            continue

        audio = np.concatenate(chunks)
        if shortest is None or len(audio) < len(shortest):
            shortest = audio

        if not _has_drifted(text, len(audio) / SAMPLE_RATE):
            return audio

        print(
            f"\n  voix dérivée sur {text[:40]!r} "
            f"(temperature={temperature}), nouvelle tentative"
        )

    if shortest is None:
        raise SynthesisError(f"Aucun audio généré pour: {text[:60]!r}")

    # Toutes les tentatives ont dérivé: on garde la moins bavarde.
    print(f"\n  segment à revérifier: {text[:60]!r}")
    return shortest


def _reusable(dest: Path, text: str) -> np.ndarray | None:
    """Relit un segment déjà synthétisé, s'il est exploitable."""
    if not dest.exists():
        return None
    try:
        audio, sr = sf.read(dest, dtype="float32")
    except Exception:
        return None
    if sr != SAMPLE_RATE or audio.ndim > 1 or len(audio) == 0:
        return None
    if _has_drifted(text, len(audio) / SAMPLE_RATE):
        return None
    return audio


def synthesize(
    segments: list[TextSegment],
    workdir: Path,
    *,
    model_id: str = DEFAULT_MODEL,
    voice: str = "fr_male",
    reuse: bool = True,
    on_progress=None,
) -> list[TextSegment]:
    """Synthétise chaque segment, en reprenant le travail déjà fait.

    Avec *reuse*, un .wav déjà présent et de durée plausible est conservé:
    une relance ne régénère que les segments manquants ou dérivés, au lieu de
    reprendre les vingt minutes depuis le début.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    model = None  # chargé à la première synthèse réellement nécessaire

    for i, seg in enumerate(segments, start=1):
        dest = workdir / f"seg_{seg.index:04d}.wav"
        audio = _reusable(dest, seg.text) if reuse else None

        if audio is None:
            if model is None:
                model = _load_model(model_id)
            audio = _generate_one(model, seg.text, voice)
            sf.write(dest, audio, SAMPLE_RATE)

        seg.audio_path = str(dest)
        seg.duration = len(audio) / SAMPLE_RATE
        if on_progress:
            on_progress(i, len(segments))

    return segments


def assign_timings(
    segments: list[TextSegment],
    *,
    gap: float = GAP_BETWEEN,
    lead_in: float = LEAD_IN,
) -> list[TextSegment]:
    """Pose les segments bout à bout et renvoie la liste horodatée."""
    cursor = lead_in
    for seg in segments:
        seg.start = cursor
        cursor += seg.duration + gap
    return segments


def concatenate(
    segments: list[TextSegment],
    dest: Path,
    *,
    tail: float = TAIL,
) -> tuple[Path, float]:
    """Assemble la piste audio complète. Renvoie (chemin, durée totale)."""
    if not segments:
        raise SynthesisError("Aucun segment à assembler.")

    total = segments[-1].end + tail
    track = np.zeros(int(total * SAMPLE_RATE) + 1, dtype=np.float32)

    for seg in segments:
        if not seg.audio_path:
            continue
        audio, sr = sf.read(seg.audio_path, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != SAMPLE_RATE:
            raise SynthesisError(f"Fréquence inattendue {sr} Hz")
        offset = int(seg.start * SAMPLE_RATE)
        end = offset + len(audio)
        if end > len(track):
            track = np.pad(track, (0, end - len(track)))
        track[offset:end] += audio

    peak = float(np.max(np.abs(track))) if track.size else 0.0
    if peak > 0.99:
        track *= 0.99 / peak

    dest.parent.mkdir(parents=True, exist_ok=True)
    sf.write(dest, track, SAMPLE_RATE)
    return dest, len(track) / SAMPLE_RATE
