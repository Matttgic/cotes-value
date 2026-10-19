"""Ordres de pari : garde-fous, expiration, liens."""
from datetime import datetime, timedelta, timezone

from cotes import ordres
from cotes.notifications import empreinte_prix

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def opportunite(**kw):
    return {"bookmaker": "Winamax", "sport": "football", "ligue": "Ligue 1", "domicile": "Rodez", "exterieur": "Montpellier",
            "debut": (NOW + timedelta(hours=3)).isoformat(), "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None,
            "issue": "DOM", "pari": "Rodez", "cote": 2.75, "lien": "/paris-sportifs/match/68932762",
            "match_id": "winamax|1", "libelle_bookmaker": "Match", **kw}


def alerte(o, recue=NOW - timedelta(minutes=2)):
    return {"id": empreinte_prix(o), "bookmaker": o["bookmaker"], "cote": o["cote"], "debut": o["debut"],
            "collecte_le": recue.isoformat(), "labels": ["M3"]}


def test_ordre_complet_avec_cote_minimale_mise_et_lien():
    o = opportunite()
    r = ordres.construire({"alertes": [alerte(o)]}, [o], NOW)
    (x,) = r["ordres"]
    assert x["cote_relevee"] == 2.75 and x["cote_min"] == 2.67 and x["mise"] == 10.0
    assert x["lien"] == "https://www.winamax.fr/paris-sportifs/match/68932762"
    assert x["recherche"] == "Rodez – Montpellier · Ligue 1" and x["expire_le"] == (NOW + timedelta(minutes=8)).isoformat()
    assert any("exactement" in t and "mise" in t for t in r["regles"]) and any("dépôt" in t for t in r["regles"])


def test_ordre_expire_ou_sans_correspondance_est_ecarte():
    o = opportunite()
    assert ordres.construire({"alertes": [alerte(o, recue=NOW - timedelta(minutes=11))]}, [o], NOW)["ordres"] == []
    proche = opportunite(debut=(NOW + timedelta(minutes=2)).isoformat())
    assert ordres.construire({"alertes": [alerte(proche)]}, [proche], NOW)["ordres"] == []        # moins de 3 minutes avant le match
    assert ordres.construire({"alertes": [alerte(o)]}, [], NOW)["ordres"] == []                      # prix disparu
    assert ordres.construire({"alertes": [{**alerte(o), "cote": True}]}, [o], NOW)["ordres"] == []


def test_liens_absolus_seulement_quand_la_base_est_connue():
    assert ordres.lien_absolu("Betclic", "/x-m1") == "https://www.betclic.fr/x-m1"
    assert ordres.lien_absolu("PMU", "sport/x") == "https://paris-sportifs.pmu.fr/sport/x"
    assert ordres.lien_absolu("OlyBet", "/x") is None and ordres.lien_absolu("Winamax", None) is None
    assert ordres.lien_absolu("OlyBet", "https://exemple.fr/x") == "https://exemple.fr/x"
    o = opportunite(bookmaker="OlyBet", lien=None)
    assert ordres.construire({"alertes": [alerte(o)]}, [o], NOW)["ordres"][0]["lien"] is None
