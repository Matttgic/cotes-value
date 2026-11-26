import json
from datetime import datetime, timedelta, timezone

from cotes import pauses, protection
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
    assert set(etat["liste"]) == {"PIN-x"} | {r["id"] for r in pauses.RETIREES.values()}
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
    for _ in range(protection.SEUIL_PANNES + 2):
        etat = protection.mettre_a_jour_pannes(tmp_path, {"grok_1": {"message": "KeyError: x"}}, T, env, ouvrir)
    assert len(envois) == 1 and etat["strategies"]["grok_1"]["consecutifs"] == protection.SEUIL_PANNES + 2
    protection.mettre_a_jour_pannes(tmp_path, {}, T, env, ouvrir)               # retour à la normale : compteur remis à zéro
    assert json.loads((tmp_path / protection.FICHIER_PANNES).read_text()) == {}


def test_durees_temps_propre():
    with protection.proteger_strategies():
        protection.calculer("parent", lambda: protection.calculer("enfant", lambda: sum(range(10000))))
        d = protection.durees()
    assert d["strategies"] == 2 and {x["nom"] for x in d["plus_lentes"]} == {"parent", "enfant"}


def test_strategies_retirees_sans_nouveaux_paris_et_hors_des_notifs():
    pauses.charger({})
    try:
        for cle, r in pauses.RETIREES.items():
            depuis = datetime.fromisoformat(pauses.depuis_retrait(cle))
            avant = {"id": "a", "detecte": (depuis - timedelta(hours=1)).isoformat()}
            apres = {"id": "b", "detecte": (depuis + timedelta(hours=1)).isoformat()}
            attendu = {id(avant), id(apres)} if r.get("votes") else {id(avant)}   # bases : votes de convergence gardés
            assert appliquer([avant, apres], {id(avant), id(apres)}, cle) == attendu, cle
        liste = pauses.mettre_a_jour("/nexiste/pas", [], {}, lambda _: [], set(), T)["liste"]
        assert all(liste[r["id"]]["retiree"] for r in pauses.RETIREES.values())
        assert liste["Qwen"]["depuis"] == pauses.RETIREES_27_11 and liste["Claude Défi 2 · Handicaps"]["depuis"] == \
            pauses.RETIREES_DEPUIS
    finally:
        pauses.charger({})


def test_retirees_identifiees_par_le_registre_et_jamais_membres_d_une_fusion():
    from cotes.strategie_recommandee import MEMBRES
    from cotes.strategies import registre
    lignes = {s.cle: s.ligne for s in registre.toutes()}
    assert all(lignes[cle] == r["id"] for cle, r in pauses.RETIREES.items())     # même nom que la ligne du site
    assert not {r["id"] for r in pauses.RETIREES.values()} & set(MEMBRES)
    assert all(r.get("votes") is None or cle in {"strategie", "jules", "jules_v2", "gemini"}
               for cle, r in pauses.RETIREES.items())


def test_retiree_jamais_recommandee():
    from cotes.recommandations import recommander
    stats = {"preuve": {"clv_ic": [2.0, 4.0]}, "regles": 200}
    lignes = [{"id": "x", "stats": stats, "ensemble": {1}, "retiree": True}]
    import cotes.recommandations as reco
    avant = reco.raisons_refus
    reco.raisons_refus = lambda _s: []
    try:
        assert recommander(lignes)["liste"] == []
        assert recommander([{**lignes[0], "retiree": False}])["liste"][0]["id"] == "x"
    finally:
        reco.raisons_refus = avant
