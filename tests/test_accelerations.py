"""Accélérations sans changement de résultat : cache de ``normaliser``, index réutilisé pour les écarts,
une seule lecture de paris.json, connexions gardées, HEAD bornés par l'échéance."""
import json
import threading

import pytest

from cotes import comparaison, connexion, correspondance as C, pinnacle as P
from cotes.delai import Echeance
from scripts import envoyer_notifications as E

NOMS = ["Paris Saint-Germain", "PSG", "Olympique de Marseille", "F.C. Porto", "AEK B.C.", "Toulouse V.B.",
        "Real Madrid U19", "Barcelona (F)", "Manchester City W", "Bayern München II", "", None,
        "Šibenik", "Crystal Palace", "Islanders", "New York Rangers", "Ü-ber  Club  "]


def test_normaliser_en_cache_identique_au_calcul():
    for nom in NOMS:
        attendu = C._normaliser.__wrapped__(nom or "")
        assert C.normaliser(nom) == attendu
        assert C.normaliser(nom) == attendu          # deuxième appel : depuis le cache
    assert C.normaliser(None) == C.normaliser("")
    assert C._normaliser.cache_info().hits > 0
    mots, _, marqueurs = C.normaliser("Real Madrid U19")
    assert isinstance(mots, tuple) and isinstance(marqueurs, frozenset)   # immuables : partage sans risque


def _ecart_fixture():
    moment = "2026-10-18T12:00:00+00:00"
    debut = "2026-10-18T15:00:00+00:00"
    fr = {"source": "winamax", "bookmaker": "winamax", "sport": "football", "match_id": "w|1",
          "domicile": "Fulham", "exterieur": "Crystal Palace", "debut": debut, "collecte": moment,
          "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None, "issue": "DOM", "cote": 2.20}
    sm = {"source": "Smarkets", "bookmaker": "smarkets", "sport": "football", "match_id": "smarkets|1",
          "domicile": "Fulham", "exterieur": "Crystal Palace", "debut": debut, "collecte": moment,
          "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None, "issue": "DOM",
          "proba_juste": 0.48, "cote_juste": 2.0833, "ecart_achat_vente": 0.02, "liquidite": 50}
    poly = {**sm, "source": "Polymarket", "bookmaker": "polymarket", "match_id": "poly|1", "proba_juste": 0.46,
            "liquidite": 100000}
    opp = {**fr, "detecte": moment, "reference": "Pinnacle", "ecart": 0.05}
    return fr, sm, poly, opp


def test_ecarts_avec_index_du_cycle_identiques_et_sans_seconde_association(monkeypatch):
    fr, sm, poly, opp = _ecart_fixture()
    refs = {"Polymarket": [poly], "Smarkets": [sm]}
    sans = dict(opp)
    comparaison.annoter_ecarts([sans], [fr], refs)
    index = comparaison.indexer([fr], {"Pinnacle": [], **refs})
    appels = []
    vrai = comparaison.indexer
    monkeypatch.setattr(comparaison, "indexer", lambda *a, **k: appels.append(a) or vrai(*a, **k))
    avec = dict(opp)
    comparaison.annoter_ecarts([avec], [fr], refs, index=index)
    assert appels == []                                   # l'index du cycle suffit
    assert avec == sans and avec["ecart_smarkets"] == round(2.20 * 0.48 - 1, 4)
    assert avec["ecart_polymarket"] == round(2.20 * 0.46 - 1, 4)
    partiel = dict(opp)                                   # référence absente de l'index : recalculée seule
    comparaison.annoter_ecarts([partiel], [fr], refs, index={"Smarkets": index["Smarkets"]})
    assert partiel == sans and len(appels) == 1 and list(appels[0][1]) == ["Polymarket"]


def test_paris_json_lu_une_seule_fois(tmp_path, monkeypatch):
    (tmp_path / "paris.json").write_text("[]")
    lectures = []
    vrai = E.lire_paris
    monkeypatch.setattr(E, "lire_paris", lambda d: lectures.append(d) or vrai(d))
    vus = {}
    monkeypatch.setattr(E, "preparer", lambda d, **kw: vus.setdefault("preparer", kw["paris_bruts"])
                        or {"generated_at": "2026-10-30T00:00:00+00:00", "alertes": []})
    monkeypatch.setattr(E, "pushover", lambda d, f, env=None, paris=None: vus.setdefault("pushover", paris) or {})
    monkeypatch.setattr(E, "webhook_pinnacle2", lambda d, f, paris=None: vus.setdefault("webhook", paris) or {})
    monkeypatch.setattr(E, "transmettre", lambda f: {"envoye": 0})
    E.envoyer_et_journaliser(tmp_path, tmp_path / "notifications.json")
    assert len(lectures) == 1
    assert vus["preparer"] is vus["pushover"] is vus["webhook"]


def test_paris_json_illisible_chacun_relit_comme_avant(tmp_path, monkeypatch):
    vus = {}
    monkeypatch.setattr(E, "preparer", lambda d, **kw: vus.setdefault("preparer", kw["paris_bruts"])
                        or {"generated_at": "2026-10-30T00:00:00+00:00", "alertes": []})
    monkeypatch.setattr(E, "transmettre", lambda f: {"envoye": 0})
    E.envoyer_et_journaliser(tmp_path, tmp_path / "notifications.json")   # pas de paris.json : pas de levée
    assert vus["preparer"] is None
    journal = json.loads((tmp_path / "notifications_diagnostic.json").read_text())["cycles"][-1]
    assert journal["webhook"]["erreurs"] == ["FileNotFoundError"]


def test_client_une_session_par_fil_sans_cookie():
    client = connexion.Client()
    a = client.session()
    assert client.session() is a
    autre = []
    t = threading.Thread(target=lambda: autre.append(client.session()))
    t.start(); t.join()
    assert autre[0] is not a
    import email.message
    import requests
    from requests.cookies import extract_cookies_to_jar
    requete = requests.Request("GET", "https://api.example.com/x").prepare()
    entetes = email.message.Message()
    entetes["Set-Cookie"] = "__cf_bm=abc; Path=/; Domain=.example.com"
    brut = type("Brut", (), {"_original_response": type("O", (), {"msg": entetes})()})()
    extract_cookies_to_jar(a.cookies, requete, brut)  # une Session ordinaire garderait ce cookie
    assert len(a.cookies) == 0                      # comme requests.get : rien n'est renvoyé au suivant


def test_client_head_sans_redirection_par_defaut(monkeypatch):
    client = connexion.Client()
    vus = {}
    monkeypatch.setattr(client.session(), "head", lambda url, **kw: vus.update(kw) or "ok")
    assert client.head("https://x", timeout=3) == "ok" and vus == {"allow_redirects": False, "timeout": 3}


def test_sondes_head_respectent_l_echeance(monkeypatch):
    monkeypatch.setenv("PINNACLE_CHOIX_PRIX", "oui")
    heads, delais = [], []
    monkeypatch.setattr(P._http, "head", lambda url, **kw: heads.append(url) or delais.append(kw["timeout"]))
    monkeypatch.setattr(P, "_choix_coupe", False)
    monkeypatch.setattr(P, "_bloque", False)
    P._ortho_refusees.clear(); P.choix_prix.clear()
    monkeypatch.setattr(P, "_echeance_active", Echeance(0))
    assert P._choisir_chemin_prix(29) == P._chemin_marches(29)
    assert heads == [] and P.choix_prix.get("head_budget") == 1
    monkeypatch.setattr(P, "_echeance_active", Echeance(4))
    P._choisir_chemin_prix(29)
    assert heads and all(d <= 4 for d in delais)    # plus de 15 s fixes quand il reste 4 s
