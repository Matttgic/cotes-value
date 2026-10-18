"""PMU via Kambi : fixtures enregistrées, aucun appel réseau."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cotes.direct import pmu
from cotes.simulation import REFERENCES, bilan

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "kambi_pmu.json").read_text())
MAINTENANT = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


class Reponse:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code = status
        self._data = data if data is not None else {}
        self.headers = headers or {}
        self.text = "SECRET_CORPS"

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


class Session:
    def __init__(self, plan):
        self.plan = list(plan)
        self.urls = []

    def get(self, url, timeout=30, headers=None):
        self.urls.append(url)
        statut, data = self.plan.pop(0)
        return Reponse(statut, data)


def _collecter(plan, pause=(0, 0)):
    session = Session(plan)
    lignes, meta = pmu.collecter({"football"}, 36, session=session, pause=pause, maintenant=MAINTENANT)
    return lignes, meta, session


def test_fixture_traduit_les_marches_connus_et_ecarte_le_reste():
    liste = {"events": FIXTURE["events"]}
    offres = {"betOffers": FIXTURE["betOffers"]}
    lignes, meta, session = _collecter([(200, liste), (200, offres)])
    assert meta["ok"] and meta["matchs"] == 1 and meta["requetes"] == 2
    assert len(session.urls) == 2
    assert "listView/football/" in session.urls[0]
    assert "betoffer/event/1025806339.json" in session.urls[1]
    assert "1028404555" not in session.urls[1]
    assert all(l["bookmaker"] == "pmu" and l["source"] == "PMU" for l in lignes)
    cles = {(l["marche"], l["issue"], l["ligne"]) for l in lignes}
    assert ("RESULTAT_1N2", "DOM", None) in cles
    assert ("RESULTAT_1N2", "NUL", None) in cles
    assert ("RESULTAT_1N2", "EXT", None) not in cles
    assert ("TOTAL", "PLUS", 2.5) in cles
    assert ("TOTAL_DOM", "PLUS", 1.5) in cles
    assert ("HANDICAP", "DOM", -0.5) in cles
    assert ("HANDICAP_3", "NUL", -1.0) in cles
    assert ("BOTH_TEAMS_TO_SCORE", "YES", None) in cles
    assert ("DOUBLE_CHANCE", "HOME_DRAW", None) in cles
    assert ("DRAW_NO_BET", "EXT", None) in cles
    assert ("CORRECT_SCORE", "1-0", None) in cles
    assert ("HALF_TIME_FULL_TIME", "DOM/DOM", None) in cles
    assert not any("corner" in (l.get("libelle") or "").lower() for l in lignes)
    assert not any("pair" in (l.get("libelle") or "").lower() for l in lignes)
    assert not any("buteur" in (l.get("libelle") or "").lower() for l in lignes)
    domicile = next(l for l in lignes if l["marche"] == "RESULTAT_1N2" and l["issue"] == "DOM")
    assert domicile["cote"] == 2.85 and domicile["sport"] == "football"


def test_pause_entre_1_et_1_5_et_429_sans_fuite(monkeypatch, caplog):
    pauses = []
    monkeypatch.setattr(pmu.time, "sleep", lambda s: pauses.append(s))
    monkeypatch.setattr(pmu.random, "uniform", lambda a, b: 1.2)
    liste = {"events": FIXTURE["events"]}
    offres = {"betOffers": FIXTURE["betOffers"]}
    lignes, meta, session = _collecter(
        [(429, {"secret": "NE_PAS_LOGUER"}), (200, liste), (200, offres)], pause=(1.0, 1.5))
    assert lignes and meta["ok"]
    assert 1.2 in pauses and any(s >= 2 for s in pauses)
    assert "NE_PAS_LOGUER" not in caplog.text
    assert "SECRET_CORPS" not in json.dumps(meta)


def test_echec_total_nest_pas_ok_et_un_sport_hors_catalogue_nest_pas_demande():
    lignes, meta, session = _collecter([(404, {})])
    assert lignes == [] and meta["ok"] is False and meta["erreurs"] == ["HTTP 404"]
    assert pmu.sports_demandes({"football", "formule_1", "darts"}) == [("football", "football")]
    assert "cricket" not in pmu.SPORTS and "esports" not in pmu.SPORTS
    assert session.urls


def test_rapport_shadow_et_cotes_a_un_centime():
    base = {"bookmaker": "pmu", "sport": "football", "domicile": "Lens", "exterieur": "Lille",
            "debut": "2026-10-18T20:00:00Z", "marche": "TOTAL", "periode": "MATCH", "issue": "PLUS"}
    pulse = [{**base, "match_id": "pmu|ps", "ligne": 2.5, "cote": 1.85},
             {**base, "match_id": "pmu|ps", "issue": "MOINS", "ligne": 2.5, "cote": 1.95},
             {**base, "match_id": "pmu|manque", "domicile": "Nice", "exterieur": "Rennes", "cote": 2.1}]
    direct = [{**base, "match_id": "pmu|k", "ligne": 2.5, "cote": 1.86},
              {**base, "match_id": "pmu|k", "issue": "MOINS", "ligne": 2.5, "cote": 2.10}]
    r = pmu.rapport(pulse, direct)
    assert r["matchs_pulsescore"] == 2 and r["matchs_communs"] == 1
    assert r["couverture"] == 0.5
    assert r["selections_communes"] == 2 and r["selections_egales"] == 1
    assert r["accord_cotes"] == 0.5 and r["pret_a_basculer"] is False
    parfait = pmu.rapport(pulse[:1], [{**direct[0], "cote": 1.85}])
    assert parfait["couverture"] == 1 and parfait["accord_cotes"] == 1
    assert parfait["pret_a_basculer"] is True
    vide = pmu.rapport([], direct)
    assert vide["couverture"] is None and vide["pret_a_basculer"] is False


def test_mode_par_defaut_shadow(monkeypatch):
    monkeypatch.delenv("SOURCE_PMU", raising=False)
    assert pmu.mode_source() == "shadow"
    monkeypatch.setenv("SOURCE_PMU", "AUTO")
    assert pmu.mode_source() == "auto"
    monkeypatch.setenv("SOURCE_PMU", "ailleurs")
    assert pmu.mode_source() == "shadow"


def test_pari_kalshi_historique_reste_dans_le_bilan():
    from tests.test_contre_audit import candidat
    assert "Kalshi" in REFERENCES
    pari = candidat(reference="Kalshi", statut="gagne", gain=8, mise=10, cote=2.0, cote_juste=1.8)
    resume = bilan([pari])
    assert resume["C|Kalshi"]["regles"] == 1
    assert resume["C|Kalshi"]["gains"] == 8
