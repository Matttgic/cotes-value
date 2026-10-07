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


def test_noms_ecrits_autrement_et_periode_douteuse():
    assert CT.type_intitule("Nombre de jeux de D. Snigur", "Daria Snigur", "Iga Swiatek") == "nombre de jeux de {eq}"
    # la cote suit de près l'autre version (prolongation) et mal la sienne : période douteuse
    import random
    random.seed(1)
    paires = [(0.9 * random.uniform(0.85, 1.15), 0.9 * random.uniform(0.99, 1.01)) for _ in range(20)]
    assert CT.statut([a for a, _ in paires], "TOTAL", paires) == "non_conforme"
    assert CT.statut([b for _, b in paires], "TOTAL", [(b, a) for a, b in paires]) == "conforme"
    assert CT.statut([0.65] * 20, "CORRECT_SCORE") == "conforme"           # marge forte sur le score exact



def test_equipes_inversees_vues_sur_les_marches_orientes():
    # 20 totaux normaux (symétriques) + 8 cotes de handicap aberrantes : la médiane globale reste normale,
    # mais les marchés orientés trahissent l'inversion
    mesures = [(ligne(match="m7"), "Pinnacle", 2.0, 0.93, None) for _ in range(20)]
    mesures += [(ligne(match="m7", marche="HANDICAP"), "Pinnacle", 2.0, 1.3, None) for _ in range(8)]
    assert "m7" in CT.matchs_suspects(mesures)



def test_groupes_plus_mesures_retires():
    etat = {"groupes": {"vieux": {"bookmaker": "unibet-fr", "sport": "hockey", "marche": "TOTAL", "periode": "MATCH",
                                  "type": "x", "n": 20, "rapports": [0.9] * 20, "exemples": [],
                                  "maj": "2026-09-03T10:00:00+00:00"}}}
    CT.mettre_a_jour(etat, [(ligne(), "Pinnacle", 2.0, 0.93, None)], "2026-10-06T10:00:00+00:00")
    assert "vieux" not in etat["groupes"] and len(etat["groupes"]) == 1


def test_mesure_seulement_avec_une_reference_lue_au_meme_moment():
    # revue externe (R1) : une cote Pinnacle lue 30 min avant la cote française ne mesure pas l'intitulé ;
    # on se rabat sur une autre référence lue au même moment
    fr = ligne(cote=2.0, collecte="2030-01-01T17:50:00+00:00")
    vieux = {**ligne(), "proba_juste": 0.8, "collecte": "2030-01-01T17:20:00+00:00"}
    frais = {**ligne(), "proba_juste": 0.47, "collecte": "2030-01-01T17:48:00+00:00"}
    k = CT.cle(fr)
    assert CT.mesurer([fr], {"Pinnacle": {"m1": {k: vieux}}}) == []
    m = CT.mesurer([fr], {"Pinnacle": {"m1": {k: vieux}}, "Betfair": {"m1": {k: frais}}})
    assert [(nom, round(r, 2)) for _, nom, _, r, _ in m] == [("Betfair", 0.94)]
    assert CT.mesurer([fr], {"Pinnacle": {"m1": {k: frais}}})[0][1] == "Pinnacle"
