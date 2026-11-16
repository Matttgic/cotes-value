"""Alertes Pushover des surebets et des cotes boostées (cotes/alertes/promos.py)."""
from datetime import datetime, timedelta, timezone

from cotes.alertes import promos
from cotes.alertes.pushover import message_pushover, strategies_pushover

T = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
DEBUT = (T + timedelta(hours=3)).isoformat()


def _surebet(**kw):
    return {"cle": "Pinnacle|1|VAINQUEUR|MATCH|None|", "match": "Alcaraz – Sinner", "pari": "Vainqueur", "debut": DEBUT,
            "rendement": 0.05, "verifie": True, "suspect": None,
            "jambes": [{"bookmaker": "Winamax", "pari": "Alcaraz", "cote": 2.1, "lien": "https://www.winamax.fr/paris-sportifs/match/1"},
                       {"bookmaker": "Betclic", "pari": "Sinner", "cote": 2.1, "lien": None}], **kw}


def _doc(actuels, maj=T, episodes=None):
    return {"maj": maj.isoformat(), "actuels": actuels, "episodes": episodes or []}


def test_surebet_envoye_une_fois_par_episode():
    doc = _doc([_surebet()], episodes=[{"cle": "Pinnacle|1|VAINQUEUR|MATCH|None|", "premier": "2026-11-16T11:55:00+00:00"}])
    a = promos.alertes_surebets(doc, {}, T)
    assert [x["id"] for x in a] == ["surebet:Pinnacle|1|VAINQUEUR|MATCH|None||2026-11-16T11:55:00+00:00"]
    assert promos.alertes_surebets(doc, {a[0]["id"]: "x"}, T) == []


def test_surebet_ecarte():
    assert promos.alertes_surebets(_doc([_surebet(rendement=0.004)]), {}, T) == []          # sous le seuil (1 %)
    assert promos.alertes_surebets(_doc([_surebet(suspect="rendement trop grand")]), {}, T) == []
    assert promos.alertes_surebets(_doc([_surebet(debut=(T - timedelta(minutes=1)).isoformat())]), {}, T) == []
    assert promos.alertes_surebets(_doc([_surebet()], maj=T - timedelta(minutes=20)), {}, T) == []   # relevé périmé


def test_seuil_lu_dans_l_environnement(monkeypatch):
    monkeypatch.setenv("SUREBET_SEUIL_ALERTE", "0,06")
    assert promos.alertes_surebets(_doc([_surebet()]), {}, T) == []
    monkeypatch.setenv("SUREBET_SEUIL_ALERTE", "n'importe quoi")
    assert len(promos.alertes_surebets(_doc([_surebet()]), {}, T)) == 1


def test_message_surebet():
    m = message_pushover({**_surebet(), "type": "surebet", "id": "s"}, env={"PUSHOVER_BANKROLL": "1000"}, maintenant=T)
    assert m["title"] == "Surebet +5,0 % · Alcaraz – Sinner"
    assert "Winamax : Alcaraz 2,10 → 50 €" in m["message"] and "Betclic : Sinner 2,10 → 50 €" in m["message"]
    assert "Retour d'au moins 105,00 € pour 100 € (+5,00 €)" in m["message"] and "Vérifié" in m["message"]
    assert m["url"].startswith("https://www.winamax.fr") and m["ttl"] == 3 * 3600 and m["priority"] == 0
    m = message_pushover({**_surebet(verifie=False), "type": "surebet", "id": "s"}, env={}, maintenant=T)
    assert "Non vérifié" in m["message"]


def _boost(**kw):
    return {"id": "winamax|1|2", "bookmaker": "Winamax", "libelle": "Carlos Alcaraz gagne par au moins 6 jeux d'écart",
            "domicile": "Carlos Alcaraz", "exterieur": "Frances Tiafoe", "debut": DEBUT, "cote": 2.8, "cote_avant": 2.5,
            "mise_max": 20.0, "cote_juste": 2.632, "reference": "Pinnacle", "value": 0.064,
            "pari": "Carlos Alcaraz -5,5 jeux", "lien": "https://www.winamax.fr/paris-sportifs/match/9", **kw}


def test_boosts_en_value_seulement():
    doc = _doc([_boost(), _boost(id="b", value=0.01), _boost(id="c", value=None)])
    assert [a["id"] for a in promos.alertes_boosts(doc, {}, T)] == ["boost:winamax|1|2"]
    assert promos.alertes_boosts(doc, {"boost:winamax|1|2": "x"}, T) == []
    m = message_pushover({**_boost(), "type": "boost"}, env={}, maintenant=T)
    assert m["title"] == "Boost +6,4 % · Carlos Alcaraz – Frances Tiafoe"
    assert "Winamax 2,80 (avant 2,50) · mise max 20 €" in m["message"] and "Cote juste 2,63 (Pinnacle)" in m["message"]


def test_cases_reconnues(tmp_path):
    import json
    choisies, inconnues = strategies_pushover({"PUSHOVER_STRATEGIES": "surebets, boosts, inconnue"})
    assert choisies == {"surebets", "boosts"} and inconnues == ["inconnue"]
    (tmp_path / "surebets.json").write_text(json.dumps(_doc([_surebet()])))
    (tmp_path / "boosts.json").write_text(json.dumps(_doc([_boost()])))
    assert len(promos.alertes(tmp_path, {}, {"surebets"}, T)) == 1
    assert len(promos.alertes(tmp_path, {}, {"surebets", "boosts"}, T)) == 2
    assert promos.alertes(tmp_path, {}, {"strategie"}, T) == []
