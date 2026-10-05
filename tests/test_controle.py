from cotes import controle as CT
from cotes.comparaison import comparer


def ligne(bm="winamax", libelle="Nombre de buts", cote=1.9, match="m1", **k):
    return {"bookmaker": bm, "source": bm, "sport": "football", "marche": "TOTAL", "periode": "MATCH",
            "ligne": 2.5, "issue": "PLUS", "libelle": libelle, "domicile": "Lens", "exterieur": "Lille",
            "match_id": match, "cote": cote, "debut": "2030-01-01T20:00:00+00:00",
            "collecte": "2029-12-31T20:00:00+00:00", "joueur": None, "ligue": "L1", **k}


def test_type_intitule_sans_equipes_ni_nombres():
    assert CT.type_intitule("Plus / Moins Tirs cadrés - Lens [2,5]", "Lens", "Lille") == "plus / moins tirs cadres - {eq} [#]"


def test_statut():
    assert CT.statut([0.94] * 5) == "a_verifier"
    assert CT.statut([0.94] * 20) == "conforme"
    assert CT.statut([0.94] * 15 + [4.0] * 5) == "non_conforme"       # 25 % de cotes aberrantes
    assert CT.statut([1.10] * 20) == "non_conforme"                   # systématiquement au-dessus du juste


def test_pas_de_pari_tant_que_l_intitule_n_est_pas_conforme():
    ref = [{**ligne(), "source": "pinnacle", "match_id": "p1", "cote": 1.95, "proba_juste": 0.5,
            "marge_pinnacle": 0.03}]
    fr = [ligne(cote=2.2)]
    etat = {}
    # premier passage : une seule mesure -> à vérifier, pas de pari possible
    from cotes.comparaison import indexer
    idx = indexer(fr, {"Pinnacle": ref})
    m = CT.mesurer(fr, idx)
    CT.mettre_a_jour(etat, m, "t")
    o = comparer(fr, {"Pinnacle": ref}, index=idx, controle=(etat, {}))
    assert o[0]["suspect"] == "intitulé à vérifier"
    # assez de mesures normales (cotes sous le juste) sur cet intitulé -> conforme -> le pari est possible
    autres = [ligne(cote=1.88, match=f"x{i}") for i in range(10)]
    CT.mettre_a_jour(etat, [(l, "Pinnacle", 2.0, l["cote"] / 2.0) for l in autres], "t")
    o = comparer(fr, {"Pinnacle": ref}, index=idx, controle=(etat, {}))
    assert o[0]["suspect"] is None


def test_match_mal_associe():
    mesures = [(ligne(match="m9"), "Pinnacle", 2.0, 1.6) for _ in range(8)]
    assert "m9" in CT.matchs_suspects(mesures)
