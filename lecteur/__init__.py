"""Lecture vidéo de communiqués politiques: texte ou image -> vidéo 9:16.

On n'expose volontairement pas la fonction `segment` ici: elle masquerait
le module `lecteur.segment` du même nom.
"""

from .segment import TextSegment

__all__ = ["TextSegment"]
__version__ = "0.1.0"
