"""Note des stratégies sur 100 : régularité et solidité avant le gain brut."""
import random

from cotes.notation import noter


def _serie(gains, cote=2.0, mise=10.0, clv=0.01, jours=None):
    n = len(gains)
    jours = jours if jours is not None else [sum(gains[i::20]) for i in range(20)]
    return noter(gains, [mise] * n, [cote] * n, [clv] * n, jours, _baisse(gains))


def _baisse(gains):
    cumul = sommet = baisse = 0.0
    for g in gains:
        cumul += g
        sommet = max(sommet, cumul)
        baisse = max(baisse, sommet - cumul)
    return baisse


def test_pas_de_note_sous_dix_paris_et_provisoire_sous_cinquante():
    assert _serie([10, -10] * 4) is None
    assert _serie([10, -10, 10] * 10)["provisoire"] is True
    assert _serie([10, -10, 10] * 20)["provisoire"] is False


def test_bornes_et_total_coherent():
    n = _serie([10, -10, 10, -10, 10] * 40)
    assert 0 <= n["total"] <= 100
    assert abs(n["total"] - (n["rentabilite"] + n["valeur"] + n["regularite"] + n["solidite"])) <= 1


def test_meme_gain_total_la_serie_reguliere_est_mieux_notee():
    """Même ROI : l'une gagne régulièrement, l'autre enchaîne une longue série de pertes puis un rattrapage."""
    reguliere = [10, -10, 10] * 60
    chaotique = [-10] * 60 + [10] * 120
    assert sum(reguliere) == sum(chaotique)
    a, b = _serie(reguliere), _serie(chaotique)
    assert a["regularite"] > b["regularite"] and a["total"] > b["total"]


def test_gros_roi_sur_peu_de_paris_moins_bien_note_qu_un_roi_modeste_solide():
    hasard = random.Random(7)
    solide = [9.0 if hasard.random() < .55 else -10.0 for _ in range(400)]     # cote 1,9, ~5 % de ROI
    chanceux = [-10.0] * 9 + [140.0]                                          # un gros gain sur 10 paris (cote 15)
    s = noter(solide, [10.0] * 400, [1.9] * 400, [0.01] * 400, [sum(solide[i::25]) for i in range(25)], _baisse(solide))
    c = noter(chanceux * 2, [10.0] * 20, [15.0] * 20, [0.01] * 20, [sum(chanceux)] * 2, _baisse(chanceux * 2))
    assert sum(chanceux * 2) / 200 > sum(solide) / 4000       # meilleur ROI brut…
    assert s["total"] > c["total"]                           # …mais moins bonne note


def test_longues_cotes_penalisees_en_solidite():
    gains = [10, -10, 10] * 40
    courte, longue = _serie(gains, cote=2.0), _serie(gains, cote=9.0)
    assert courte["solidite"] > longue["solidite"]
