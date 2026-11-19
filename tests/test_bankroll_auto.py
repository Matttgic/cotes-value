from datetime import datetime, timedelta, timezone

from cotes.alertes import bankroll as B
from cotes.notifications import empreinte_prix

T = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
PARI = {"match_id": "pmu|1", "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None, "issue": "1", "cote": 2.0,
        "statut": "en_cours", "mise": 10.0, "gain": None}


def test_regle_asymetrique():
    assert B.bankroll_de_mise(1000, 1000) == 1000
    assert B.bankroll_de_mise(1150, 1000) == 1000            # pas encore le palier
    assert B.bankroll_de_mise(1200, 1000) == 1200            # palier +20 %
    assert B.bankroll_de_mise(1500, 1000) == 1440            # deux paliers
    assert B.bankroll_de_mise(905, 1000) == 1000             # baisse de moins de 10 % : on garde
    assert B.bankroll_de_mise(880, 1000) == 880              # baisse de plus de 10 % : tout de suite


def test_cycle_complet_et_recalage():
    env = {"PUSHOVER_BANKROLL": "1000"}
    e = B.mettre_a_jour({}, [], env, T)
    assert e["bankroll"] == 1000 and e["mise_sur"] == 1000
    alerte = {"id": empreinte_prix(PARI), "mise_kelly": 2.4, "mises": 2, "cote": 2.0}
    B.noter(e, [alerte, {"id": "sans-mise"}], T)
    assert e["ouvertes"][alerte["id"]]["mise"] == 6.0            # 2 × 3 € (2,40 arrondi à l'euro supérieur)
    assert "sans-mise" not in e["ouvertes"]
    B.mettre_a_jour(e, [PARI], env, T)                          # pas encore réglé
    assert e["bankroll"] == 1000 and len(e["ouvertes"]) == 1
    regle = {**PARI, "statut": "gagne", "gain": 10.0}
    B.mettre_a_jour(e, [regle], env, T + timedelta(hours=3))
    assert e["bankroll"] == 1006 and not e["ouvertes"] and e["historique"][-1]["gain"] == 6.0
    e2 = B.mettre_a_jour(e, [], {"PUSHOVER_BANKROLL": "1500"}, T)  # chiffre changé : on repart de là
    assert e2["bankroll"] == 1500 and e2["mise_sur"] == 1500 and not e2["historique"]


def test_alerte_sans_pari_retiree_sans_gain_apres_10_jours():
    env = {"PUSHOVER_BANKROLL": "1000"}
    e = B.mettre_a_jour({}, [], env, T)
    B.noter(e, [{"id": "x", "mise_kelly": 5.0}], T)
    B.mettre_a_jour(e, [], env, T + timedelta(days=9))
    assert "x" in e["ouvertes"]
    B.mettre_a_jour(e, [], env, T + timedelta(days=11))
    assert not e["ouvertes"] and e["bankroll"] == 1000 and e["historique"][-1]["statut"] == "introuvable"


def test_perte_fait_baisser_la_mise_tout_de_suite():
    env = {"PUSHOVER_BANKROLL": "1000"}
    e = B.mettre_a_jour({}, [], env, T)
    e["ouvertes"]["a"] = {"mise": 150.0, "le": T.isoformat()}
    p = {**PARI, "cote": 3.0, "statut": "perdu", "gain": -10.0}
    e["ouvertes"] = {empreinte_prix(p): {"mise": 150.0, "le": T.isoformat()}}
    B.mettre_a_jour(e, [p], env, T)
    assert e["bankroll"] == 850 and e["mise_sur"] == 850


def test_desactivable():
    assert B.actif({}) and not B.actif({"PUSHOVER_BANKROLL_AUTO": "non"})


def test_resume_et_ligne():
    assert B.resume({}) is None and B.ligne(None) == ""
    e = {"bankroll": 950.0, "depart": 1000.0, "depart_le": "2026-11-19T18:00:00+00:00", "mise_sur": 1000.0,
         "ouvertes": {"a": {"mise": 4.0}}, "historique": [{}]}
    r = B.resume(e)
    assert r["gain"] == -50 and r["en_cours"] == 1 and r["engage"] == 4 and r["regles"] == 1
    assert B.ligne(r) == "Bankroll 950 € (−50 € depuis le 19/11) · mises sur 1 000 € · 1 en cours (4 €)"


def test_recap_ouvre_sur_la_bankroll():
    from cotes.recap_jouables import messages
    p = {"debut": "2026-11-20T18:00:00+00:00", "domicile": "A", "exterieur": "B", "pari": "A", "bookmaker": "PMU",
         "cote_actuelle": 2.0, "cote_min": 1.95, "cote": 2.0, "ecart": 0.05}
    m = messages([p], 1000.0, T, entete="Bankroll 1 012 €")
    assert m[0]["message"].startswith("<i>Bankroll 1 012 €</i><br><br>")
    assert not messages([p], 1000.0, T)[0]["message"].startswith("<i>")


def test_site_affiche_la_bankroll(tmp_path):
    import json
    import re
    from scripts import site_web
    (tmp_path / "paris.json").write_text("[]")
    (tmp_path / "bankroll.json").write_text(json.dumps({"bankroll": 1012.0, "depart": 1000.0, "mise_sur": 1000.0,
                                                        "depart_le": "2026-11-19T18:00:00+00:00", "ouvertes": {},
                                                        "historique": []}))
    html = site_web.construire(tmp_path, tmp_path / "site").read_text()
    d = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1).replace("<\\/", "</"))
    assert d["bankroll_auto"]["bankroll"] == 1012 and d["bankroll_auto"]["gain"] == 12
    assert 'id="bilan-bankroll"' in html
