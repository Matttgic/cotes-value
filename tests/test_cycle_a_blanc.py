"""Cycle complet à blanc, sans réseau (docs/architecture-cible.md, E0.2).

`cycle.main()` tourne de bout en bout sur un dossier vide : Pinnacle donne un match de football (1N2),
Winamax la même affiche avec une cote 5 % au-dessus de la cote juste, les autres sources sont vides ou coupées.
Filet de sécurité des déplacements de la phase 3 : mêmes fichiers écrits, mêmes clés du journal.
"""
import gzip
import json
import socket
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

from cotes import controle
from scripts import cycle

VIDE = ([], {"ok": True, "erreurs": [], "requetes": 0})
PROBAS = {"DOM": 0.5, "NUL": 0.28, "EXT": 0.22}


def _lignes(maintenant: datetime):
    collecte = maintenant.isoformat(timespec="seconds")
    debut = (maintenant + timedelta(hours=6)).replace(microsecond=0).isoformat()
    commun = {"sport": "football", "ligue": "Ligue 1", "debut": debut, "domicile": "Lens", "exterieur": "Lille",
              "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None, "collecte": collecte}
    pinnacle = [{**commun, "source": "Pinnacle", "bookmaker": "pinnacle", "match_id": "pin-1", "issue": issue,
                 "cote": round(1 / (p * 1.03), 3), "proba_juste": p, "marge_pinnacle": 0.03, "age_cache_s": 5}
                for issue, p in PROBAS.items()]
    winamax = {**commun, "source": "Winamax", "bookmaker": "winamax", "match_id": "wina-1", "issue": "DOM",
               "cote": round(1.05 / PROBAS["DOM"], 2), "libelle": "Lens"}
    return pinnacle, winamax


def _controle_conforme(donnees, ligne, maintenant):
    """Intitulé déjà contrôlé conforme : sans cela, le premier cycle ne prend aucun pari (« à vérifier »)."""
    cle = controle.cle_groupe(ligne)
    groupe = {"bookmaker": ligne["bookmaker"], "sport": ligne["sport"], "marche": ligne["marche"],
              "periode": ligne["periode"], "type": cle.rsplit("|", 1)[1], "n": 20, "rapports": [1.0] * 20,
              "exemples": [], "maj": (maintenant - timedelta(minutes=5)).isoformat(timespec="seconds")}
    (donnees / "controle.json").write_text(json.dumps({"groupes": {cle: groupe}}), encoding="utf-8")


@pytest.fixture
def cycle_a_blanc(tmp_path, monkeypatch):
    donnees = tmp_path / "donnees"
    donnees.mkdir()
    for nom, valeur in {"SOURCE_MATCHBOOK": "off", "SOURCE_FANDUEL": "off", "SOURCE_DRAFTKINGS": "off",
                        "SOURCE_OLYBET": "off", "SOURCE_NETBET": "off", "SOURCE_BETFAIR": "off",
                        "SMARKETS_COLLECTE": "non", "REPRISE_CHEMIN": "",
                        "MEMOIRE_CHEMIN": str(tmp_path / "memoire")}.items():
        monkeypatch.setenv(nom, valeur)
    for nom in ("PINNACLE_API_KEY", "PINBOOK_API_KEY", "SERVEUR_DIRECT"):
        monkeypatch.delenv(nom, raising=False)
    monkeypatch.setattr(cycle.pinnacle_secours, "disponible", lambda: False)

    def connexion_interdite(*args, **kwargs):
        raise AssertionError(f"réseau interdit dans le cycle à blanc : {args[1:]}")

    monkeypatch.setattr(socket.socket, "connect", connexion_interdite)
    maintenant = datetime.now(timezone.utc)
    pinnacle, winamax = _lignes(maintenant)
    _controle_conforme(donnees, winamax, maintenant)
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda *a, **k: [dict(l) for l in pinnacle])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a, **k: [])
    monkeypatch.setattr(cycle.winamax_direct, "collecter",
                        lambda *a, **k: ([dict(winamax)], {"ok": True, "erreurs": [], "requetes": 1, "matchs": 1}))
    for module in (cycle.pmu_direct, cycle.betclic_direct, cycle.unibet_direct):
        monkeypatch.setattr(module, "collecter", lambda *a, **k: (list(VIDE[0]), dict(VIDE[1])))
    monkeypatch.setattr(sys, "argv", ["cycle.py", "--mode", "complet", "--donnees", str(donnees), "--sans-site",
                                      "--reglement", "non"])
    return donnees


def _paris(donnees):
    return json.loads((donnees / "paris.json").read_text(encoding="utf-8"))


def test_cycle_complet_sans_reseau(cycle_a_blanc, capsys):
    donnees = cycle_a_blanc
    t = time.perf_counter()
    assert cycle.main() == 0
    assert time.perf_counter() - t < 5
    paris = _paris(donnees)
    assert [p["bookmaker"] for p in paris] == ["Winamax"]
    assert paris[0]["issue"] == "DOM" and paris[0]["reference"] in ("Pinnacle", "Consensus")
    jours = list((donnees / "opportunites").glob("*.jsonl.gz"))
    assert len(jours) == 1
    with gzip.open(jours[0], "rt", encoding="utf-8") as f:
        assert len([l for l in f if l.strip()]) >= 1
    etat = json.loads((donnees / "etat.json").read_text(encoding="utf-8"))
    dernier = etat["dernier_cycle"]
    for cle in ("cotes", "opportunites", "nouveaux_paris", "etapes"):
        assert cle in dernier
    assert dernier["nouveaux_paris"] == 1 and dernier["cotes"]["pinnacle"] >= 3
    assert dernier["etapes"]["winamax_direct"]["ok"] is True
    sortie = capsys.readouterr().out
    assert json.loads(sortie[sortie.index("{"):])["nouveaux_paris"] == 1


def test_second_passage_sans_nouveau_pari(cycle_a_blanc):
    donnees = cycle_a_blanc
    assert cycle.main() == 0
    assert cycle.main() == 0
    assert len(_paris(donnees)) == 1
    etat = json.loads((donnees / "etat.json").read_text(encoding="utf-8"))
    assert etat["dernier_cycle"]["nouveaux_paris"] == 0
    assert [h["nouveaux_paris"] for h in etat["historique"]] == [1, 0]
