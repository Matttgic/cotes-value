from cotes import comparaison, reglement
from cotes.direct import betclic
from cotes.pulsescore import traduire

T = "2026-11-13T10:00:00+00:00"


def _lignes(nom="L'équipe possède 2 buts d'avance ou gagne (tps rég.)", sport="football"):
    mk = {"nom": nom, "selections": [{"nom": "Lyon", "cote": 1.9}, {"nom": "Nice", "cote": 3.1}]}
    ev = {"eventId": "1", "home": "Lyon", "away": "Nice", "startTime": "2026-11-14T18:00:00+00:00",
          "markets": betclic.marches_pulse(mk, "Lyon", "Nice", sport)}
    return traduire(ev, "betclic", sport, T)


def test_traduction():
    ls = _lignes()
    assert {(l["marche"], l["periode"], l["ligne"], l["issue"]) for l in ls} == {
        ("AVANCE_OU_GAGNE", "MATCH", 2.0, "DOM"), ("AVANCE_OU_GAGNE", "MATCH", 2.0, "EXT")}
    assert {l["periode"] for l in _lignes("L'équipe possède 2 buts d'avance ou gagne (tps rég.)", "hockey")} == {"TEMPS_REG"}
    assert comparaison.libelle_pari(ls[0]).startswith("Lyon gagne ou mène de 2 buts")


def test_comparee_a_la_victoire_ecart_minimum():
    fr = [l for l in _lignes() if l["issue"] == "DOM"]
    ref = {"source": "pinnacle", "sport": "football", "match_id": "p1", "domicile": "Lyon", "exterieur": "Nice",
           "debut": "2026-11-14T18:00:00+00:00", "collecte": T, "marche": "RESULTAT_1N2", "periode": "MATCH",
           "ligne": None, "issue": "DOM", "proba_juste": 0.56, "cote_juste": 1.786, "cote": 1.75}
    ops = comparaison.comparer(fr, {"Pinnacle": [ref]})
    assert len(ops) == 1 and ops[0]["ecart"] == round(1.9 * 0.56 - 1, 4) and ops[0]["ecart_minimum"]
    # contrôle des intitulés absent : pas bloquant pour ce marché, seul le match suspect l'est
    assert not comparaison.comparer(fr, {"Pinnacle": [ref]}, controle=({}, {}))[0]["suspect"]
    assert comparaison.comparer(fr, {"Pinnacle": [ref]}, controle=({}, {fr[0]["match_id"]: 1}))[0]["suspect"]


def test_reglement():
    p = {"marche": "AVANCE_OU_GAGNE", "periode": "MATCH", "issue": "DOM", "ligne": 2.0}
    assert reglement.regler(p, {"MATCH": (2, 1)}) == "gagne"
    assert reglement.regler(p, {"MATCH": (2, 2), "MT1": (2, 0)}) == "gagne"
    assert reglement.regler(p, {"MATCH": (1, 1)}) == "perdu"
    assert reglement.regler(p, {"MATCH": (2, 2), "MT1": (1, 0)}) is None      # 2-0 possible avant 2-2 : à la main
    assert reglement.regler(p, {"MATCH": (2, 2), "MT1": (1, 1)}) == "perdu"   # jamais plus d'un but d'avance
    assert reglement.regler({**p, "issue": "EXT"}, {"MATCH": (3, 1)}) == "perdu"
