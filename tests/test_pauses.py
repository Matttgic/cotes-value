import json
from datetime import datetime, timezone

from cotes import pannes, pauses, protection
from cotes.decisions import appliquer
from cotes.recommandations import doublons

T = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


def _stats(regles=250, clv_match=-1.0):
    return {"regles": regles, "note": {"mesures": {"clv_ajustee": clv_match}}}


def test_pause_seulement_si_clv_clairement_negative():
    negatives = [-0.03, -0.01, -0.02, 0.0] * 50
    assert pauses.a_mettre_en_pause(_stats(), negatives)["clv_haute"] < 0
    assert pauses.a_mettre_en_pause(_stats(regles=150), negatives) is None
    assert pauses.a_mettre_en_pause(_stats(clv_match=0.2), negatives) is None
    assert pauses.a_mettre_en_pause(_stats(), [-0.2, 0.19] * 100) is None      # moyenne négative mais incertaine


def test_mettre_a_jour_puis_filtrer(tmp_path):
    lignes = [{"id": "PIN-x", "stats": _stats()}, {"id": "Claude (rejeu)", "stats": _stats()}]
    clvs = lambda _id: [-0.02] * 120 + [-0.01] * 100
    etat = pauses.mettre_a_jour(tmp_path, lignes, {"PIN-x": "labo:PIN-x", "Claude (rejeu)": "strategie"}, clvs,
                                {"Claude (rejeu)"}, T)
    assert set(etat["liste"]) == {"PIN-x"}
    pauses.charger(tmp_path)
    try:
        avant = {"id": "a", "detecte": "2026-11-08T11:00:00+00:00"}
        apres = {"id": "b", "detecte": "2026-11-08T13:00:00+00:00"}
        paris = [avant, apres]
        assert appliquer(paris, {id(avant), id(apres)}, "labo:PIN-x") == {id(avant)}
        assert appliquer(paris, {id(avant), id(apres)}, "autre") == {id(avant), id(apres)}
        # jamais de reprise automatique
        lignes[0]["stats"] = _stats(clv_match=3.0)
        assert "PIN-x" in pauses.mettre_a_jour(tmp_path, lignes, {"PIN-x": "labo:PIN-x"}, lambda _: [], set(), T)["liste"]
    finally:
        pauses.charger({})


def test_doublons():
    a, b, c = set(range(100)), set(range(5, 100)), set(range(200, 300))
    d = doublons([{"id": "A", "ensemble": a}, {"id": "B", "ensemble": b}, {"id": "C", "ensemble": c},
                  {"id": "Fusion 2", "ensemble": a}, {"id": "base:Pinnacle", "ensemble": a, "base": True}])
    assert [(x["a"], x["b"], x["part"]) for x in d] == [("A", "B", 100.0)]


class _Rep:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_pannes_alerte_une_fois_au_seuil(tmp_path):
    envois = []
    ouvrir = lambda req, timeout: envois.append(req) or _Rep()
    env = {"PUSHOVER_APP_TOKEN": "jeton", "PUSHOVER_USER_KEY": "cle"}
    for _ in range(pannes.SEUIL + 2):
        etat = pannes.mettre_a_jour(tmp_path, {"grok_1": {"message": "KeyError: x"}}, T, env, ouvrir)
    assert len(envois) == 1 and etat["strategies"]["grok_1"]["consecutifs"] == pannes.SEUIL + 2
    pannes.mettre_a_jour(tmp_path, {}, T, env, ouvrir)               # retour à la normale : compteur remis à zéro
    assert json.loads((tmp_path / pannes.FICHIER).read_text()) == {}


def test_durees_temps_propre():
    with protection.proteger_strategies():
        protection.calculer("parent", lambda: protection.calculer("enfant", lambda: sum(range(10000))))
        d = protection.durees()
    assert d["strategies"] == 2 and {x["nom"] for x in d["plus_lentes"]} == {"parent", "enfant"}
