"""Vérifie que le découpage ne casse pas les groupes de sens.

Ces cas sont des régressions constatées: un remplissage glouton respectait
la limite de caractères mais coupait « jusqu'au 30 | octobre », ce qui fait
marquer une pause à la synthèse au milieu d'une date.
"""

from lecteur.segment import segment

CAS = [
    (
        "La révision de la liste électorale débutera le 15 septembre et se "
        "poursuivra jusqu'au 30 octobre sur toute l'étendue du territoire.",
        ["30", "15"],  # ne doit pas finir un segment sur un nombre
    ),
    (
        "Le président de la République a reçu ce matin une délégation de la "
        "chambre de commerce et d'industrie de Côte d'Ivoire au palais.",
        ["de", "la", "le", "d'", "et"],
    ),
    (
        "Nous demandons à tous les militants de se rendre dans les bureaux "
        "de vote dès l'ouverture pour accomplir leur devoir citoyen.",
        ["les", "de", "à", "dans"],
    ),
]


def test_pas_de_coupure_orpheline():
    for texte, interdits in CAS:
        segs = segment(texte)
        for s in segs[:-1]:  # le dernier finit sur un point, c'est normal
            dernier = s.text.split()[-1].lower().rstrip(".,;:")
            assert dernier not in interdits, (
                f"segment terminé par « {dernier} »: {s.text!r}"
            )
            assert not any(c.isdigit() for c in dernier), (
                f"segment terminé par un nombre: {s.text!r}"
            )
            assert not dernier.endswith("'"), (
                f"segment terminé par une élision: {s.text!r}"
            )
    print("  aucune coupure orpheline OK")


def test_equilibre():
    """Les segments d'une même phrase doivent avoir des tailles proches."""
    texte = ("Chaque citoyen en âge de voter devra se présenter muni d'une "
             "pièce d'identité en cours de validité sans exception aucune.")
    segs = segment(texte)
    tailles = [len(s.text) for s in segs]
    assert max(tailles) - min(tailles) < 45, tailles
    print(f"  équilibre OK {tailles}")


def test_ponctuation_privilegiee():
    """Une virgule bien placée doit servir de point de coupure."""
    texte = ("Les centres mobiles seront déployés dans toutes les zones "
             "rurales du pays, afin d'éviter aux populations les longs "
             "déplacements vers les chefs-lieux.")
    segs = segment(texte)
    assert any(s.text.rstrip().endswith(",") for s in segs), \
        [s.text for s in segs]
    print("  coupure sur virgule OK")


if __name__ == "__main__":
    test_pas_de_coupure_orpheline()
    test_equilibre()
    test_ponctuation_privilegiee()
    print("\nDécoupage validé.")
