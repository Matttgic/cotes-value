"""Méthodes de mise : formules, absence d'information du futur, bankroll et séries au moment de la détection."""
from cotes.mises import BANKROLL, METHODES, comparer, simuler
from tests.test_strategie_jules_v2 import pari


def regle(pid, statut, detecte, regle_le, **kw):
    return pari(pid, statut=statut, detecte=detecte, regle_le=regle_le, **kw)


def test_toutes_les_methodes_sont_simulees_sur_un_pari_gagne():
    p = regle("a", "gagne", "2026-10-15T09:00:00Z", "2026-10-15T15:00:00Z", cote=2.0, ecart=.05)
    r = comparer([p])
    assert set(r) == set(METHODES) and len(METHODES) == 18
    assert r["fixe"]["mise"] == 10 and r["fixe"]["gain"] == 10 and r["fixe"]["roi"] == 100
    assert r["kelly_4"]["mise"] == 12.5 and r["kelly_2"]["mise"] == 20 and r["kelly_8"]["mise"] == 6.25   # 1000 × f × 0,05 / 1
    assert r["kelly_1"]["mise"] == 50 and r["kelly_4_p1"]["mise"] == 10 and r["kelly_4_p3"]["mise"] == 12.5
    assert r["kelly_4_liquide"]["mise"] == 10
    assert r["kelly_prudent"]["mise"] == 6.25 and r["kelly_sans_gros"]["mise"] == 12.5   # ¼ de Kelly sur 2,5 % d'écart
    assert r["par_ecart"]["mise"] == 12.5 and r["gain_constant"]["mise"] == 10 and r["paliers"]["mise"] == 10
    assert r["pct_1"]["mise"] == 10 and r["kelly_4_evol"]["mise"] == 12.5


def test_gain_constant_plafonne_et_remboursement_sans_gain():
    p = regle("a", "rembourse", "2026-10-15T09:00:00Z", "2026-10-15T15:00:00Z", cote=1.3, ecart=.03)
    r = comparer([p])
    assert r["gain_constant"]["mise"] == 25 and r["fixe"]["gain"] == 0 and r["fixe"]["roi"] == 0


def test_la_bankroll_ne_connait_que_les_paris_deja_regles():
    a = regle("a", "gagne", "2026-10-15T09:00:00Z", "2026-10-15T12:00:00Z", cote=3.0, ecart=.05)      # +20 si misé 10
    b = regle("b", "perdu", "2026-10-15T13:00:00Z", "2026-10-15T20:00:00Z", cote=2.0, ecart=.05)       # détecté après a
    c = regle("c", "perdu", "2026-10-15T10:00:00Z", "2026-10-15T20:00:00Z", cote=2.0, ecart=.05)       # détecté avant le règlement de a
    r = simuler([a, b, c], "pct_1")
    assert r["mise"] == round(10 + 10 + 1000 * .01 * (1 + 20 / 1000), 2)    # c : 1000, b : 1020 (gain de a connu)
    assert r["paris"] == 3


def test_serie_de_pertes_reduit_la_mise_et_martingale_double():
    def p(i, statut, h):
        return regle(f"p{i}", statut, f"2026-10-1{i}T09:00:00Z", f"2026-10-1{i}T10:00:00Z", cote=2.0, ecart=.05)
    rows = [p(1, "perdu", 0), p(2, "perdu", 0), p(3, "perdu", 0), p(4, "perdu", 0), p(5, "gagne", 0)]
    ap = simuler(rows, "apres_pertes")
    assert ap["mise"] == 10 * 3 + 5 + 5          # 4e et 5e paris : après 3 pertes d'affilée
    mg = simuler(rows, "martingale")
    assert mg["mise"] == 10 + 20 + 40 + 80 + 80   # doublement plafonné à 80 €
    assert mg["mise_max"] == 80


def test_pas_de_mise_au_dela_du_solde_et_ecart_inexploitable():
    perdu = [regle(f"p{i}", "perdu", f"2026-10-0{i}T09:00:00Z", f"2026-10-0{i}T10:00:00Z", cote=2.0, ecart=.05) for i in range(1, 9)]
    r = simuler(perdu, "martingale")
    assert r["solde_min"] >= 0 and r["gain"] >= -BANKROLL
    sans = regle("z", "gagne", "2026-10-15T09:00:00Z", "2026-10-15T15:00:00Z", cote=2.0, ecart=None)
    assert simuler([sans], "kelly_4")["paris"] == 0 and simuler([sans], "fixe")["paris"] == 1


def test_les_paris_en_cours_et_les_donnees_d_origine_sont_ignores_ou_intacts():
    en_cours = pari("e", statut="en_cours")
    gagne = regle("g", "gagne", "2026-10-15T09:00:00Z", "2026-10-15T15:00:00Z")
    avant = [dict(en_cours), dict(gagne)]
    r = comparer([en_cours, gagne])
    assert r["fixe"]["paris"] == 1 and [en_cours, gagne] == avant


def test_les_grosses_cotes_sont_ecartees_par_les_deux_methodes_prudentes():
    gros = regle("g", "perdu", "2026-10-15T09:00:00Z", "2026-10-15T15:00:00Z", cote=7.0, ecart=.05)
    moyen = regle("m", "perdu", "2026-10-15T09:00:00Z", "2026-10-15T15:00:00Z", cote=5.0, ecart=.05)
    assert simuler([gros], "kelly_prudent")["paris"] == 0 and simuler([gros], "kelly_sans_gros")["paris"] == 0
    assert simuler([moyen], "kelly_prudent")["paris"] == 1 and simuler([moyen], "kelly_sans_gros")["paris"] == 0
