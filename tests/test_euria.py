"""Page Euria : milieux en value et conversions de freebets calculés à chaque cycle (cotes/euria.py)."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from cotes import euria as E
from cotes import surebets as SB
from cotes.pipeline import reglement as PR

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


def test_tous_les_milieux_en_value_d_un_match_classes_par_esperance():
    fr = [*TOTAUX, _l("Unibet", 3, "TOTAL", "MOINS", 2.05, 212.5)]
    j = {**J_TOTAUX, _cle("TOTAL", 212.5, "MOINS"): 0.50, _cle("TOTAL", 212.5, "PLUS"): 0.50}
    index = _index(J_TOTAUX, J_TOTAUX)
    index["Pinnacle"]["unibet|3"] = _ref(j)
    out = E.milieux(*_calcul(fr, index), T)
    assert len(out) >= 2 and len({m["cle"] for m in out}) == len(out)
    assert out[0]["jambes"][1]["ligne"] == 213.5                            # 8 % de milieu et +6,6 % : le meilleur
    assert all(m["esperance_100"] > 0 for m in out)
    assert [m["esperance_100"] for m in out] == sorted((m["esperance_100"] for m in out), reverse=True)


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
    assert euria_du_cycle(tmp_path, TOTAUX, idx, None, {}, maintenant=T) == {"milieux": 1, "conversions": 2,
                                                                          "archives": 0}
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


def test_marche_mal_lu_ecarte_des_conversions():
    """Relevé du 16/11 : « Grèce U21 – Islande U21 » chez Unibet, « U21 » lu comme un handicap de +21 ; cotes
    20 / 17 / 6,7 (somme des 1/cote 0,26 : faux surebet de 287 %), sans cote juste. Rien n'est proposé."""
    kw = dict(dom="Grèce U21", ext="Islande U21", sport="football")
    fr = [_l("Unibet", 7, "HANDICAP_3", i, c, ligne=21, **kw) for i, c in (("DOM", 6.7), ("NUL", 17.0), ("EXT", 20.0))]
    idx = {"Pinnacle": {"unibet|7": _ref({_cle("RESULTAT_1N2", None, "DOM"): 0.5}, mid=99)}}
    assert E.conversions(*_calcul(fr, idx), T) == {}
    # probabilités justes qui ne font pas 1 (48 + 28 + 40 %) : marché incohérent, écarté aussi
    assert not E.marche_credible([{"cote": 2.0, "proba_juste": 0.48}, {"cote": 3.5, "proba_juste": 0.28},
                                  {"cote": 2.6, "proba_juste": 0.40}])
    assert E.marche_credible([{"cote": 1.95, "proba_juste": 0.48}, {"cote": 3.4, "proba_juste": 0.28},
                              {"cote": 3.9, "proba_juste": 0.24}])


def test_milieux_regles_pour_le_bilan():
    """Après le match : chaque pari du milieu est réglé aux cotes de la première lecture, le bilan compare le résultat
    à l'espérance. 212 points : milieu tombé ; 220 : hors du milieu."""
    calcul = {"milieux": E.milieux(*_calcul(TOTAUX, _index(J_TOTAUX, J_TOTAUX)), T), "conversions": {}}
    eps = E.suivre({}, calcul["milieux"], T)
    assert E.a_regler(eps, T) == []                                                    # pas encore commencé
    apres = T + timedelta(hours=6)
    (p,) = E.a_regler(eps, apres)
    assert (p["domicile"], p["exterieur"], p["sport"], p["statut"]) == ("Lakers", "Celtics", "basket", "en_cours")
    e = eps[0]
    assert PR.regler_episode(e, {"score": (110, 102), "periodes": [], "libelles": []})
    assert e["tombe"] and e["statuts"] == ["gagne", "gagne"] and e["resultat_100"] == pytest.approx(97.47, abs=0.02)
    assert E.a_regler(eps, apres) == []
    autre = {**e, "id": "b", "cle": "b"}
    for k in ("resultat_100", "tombe", "statuts", "score"):
        autre.pop(k)
    assert PR.regler_episode(autre, {"score": (120, 100), "periodes": [], "libelles": []})
    assert not autre["tombe"] and autre["resultat_100"] == pytest.approx(-1.27, abs=0.02)
    b = E.bilan_regle([e, autre], apres)
    assert b["n"] == 2 and b["tombes"] == 1 and b["tombes_attendus"] == pytest.approx(0.16)
    assert b["resultat"] == pytest.approx(96.2, abs=0.05) and b["esperance"] == pytest.approx(13.26, abs=0.02)
    d = E.publie(E.publier(calcul, [e, autre], apres), None, None, apres)
    assert d["bilan_regle"]["tout"]["n"] == 2 and len(d["regles"]) == 2 and d["regles"][0]["score"] == [110, 102]


def test_stats_tous_les_milieux_regles(tmp_path):
    """euria-stats.json : une ligne par milieu réglé (plus récent d'abord), colonnes nommées, largeur du milieu,
    avance sur le match, référence ; les milieux pas encore réglés n'y sont pas."""
    calcul = {"milieux": E.milieux(*_calcul(TOTAUX, _index(J_TOTAUX, J_TOTAUX)), T), "conversions": {}}
    (e,) = E.suivre({}, calcul["milieux"], T)
    vide = E.stats([e])
    assert vide == {"colonnes": list(E.STATS_COLONNES), "lignes": []}
    assert PR.regler_episode(e, {"score": (110, 102), "periodes": [], "libelles": []})
    s = E.stats([e, {"premier": "x"}])
    (ligne,) = s["lignes"]
    x = dict(zip(s["colonnes"], ligne))
    assert x["sport"] == "basket" and x["marche"] == e["marche"] and x["tombe"] is True and x["match"] == e["match"]
    assert x["largeur"] == e["a"] - e["de"] + 1 and x["resultat_100"] == e["resultat_100"]
    assert x["esperance"] == e["esperance_initiale"] and x["p_milieu"] == e["p_milieu_initiale"]
    assert x["reference"] == e["reference"] and x["avance_h"] > 0 and x["duree_min"] == 0
    from cotes.site.construction import construire
    (tmp_path / "euria.json").write_text(json.dumps(E.publier(calcul, [e], T)))
    construire(tmp_path, tmp_path / "site", T + timedelta(hours=6))
    d = json.loads((tmp_path / "site" / "euria-stats.json").read_text())
    assert d["colonnes"] == list(E.STATS_COLONNES) and len(d["lignes"]) == 1


def test_ancien_milieu_sans_issues_pas_reglable():
    calcul = {"milieux": E.milieux(*_calcul(TOTAUX, _index(J_TOTAUX, J_TOTAUX)), T)}
    e = E.suivre({}, calcul["milieux"], T)[0]
    e.pop("issues")
    assert E.a_regler([e], T + timedelta(hours=6)) == []


def test_reglement_du_cycle_regle_les_milieux(tmp_path):
    """Étape règlement : le score validé par deux sources règle le milieu et réécrit euria.json."""
    from cotes import resultats as RES
    calcul = {"milieux": E.milieux(*_calcul(TOTAUX, _index(J_TOTAUX, J_TOTAUX)), T), "conversions": {}}
    doc = E.publier(calcul, E.suivre({}, calcul["milieux"], T), T)
    apres = T + timedelta(hours=6)
    milieux = E.a_regler(doc["episodes_milieux"], apres)
    enr = [{"source": s, "sport": "basket", "domicile": "Lakers", "exterieur": "Celtics", "debut": DEBUT,
            "score": (110, 102), "periodes": [], "libelles": [], "corners": None} for s in ("espn", "livescore")]
    assert RES.consensus(milieux[0], enr, apres)
    assert PR._regler_milieux(tmp_path, doc, milieux, enr, apres) == {"a_regler": 1, "regles": 1}
    lu = json.loads((tmp_path / "euria.json").read_text())
    assert lu["episodes_milieux"][0]["tombe"] is True


AUTRE = {_cle("VAINQUEUR", None, "DOM"): 0.5}               # match relié à Pinnacle, sans la ligne cherchée


def test_chance_estimee_par_poisson_quand_pinnacle_n_a_qu_une_ligne():
    """Football : Pinnacle n'a que 2,5 buts (Plus 55 %). Moins de 3,5 estimé par Poisson ajusté sur 2,5."""
    fr = [_l("Betclic", 1, "TOTAL", "PLUS", 1.90, 2.5, sport="football"),
          _l("PMU", 2, "TOTAL", "MOINS", 1.45, 3.5, sport="football")]
    j = {_cle("TOTAL", 2.5, "PLUS"): 0.55, _cle("TOTAL", 2.5, "MOINS"): 0.45}
    index = {"Pinnacle": {"betclic|1": _ref(j), "pmu|2": _ref(AUTRE)}}
    m = E.milieux(*_calcul(fr, index), T)[0]
    lam = E._lambda(2.5, 0.55)
    p2 = 1 - E._poisson_queue(lam, 3.5)
    assert m["estime"] is True and m["jambes"][1]["estimee"] is True and "estimee" not in m["jambes"][0]
    assert m["p_milieu"] == pytest.approx(0.55 + p2 - 1, abs=1e-4)
    assert (m["de"], m["a"]) == (3, 3)
    loin = [fr[0], _l("PMU", 2, "TOTAL", "MOINS", 1.10, 5.5, sport="football")]     # 3 buts de la ligne connue
    assert E.milieux(*_calcul(loin, index), T) == []


def test_chance_estimee_par_loi_normale_sur_deux_lignes_connues():
    """Basket : Pinnacle a 210,5 et 213,5 ; Moins de 214,5 (sans Pinnacle) estimé par la loi normale ajustée."""
    fr = [*TOTAUX[:3], _l("Betclic", 2, "TOTAL", "MOINS", 1.80, 213.5), _l("Unibet", 3, "TOTAL", "MOINS", 1.95, 214.5)]
    index = _index(J_TOTAUX, J_TOTAUX)
    index["Pinnacle"]["unibet|3"] = _ref(AUTRE)
    out = E.milieux(*_calcul(fr, index), T)
    assert out and out[0]["jambes"][1]["ligne"] == 214.5 and out[0]["estime"] is True
    p = out[0]["jambes"][1]["proba_juste"]
    assert 0.53 < p < 0.62                                   # entre P(Moins 213,5) = 53 % et un peu plus
    seul = {k: v for k, v in J_TOTAUX.items() if k[2] == 210.5}                  # une seule ligne : pas d'estimation
    assert all(not m.get("estime") for m in E.milieux(*_calcul(fr, _index(seul, seul)), T))


def test_cote_loin_de_sa_cote_estimee_ecartee():
    fr = [_l("Betclic", 1, "TOTAL", "PLUS", 1.90, 2.5, sport="football"),
          _l("PMU", 2, "TOTAL", "MOINS", 3.00, 3.5, sport="football")]               # ~1,5 attendu : mal lue
    j = {_cle("TOTAL", 2.5, "PLUS"): 0.55, _cle("TOTAL", 2.5, "MOINS"): 0.45}
    index = {"Pinnacle": {"betclic|1": _ref(j), "pmu|2": _ref(AUTRE)}}
    assert E.milieux(*_calcul(fr, index), T) == []


def test_milieux_regles_archives_jamais_perdus(tmp_path):
    """25/11 : les réglés restaient parmi les 2000 épisodes de euria.json et disparaissaient du bilan et des Stats quand
    de nouveaux milieux arrivaient. Ils passent dans euria_regles.json, sans plafond ; le plafond ne touche plus que
    les milieux pas encore réglés, ceux du match le plus ancien d'abord."""
    from cotes.pipeline.analyse import euria_du_cycle
    from cotes.site.construction import construire
    idx = _index(J_TOTAUX, J_TOTAUX)
    euria_du_cycle(tmp_path, TOTAUX, idx, None, {}, maintenant=T)
    doc = json.loads((tmp_path / "euria.json").read_text())
    (e,) = doc["episodes_milieux"]
    assert PR.regler_episode(e, {"score": (110, 102), "periodes": [], "libelles": []})
    (tmp_path / "euria.json").write_text(json.dumps(doc))
    apres = T + timedelta(hours=6)
    assert euria_du_cycle(tmp_path, [], idx, None, {}, maintenant=apres)["archives"] == 1
    assert json.loads((tmp_path / "euria.json").read_text())["episodes_milieux"] == []
    arch = json.loads((tmp_path / E.ARCHIVE).read_text())
    assert [x["cle"] for x in arch["episodes"]] == [e["cle"]] and arch["episodes"][0]["tombe"] is True
    assert euria_du_cycle(tmp_path, [], idx, None, {}, maintenant=apres)["archives"] == 0     # une fois par clé
    construire(tmp_path, tmp_path / "site", apres)
    site = json.loads((tmp_path / "site" / "euria.json").read_text())
    assert site["bilan_regle"]["tout"]["n"] == 1 and len(site["regles"]) == 1
    assert site["bilan_milieux"]["7"]["n"] == 1
    assert len(json.loads((tmp_path / "site" / "euria-stats.json").read_text())["lignes"]) == 1
    # réglé pas encore archivé : gardé dans euria.json et compté une seule fois
    assert len(E.regles_connus({"episodes_milieux": [e]}, arch)) == 1
    assert E.suivre({"episodes_milieux": [e]}, [], apres) == [e]
    # archive : matchs de plus de 60 jours retirés
    vieux, n = E.archiver(arch, [], T + timedelta(days=E.GARDER_JOURS + 1))
    assert vieux["episodes"] == [] and n == 0


def test_plafond_sur_les_seuls_milieux_pas_encore_regles(monkeypatch):
    monkeypatch.setattr(E, "EPISODES_MAX", 2)
    def ep(cle, debut, regle=False):
        x = {"cle": cle, "premier": ISO, "dernier": ISO, "debut": debut}
        return {**x, "resultat_100": 1.0} if regle else x
    eps = [ep("r", "2026-01-01T00:00:00+00:00", True), ep("a", "2026-01-02T00:00:00+00:00"),
           ep("b", "2026-01-04T00:00:00+00:00"), ep("c", "2026-01-03T00:00:00+00:00")]
    garde = E.suivre({"episodes_milieux": eps}, [], T)
    assert sorted(x["cle"] for x in garde) == ["b", "c", "r"]           # « a » : match le plus ancien
    assert sorted(x["cle"] for x in E.suivre({"episodes_milieux": eps}, [], T, {"r"})) == ["b", "c"]
