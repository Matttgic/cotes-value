"""Ordres de pari : garde-fous, expiration, liens."""
from datetime import datetime, timedelta, timezone

from cotes import ordres
from cotes.notifications import empreinte_prix

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def opportunite(**kw):
    return {"bookmaker": "Winamax", "sport": "football", "ligue": "Ligue 1", "domicile": "Rodez", "exterieur": "Montpellier",
            "debut": (NOW + timedelta(hours=3)).isoformat(), "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None,
            "issue": "DOM", "pari": "Rodez", "cote": 2.75, "lien": "/paris-sportifs/match/68932762",
            "match_id": "winamax|68932762", "libelle_bookmaker": "Match", **kw}


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


def test_lien_de_l_alerte_sinon_celui_du_prix_et_repli_annonce():
    o = opportunite()
    x = ordres.construire({"alertes": [{**alerte(o), "lien": "https://www.winamax.fr/paris-sportifs/match/7"}]}, [o], NOW)
    assert x["ordres"][0]["lien"].endswith("/match/7") and x["ordres"][0]["lien_repli"] is False
    assert ordres.construire({"alertes": [alerte(o)]}, [o], NOW)["ordres"][0]["lien_repli"] is False
    o = opportunite(bookmaker="OlyBet", match_id="olybet|31187407", lien=None)
    (x,) = ordres.construire({"alertes": [alerte(o)]}, [o], NOW)["ordres"]
    assert x["lien"] == "https://www.olybet.fr/sportsbook/pre-match/match/Soccer" and x["lien_repli"] is True


def test_cote_min_jamais_sous_le_plancher_de_valeur():
    # Cote juste 2,00 relevée à 2,05 (+2,5 %) : 3 % de tolérance donnerait 1,99, sous la cote juste.
    o = opportunite(cote=2.05, cote_juste=2.00)
    (x,) = ordres.construire({"alertes": [alerte(o)]}, [o], NOW)["ordres"]
    assert x["cote_min"] == 2.04
    # Gros écart : la tolérance (2,13) est au-dessus du plancher (2,04) et reste la règle.
    o = opportunite(cote=2.20, cote_juste=2.00)
    assert ordres.construire({"alertes": [alerte(o)]}, [o], NOW)["ordres"][0]["cote_min"] == 2.13


def test_ordre_non_emis_sous_le_plancher_et_plancher_de_l_alerte_prioritaire():
    o = opportunite(cote=2.02, cote_juste=2.00)                  # +1 % seulement
    assert ordres.construire({"alertes": [alerte(o)]}, [o], NOW)["ordres"] == []
    o = opportunite(cote=2.20, cote_juste=2.00)
    (x,) = ordres.construire({"alertes": [{**alerte(o), "cote_min": 2.151}]}, [o], NOW)["ordres"]
    assert x["cote_min"] == 2.16                                  # arrondi au centime supérieur
    o = opportunite(cote=1.32, cote_juste=1.25)                   # plancher absolu 1,30
    assert ordres.construire({"alertes": [alerte(o)]}, [o], NOW)["ordres"][0]["cote_min"] == 1.3
