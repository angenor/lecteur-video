"""Extraction du texte source: fichier texte, ou image contenant du texte.

Deux voies pour les images:
  - `vision` (défaut): un modèle multimodal via OpenRouter. Meilleur sur les
    captures d'écran de réseaux sociaux — accents, mise en page cassée,
    emojis, texte sur fond coloré.
  - `local`: l'OCR natif de macOS via ocrmac. Gratuit, hors ligne, mais moins
    tolérant aux mises en page inhabituelles.
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path

TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".tiff", ".bmp"}

BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_VISION_MODEL = "anthropic/claude-sonnet-5"

OCR_PROMPT = """\
Transcris intégralement le texte visible dans cette image.

Règles:
- Restitue le texte tel qu'il est écrit, sans le corriger ni le résumer.
- Respecte les accents et la ponctuation française.
- Ignore les éléments d'interface: boutons, compteurs de likes, horodatages,
  noms de réseaux sociaux, mentions "Voir plus" ou "Traduire".
- Ignore les emojis décoratifs isolés en début ou fin de ligne.
- Rends les paragraphes séparés par une ligne vide.
- Si l'image ne contient aucun texte lisible, réponds exactement: AUCUN_TEXTE

Réponds uniquement par le texte transcrit, sans préambule ni commentaire.
"""

MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
}


class ExtractionError(RuntimeError):
    pass


def clean_text(raw: str) -> str:
    """Normalise le texte avant découpage.

    Les copiés-collés de réseaux sociaux arrivent avec des espaces
    insécables, des guillemets exotiques et des retours à la ligne
    arbitraires au milieu des phrases.
    """
    text = raw.replace("\u00a0", " ").replace("\u202f", " ")
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"[ \t]+", " ", text)
    # un retour simple au milieu d'un paragraphe = espace; double = paragraphe
    text = re.sub(r"\n{2,}", "\n\n", text)
    text = re.sub(r"(?<![.!?:\n])\n(?!\n)", " ", text)
    return text.strip()


def _read_text_file(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ExtractionError(f"Encodage illisible: {path}")


def _ocr_vision(path: Path, model: str, api_key: str | None) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ExtractionError("SDK manquant: pip install openai") from exc

    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ExtractionError(
            "Clé absente. Exporte OPENROUTER_API_KEY, ou utilise --ocr local."
        )

    mime = MIME.get(path.suffix.lower())
    if mime is None:
        raise ExtractionError(f"Format d'image non géré: {path.suffix}")

    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    client = OpenAI(base_url=BASE_URL, api_key=key)

    response = client.chat.completions.create(
        model=model,
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": OCR_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{payload}"},
                },
            ],
        }],
        extra_headers={"X-Title": "lecteur-video"},
    )
    if not response.choices:
        raise ExtractionError("Réponse vide du modèle vision.")
    return response.choices[0].message.content or ""


def _ocr_local(path: Path) -> str:
    """OCR natif macOS (framework Vision) via ocrmac."""
    try:
        from ocrmac import ocrmac
    except ImportError as exc:
        raise ExtractionError(
            "ocrmac manquant: pip install ocrmac  (macOS uniquement)"
        ) from exc

    results = ocrmac.OCR(str(path), language_preference=["fr-FR"]).recognize()
    # results: [(texte, confiance, bbox), ...] — on trie de haut en bas
    lines = sorted(results, key=lambda r: -r[2][1])
    return "\n".join(line[0] for line in lines)


def extract(
    source: Path,
    *,
    ocr: str = "vision",
    vision_model: str = DEFAULT_VISION_MODEL,
    api_key: str | None = None,
) -> str:
    if not source.exists():
        raise ExtractionError(f"Fichier introuvable: {source}")

    suffix = source.suffix.lower()

    if suffix in TEXT_SUFFIXES:
        raw = _read_text_file(source)
    elif suffix in IMAGE_SUFFIXES:
        raw = _ocr_vision(source, vision_model, api_key) if ocr == "vision" \
            else _ocr_local(source)
        if raw.strip() == "AUCUN_TEXTE":
            raise ExtractionError(f"Aucun texte détecté dans {source.name}")
    else:
        raise ExtractionError(
            f"Format non géré: {suffix}\n"
            f"Attendu: {', '.join(sorted(TEXT_SUFFIXES | IMAGE_SUFFIXES))}"
        )

    text = clean_text(raw)
    if not text:
        raise ExtractionError(f"Texte vide après nettoyage: {source.name}")
    return text


def extract_many(
    sources: list[Path],
    *,
    ocr: str = "vision",
    vision_model: str = DEFAULT_VISION_MODEL,
    api_key: str | None = None,
) -> str:
    """Plusieurs images = un communiqué découpé en captures successives."""
    parts = [
        extract(s, ocr=ocr, vision_model=vision_model, api_key=api_key)
        for s in sources
    ]
    return "\n\n".join(parts)
