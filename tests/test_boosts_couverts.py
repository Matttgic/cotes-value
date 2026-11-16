"""Boosts couverts : un boost joué à sa mise maximale et couvert sur les autres issues (cotes/boosts.py)."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from cotes import boosts as B

T = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
ISO = T.isoformat(timespec="seconds")
DEBUT = (T + timedelta(hours=3)).isoformat(timespec="seconds")
N2 = "RESULTAT_1N2"


def _l(book, mid, marche, issue, cote, dom="Lens", ext="Lille", ligne=None):
    return {"source": book, "bookmaker": book.lower(), "match_id": f"{book.lower()}|{mid}", "sport": "football",
            "ligue": "Ligue 1", "domicile": dom, "exterieur": ext, "debut": DEBUT, "collecte": ISO, "marche": marche,
            "periode": "MATCH", "ligne": ligne, "issue": issue, "cote": cote, "libelle": "1N2", "lien": None}


# Pinnacle écrit le match Lens – Lille ; Unibet l'écrit Lille – Lens (relié à l'envers).
JUSTES = {"DOM": 0.48, "NUL": 0.28, "EXT": 0.24}
FR = [_l("Winamax", 1, N2, "DOM", 1.95), _l("Winamax", 1, N2, "NUL", 3.40), _l("Winamax", 1, N2, "EXT", 3.90),
      _l("Betclic", 2, N2, "DOM", 1.98), _l("Betclic", 2, N2, "NUL", 3.60), _l("Betclic", 2, N2, "EXT", 4.10),
      _l("Betclic", 2, "DOUBLE_CHANCE", "DRAW_AWAY", 1.85),
      _l("Unibet", 3, N2, "DOM", 4.50, dom="Lille", ext="Lens")]


def _ref(probas: dict, inverse=False):
    return {k: {"match_id": 77, "inverse": inverse, "proba_juste": p, "collecte": ISO} for k, p in probas.items()}


def _index(dom=JUSTES["DOM"]):
    sens = {(N2, "MATCH", None, i): p for i, p in {**JUSTES, "DOM": dom}.items()}
    sens[("DOUBLE_CHANCE", "MATCH", None, "DRAW_AWAY")] = JUSTES["NUL"] + JUSTES["EXT"]
    envers = {(N2, "MATCH", None, "DOM"): JUSTES["EXT"], (N2, "MATCH", None, "NUL"): JUSTES["NUL"],
              (N2, "MATCH", None, "EXT"): dom}
    return {"Pinnacle": {"winamax|1": _ref(sens), "betclic|2": _ref(sens), "unibet|3": _ref(envers, inverse=True)}}


def _boost(ident, book, libelle, cote, avant, mise=10.0, dom="Lens", ext="Lille"):
    return {"id": ident, "bookmaker": book, "domicile": dom, "exterieur": ext, "debut": DEBUT, "libelle": libelle,
            "cote": cote, "cote_avant": avant, "mise_max": mise, "lu": ISO, "lien": f"https://{book.lower()}.fr/m"}


LENS = _boost("winamax|1|1", "Winamax", "Lens gagne le match", 2.30, 1.95)
LILLE = _boost("unibet|9|9", "Unibet", "Lille gagne le match", 5.50, 4.50, mise=5.0, dom="Lille", ext="Lens")


def _couverts(boosts, index=None, fr=FR):
    index = _index() if index is None else index
    return B.couverts(B.evaluer(boosts, fr, index, T), fr, index, T)


def test_mises_au_plafond_du_boost():
    r = B.mises_couverture(2.30, 10, [3.60, 4.50])
    assert r == {"mises": [10.0, 6.4, 5.1], "mise_totale": 21.5, "gain_min": 1.45, "gain_max": 1.54}


@pytest.mark.parametrize("marche, ligne, issue, attendu", [
    (N2, None, "DOM", [[(N2, None, "NUL"), (N2, None, "EXT")], [("DOUBLE_CHANCE", None, "DRAW_AWAY")]]),
    ("VAINQUEUR", None, "EXT", [[("VAINQUEUR", None, "DOM")]]),
    ("TOTAL", 2.5, "PLUS", [[("TOTAL", 2.5, "MOINS")]]),
    ("JEUX_HANDICAP", -5.5, "DOM", [[("JEUX_HANDICAP", -5.5, "EXT")]]),
    ("DOUBLE_CHANCE", None, "HOME_DRAW", [[(N2, None, "EXT")]]),
    ("BOTH_TEAMS_TO_SCORE", None, "YES", [[("BOTH_TEAMS_TO_SCORE", None, "NO")]]),
    ("TOTAL", 2.0, "PLUS", []), ("CORRECT_SCORE", None, "1-0", []), ("HALF_TIME_FULL_TIME", None, "DOM/DOM", []),
    ("JOUEUR:Goals", 0.5, "PLUS", []),
])
def test_issues_a_couvrir(marche, ligne, issue, attendu):
    assert B.complements(marche, ligne, issue) == attendu


def test_boost_couvert_aux_meilleures_cotes_des_autres_issues():
    """Lens boosté de 1,95 à 2,30 chez Winamax : nul à 3,60 (Betclic), Lille à 4,50 (Unibet, match écrit à l'envers).
    1/2,30 + 1/3,60 + 1/4,50 = 0,935 : 10 € sur le boost, 6,40 € et 5,10 € de couverture, +1,45 € quoi qu'il arrive."""
    c = _couverts([LENS])[0]
    assert [(j["bookmaker"], j["issue"], j["cote"], j["mise"]) for j in c["jambes"]] == [
        ("Winamax", "DOM", 2.3, 10.0), ("Betclic", "NUL", 3.6, 6.4), ("Unibet", "EXT", 4.5, 5.1)]
    assert c["jambes"][0]["boost"] is True and c["jambes"][0]["libelle_bookmaker"] == "Lens gagne le match"
    assert c["rendement"] == pytest.approx(1 / (1 / 2.3 + 1 / 3.6 + 1 / 4.5) - 1, abs=1e-5)
    assert (c["gain"], c["mise_totale"], c["mise_boost"]) == (1.45, 21.5, 10.0)
    assert c["verifie"] is True and c["suspect"] is None and c["value"] == pytest.approx(0.104)
    assert c["bookmakers"] == ["Betclic", "Unibet", "Winamax"] and c["boost_id"] == "winamax|1|1"
    assert c["match"] == "Lens – Lille" and c["reference"] == "Pinnacle"


def test_boost_sur_un_match_relie_a_l_envers():
    """Unibet écrit Lille – Lens : le boost « Lille gagne » est l'extérieur de la référence, couvert par Lens et le nul."""
    c = _couverts([LILLE])[0]
    assert [(j["bookmaker"], j["issue"], j["cote"]) for j in c["jambes"]] == [
        ("Unibet", "EXT", 5.5), ("Betclic", "DOM", 1.98), ("Betclic", "NUL", 3.6)]
    assert c["rendement"] == pytest.approx(1 / (1 / 5.5 + 1 / 1.98 + 1 / 3.6) - 1, abs=1e-5)
    assert c["mise_boost"] == 5.0 and c["gain"] == pytest.approx(0.92) and c["verifie"] is True


def test_plusieurs_boosts_du_plus_rentable_au_moins_rentable():
    assert [c["boost_id"] for c in _couverts([LILLE, LENS])] == ["winamax|1|1", "unibet|9|9"]


def test_double_chance_quand_elle_paie_mieux():
    fr = [*FR, _l("Betclic", 2, "DOUBLE_CHANCE", "DRAW_AWAY", 2.10)]
    fr = [l for l in fr if not (l["marche"] == "DOUBLE_CHANCE" and l["cote"] == 1.85)]
    c = _couverts([LENS], fr=fr)[0]
    assert [(j["issue"], j["cote"]) for j in c["jambes"][1:]] == [("DRAW_AWAY", 2.1)]


def test_boost_trop_petit_pour_etre_couvert():
    assert _couverts([{**LENS, "cote": 2.0}]) == []


def test_mise_max_inconnue_dix_euros():
    c = _couverts([{**LENS, "mise_max": None}])[0]
    assert c["mise_boost"] == 10.0 and c["mise_max"] is None


def test_probabilites_justes_incoherentes_pas_de_couverture():
    """Le boost aurait 60 % de chances, nul et Lille 52 % : ce n'est pas le même marché, rien n'est proposé."""
    b = {**LENS, "match_id": "winamax|1", "marche": N2, "periode": "MATCH", "ligne": None, "issue": "DOM",
         "pari": "Lens", "proba_juste": 0.60, "cote_juste": 1.667, "value": 0.38}
    assert B.couverts([b], FR, _index(), T) == []


def test_sans_cote_juste_du_boost_non_verifie_et_suspect_au_dela_de_5_pour_cent():
    b = {**LENS, "match_id": "winamax|1", "marche": N2, "periode": "MATCH", "ligne": None, "issue": "DOM",
         "pari": "Lens", "proba_juste": None, "cote_juste": None, "value": None}
    c = B.couverts([b], FR, _index(), T)[0]
    assert c["verifie"] is False and c["suspect"] == "trop beau sans cote juste pour vérifier"
    petit = B.couverts([{**b, "cote": 2.10}], FR, _index(), T)[0]
    assert petit["verifie"] is False and petit["suspect"] is None and 0 < petit["rendement"] < 0.05


def test_couverture_trop_ancienne_ecartee():
    """Les cotes de couverture lues il y a 30 minutes ne comptent plus (même règle que les surebets)."""
    vieux = (T - timedelta(minutes=30)).isoformat(timespec="seconds")
    assert _couverts([LENS], fr=[{**l, "collecte": vieux} for l in FR]) == []


def test_couvert_par_les_cotes_normales_du_meme_bookmaker():
    """Sans Betclic ni Unibet, Winamax couvre lui-même son boost : 1/2,30 + 1/3,40 + 1/3,90 = 0,985."""
    c = _couverts([LENS], fr=[l for l in FR if l["source"] == "Winamax"])[0]
    assert c["bookmakers"] == ["Winamax"] and c["rendement"] == pytest.approx(0.0149, abs=1e-4)


def test_suivi_et_bilan_des_boosts_couverts():
    actuels = _couverts([LENS, LILLE])
    eps = B.suivre_couverts({}, actuels, T)
    eps = B.suivre_couverts({"episodes_couverts": eps}, actuels[:1], T + timedelta(minutes=5))
    e = next(x for x in eps if x["bookmaker"] == "Winamax")
    assert (e["cycles"], e["gain_initial"], e["mise_initiale"], e["verifie"]) == (2, 1.45, 21.5, True)
    bl = B.bilan_couverts(eps, T + timedelta(hours=1))
    assert (bl["n"], bl["verifies"], bl["gain"]) == (2, 2, pytest.approx(1.45 + 0.92))
    assert B.bilan_couverts([], T) == {"jours": 7, "n": 0}
    suspect = [{**actuels[0], "suspect": "rendement trop grand"}]
    assert B.suivre_couverts({}, suspect, T) == []


def test_etape_du_cycle_ecrit_les_boosts_couverts(tmp_path):
    from cotes.pipeline.analyse import boosts_du_cycle
    r = boosts_du_cycle(tmp_path, FR, _index(), {}, lire=lambda: ([LENS, LILLE], []), maintenant=T)
    assert r["couverts"] == 2 and r["lus"] == 2
    doc = json.loads((tmp_path / "boosts.json").read_text())
    assert len(doc["couverts"]) == 2 and len(doc["episodes_couverts"]) == 2


def test_alertes_un_boost_couvert_remplace_l_alerte_de_value(tmp_path):
    from cotes.alertes import promos
    from cotes.pipeline.analyse import boosts_du_cycle
    boosts_du_cycle(tmp_path, FR, _index(), {}, lire=lambda: ([LENS], []), maintenant=T)
    maintenant = T + timedelta(minutes=2)
    a = promos.alertes(tmp_path, {}, {"boosts"}, maintenant)
    assert [x["type"] for x in a] == ["couvert"]                # la value de 10 % ne part pas en double
    assert [x["type"] for x in promos.alertes(tmp_path, {}, {"surebets"}, maintenant)] == ["couvert"]
    assert promos.alertes(tmp_path, {a[0]["id"]: ISO}, {"boosts"}, maintenant) == []
    assert promos.alertes(tmp_path, {}, set(), maintenant) == []
    m = promos.message_couvert(a[0])
    assert m["title"].startswith("Boost couvert +7,0 % · Lens – Lille")
    assert "Winamax : boost 2,30 → 10,00 €" in m["message"] and "Betclic : " in m["message"]
    assert "Gain d'au moins +1,45 € pour 21,50 € misés" in m["message"] and "Vérifié" in m["message"]
    assert m["url"] == "https://winamax.fr/m"


def test_message_pushover_d_un_boost_couvert(tmp_path):
    from cotes.alertes import promos
    from cotes.alertes.pushover import message_pushover
    from cotes.pipeline.analyse import boosts_du_cycle
    boosts_du_cycle(tmp_path, FR, _index(), {}, lire=lambda: ([LENS], []), maintenant=T)
    a = promos.alertes(tmp_path, {}, {"boosts"}, T)[0]
    m = message_pushover(a, env={}, maintenant=T)
    assert m["title"].startswith("Boost couvert") and m["ttl"] == 3 * 3600


def test_page_boosts_publie_les_boosts_couverts(tmp_path):
    from cotes.pipeline.analyse import boosts_du_cycle
    from cotes.site.construction import boosts_publies
    boosts_du_cycle(tmp_path, FR, _index(), {}, lire=lambda: ([LENS], []), maintenant=T)
    d = boosts_publies(json.loads((tmp_path / "boosts.json").read_text()), T + timedelta(minutes=5))
    assert len(d["couverts"]) == 1 and d["bilan_couverts"]["7"]["n"] == 1 and len(d["episodes_couverts"]) == 1
    assert boosts_publies(json.loads((tmp_path / "boosts.json").read_text()), T + timedelta(hours=4))["couverts"] == []


def test_alerte_de_value_gardee_quand_la_couverture_rapporte_trop_peu(tmp_path):
    """Couvert à +0,5 % (sous le seuil de 1 %) : pas d'alerte « couvert », l'alerte de value du boost part ; une fois
    le boost envoyé comme couvert, plus d'alerte de value."""
    from cotes.alertes import promos
    boost = {"id": "x", "value": 0.10, "debut": DEBUT, "libelle": "L", "cote": 2.3}
    couvert = {"boost_id": "x", "cle": "x|Betclic:NUL", "rendement": 0.005, "debut": DEBUT, "jambes": [{"cote": 2.3}]}
    (tmp_path / "boosts.json").write_text(json.dumps({"maj": ISO, "actuels": [boost], "couverts": [couvert]}))
    assert [a["id"] for a in promos.alertes(tmp_path, {}, {"boosts"}, T)] == ["boost:x"]
    assert promos.alertes(tmp_path, {"couvert:x|Betclic:NUL": ISO}, {"boosts"}, T) == []
