"""Une date sans fuseau chez une référence ne vide plus le cycle (audit du 20/11/2026)."""
from cotes import comparaison


def _l(source, mid, debut, **k):
    return {"source": source, "match_id": mid, "sport": "football", "domicile": "Lyon", "exterieur": "Lens",
            "debut": debut, "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None, "issue": "DOM",
            "joueur": None, "cote": 2.0, "collecte": "2026-11-20T10:00:00+00:00", **k}


def test_date_sans_fuseau_ecartee_et_autres_references_gardees(monkeypatch):
    fr = [_l("pmu", "pmu|1", "2026-11-20T18:00:00+00:00"), _l("pmu", "pmu|2", "2026-11-20T18:00:00")]
    refs = {"Pinnacle": [_l("pinnacle", "pin|1", "2026-11-20T18:00:00Z"), _l("pinnacle", "pin|2", "2026-11-20T18:00:00")],
            "Betfair": [_l("betfair", "bf|1", "2026-11-20T18:00:00+00:00")]}
    vrai = comparaison._indexer_reference

    def casse(nom, *a):
        if nom == "Betfair":
            raise TypeError("can't compare offset-naive and offset-aware datetimes")
        return vrai(nom, *a)
    monkeypatch.setattr(comparaison, "_indexer_reference", casse)
    index = comparaison.indexer(fr, refs)
    assert index["Betfair"] == {} and "TypeError" in comparaison.ERREURS_INDEX["Betfair"]
    assert "Pinnacle" in index and "Pinnacle" not in comparaison.ERREURS_INDEX
    monkeypatch.setattr(comparaison, "_indexer_reference", vrai)
    comparaison.indexer(fr, refs)                       # sans erreur : les dates naïves sont écartées à l'entrée
    assert comparaison.ERREURS_INDEX == {}


def test_bourses_avec_liquidite_minimale():
    l = {"proba_juste": 0.5, "ecart_achat_vente": 0.01, "liquidite": 0}
    for nom in ("Betfair", "Matchbook", "Smarkets"):
        assert not comparaison._fiable(nom, l)
        assert comparaison._fiable(nom, {**l, "liquidite": 20})


def test_fil_abandonne_garde_une_echeance_depassee():
    import threading
    import types

    from cotes.pipeline import collecte
    module = types.SimpleNamespace(_echeance=None)
    lache = threading.Event()

    def lent():
        lache.wait(2)
    journal = {"etapes": {}}
    collecte.source_bornee(module, "lent", journal, 0.05, lent)
    assert journal["etapes"]["lent"]["erreur"] == "budget dépassé"
    assert module._echeance is not None and not module._echeance.ok()
    lache.set()
    collecte.source_bornee(module, "vif", journal, 1, lambda: 1)
    assert module._echeance is None


def test_polymarket_ne_depasse_pas_son_echeance(monkeypatch):
    from cotes import polymarket
    from cotes.delai import Echeance
    appels = []
    monkeypatch.setattr(polymarket._http, "get", lambda *a, **k: appels.append(k["timeout"]))
    monkeypatch.setattr(polymarket, "_bloque", False)
    monkeypatch.setattr(polymarket, "_echeance", Echeance(0))
    assert polymarket._get("/events", {}) is None and appels == []
    monkeypatch.setattr(polymarket, "_echeance", Echeance(5))

    def http_500(*a, **k):
        appels.append(k["timeout"])
        return type("R", (), {"status_code": 500})()
    monkeypatch.setattr(polymarket._http, "get", http_500)
    monkeypatch.setattr(polymarket.time, "sleep", lambda s: None)
    polymarket._get("/events", {})
    assert appels and max(appels) <= 5


def test_websocket_borne_olybet():
    import time

    from cotes.direct.ws import fin_lecture
    from cotes.delai import Echeance
    assert fin_lecture(12, Echeance(1)) <= time.monotonic() + 1.01
    assert fin_lecture(2) <= time.monotonic() + 2.01


def test_jeton_masque_dans_le_journal_du_serveur(capsys):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import serveur_direct
    url = serveur_direct.url_depot("ghs_secret123")
    assert "ghs_secret123" not in serveur_direct.masquer(f"échec ['bash', 'x', '{url}'] : fatal {url}")
    serveur_direct.executer(["false", url])
    assert "ghs_secret123" not in capsys.readouterr().out
