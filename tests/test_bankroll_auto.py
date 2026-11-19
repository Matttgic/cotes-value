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
