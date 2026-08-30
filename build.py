#!/usr/bin/env python3
"""Communiqué politique -> données vidéo prêtes pour Remotion.

    python build.py communique.txt --speaker "Nom Prénom" --photo photo.jpg
    python build.py capture1.png capture2.png --speaker "Nom Prénom"

Produit dans le dossier de sortie:
    texte.txt        le texte extrait, relisible et corrigeable
    segments.json    les cartes d'affichage avec tailles de police
    voix.wav         la piste audio complète
    video-data.json  le contrat consommé par la composition Remotion
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

from lecteur import extract as EX
from lecteur import render as RD
from lecteur import segment as SEG
from lecteur import synthesize as TTS
from lecteur import timeline as TL
from lecteur import waveform as WF

from dotenv import load_dotenv
load_dotenv()

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]


def french_date(d: date) -> str:
    return f"{d.day} {MOIS[d.month - 1]} {d.year}"


def step(n: int, title: str) -> float:
    print(f"\n[{n}] {title}", flush=True)
    return time.time()


def done(t: float) -> None:
    print(f"  terminé en {time.time() - t:.1f}s", flush=True)


def progress(label: str):
    def _cb(current: int, total: int) -> None:
        print(f"\r  {label}: {current}/{total}", end="", flush=True)
        if current >= total:
            print()
    return _cb


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Communiqué politique -> vidéo 9:16 (gabarit Bandeau télé)"
    )
    p.add_argument("sources", type=Path, nargs="+",
                   help="Fichier(s) .txt/.md, ou image(s) contenant le texte")
    p.add_argument("-o", "--outdir", type=Path, default=None,
                   help="Dossier de sortie (défaut: ./sortie/<nom>)")

    p.add_argument("--speaker", default="[Nom du responsable politique]")
    p.add_argument("--rubrique", default="POLITIQUE")
    p.add_argument("--date", default=None, help="Défaut: aujourd'hui")
    p.add_argument("--photo", default="", help="Chemin de la photo du locuteur")
    p.add_argument("--signature", default="ANGENOR N'GOUANDI")
    p.add_argument("--no-disclaimer", action="store_true",
                   help="Retire la mention 'lu par synthèse vocale'")

    p.add_argument("--ocr", choices=["vision", "local"], default="vision",
                   help="vision: modèle multimodal OpenRouter. "
                        "local: OCR natif macOS (ocrmac)")
    p.add_argument("--vision-model", default=EX.DEFAULT_VISION_MODEL)
    p.add_argument("--api-key", default=None,
                   help="Clé OpenRouter (sinon $OPENROUTER_API_KEY)")

    p.add_argument("--voice", choices=["female", "male"], default="male")
    p.add_argument("--tts-model", default=TTS.DEFAULT_MODEL)
    p.add_argument("--fresh", action="store_true",
                   help="Resynthétise tout, sans réutiliser les .wav existants")
    p.add_argument("--max-chars", type=int, default=SEG.MAX_CHARS,
                   help="Longueur max d'un segment (contrainte du gabarit)")
    p.add_argument("--gap", type=float, default=TTS.GAP_BETWEEN,
                   help="Silence entre deux énoncés, en secondes")
    p.add_argument("--fps", type=int, default=TL.FPS)

    p.add_argument("--render", action="store_true",
                   help="Enchaîne le rendu vidéo Remotion et sort un MP4")
    p.add_argument("--studio", action="store_true",
                   help="Ouvre l'aperçu Remotion sur ces données (bloquant)")
    p.add_argument("--concurrency", type=int, default=None,
                   help="Rendus parallèles Remotion (défaut: auto)")
    p.add_argument("--text-only", action="store_true",
                   help="S'arrête après le découpage, sans synthèse")
    p.add_argument("--from-text", type=Path,
                   help="Repart d'un texte.txt corrigé à la main")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    stem = args.sources[0].stem
    outdir = args.outdir or Path("sortie") / stem
    outdir.mkdir(parents=True, exist_ok=True)

    text_path = outdir / "texte.txt"
    seg_path = outdir / "segments.json"
    audio_path = outdir / "voix.wav"
    data_path = outdir / "video-data.json"

    # 1. Extraction
    t = step(1, "Extraction du texte")
    if args.from_text:
        text = EX.clean_text(args.from_text.read_text(encoding="utf-8"))
        print(f"  repris de {args.from_text}")
    else:
        try:
            text = EX.extract_many(
                args.sources,
                ocr=args.ocr,
                vision_model=args.vision_model,
                api_key=args.api_key,
            )
        except EX.ExtractionError as exc:
            print(f"\nErreur: {exc}", file=sys.stderr)
            return 1
        text_path.write_text(text, encoding="utf-8")
    words = len(text.split())
    print(f"  {len(text)} caractères, {words} mots")
    done(t)

    # 2. Découpage
    t = step(2, "Découpage")
    units = SEG.utterances(text, max_chars=args.max_chars)
    segments = SEG.all_cards(units)
    tiers: dict[int, int] = {}
    for s in segments:
        tiers[s.font_size] = tiers.get(s.font_size, 0) + 1
    print(f"  {len(units)} énoncés à lire, {len(segments)} cartes à afficher")
    for size in sorted(tiers, reverse=True):
        print(f"    {size}px : {tiers[size]}")
    over = [s for s in segments if s.notes]
    if over:
        print(f"  {len(over)} carte(s) au-delà de la limite, à vérifier")
    done(t)

    if args.text_only:
        _save_segments(segments, seg_path)
        print(f"\nTexte:    {text_path}")
        print(f"Segments: {seg_path}")
        print("\nCorrige le texte si besoin, puis relance avec --from-text.")
        return 0

    # 3. Synthèse
    t = step(3, "Synthèse vocale française")
    TTS.synthesize(
        units, outdir / "audio",
        model_id=args.tts_model,
        voice=TTS.VOICES[args.voice],
        reuse=not args.fresh,
        on_progress=progress("énoncés"),
    )
    TTS.assign_timings(units, gap=args.gap)
    _, total = TTS.concatenate(units, audio_path)
    print(f"  durée totale: {total:.1f}s ({total / 60:.1f} min)")
    done(t)

    # 4. Timeline
    t = step(4, "Construction de la timeline")
    env = WF.envelope(audio_path, fps=args.fps)
    meta = TL.Meta(
        rubrique=args.rubrique,
        speaker=args.speaker,
        date=args.date or french_date(date.today()),
        signature=args.signature,
        photo=args.photo,
        disclaimer="" if args.no_disclaimer else "Texte lu par synthèse vocale",
    )
    payload = TL.build(
        segments, audio_path, env, meta,
        fps=args.fps, total_duration=total,
    )
    TL.save(payload, data_path)
    _save_segments(segments, seg_path)
    print(f"  {payload['durationInFrames']} frames à {args.fps} fps")
    done(t)

    if not (args.render or args.studio):
        print(f"\nPrêt: {data_path}")
        print("Relance avec --render pour produire le MP4, "
              "ou --studio pour l'aperçu.")
        return 0

    # 5. Rendu vidéo
    if args.studio:
        RD.studio(payload, audio_path, args.photo or None)
        return 0

    t = step(5, "Rendu vidéo (Remotion)")
    video_path = outdir / f"{stem}.mp4"
    try:
        RD.render(
            payload, audio_path, video_path,
            photo=args.photo or None,
            concurrency=args.concurrency,
        )
    except RD.RenderError as exc:
        print(f"\nErreur: {exc}", file=sys.stderr)
        print(f"Les données restent utilisables: {data_path}", file=sys.stderr)
        return 1
    done(t)

    size = video_path.stat().st_size / 1_048_576
    print(f"\nTerminé: {video_path}  ({size:.1f} Mo)")
    return 0


def _save_segments(segments: list[SEG.TextSegment], path: Path) -> None:
    import json

    path.write_text(
        json.dumps([s.to_dict() for s in segments], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
