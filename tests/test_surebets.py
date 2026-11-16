"""Surebets entre bookmakers français (cotes/surebets.py)."""
from datetime import datetime, timedelta, timezone

import pytest

from cotes import surebets as S

T = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
ISO = T.isoformat(timespec="seconds")
DEBUT = (T + timedelta(hours=3)).isoformat(timespec="seconds")


def _l(book, mid, marche, issue, cote, ligne=None, periode="MATCH", dom="Alcaraz", ext="Sinner", lu=ISO,
       sport="tennis", debut=DEBUT):
    return {"source": book, "bookmaker": book.lower(), "match_id": f"{book.lower()}|{mid}", "sport": sport,
            "ligue": "ATP", "domicile": dom, "exterieur": ext, "debut": debut, "collecte": lu, "marche": marche,
            "periode": periode, "ligne": ligne, "issue": issue, "cote": cote, "libelle": "Vainqueur", "lien": None}


def _ref(probas: dict, inverse=False, mid=999, lu=ISO):
    """Lignes de référence d'un match français, déjà dans le sens du match français (comme indexer)."""
    return {k: {"match_id": mid, "inverse": inverse, "proba_juste": p, "collecte": lu} for k, p in probas.items()}


def _index(*matchs, nom="Pinnacle"):
    return {nom: {mid_fr: lignes for mid_fr, lignes in matchs}}


V = {("VAINQUEUR", "MATCH", None, "DOM"): 0.5, ("VAINQUEUR", "MATCH", None, "EXT"): 0.5}


def test_demi_ligne():
    assert S.demi_ligne(2.5) and S.demi_ligne(-1.5) and S.demi_ligne(0.5)
    assert not S.demi_ligne(2) and not S.demi_ligne(2.25) and not S.demi_ligne(-0.75) and not S.demi_ligne(None)


def test_repartir_ne_depasse_jamais_le_total():
    r = S.repartir([2.10, 2.10])
    assert r == {"mises": [50.0, 50.0], "mise_totale": 100.0, "gain_min": 5.0, "gain_max": 5.0}
    r = S.repartir([2.1, 3.6, 4.2])
    assert r["mise_totale"] <= 100 and r["gain_min"] > 0


def test_deux_bookmakers_vainqueur():
    fr = [_l("Winamax", 1, "VAINQUEUR", "DOM", 2.10), _l("Winamax", 1, "VAINQUEUR", "EXT", 1.70),
          _l("Betclic", 2, "VAINQUEUR", "DOM", 1.75), _l("Betclic", 2, "VAINQUEUR", "EXT", 2.10)]
    idx = _index(("winamax|1", _ref(V)), ("betclic|2", _ref(V)))
    out, journal = S.detecter(fr, idx, T)
    assert len(out) == 1
    s = out[0]
    assert s["rendement"] == pytest.approx(0.05)
    assert [(j["bookmaker"], j["issue"], j["cote"]) for j in s["jambes"]] == [("Winamax", "DOM", 2.1), ("Betclic", "EXT", 2.1)]
    assert [j["mise_100"] for j in s["jambes"]] == [50.0, 50.0] and s["gain_100"] == 5.0
    assert s["bookmakers"] == ["Betclic", "Winamax"] and s["suspect"] is None and s["verifie"] is True
    assert s["pari"] == "Vainqueur" and s["match"] == "Alcaraz – Sinner"
    assert journal["surebets"] == 1


def test_un_seul_bookmaker_n_est_pas_un_surebet():
    fr = [_l("Winamax", 1, "VAINQUEUR", "DOM", 2.10), _l("Winamax", 1, "VAINQUEUR", "EXT", 2.10)]
    out, _ = S.detecter(fr, _index(("winamax|1", _ref(V))), T)
    assert out == []


def test_match_relie_a_l_envers_est_retourne():
    """Betclic écrit Sinner – Alcaraz : son « DOM » est Sinner, l'issue EXT du sens de la référence."""
    fr = [_l("Winamax", 1, "VAINQUEUR", "DOM", 2.10),
          _l("Betclic", 2, "VAINQUEUR", "DOM", 2.10, dom="Sinner", ext="Alcaraz"),
          _l("Betclic", 2, "VAINQUEUR", "EXT", 1.70, dom="Sinner", ext="Alcaraz")]
    idx = _index(("winamax|1", _ref(V)), ("betclic|2", _ref(V, inverse=True)))
    out, _ = S.detecter(fr, idx, T)
    assert len(out) == 1
    assert [(j["bookmaker"], j["issue"], j["pari"]) for j in out[0]["jambes"]] == [
        ("Winamax", "DOM", "Alcaraz"), ("Betclic", "EXT", "Sinner")]


@pytest.mark.parametrize("modif, raison", [
    ({"collecte": (T - timedelta(minutes=12)).isoformat()}, "cote ancienne"),
    ({"debut": (T - timedelta(minutes=1)).isoformat()}, "commencé"),
    ({"cote": 2.9}, "loin de la cote juste"),
    ({"cote": 2.32}, "loin de la cote juste"),            # +16 % : au-delà de ECART_JAMBE_MAX
])
def test_garde_fous_d_une_jambe(modif, raison):
    fr = [_l("Winamax", 1, "VAINQUEUR", "DOM", 2.10), {**_l("Betclic", 2, "VAINQUEUR", "EXT", 2.10), **modif}]
    out, journal = S.detecter(fr, _index(("winamax|1", _ref(V)), ("betclic|2", _ref(V))), T)
    assert out == [] and journal["exclues"].get(raison) == 1


def test_age_des_cotes_selon_le_bookmaker_et_l_horizon():
    """Match proche : 10 min au plus. Match à plus de 6 h : PMU relu par tranches, 25 min acceptées."""
    vieux = (T - timedelta(minutes=20)).isoformat(timespec="seconds")
    loin = (T + timedelta(hours=8)).isoformat(timespec="seconds")
    for debut, attendu in ((DEBUT, 0), (loin, 1)):
        fr = [_l("Winamax", 1, "VAINQUEUR", "DOM", 2.10, debut=debut),
              _l("PMU", 2, "VAINQUEUR", "EXT", 2.10, lu=vieux, debut=debut)]
        idx = _index(("winamax|1", _ref(V)), ("pmu|2", _ref(V, lu=vieux)))
        assert len(S.detecter(fr, idx, T)[0]) == attendu


def test_sans_cote_juste_surebet_non_verifie():
    """La référence ne propose pas la ligne : le surebet reste, marqué « non vérifié »."""
    fr = [_l("Winamax", 1, "VAINQUEUR", "DOM", 2.10), _l("Betclic", 2, "VAINQUEUR", "EXT", 2.10)]
    idx = _index(("winamax|1", _ref(V)), ("betclic|2", _ref({("VAINQUEUR", "MATCH", None, "DOM"): 0.5})))
    out, _ = S.detecter(fr, idx, T)
    assert len(out) == 1 and out[0]["verifie"] is False
    assert [j["cote_juste"] for j in out[0]["jambes"]] == [2.0, None]


def test_probabilites_justes_qui_ne_couvrent_pas_tout():
    """Deux jambes vérifiées dont les probabilités justes ne font pas 1 : ce ne sont pas les mêmes résultats."""
    fr = [_l("Winamax", 1, "VAINQUEUR", "DOM", 2.10), _l("Betclic", 2, "VAINQUEUR", "EXT", 2.10)]
    faux = {("VAINQUEUR", "MATCH", None, "DOM"): 0.5, ("VAINQUEUR", "MATCH", None, "EXT"): 0.42}
    out, _ = S.detecter(fr, _index(("winamax|1", _ref(faux)), ("betclic|2", _ref(faux))), T)
    assert out == []


def test_totaux_seulement_a_demi_ligne():
    def ref(l):
        return _ref({("TOTAL", "MATCH", l, "PLUS"): 0.5, ("TOTAL", "MATCH", l, "MOINS"): 0.5})
    fr, idx = [], {}
    for ligne in (2.5, 3.0):
        fr += [_l("PMU", 1, "TOTAL", "PLUS", 2.06, ligne, sport="football"),
               _l("Unibet", 2, "TOTAL", "MOINS", 2.06, ligne, sport="football")]
    idx = {"Pinnacle": {"pmu|1": {**ref(2.5), **ref(3.0)}, "unibet|2": {**ref(2.5), **ref(3.0)}}}
    out, _ = S.detecter(fr, idx, T)
    assert [(s["ligne"], s["pari"]) for s in out] == [(2.5, "Plus/moins de 2,5 buts")]


def _un_n_deux(p_dom=0.45, p_nul=0.28, p_ext=0.27):
    return {("RESULTAT_1N2", "TEMPS_REG", None, "DOM"): p_dom, ("RESULTAT_1N2", "TEMPS_REG", None, "NUL"): p_nul,
            ("RESULTAT_1N2", "TEMPS_REG", None, "EXT"): p_ext,
            ("DOUBLE_CHANCE", "TEMPS_REG", None, "HOME_DRAW"): p_dom + p_nul,
            ("DOUBLE_CHANCE", "TEMPS_REG", None, "DRAW_AWAY"): p_nul + p_ext,
            ("DOUBLE_CHANCE", "TEMPS_REG", None, "HOME_AWAY"): p_dom + p_ext}


def test_un_n_deux_trois_bookmakers():
    fr = [_l("PMU", 1, "RESULTAT_1N2", "DOM", 2.35, periode="TEMPS_REG", sport="football", dom="Lens", ext="Lille"),
          _l("Unibet", 2, "RESULTAT_1N2", "NUL", 3.75, periode="TEMPS_REG", sport="football", dom="Lens", ext="Lille"),
          _l("Winamax", 3, "RESULTAT_1N2", "EXT", 3.90, periode="TEMPS_REG", sport="football", dom="Lens", ext="Lille")]
    idx = {"Pinnacle": {m: _ref(_un_n_deux()) for m in ("pmu|1", "unibet|2", "winamax|3")}}
    out, _ = S.detecter(fr, idx, T)
    assert len(out) == 1 and out[0]["pari"] == "1N2 (temps réglementaire)"
    assert out[0]["rendement"] == pytest.approx(1 / (1 / 2.35 + 1 / 3.75 + 1 / 3.90) - 1, abs=1e-5)
    assert len(out[0]["jambes"]) == 3


def test_double_chance_contre_l_issue_restante():
    fr = [_l("Betclic", 1, "DOUBLE_CHANCE", "HOME_DRAW", 1.45, periode="TEMPS_REG", sport="football"),
          _l("PMU", 2, "RESULTAT_1N2", "EXT", 3.70, periode="TEMPS_REG", sport="football")]
    idx = {"Pinnacle": {m: _ref(_un_n_deux()) for m in ("betclic|1", "pmu|2")}}
    out, _ = S.detecter(fr, idx, T)
    assert len(out) == 1
    assert out[0]["pari"] == "Double chance 1X + 2 (temps réglementaire)" and out[0]["marche"] == "DOUBLE_CHANCE+1N2"
    assert out[0]["rendement"] == pytest.approx(1 / (1 / 1.45 + 1 / 3.70) - 1, abs=1e-5)


def test_controle_des_intitules():
    fr = [_l("Winamax", 1, "VAINQUEUR", "DOM", 2.10), _l("Betclic", 2, "VAINQUEUR", "EXT", 2.10)]
    idx = _index(("winamax|1", _ref(V)), ("betclic|2", _ref(V)))
    out, journal = S.detecter(fr, idx, T, controle=({"groupes": {}}, {}))
    assert out == [] and journal["exclues"]["intitulé à vérifier"] == 2


def test_rendement_trop_grand_suspect():
    """Sans cote juste pour l'une des jambes, rien ne borne les cotes : au-delà de 15 %, suspect."""
    fr = [_l("Winamax", 1, "VAINQUEUR", "DOM", 2.4), _l("Betclic", 2, "VAINQUEUR", "EXT", 2.4)]
    autre = _ref({("TOTAL", "MATCH", 22.5, "PLUS"): 0.5})          # la rencontre est connue, pas ce marché
    out, _ = S.detecter(fr, _index(("winamax|1", autre), ("betclic|2", autre)), T)
    assert len(out) == 1 and out[0]["rendement"] > S.RENDEMENT_SUSPECT and out[0]["suspect"] == "rendement trop grand"


def _surebet(r=0.03, cle="a", suspect=None):
    return {"cle": cle, "id": cle, "rendement": r, "gain_100": round(100 * r, 2), "sport": "tennis", "match": "A – B",
            "pari": "Vainqueur", "debut": DEBUT, "bookmakers": ["Betclic", "Winamax"], "suspect": suspect,
            "jambes": [{"bookmaker": "Winamax", "issue": "DOM", "cote": 2.1, "cote_juste": 2.0, "mise_100": 50.0},
                       {"bookmaker": "Betclic", "issue": "EXT", "cote": 2.1, "cote_juste": 2.0, "mise_100": 50.0}]}


def test_suivi_des_episodes():
    etat = S.suivre({}, [_surebet(0.02), _surebet(0.5, "b", suspect="rendement trop grand")], T)
    assert [e["cle"] for e in etat["episodes"]] == ["a"]
    etat = S.suivre(etat, [_surebet(0.04)], T + timedelta(minutes=5))
    e = etat["episodes"][0]
    assert (e["cycles"], e["rendement_initial"], e["rendement_max"], e["rendement_dernier"]) == (2, 0.02, 0.04, 0.04)
    etat = S.suivre(etat, [], T + timedelta(minutes=10))              # disparu : l'épisode reste tel quel
    etat = S.suivre(etat, [_surebet(0.01)], T + timedelta(minutes=30))  # revenu après le délai : nouvel épisode
    assert len(etat["episodes"]) == 2 and etat["episodes"][1]["premier"] == (T + timedelta(minutes=30)).isoformat()
    vieux = S.suivre(etat, [], T + timedelta(days=S.GARDER_JOURS + 1))
    assert vieux["episodes"] == []


def test_bilan():
    etat = S.suivre({}, [_surebet(0.02), _surebet(0.008, "b")], T)
    b = S.bilan(etat["episodes"], T + timedelta(hours=1))
    assert (b["n"], b["gain_100"], b["un_pour_cent"]) == (2, 2.8, 1)
    assert b["par_bookmakers"][0]["cle"] == "Betclic + Winamax"
    assert S.bilan([], T)["n"] == 0


def test_etape_du_cycle_ecrit_surebets_json(tmp_path):
    import json
    from cotes.pipeline.analyse import surebets_du_cycle
    fr = [_l("Winamax", 1, "VAINQUEUR", "DOM", 2.10), _l("Betclic", 2, "VAINQUEUR", "EXT", 2.10)]
    idx = _index(("winamax|1", _ref(V)), ("betclic|2", _ref(V)))
    journal = {}
    r = surebets_du_cycle(tmp_path, fr, idx, None, journal, maintenant=T)
    assert r == {"surebets": 1, "suspects": 0, "verifies": 1, "familles": 1}
    doc = json.loads((tmp_path / "surebets.json").read_text())
    assert len(doc["actuels"]) == 1 and len(doc["episodes"]) == 1
    r = surebets_du_cycle(tmp_path, None, idx, None, journal, maintenant=T)       # entrée invalide : noté, pas levé
    assert "erreur" in r and journal["echecs"][0]["etape"] == "surebets"


def test_non_verifie_trop_beau_est_suspect():
    fr = [_l("Winamax", 1, "VAINQUEUR", "DOM", 2.25), _l("Betclic", 2, "VAINQUEUR", "EXT", 2.25)]
    idx = _index(("winamax|1", _ref(V)), ("betclic|2", _ref({("VAINQUEUR", "MATCH", None, "DOM"): 0.5})))
    out, _ = S.detecter(fr, idx, T)
    assert out[0]["verifie"] is False and out[0]["suspect"] == "trop beau sans cote juste pour vérifier"


def test_jambe_loin_au_dessus_de_sa_cote_juste_ecartee():
    """Cas du rejeu : une cote 23 % au-dessus de sa cote juste faisait un faux surebet « vérifié » ; elle est écartée et
    la meilleure combinaison restante (PMU) est gardée."""
    v = {("VAINQUEUR", "MATCH", None, "DOM"): 0.4, ("VAINQUEUR", "MATCH", None, "EXT"): 0.6}
    fr = [_l("Winamax", 1, "VAINQUEUR", "DOM", 2.62), _l("Betclic", 2, "VAINQUEUR", "EXT", 2.05),
          _l("PMU", 3, "VAINQUEUR", "EXT", 1.68)]
    idx = _index(("winamax|1", _ref(v)), ("betclic|2", _ref(v)), ("pmu|3", _ref(v)))
    out, journal = S.detecter(fr, idx, T)
    assert journal["exclues"]["loin de la cote juste"] == 1
    assert [j["bookmaker"] for j in out[0]["jambes"]] == ["Winamax", "PMU"] and out[0]["suspect"] is None
