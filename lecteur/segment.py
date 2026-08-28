"""Découpage du texte en segments affichables dans le gabarit « Bandeau télé ».

Les contraintes viennent directement de la maquette:
  - le bandeau ocre dispose de 372px utiles avant de heurter l'onde audio;
  - à 70px avec un interlignage de 1.02, ça fait 3 lignes confortables;
  - soit environ 90 caractères par segment.

La taille de police s'adapte à la longueur pour absorber les segments
qu'on ne peut pas raccourcir sans casser le sens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field

MAX_CHARS = 90
MIN_CHARS = 25  # en dessous, on préfère recoller au segment voisin

# (longueur max, taille de police) — cohérent avec le gabarit corrigé
FONT_TIERS = ((60, 70), (90, 60), (10_000, 52))

SENTENCE_SPLIT = re.compile(r'(?<=[.!?…])\s+(?=[A-ZÀ-ÜŒ«"])')
CLAUSE_SPLIT = re.compile(r"(?<=[,;:])\s+")


@dataclass
class TextSegment:
    index: int
    text: str
    font_size: int = 0
    start: float = 0.0
    duration: float = 0.0
    audio_path: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def end(self) -> float:
        return self.start + self.duration

    def to_dict(self) -> dict:
        d = asdict(self)
        d["chars"] = len(self.text)
        return d


def font_size_for(text: str) -> int:
    length = len(text)
    for ceiling, size in FONT_TIERS:
        if length <= ceiling:
            return size
    return FONT_TIERS[-1][1]


def _split_long(chunk: str, max_chars: int) -> list[str]:
    """Découpe une phrase trop longue, du moins brutal au plus brutal."""
    if len(chunk) <= max_chars:
        return [chunk]

    # 1) sur les virgules, points-virgules, deux-points
    pieces = CLAUSE_SPLIT.split(chunk)
    if len(pieces) > 1:
        out: list[str] = []
        buffer = ""
        for piece in pieces:
            candidate = f"{buffer} {piece}".strip()
            if buffer and len(candidate) > max_chars:
                out.append(buffer)
                buffer = piece
            else:
                buffer = candidate
        if buffer:
            out.append(buffer)
        if all(len(p) <= max_chars for p in out):
            return out
        chunk_pieces: list[str] = []
        for piece in out:
            chunk_pieces.extend(_split_words(piece, max_chars))
        return chunk_pieces

    # 2) sur les mots, en dernier recours
    return _split_words(chunk, max_chars)


def _split_words(chunk: str, max_chars: int) -> list[str]:
    """Découpe équilibrée, en cherchant des coupures qui tiennent à l'oral.

    Un remplissage glouton produit des coupures du type « jusqu'au 30 |
    octobre » : conforme à la limite, mais la synthèse marque une pause au
    milieu d'un groupe de sens. On score donc chaque coupure possible et on
    retient la meilleure, en équilibrant les longueurs.
    """
    words = chunk.split()
    if len(chunk) <= max_chars or len(words) < 2:
        return [chunk]

    best = _best_boundary(words, max_chars)
    left = " ".join(words[:best])
    right = " ".join(words[best:])
    return _split_words(left, max_chars) + _split_words(right, max_chars)


# mots devant lesquels une coupure est naturelle: on respire avant eux
LIAISON_START = {
    "et", "ou", "mais", "donc", "car", "ni", "que", "qui", "dont", "où",
    "lorsque", "lorsqu'", "quand", "parce", "afin", "pour", "dans", "sur",
    "avec", "sans", "par", "vers", "chez", "entre", "depuis", "selon",
    "malgré", "après", "avant", "pendant", "jusqu'", "ainsi", "puis",
}
# mots après lesquels couper casse un groupe de sens
NO_BREAK_AFTER = {
    "le", "la", "les", "un", "une", "des", "du", "de", "au", "aux", "à",
    "ce", "cet", "cette", "ces", "son", "sa", "ses", "leur", "leurs",
    "mon", "ma", "mes", "notre", "nos", "votre", "vos", "en", "et", "ou",
    "ni", "que", "qui", "pour", "dans", "sur", "par", "avec", "sans",
    "plus", "très", "tout", "toute", "tous", "toutes",
}


def _boundary_score(words: list[str], i: int, ideal: int, total: int) -> float:
    """Qualité d'une coupure placée avant le mot d'indice i."""
    left_len = len(" ".join(words[:i]))
    # équilibre: on veut des morceaux de taille comparable
    score = -abs(left_len - ideal) / max(1, ideal) * 3.0

    prev = words[i - 1].lower().rstrip(".,;:!?»\"")
    nxt = words[i].lower().lstrip("«\"")

    if words[i - 1].endswith((",", ";", ":")):
        score += 2.5          # ponctuation faible: coupure idéale
    if nxt in LIAISON_START:
        score += 1.2          # on coupe avant un connecteur
    if prev in NO_BREAK_AFTER:
        score -= 3.0          # déterminant ou préposition orpheline
    if prev.endswith("'"):
        score -= 2.5          # « l' », « d' », « qu' »
    if any(c.isdigit() for c in prev):
        score -= 2.5          # « 30 | octobre », « 15 | septembre »
    if nxt and nxt[0].isdigit():
        score -= 0.8
    return score


def _best_boundary(words: list[str], max_chars: int) -> int:
    ideal = len(" ".join(words)) / 2
    candidates = []
    for i in range(1, len(words)):
        left = len(" ".join(words[:i]))
        right = len(" ".join(words[i:]))
        # les deux côtés doivent rester découpables sans absurdité
        if left < 8 or right < 8:
            continue
        candidates.append((_boundary_score(words, i, ideal, len(words)), i))

    if not candidates:
        return max(1, len(words) // 2)
    return max(candidates)[1]


def _merge_stubs(pieces: list[str], max_chars: int) -> list[str]:
    """Recolle les fragments trop courts au voisin, si ça tient."""
    out: list[str] = []
    for piece in pieces:
        if out and len(piece) < MIN_CHARS:
            joined = f"{out[-1]} {piece}"
            if len(joined) <= max_chars:
                out[-1] = joined
                continue
        out.append(piece)
    return out


def segment(text: str, *, max_chars: int = MAX_CHARS) -> list[TextSegment]:
    """Texte brut -> segments prêts pour la synthèse et l'affichage."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    pieces: list[str] = []

    for paragraph in paragraphs:
        for sentence in SENTENCE_SPLIT.split(paragraph):
            sentence = sentence.strip()
            if sentence:
                pieces.extend(_split_long(sentence, max_chars))

    pieces = _merge_stubs(pieces, max_chars)

    segments: list[TextSegment] = []
    for i, piece in enumerate(pieces):
        seg = TextSegment(index=i, text=piece, font_size=font_size_for(piece))
        if len(piece) > max_chars:
            seg.notes.append(f"dépasse la limite: {len(piece)} caractères")
        segments.append(seg)
    return segments
