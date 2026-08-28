"""Construction du fichier de données consommé par Remotion.

C'est le contrat entre le Python et le React: tout ce dont la composition
a besoin pour se rendre, sans qu'elle ait à recalculer quoi que ce soit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .segment import TextSegment

FPS = 30
FADE_FRAMES = 8  # durée du fondu de transition entre deux segments


@dataclass
class Meta:
    rubrique: str = "POLITIQUE"
    speaker: str = "[Nom du responsable politique]"
    date: str = ""
    signature: str = "ANGENOR N'GOUANDI"
    photo: str = ""
    disclaimer: str = "Texte lu par synthèse vocale"


def build(
    segments: list[TextSegment],
    audio_path: Path,
    envelope: list[float],
    meta: Meta,
    *,
    fps: int = FPS,
    total_duration: float,
    fade_frames: int = FADE_FRAMES,
) -> dict:
    payload_segments = []
    for seg in segments:
        payload_segments.append({
            "index": seg.index,
            "text": seg.text,
            "chars": len(seg.text),
            "fontSize": seg.font_size,
            "startFrame": round(seg.start * fps),
            "endFrame": round(seg.end * fps),
            "startSec": round(seg.start, 3),
            "durationSec": round(seg.duration, 3),
            "notes": seg.notes,
        })

    return {
        "fps": fps,
        "width": 1080,
        "height": 1920,
        "durationInFrames": int(round(total_duration * fps)),
        "fadeFrames": fade_frames,
        "audio": str(audio_path),
        "envelope": envelope,
        "waveBars": 90,
        "waveWindowFrames": fps * 2,  # 2 s d'onde visible à l'écran
        "meta": {
            "rubrique": meta.rubrique,
            "speaker": meta.speaker,
            "date": meta.date,
            "signature": meta.signature,
            "photo": meta.photo,
            "disclaimer": meta.disclaimer,
        },
        "theme": {
            "page": "#141312",
            "card": "#B65C10",
            "accent": "#D97B2A",
            "rubrique": "#22386B",
            "bar": "#111010",
            "muted": "#9E9890",
            "text": "#FFFFFF",
            "module": 37,
        },
        "segments": payload_segments,
    }


def save(payload: dict, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return dest
