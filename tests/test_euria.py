"""Page Euria : milieux en value et conversions de freebets calculés à chaque cycle (cotes/euria.py)."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from cotes import euria as E
from cotes import surebets as SB

T = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
ISO = T.isoformat(timespec="seconds")
DEBUT = (T + timedelta(hours=3)).isoformat(timespec="seconds")


def _l(book, mid, marche, issue, cote, ligne=None, dom="Lakers", ext="Celtics", sport="basket"):
    return {"source": book, "bookmaker": book.lower(), "match_id": f"{book.lower()}|{mid}", "sport": sport,
            "ligue": "NBA", "domicile": dom, "exterieur": ext, "debut": DEBUT, "collecte": ISO, "marche": marche,
            "periode": "MATCH", "ligne": ligne, "issue": issue, "cote": cote, "libelle": marche, "lien": None}


def _ref(probas: dict, inverse=False, mid=88):
    return {k: {"match_id": mid, "inverse": inverse, "proba_juste": p, "collecte": ISO} for k, p in probas.items()}


def _cle(marche, ligne, issue):
    return (marche, "MATCH", ligne, issue)


# Totaux : Plus de 210,5 chez Winamax, Moins de 213,5 chez Betclic. Pinnacle : P(Plus 210,5) = 55 %, P(Plus 213,5) = 47 %.
TOTAUX = [_l("Winamax", 1, "TOTAL", "PLUS", 1.95, 210.5), _l("Winamax", 1, "TOTAL", "MOINS", 1.80, 210.5),
          _l("Betclic", 2, "TOTAL", "PLUS", 1.80, 213.5), _l("Betclic", 2, "TOTAL", "MOINS", 2.00, 213.5)]
J_TOTAUX = {_cle("TOTAL", 210.5, "PLUS"): 0.55, _cle("TOTAL", 210.5, "MOINS"): 0.45,
            _cle("TOTAL", 213.5, "PLUS"): 0.47, _cle("TOTAL", 213.5, "MOINS"): 0.53}
# Handicaps : Lakers −3,5 chez Winamax ; Betclic écrit le match à l'envers (Celtics +6,5 = Lakers −6,5 côté extérieur).
HANDICAPS = [_l("Winamax", 1, "HANDICAP", "DOM", 2.10, -3.5),
             _l("Betclic", 2, "HANDICAP", "DOM", 1.95, 6.5, dom="Celtics", ext="Lakers")]


def _index(lignes_winamax: dict, lignes_betclic: dict, betclic_inverse=False):
    return {"Pinnacle": {"winamax|1": _ref(lignes_winamax), "betclic|2": _ref(lignes_betclic, inverse=betclic_inverse)}}


def _calcul(fr, index):
    familles, matchs, _ = SB.candidates(fr, index, T)
    return familles, matchs


def test_milieu_sur_les_totaux():
    """Plus de 210,5 à 1,95 et Moins de 213,5 à 2,00 : milieu de 211 à 213 points, 8 % de chances d'après Pinnacle."""
    out = E.milieux(*_calcul(TOTAUX, _index(J_TOTAUX, J_TOTAUX)), T)
    assert len(out) == 1
    m = out[0]
    assert [(j["bookmaker"], j["issue"], j["ligne"], j["cote"]) for j in m["jambes"]] == [
        ("Winamax", "PLUS", 210.5, 1.95), ("Betclic", "MOINS", 213.5, 2.0)]
    assert (m["de"], m["a"], m["ecart"], m["unite"]) == (211, 213, False, "points")
    assert m["p_milieu"] == pytest.approx(0.08) and m["p_dessous"] == pytest.approx(0.45)
    m1 = 100 * 2.0 / 3.95
    assert m["mises_100"] == [pytest.approx(m1, abs=0.01), pytest.approx(100 - m1, abs=0.01)]
    assert m["esperance_100"] == pytest.approx(m1 * (1.95 * 0.55 - 1) + (100 - m1) * (2.0 * 0.53 - 1), abs=0.01)
    assert m["milieu_100"] == pytest.approx(97.47, abs=0.01) and m["hors_100"] == pytest.approx(-1.27, abs=0.01)
    assert m["match"] == "Lakers – Celtics" and m["reference"] == "Pinnacle"


def test_milieu_sur_les_handicaps_et_match_ecrit_a_l_envers():
    """Lakers −3,5 (Winamax) et Celtics +6,5 (Betclic, match écrit à l'envers) : les deux gagnent si les Lakers
    gagnent de 4 à 6 points."""
    jw = {_cle("HANDICAP", -3.5, "DOM"): 0.50}
    jb = {_cle("HANDICAP", 6.5, "DOM"): 0.58}                   # dans le sens de Betclic : Celtics +6,5
    m = E.milieux(*_calcul(HANDICAPS, _index(jw, jb, betclic_inverse=True)), T)[0]
    assert [(j["bookmaker"], j["issue"], j["ligne"]) for j in m["jambes"]] == [("Winamax", "DOM", -3.5),
                                                                               ("Betclic", "EXT", -6.5)]
    assert (m["de"], m["a"], m["ecart"], m["bornes"]) == (4, 6, True, [3.5, 6.5])
    assert m["p_milieu"] == pytest.approx(0.08) and m["esperance_100"] > 0


def test_pas_de_milieu_sans_value_ni_cote_juste():
    perdant = [{**l, "cote": round(l["cote"] - 0.15, 2)} for l in TOTAUX]   # deux jambes sous leur cote juste
    assert E.milieux(*_calcul(perdant, _index(J_TOTAUX, J_TOTAUX)), T) == []
    sans = {k: v for k, v in J_TOTAUX.items() if k[2] != 213.5}
    assert E.milieux(*_calcul(TOTAUX, _index(sans, sans)), T) == []


def test_un_seul_milieu_par_match_et_marche():
    fr = [*TOTAUX, _l("Unibet", 3, "TOTAL", "MOINS", 2.05, 212.5)]
    j = {**J_TOTAUX, _cle("TOTAL", 212.5, "MOINS"): 0.50, _cle("TOTAL", 212.5, "PLUS"): 0.50}
    index = _index(J_TOTAUX, J_TOTAUX)
    index["Pinnacle"]["unibet|3"] = _ref(j)
    out = E.milieux(*_calcul(fr, index), T)
    assert len(out) == 1 and out[0]["jambes"][1]["ligne"] == 213.5        # 8 % de milieu et +6,6 % : le meilleur


# 1N2 de football : Pinnacle 48 / 28 / 24 %. Unibet écrit Lille – Lens (à l'envers).
N2 = "RESULTAT_1N2"
FOOT = [_l("Winamax", 1, N2, "DOM", 1.95, dom="Lens", ext="Lille", sport="football"),
        _l("Winamax", 1, N2, "NUL", 3.40, dom="Lens", ext="Lille", sport="football"),
        _l("Winamax", 1, N2, "EXT", 3.90, dom="Lens", ext="Lille", sport="football"),
        _l("Betclic", 2, N2, "DOM", 1.98, dom="Lens", ext="Lille", sport="football"),
        _l("Betclic", 2, N2, "NUL", 3.60, dom="Lens", ext="Lille", sport="football"),
        _l("Betclic", 2, N2, "EXT", 4.10, dom="Lens", ext="Lille", sport="football"),
        _l("Betclic", 2, "DOUBLE_CHANCE", "DRAW_AWAY", 1.85, dom="Lens", ext="Lille", sport="football"),
        _l("Unibet", 3, N2, "DOM", 4.50, dom="Lille", ext="Lens", sport="football")]


def _index_foot():
    sens = {_cle(N2, None, "DOM"): 0.48, _cle(N2, None, "NUL"): 0.28, _cle(N2, None, "EXT"): 0.24,
            _cle("DOUBLE_CHANCE", None, "DRAW_AWAY"): 0.52}
    envers = {_cle(N2, None, "DOM"): 0.24, _cle(N2, None, "NUL"): 0.28, _cle(N2, None, "EXT"): 0.48}
    return {"Pinnacle": {"winamax|1": _ref(sens), "betclic|2": _ref(sens), "unibet|3": _ref(envers, inverse=True)}}


def test_conversions_par_bookmaker():
    """Freebet Winamax : le nul à 3,40, couvert par Lens à 1,98 et Lille à 4,50 : 2,40 × (1 − 0,727) = 65 %."""
    conv = E.conversions(*_calcul(FOOT, _index_foot()), T)
    assert sorted(conv) == ["Betclic", "Unibet", "Winamax"]
    w = conv["Winamax"]
    assert len(w) == 1                                           # un pari par match
    assert [(j["bookmaker"], j["issue"], j["cote"]) for j in w[0]["jambes"]] == [
        ("Winamax", "NUL", 3.4), ("Betclic", "DOM", 1.98), ("Unibet", "EXT", 4.5)]
    assert w[0]["conversion"] == pytest.approx(2.4 * (1 - 1 / 1.98 - 1 / 4.5), abs=1e-4)
    assert w[0]["rembourse"] == pytest.approx(2.4 - 2.65 * (1 / 1.98 + 1 / 4.5), abs=1e-4)
    u = conv["Unibet"][0]
    assert u["jambes"][0]["issue"] == "EXT" and u["conversion"] == pytest.approx(3.5 * (1 - 1 / 1.98 - 1 / 3.6), abs=1e-4)
    assert u["pari"] == "1N2" and u["match"] == "Lens – Lille"


def test_conversion_par_la_double_chance_quand_elle_paie_mieux():
    """Freebet Winamax sur Lens : « nul ou Lille » à 2,20 (1/2,20 = 0,455) couvre mieux que nul + Lille (0,522)."""
    fr = [l for l in FOOT if l["source"] == "Betclic" or (l["source"] == "Winamax" and l["issue"] == "DOM")]
    fr = [l if l["marche"] != "DOUBLE_CHANCE" else {**l, "cote": 2.20} for l in fr]
    idx = _index_foot()
    idx["Pinnacle"]["betclic|2"][_cle("DOUBLE_CHANCE", None, "DRAW_AWAY")]["proba_juste"] = 0.50
    w = E.conversions(*_calcul(fr, idx), T)["Winamax"][0]
    assert [(j["issue"], j["cote"]) for j in w["jambes"]] == [("DOM", 1.95), ("DRAW_AWAY", 2.2)]


def test_cycle_suivi_alerte_et_message(tmp_path):
    from cotes.alertes import promos
    from cotes.alertes.pushover import message_pushover
    from cotes.pipeline.analyse import euria_du_cycle
    idx = _index(J_TOTAUX, J_TOTAUX)
    assert euria_du_cycle(tmp_path, TOTAUX, idx, None, {}, maintenant=T) == {"milieux": 1, "conversions": 2}
    euria_du_cycle(tmp_path, TOTAUX, idx, None, {}, maintenant=T + timedelta(minutes=5))
    doc = json.loads((tmp_path / "euria.json").read_text())
    assert doc["episodes_milieux"][0]["cycles"] == 2 and len(doc["milieux"]) == 1
    maintenant = T + timedelta(minutes=6)
    a = promos.alertes(tmp_path, {}, {"milieux"}, maintenant)
    assert [x["type"] for x in a] == ["milieu"]
    assert promos.alertes(tmp_path, {a[0]["id"]: ISO}, {"milieux"}, maintenant) == []
    assert promos.alertes(tmp_path, {}, {"surebets"}, maintenant) == []
    assert promos.alertes_milieux(doc, {}, maintenant, seuil=0.07) == []          # espérance 6,6 % sous 7 %
    m = message_pushover(a[0], env={"PUSHOVER_BANKROLL": "1000"}, maintenant=maintenant)
    assert m["title"].startswith("Milieu +6,6 % · Lakers – Celtics")
    assert "Winamax : " in m["message"] and "→ 51 €" in m["message"] and "Milieu (211 à 213 points)" in m["message"]
    assert "Chance du milieu 8,0 %" in m["message"]
    journal = {}
    assert "erreur" in euria_du_cycle(tmp_path, None, idx, None, journal, maintenant=T)
    assert journal["echecs"][0]["etape"] == "euria"


def test_bilan_et_fichier_publie():
    calcul = E.calculer(TOTAUX, _index(J_TOTAUX, J_TOTAUX), T)
    eps = E.suivre({}, calcul["milieux"], T)
    doc = E.publier(calcul, eps, T)
    d = E.publie(doc, {"actuels": [{"suspect": None}, {"suspect": "x"}]}, {"couverts": []}, T + timedelta(minutes=5))
    assert len(d["milieux"]) == 1 and d["autres"] == {"surebets": 1, "boosts_couverts": 0}
    assert d["bilan_milieux"]["7"]["n"] == 1 and d["bilan_milieux"]["7"]["esperance"] == pytest.approx(6.63, abs=0.01)
    assert set(d["conversions"]) == {"Betclic", "Winamax"}
    assert E.publie(doc, None, None, T + timedelta(hours=4))["milieux"] == []           # match commencé
    assert E.publie(None, None, None, T)["milieux"] == []


def test_le_site_publie_euria_json(tmp_path):
    from cotes.site.construction import construire
    calcul = E.calculer(TOTAUX, _index(J_TOTAUX, J_TOTAUX), T)
    (tmp_path / "euria.json").write_text(json.dumps(E.publier(calcul, E.suivre({}, calcul["milieux"], T), T)))
    construire(tmp_path, tmp_path / "site", T + timedelta(minutes=5))
    d = json.loads((tmp_path / "site" / "euria.json").read_text())
    assert len(d["milieux"]) == 1 and set(d["conversions"]) == {"Betclic", "Winamax"} and d["maj"] == ISO
