"""Moteur des stratégies du conseil : filtres connus à la détection, convergence causale, une prise par match."""
from cotes.strategie_conseil import index_convergence, motif_refus, paris_conseil
from tests.test_strategie_jules_v2 import pari

REGLE = {"cle": "essai", "nom": "Essai", "debut": "2026-10-15T00:00:00Z", "version": "1",
         "references": ("Pinnacle",), "bookmakers": ("Winamax", "Betclic", "PMU"), "sports": ("football", "tennis"),
         "marches": ("VAINQUEUR", "TOTAL", "DOUBLE_CHANCE", "TOTAL_DOM"),
         "cote_min": 1.3, "cote_max": 3.0, "edge_min": 0.02, "edge_max": 0.12, "maximum_jour": 2}


def test_pari_dans_le_perimetre_retenu():
    p = pari("a")
    assert motif_refus(p, REGLE) is None
    assert paris_conseil([p], REGLE) == {id(p)}


def test_refus_par_filtre():
    assert motif_refus(pari("a", reference="Polymarket"), REGLE) == "référence hors périmètre"
    assert motif_refus(pari("a", bookmaker="Unibet"), REGLE) == "bookmaker ou sport hors périmètre"
    assert motif_refus(pari("a", cote=3.2, cote_juste=3.04, ecart=3.2 / 3.04 - 1), REGLE) == "cote hors intervalle"
    assert motif_refus(pari("a", cote=2.4, cote_juste=2.0, ecart=.2), REGLE) == "écart hors intervalle"
    assert motif_refus(pari("a", ecart=.03), REGLE) == "écart incohérent avec la cote juste"
    assert motif_refus(pari("a", detecte="2026-10-15T11:55:00Z", lu_reference="2026-10-15T11:55:00Z"),
                       REGLE) == "détection hors fenêtre avant le match"
    assert motif_refus(pari("a", lu_reference="2026-10-15T08:40:00Z"), REGLE) == "référence trop ancienne"
    assert motif_refus(pari("a", preuve_prise={"match_id_reference": "a", "ressemblance_noms": .8,
                                               "controle": {"statut": "conforme"}}), REGLE) \
        == "preuve de correspondance insuffisante"
    assert motif_refus(pari("a", sport="tennis", marche="TOTAL", issue="PLUS", ligne=22.5), REGLE) \
        == "tennis et volley : vainqueur du match uniquement"
    assert motif_refus(pari("a", marche="TOTAL", issue="PLUS", ligne=2.25), REGLE) == "ligne absente ou en quarts"
    assert motif_refus(pari("a", periode="MT1"), REGLE) == "marché ou période hors périmètre"


def test_issues_par_marche_et_filtre_d_issue():
    assert motif_refus(pari("a", marche="DOUBLE_CHANCE", issue="HOME_DRAW"), REGLE) is None
    assert motif_refus(pari("a", marche="TOTAL_DOM", issue="PLUS", ligne=1.5), REGLE) is None
    assert motif_refus(pari("a", marche="TOTAL", issue="DOM", ligne=2.5), REGLE) == "issue hors périmètre"
    assert motif_refus(pari("a", marche="TOTAL", issue="MOINS", ligne=2.5), {**REGLE, "issues": ("PLUS",)}) \
        == "issue hors périmètre"


def test_jeunes_toujours_exclus_feminin_sur_demande():
    assert motif_refus(pari("a", domicile="Lyon U21", exterieur="Paris U21"), REGLE) == "jeunes ou réserve"
    f = pari("a", domicile="Lyon (F)", exterieur="Paris (F)")
    assert motif_refus(f, REGLE) is None
    assert motif_refus(f, {**REGLE, "exclure_feminin": True}) == "match féminin exclu"


def test_accord_polymarket_exige_un_ecart_mesure():
    r = {**REGLE, "accord_polymarket_min": 0.0}
    assert motif_refus(pari("a"), r) == "Polymarket ne confirme pas l'écart"
    assert motif_refus(pari("a", ecart_polymarket=-.01), r) == "Polymarket ne confirme pas l'écart"
    assert motif_refus(pari("a", ecart_polymarket=.01), r) is None


def test_convergence_ne_compte_que_les_prises_deja_vues():
    tot = dict(marche="TOTAL", issue="PLUS", ligne=2.5)
    a = pari("a", **tot)
    b = pari("a", **tot, id="b", bookmaker="Betclic", match_id="betclic|a", detecte="2026-10-15T09:05:00Z",
             lu_reference="2026-10-15T09:05:00Z")
    c = pari("a", **tot, id="c", bookmaker="PMU", match_id="pmu|a", detecte="2026-10-15T08:00:00Z",
             lu_reference="2026-10-15T08:00:00Z", marche_autre=True)
    conv = index_convergence([a, b, c])
    assert conv[id(c)] == 1 and conv[id(a)] == 2 and conv[id(b)] == 3     # PMU à 8 h, Winamax à 9 h, Betclic à 9 h 05
    r = {**REGLE, "convergence_min": 2}
    assert motif_refus(c, r, conv) == "pas assez de bookmakers sur le même écart"
    assert motif_refus(a, r, conv) is None
    assert motif_refus(a, r) == "pas assez de bookmakers sur le même écart"      # sans index : refus, jamais deviné


def test_une_prise_par_match_avant_lancement_rien_et_plafond_jour():
    meme = [pari("m", bookmaker=b, match_id=f"{b}|m", detecte=f"2026-10-15T09:0{i}:00Z",
                 lu_reference=f"2026-10-15T09:0{i}:00Z") for i, b in enumerate(("Winamax", "Betclic"))]
    assert len(paris_conseil(meme, REGLE)) == 1
    assert paris_conseil([pari("a")], {**REGLE, "debut": "2026-10-16T00:00:00Z"}) == set()
    trois = [pari(x) for x in "xyz"]
    assert len(paris_conseil(trois, REGLE)) == 2


def test_le_moteur_ne_lit_aucun_resultat():
    p, q = pari("a"), pari("a", statut="perdu", gain=-10.0, clv=-.5, cote_juste_cloture=9.0)
    assert motif_refus(p, REGLE) == motif_refus(q, REGLE) is None


def test_conseil_retard_prospectif_hors_football_et_dans_les_choix():
    from cotes.notifications import NOMS
    from cotes.strategie_conseil import CONSEIL_RETARD
    from cotes.strategies_prudentes import VARIANTES, selections_prudentes
    hockey = dict(sport="hockey", marche="HANDICAP", ligne=1.5, issue="DOM", cote=2.1, cote_juste=2.0, ecart=.05,
                  detecte="2026-10-26T09:00:00Z", debut="2026-10-26T18:00:00Z", lu_reference="2026-10-26T08:57:00Z")
    p = pari("h", **hockey)
    assert motif_refus(p, CONSEIL_RETARD) is None
    assert selections_prudentes([p])["conseil_retard"] == {id(p)}
    assert motif_refus(pari("f", **{**hockey, "sport": "football"}), CONSEIL_RETARD) == "bookmaker ou sport hors périmètre"
    assert motif_refus(pari("t", **{**hockey, "marche": "TOTAL", "issue": "PLUS"}), CONSEIL_RETARD) \
        == "marché ou période hors périmètre"
    assert motif_refus(pari("e", **{**hockey, "cote": 2.04, "cote_juste": 2.0, "ecart": .02}), CONSEIL_RETARD) \
        == "écart hors intervalle"                                                     # écart minimum 3 %
    assert motif_refus(pari("v", **{**hockey, "lu_reference": "2026-10-26T08:54:00Z"}), CONSEIL_RETARD) \
        == "référence trop ancienne"                                                   # lue il y a plus de 5 min
    avant = pari("a", **{**hockey, "detecte": "2026-10-26T03:00:00Z", "lu_reference": "2026-10-26T03:00:00Z"})
    assert selections_prudentes([avant])["conseil_retard"] == set()                   # suivi prospectif seulement
    assert CONSEIL_RETARD in VARIANTES and NOMS["conseil_retard"] == "Conseil retard"


def test_resume_donne_la_duree_du_suivi_pour_les_moyennes():
    from cotes.laboratoire import resume
    p = pari("a")
    assert resume([p], "2026-10-25T12:00:00Z", incertitude=False, depuis="2026-10-15T12:00:00Z")["jours"] == 10
    assert resume([p], "2026-10-15T13:00:00Z", incertitude=False, depuis="2026-10-15T12:00:00Z")["jours"] == 1   # au moins un jour
    assert "jours" not in resume([p], "2026-10-25T12:00:00Z", incertitude=False)
