from datetime import datetime, timedelta, timezone

from cotes import surveillance as s

T0 = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
PANNE = {"winamax_direct": {"ok": False, "degrade": True, "erreurs": ["sport:1 : réseau", "lecture vide"]}}
BUDGET = {"betclic_direct": {"ok": True, "degrade": True, "erreurs": ["budget"]}}


def test_refus_403_de_pinnacle_avec_reprise_est_benin():
    assert s.problemes({"pinnacle": {"ok": True, "degrade": True, "erreurs": ["HTTP 403", "HTTP 403"]}}) == {}


def test_budget_et_resultats_ne_sont_pas_des_problemes():
    assert s.problemes({**BUDGET, "resultats_espn_tennis": {"ok": False}, "smarkets": {"ok": True, "degrade": True, "erreurs": ["x"]}}) == {}


def test_une_panne_isolee_ne_previent_pas_la_deuxieme_oui_puis_retablie():
    etat, msgs = s.evaluer(PANNE, {}, T0)
    assert msgs == []
    etat, msgs = s.evaluer(PANNE, etat, T0 + timedelta(minutes=5))
    assert [m[0] for m in msgs] == ["Winamax en panne"] and msgs[0][2] == "high"
    etat, msgs = s.evaluer(PANNE, etat, T0 + timedelta(minutes=10))
    assert msgs == []                                            # pas de répétition
    etat, msgs = s.evaluer(PANNE, etat, T0 + timedelta(hours=3, minutes=6))
    assert len(msgs) == 1                                        # rappel
    etat, msgs = s.evaluer({"winamax_direct": {"ok": True}}, etat, T0 + timedelta(hours=4))
    assert [m[0] for m in msgs] == ["Winamax rétablie"] and etat == {}


def test_panne_qui_se_resout_avant_le_seuil_reste_silencieuse():
    etat, _ = s.evaluer(PANNE, {}, T0)
    etat, msgs = s.evaluer({"winamax_direct": {"ok": True}}, etat, T0 + timedelta(minutes=5))
    assert msgs == [] and etat == {}


def test_poster_utilise_ntfy_et_ne_leve_pas(tmp_path):
    vus = []

    class R:
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def ouvrir(req, timeout):
        vus.append(req)
        return R()
    env = {"ALERTE_WEBHOOK_URL": "https://ntfy.sh/x"}
    r = s.surveiller(tmp_path, PANNE, env, ouvrir, T0)
    r = s.surveiller(tmp_path, PANNE, env, ouvrir, T0 + timedelta(minutes=5))
    assert r["envoyes"] == 1 and vus[0].get_header("Priority") == "high"
    assert s.surveiller(tmp_path, PANNE, {}, ouvrir, T0)["envoyes"] == 0
