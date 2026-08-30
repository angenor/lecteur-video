"""Découpage du texte en segments affichables dans le gabarit « Bandeau télé ».

Les contraintes viennent directement de la maquette:
  - le bandeau ocre dispose de 372px utiles avant de heurter l'onde audio;
  - à 70px avec un interlignage de 1.02, ça fait 3 lignes confortables;
  - soit environ 90 caractères par segment.

La taille de police s'adapte à la longueur pour absorber les segments
qu'on ne peut pas raccourcir sans casser le sens.

Deux découpages cohabitent, et il ne faut pas les confondre:

  - l'ÉNONCÉ (`Utterance`) est l'unité de synthèse. C'est une phrase entière,
    lue d'un trait, pour que la voix garde son intonation et ne marque pas de
    pause au milieu d'un groupe de sens;
  - la CARTE (`TextSegment`) est l'unité d'affichage, bornée par le gabarit.

Une phrase de 200 caractères se lit donc d'une seule traite, et son texte
défile en trois cartes réparties sur la durée de l'audio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field

MAX_CHARS = 90
MIN_CHARS = 25  # en dessous, on préfère recoller au segment voisin

# Limite de l'unité de synthèse. Rien à voir avec le gabarit: c'est la
# mémoire GPU qui commande. Le modèle décode toutes ses frames en un seul
# buffer, et Metal refuse toute allocation unique au-delà de max_buffer_length
# (10,7 Go sur M3 Pro) — c'est ce mur qu'on a heurté à 4096 frames, avec une
# demande de 28 Go. Le point de rupture est donc vers 1500 frames (~2 min
# d'audio). 400 caractères, soit une trentaine de secondes, laissent une marge
# large tout en gardant entières les phrases françaises les plus longues.
MAX_SPEECH_CHARS = 400

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


@dataclass
class Utterance:
    """Unité de synthèse: une phrase, lue d'un trait, et ses cartes."""

    index: int
    text: str
    cards: list[TextSegment] = field(default_factory=list)
    start: float = 0.0
    duration: float = 0.0
    audio_path: str | None = None

    @property
    def end(self) -> float:
        return self.start + self.duration


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
    """Recolle les fragments trop courts au voisin, si ça tient.

    À n'appliquer qu'aux morceaux d'une même phrase: recoller par-dessus un
    point produirait des segments à cheval sur deux phrases, du type
    « ... servir votre communauté. Depuis 2016, ».
    """
    out: list[str] = []
    for piece in pieces:
        if out and len(piece) < MIN_CHARS:
            joined = f"{out[-1]} {piece}"
            if len(joined) <= max_chars:
                out[-1] = joined
                continue
        out.append(piece)

    # Le premier morceau n'a pas de voisin gauche: il se rabat sur sa droite.
    if len(out) > 1 and len(out[0]) < MIN_CHARS:
        joined = f"{out[0]} {out[1]}"
        if len(joined) <= max_chars:
            out[:2] = [joined]
    return out


def sentences(text: str) -> list[str]:
    """Texte brut -> phrases, paragraphe par paragraphe."""
    out: list[str] = []
    for paragraph in (p.strip() for p in text.split("\n\n")):
        if not paragraph:
            continue
        for sentence in SENTENCE_SPLIT.split(paragraph):
            sentence = sentence.strip()
            if sentence:
                out.append(sentence)
    return out


def cards_for(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Découpe un énoncé en cartes affichables dans le gabarit."""
    return _merge_stubs(_split_long(text, max_chars), max_chars)


def utterances(
    text: str,
    *,
    max_chars: int = MAX_CHARS,
    max_speech: int = MAX_SPEECH_CHARS,
) -> list[Utterance]:
    """Texte brut -> énoncés à synthétiser, chacun portant ses cartes.

    La phrase reste entière tant qu'elle tient dans le budget de synthèse;
    au-delà, on la coupe sur sa ponctuation faible plutôt que d'imposer à la
    voix les coupures du gabarit.
    """
    units: list[Utterance] = []
    card_index = 0

    for sentence in sentences(text):
        for speech in _split_long(sentence, max_speech):
            unit = Utterance(index=len(units), text=speech)
            for piece in cards_for(speech, max_chars):
                card = TextSegment(
                    index=card_index, text=piece, font_size=font_size_for(piece)
                )
                if len(piece) > max_chars:
                    card.notes.append(
                        f"dépasse la limite: {len(piece)} caractères"
                    )
                unit.cards.append(card)
                card_index += 1
            units.append(unit)

    return units


def all_cards(units: list[Utterance]) -> list[TextSegment]:
    """Les cartes de tous les énoncés, à plat et dans l'ordre."""
    return [card for unit in units for card in unit.cards]


def segment(text: str, *, max_chars: int = MAX_CHARS) -> list[TextSegment]:
    """Texte brut -> cartes d'affichage, à plat."""
    return all_cards(utterances(text, max_chars=max_chars))
