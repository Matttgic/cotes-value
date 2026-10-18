"""PMU via Kambi : fixtures enregistrées, aucun appel réseau."""
import json
from datetime import datetime, timedelta, timezone
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


GROUPE_VIDE = {"group": {"termKey": "football", "groups": []}}


def test_fixture_traduit_les_marches_connus_et_ecarte_le_reste():
    liste = {"events": FIXTURE["events"]}
    offres = {"betOffers": FIXTURE["betOffers"]}
    lignes, meta, session = _collecter([(200, liste), (200, GROUPE_VIDE), (200, offres)])
    assert meta["ok"] and meta["matchs"] == 1 and meta["requetes"] == 3
    assert len(session.urls) == 3
    assert "listView/football/" in session.urls[0]
    assert "group.json" in session.urls[1]
    assert "betoffer/event/1025806339.json" in session.urls[2]
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
        [(429, {"secret": "NE_PAS_LOGUER"}), (200, liste), (200, GROUPE_VIDE), (200, offres)],
        pause=(1.0, 1.5))
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


def _offre(type_en, label, anglais, issues, lifetime="FULL_TIME"):
    return {
        "id": 1, "eventId": 1025806339,
        "betOfferType": {"englishName": type_en},
        "criterion": {"label": label, "englishLabel": anglais, "lifetime": lifetime, "occurrenceType": "GOALS"},
        "outcomes": [{"label": a, "englishLabel": a, "odds": b, "type": c, "line": d, "status": "OPEN"}
                     for a, b, c, d in issues],
    }


def _lignes(offres, sport="football", domicile="Fagiano Okayama", exterieur="Vissel Kobe"):
    from cotes.pulsescore import traduire
    event = {"id": 1025806339, "homeName": domicile, "awayName": exterieur,
             "start": "2026-10-18T23:30:00Z", "state": "NOT_STARTED", "group": "Ligue"}
    ev = pmu.evenement_depuis(event, offres)
    return traduire(ev, "pmu", sport, "2026-10-18T12:00:00+00:00")


def test_les_marches_annexes_ne_remplacent_pas_le_resultat():
    """Premier but, race-to et « au moins N buts » ne doivent pas écraser la clé du marché principal."""
    offres = [
        _offre("Match", "Premier but (Nul : Pas de but)", "First Goal (Draw: No Goals)",
               [("1", 2080, "OT_ONE", None), ("X", 8000, "OT_CROSS", None), ("2", 1970, "OT_TWO", None)]),
        _offre("Match", "Temps réglementaire", "Full Time",
               [("1", 2700, "OT_ONE", None), ("X", 2950, "OT_CROSS", None), ("2", 2330, "OT_TWO", None)]),
        _offre("Yes/No", "Les deux équipes marquent au moins 2 buts", "Both Teams To Score at least 2 goals",
               [("Oui", 3000, "OT_YES", None), ("Non", 1300, "OT_NO", None)]),
        _offre("Yes/No", "Les deux équipes marquent", "Both Teams To Score",
               [("Oui", 1700, "OT_YES", None), ("Non", 2000, "OT_NO", None)]),
        _offre("Match", "Quart-temps 1 - Premier à 20 points", "Quarter 1 - First to 20 Points",
               [("1", 1800, "OT_ONE", None), ("2", 1900, "OT_TWO", None)], lifetime=None),
    ]
    lignes = _lignes(offres)
    un_n_deux = [l for l in lignes if l["marche"] == "RESULTAT_1N2" and l["periode"] == "MATCH"]
    assert {(l["issue"], l["cote"]) for l in un_n_deux} == {("DOM", 2.7), ("NUL", 2.95), ("EXT", 2.33)}
    assert not any(l["marche"] == "VAINQUEUR" for l in lignes)
    btts = [l for l in lignes if l["marche"] == "BOTH_TEAMS_TO_SCORE"]
    assert {(l["issue"], l["cote"]) for l in btts} == {("YES", 1.7), ("NO", 2.0)}


def test_periode_apres_l_unite_ne_se_confond_pas_avec_le_match():
    domicile, exterieur = "Löwen Frankfurt", "Iserlohn Roosters"
    offres = [
        _offre("Correct Score", "Score exact", "Correct Score",
               [("1-0", 7000, "OT_UNTYPED", None), ("2-1", 9000, "OT_UNTYPED", None)]),
        _offre("Correct Score", "Score exact - Première période", "Correct Score - Period 1",
               [("1-0", 4500, "OT_UNTYPED", None), ("2-1", 8000, "OT_UNTYPED", None)], lifetime=None),
        _offre("Over/Under", "Nombre total de buts - Période 2", "Total Goals - Period 2",
               [("Plus de 1.5", 1850, "OT_OVER", 1500), ("Moins de 1.5", 1950, "OT_UNDER", 1500)],
               lifetime=None),
        _offre("Over/Under", "Nombre de buts par Löwen Frankfurt - 1ère mi-temps",
               "Total Goals by Löwen Frankfurt - 1st Half",
               [("Plus de 0.5", 1800, "OT_OVER", 500), ("Moins de 0.5", 1900, "OT_UNDER", 500)],
               lifetime=None),
        _offre("Match", "Set 1", "Set 1",
               [("1", 1600, "OT_ONE", None), ("2", 2200, "OT_TWO", None)], lifetime=None),
    ]
    hockey = _lignes(offres[:4], sport="hockey", domicile=domicile, exterieur=exterieur)
    scores = {(l["periode"], l["issue"], l["cote"]) for l in hockey if l["marche"] == "CORRECT_SCORE"}
    assert ("TEMPS_REG", "1-0", 7.0) in scores
    assert ("P1", "1-0", 4.5) in scores
    assert not any(l["periode"] == "TEMPS_REG" and l["cote"] == 4.5 for l in hockey if l["marche"] == "CORRECT_SCORE")
    totaux = [l for l in hockey if l["marche"] == "TOTAL" and l["issue"] == "PLUS"]
    assert totaux and totaux[0]["periode"] == "P2" and totaux[0]["ligne"] == 1.5
    equipe = [l for l in hockey if l["marche"] == "TOTAL_DOM"]
    assert {(l["periode"], l["issue"]) for l in equipe} == {("MT1", "PLUS"), ("MT1", "MOINS")}
    tennis = _lignes(offres[4:], sport="tennis", domicile="Struff", exterieur="Giron")
    assert {(l["marche"], l["periode"]) for l in tennis} == {("VAINQUEUR", "SET1")}


def test_handicap_hockey_equivalent_garde_le_temps_reglementaire():
    reg = {"match_id": "pmu|1", "marche": "HANDICAP", "periode": "MATCH", "ligne": -2.5,
           "issue": "DOM", "cote": 3.95, "libelle": "Handicap - Temps réglementaire"}
    prol = {**reg, "cote": 3.90, "libelle": "Handicap - Prolongations et séance de tirs au but incluses"}
    gardes = pmu._retenir([prol, reg])
    assert gardes == [reg]
    essai = _offre("Match", "Premier Essai (Égalité: Aucune équipe ne marque un essai)", "First Try",
                   [("1", 1720, "OT_ONE", None), ("X", 20100, "OT_CROSS", None), ("2", 2100, "OT_TWO", None)])
    plein = _offre("Match", "Temps réglementaire (3-way)", "Full Time",
                   [("1", 1560, "OT_ONE", None), ("X", 21000, "OT_CROSS", None), ("2", 2400, "OT_TWO", None)])
    lignes = _lignes([essai, plein], sport="rugby", domicile="Harlequins", exterieur="Vannes")
    assert {(l["issue"], l["cote"]) for l in lignes if l["marche"] == "RESULTAT_1N2"} == {
        ("DOM", 1.56), ("NUL", 21.0), ("EXT", 2.4)}


def _event(eid, home, away, start, state="NOT_STARTED"):
    return {"event": {"id": eid, "homeName": home, "awayName": away, "start": start,
                      "group": "Ligue", "state": state, "tags": ["MATCH"]}}


def _offre_simple(eid):
    return {
        "id": eid, "eventId": eid,
        "betOfferType": {"englishName": "Match"},
        "criterion": {"label": "Temps réglementaire", "englishLabel": "Full Time",
                      "lifetime": "FULL_TIME", "occurrenceType": "GOALS"},
        "outcomes": [
            {"label": "1", "englishLabel": "1", "odds": 2000, "type": "OT_ONE", "status": "OPEN"},
            {"label": "X", "englishLabel": "X", "odds": 3000, "type": "OT_CROSS", "status": "OPEN"},
            {"label": "2", "englishLabel": "2", "odds": 3500, "type": "OT_TWO", "status": "OPEN"},
        ],
    }


def test_chemin_et_feuilles():
    assert pmu._chemin_liste("football/france/ligue_1") == (
        "listView/football/france/ligue_1/all/matches.json")
    assert pmu._chemin_liste("football/champions_league") == (
        "listView/football/champions_league/all/all/matches.json")
    doc = {"group": {"termKey": "football", "groups": [
        {"termKey": "france", "groups": [
            {"sport": "FOOTBALL", "termKey": "ligue_1", "eventCount": 3},
            {"sport": "FOOTBALL", "termKey": "vide", "eventCount": 0},
        ]},
        {"sport": "FOOTBALL", "termKey": "mls", "eventCount": 1},
    ]}}
    assert pmu._feuilles(doc, "football") == ["football/france/ligue_1", "football/mls"]
    assert pmu._feuilles(doc, "tennis") == []


def test_liste_tronquee_complete_par_les_competitions():
    """La liste globale s'arrête avant 36 h : les feuilles de group.json complètent."""
    tot = "2026-10-19T10:00:00Z"
    dedans = "2026-10-19T18:00:00Z"
    dehors = "2026-10-20T04:00:00Z"
    liste = {"events": [_event(1, "Lens", "Lille", tot)]}
    groupe = {"group": {"termKey": "football", "groups": [
        {"termKey": "france", "groups": [
            {"sport": "FOOTBALL", "termKey": "ligue_1", "eventCount": 2},
        ]},
    ]}}
    feuille = {"events": [
        _event(2, "Brest", "Nice", dedans),
        _event(3, "Marseille", "Lyon", dehors),
    ]}
    offres = {"betOffers": [_offre_simple(1), _offre_simple(2), _offre_simple(3)]}
    lignes, meta, session = _collecter(
        [(200, liste), (200, groupe), (200, feuille), (200, offres)])
    noms = {(l["domicile"], l["exterieur"]) for l in lignes if l["marche"] == "RESULTAT_1N2"}
    assert ("Lens", "Lille") in noms
    assert ("Brest", "Nice") in noms
    assert ("Marseille", "Lyon") not in noms
    assert meta["matchs"] == 2
    assert any("listView/football/france/ligue_1/all/matches.json" in u for u in session.urls)


def test_liste_qui_atteint_l_horizon_ne_relit_pas_les_competitions():
    pile = (MAINTENANT + timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M:%SZ")
    liste = {"events": [_event(1, "Lens", "Lille", pile)]}
    offres = {"betOffers": [_offre_simple(1)]}
    lignes, meta, session = _collecter([(200, liste), (200, offres)])
    assert meta["matchs"] == 1 and any(l["domicile"] == "Lens" for l in lignes)
    assert not any("group.json" in u for u in session.urls)


def test_mode_par_defaut_auto(monkeypatch):
    monkeypatch.delenv("SOURCE_PMU", raising=False)
    assert pmu.mode_source() == "auto"
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
