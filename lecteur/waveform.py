"""Enveloppe d'amplitude de l'audio, pour animer l'onde.

Le point important: l'onde doit suivre la voix réelle. Un motif aléatoire
se repère immédiatement — les barres bougent quand la voix se tait.

On calcule une valeur RMS par frame vidéo. Remotion découpe ensuite une
fenêtre glissante de 90 valeurs dans ce tableau, ce qui donne l'onde
défilante du gabarit sans alourdir le JSON.
"""

from __future__ import annotations

import numpy as np
import soundfile as sf
from pathlib import Path

FLOOR = 0.06  # hauteur minimale des barres pendant les silences


def envelope(
    audio_path: Path,
    *,
    fps: int = 30,
    smoothing: int = 3,
    floor: float = FLOOR,
) -> list[float]:
    """Renvoie une valeur d'amplitude normalisée par frame vidéo."""
    audio, sr = sf.read(audio_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    samples_per_frame = max(1, int(sr / fps))
    n_frames = int(np.ceil(len(audio) / samples_per_frame))

    values = np.zeros(n_frames, dtype=np.float32)
    for i in range(n_frames):
        window = audio[i * samples_per_frame : (i + 1) * samples_per_frame]
        if window.size:
            values[i] = float(np.sqrt(np.mean(window.astype(np.float64) ** 2)))

    # compression douce: la voix a une dynamique large, l'onde doit rester
    # lisible sans que les pics écrasent tout le reste
    values = np.sqrt(values)

    peak = float(values.max()) if values.size else 0.0
    if peak > 0:
        values /= peak

    if smoothing > 1:
        kernel = np.ones(smoothing, dtype=np.float32) / smoothing
        values = np.convolve(values, kernel, mode="same")

    values = floor + (1.0 - floor) * np.clip(values, 0.0, 1.0)
    return [round(float(v), 4) for v in values]
