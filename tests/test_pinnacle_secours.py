"""Secours Pinnacle (pinnodds) : fixtures au format documenté, aucun appel réseau."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from cotes import pinnacle, pinnacle_secours as S
from scripts import cycle

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
DEBUT = (NOW + timedelta(hours=5)).isoformat().replace("+00:00", "Z")


def evenement(**kw):
    return {"event_id": 1629513753, "sport_id": 1, "league_name": "Italy - Serie A", "home": "Cremonese",
            "away": "Lazio", "starts": DEBUT, "event_type": "prematch", "is_have_odds": True, "periods": {
                "num_0": {"money_line": {"home": 2.45, "draw": 3.30, "away": 2.90},
                          "spreads": {"-0.5": {"hdp": -0.5, "home": 2.06, "away": 1.82, "max": 500}},
                          "totals": {"2.5": {"points": 2.5, "over": 1.90, "under": 1.98, "max": 500}},
                          "team_total": {"home": {"points": 1.5, "over": 1.86, "under": 2.00}}},
                "num_1": {"money_line": {"home": 3.1, "draw": 2.2, "away": 4.0}},
                "num_9": {"money_line": {"home": 1.5, "away": 2.5}}}, **kw}


class Reponse:
    def __init__(self, evenements=None, statut=200, entetes=None):
        self.status_code, self.headers = statut, {"X-Data-Status": "fresh", "X-Data-Age-Ms": "4000", **(entetes or {})}
        self._corps = {"events": evenements if evenements is not None else [evenement()]}

    def json(self):
        return self._corps


class Session:
    def __init__(self, *reponses):
        self.reponses, self.appels = list(reponses), []

    def get(self, url, params=None, headers=None, timeout=None):
        self.appels.append((url, params, headers))
        return self.reponses.pop(0) if len(self.reponses) > 1 else self.reponses[0]


@pytest.fixture(autouse=True)
def cle(monkeypatch):
    monkeypatch.setenv("PINNODDS_API_KEY", "cle-de-test-pinnodds")
    for nom in ("PINNODDS_HANDICAPS", "PINNODDS_LIMITE_JOUR", "PINNODDS_PAUSE_MIN"):
        monkeypatch.delenv(nom, raising=False)


def test_sans_cle_aucune_requete(monkeypatch):
    monkeypatch.delenv("PINNODDS_API_KEY")
    session = Session(Reponse())
    assert not S.disponible() and S.collecter({29}, NOW, None, session) == [] and session.appels == []


def test_marches_sans_ambiguite_par_defaut():
    session = Session(Reponse())
    lignes = S.collecter({29}, NOW, None, session)
    assert session.appels[0][1] == {"sport_id": 1} and session.appels[0][2]["x-portal-apikey"] == "cle-de-test-pinnodds"
    kinds = {(l["marche"], l["periode"]) for l in lignes}
    assert kinds == {("RESULTAT_1N2", "MATCH"), ("RESULTAT_1N2", "MT1"), ("TOTAL", "MATCH")}   # num_9 inconnu, pas de handicap
    un = [l for l in lignes if l["marche"] == "RESULTAT_1N2" and l["periode"] == "MATCH"]
    assert [l["issue"] for l in un] == ["DOM", "NUL", "EXT"] and abs(sum(l["proba_juste"] for l in un) - 1) < 1e-9
    l = un[0]
    assert l["source"] == "pinnacle" and l["origine"] == "pinnodds" and l["sport"] == "football"
    assert l["match_id"] == 1629513753 and l["domicile"] == "Cremonese" and l["ligue"] == "Italy - Serie A"
    assert l["cote_perimee"] is False and l["age_cache_s"] == 4 and l["cote"] == 2.45 and l["marge_pinnacle"] > 0
    assert S.RESUME["sports"] == ["football"] and S.RESUME["lignes"] == len(lignes) and S.RESUME["requetes"] == 1


def test_handicaps_et_totaux_par_equipe_seulement_si_demandes(monkeypatch):
    monkeypatch.setenv("PINNODDS_HANDICAPS", "oui")
    lignes = S.collecter({29}, NOW, None, Session(Reponse()))
    h = [l for l in lignes if l["marche"] == "HANDICAP"]
    assert [(l["issue"], l["ligne"], l["cote"]) for l in h] == [("DOM", -0.5, 2.06), ("EXT", -0.5, 1.82)]
    assert h[0]["mise_max"] == 500.0
    td = [l for l in lignes if l["marche"] == "TOTAL_DOM"]
    assert [(l["issue"], l["ligne"]) for l in td] == [("PLUS", 1.5), ("MOINS", 1.5)]


def test_tennis_vainqueur_seulement(monkeypatch):
    monkeypatch.setenv("PINNODDS_HANDICAPS", "oui")
    ev = evenement(periods={"num_0": {"money_line": {"home": 1.5, "away": 2.6},
                                      "totals": {"22.5": {"points": 22.5, "over": 1.9, "under": 1.9}}}})
    lignes = S.collecter({33}, NOW, None, Session(Reponse([ev])))
    assert {(l["marche"], l["sport"]) for l in lignes} == {("VAINQUEUR", "tennis")}


def test_donnees_perimees_ou_erreurs_ne_donnent_rien():
    assert S.collecter({29}, NOW, None, Session(Reponse(entetes={"X-Data-Status": "stale"}))) == []
    assert "périmées" in S.ERREURS[0]
    assert S.collecter({29}, NOW, None, Session(Reponse(statut=429))) == [] and "429" in S.ERREURS[0]
    assert S.collecter({29}, NOW, None, Session(Reponse(statut=503))) == [] and "503" in S.ERREURS[0]


def test_age_inconnu_ou_trop_vieux_marque_la_cote_perimee():
    vieux = S.collecter({29}, NOW, None, Session(Reponse(entetes={"X-Data-Age-Ms": str(3_600_000)})))
    assert vieux and all(l["cote_perimee"] for l in vieux)
    inconnu = S.collecter({29}, NOW, None, Session(Reponse(entetes={"X-Data-Age-Ms": ""})))
    assert inconnu and all(l["cote_perimee"] for l in inconnu)


def test_evenements_invalides_ignores():
    mauvais = [evenement(home="Lazio"), evenement(is_have_odds=False), evenement(special={"x": 1}),
               evenement(starts=(NOW - timedelta(hours=1)).isoformat()), evenement(event_type="live"),
               evenement(periods={"num_0": {"money_line": {"home": 1.0, "away": 2.0}}}),
               evenement(periods={"num_0": {"money_line": {"home": True, "away": "2"}}})]
    assert S.collecter({29}, NOW, None, Session(Reponse(mauvais))) == []


def test_budget_journalier_et_pause(tmp_path, monkeypatch):
    monkeypatch.setenv("PINNODDS_LIMITE_JOUR", "2")
    session = Session(Reponse())
    S.collecter({29, 33, 4}, NOW, tmp_path, session)
    assert len(session.appels) == 2 and "limite journalière" in S.ERREURS[0]
    etat = json.loads((tmp_path / "pinnacle_secours.json").read_text())
    assert etat["requetes"] == 2 and etat["jour"] == "2026-10-19"
    # dans la pause de 30 minutes : aucune requête, le dernier passage est rejoué avec son âge réel
    frais = S.collecter({29}, NOW + timedelta(minutes=5), tmp_path, session)
    assert len(session.appels) == 2 and S.RESUME["pause"] is True and not S.ERREURS
    assert frais and S.RESUME["cache_lignes"] == len(frais) and not any(l["cote_perimee"] for l in frais)
    assert {l["age_cache_s"] for l in frais} == {4 + 300}
    vieux = S.collecter({29}, NOW + timedelta(minutes=10, seconds=1), tmp_path, session)
    assert vieux and all(l["cote_perimee"] for l in vieux)                  # au-delà de 10 minutes : plus de référence
    # budget épuisé le même jour, même après la pause : toujours aucune requête
    S.collecter({29}, NOW + timedelta(minutes=40), tmp_path, session)
    assert len(session.appels) == 2
    # le lendemain, le compteur repart de zéro
    S.collecter({29}, NOW + timedelta(days=1), tmp_path, session)
    assert len(session.appels) == 3


def test_sports_a_secourir():
    direct = [{"x": 1}]
    assert S.sports_a_secourir([], direct) == set() and S.sports_a_secourir([], []) == set()
    assert S.sports_a_secourir(["sport 29 matchups : HTTP 503", "sport 33 matchups : HTTP 403",
                                "sport 17 matchups : HTTP 403", "sport 4 : événements invalides"], direct) == {29, 33}
    assert S.sports_a_secourir(["budget"], []) == set(S.SPORTS_PINNODDS)


def test_comparaison_avec_la_lecture_directe():
    def l(cote, issue="DOM"):
        return {"match_id": 1, "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None, "issue": issue, "cote": cote}

    r = S.comparer([l(2.0), l(3.0, "NUL")], [l(2.01), l(3.3, "NUL"), l(9.0, "EXT")])
    assert r["secours"] == 3 and r["communes"] == 2 and r["couverture"] == round(2 / 3, 3)
    assert r["ecart_max"] == 0.1 and r["identiques_1pct"] == 0.5
    assert S.comparer([], [])["couverture"] is None


def _cycle_sans_reseau(monkeypatch, erreurs, lignes_pinnacle):
    from tests.test_collecte_parallele import _sans_reseau

    _sans_reseau(monkeypatch)

    def lire():
        pinnacle.ERREURS.clear()
        pinnacle.ERREURS.extend(erreurs)
        return list(lignes_pinnacle)

    monkeypatch.setattr(cycle.pinnacle, "collecter", lire)
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)


def test_cycle_utilise_le_secours_pour_les_sports_en_echec(monkeypatch):
    from tests.test_collecte_parallele import ligne

    _cycle_sans_reseau(monkeypatch, ["sport 29 matchups : HTTP 503"], [ligne("tennis", "pinnacle")])
    appels = []

    def secours(sports, maintenant, donnees):
        appels.append(sports)
        S.RESUME.update({"sports": ["football"], "requetes": 1, "lignes": 1})
        return [ligne("football", "pinnacle") | {"origine": "pinnodds"}]

    monkeypatch.setattr(cycle.pinnacle_secours, "collecter", secours)
    journal = {"etapes": {}}
    pin, _, _ = cycle.collecter_prematch("complet", NOW, journal)
    assert appels == [{29}] and [l.get("origine") for l in pin] == [None, "pinnodds"]
    assert journal["pinnacle_secours"]["lignes"] == 1


def test_cycle_sans_secours_quand_pinnacle_va_bien_ou_sans_cle(monkeypatch):
    from tests.test_collecte_parallele import ligne

    monkeypatch.setattr(cycle.pinnacle_secours, "collecter",
                        lambda *a: (_ for _ in ()).throw(AssertionError("secours appelé")))
    _cycle_sans_reseau(monkeypatch, [], [ligne("football", "pinnacle")])
    journal = {"etapes": {}}
    cycle.collecter_prematch("complet", NOW, journal)
    assert "pinnacle_secours" not in journal
    _cycle_sans_reseau(monkeypatch, ["sport 29 matchups : HTTP 503"], [ligne("tennis", "pinnacle")])
    monkeypatch.delenv("PINNODDS_API_KEY")
    cycle.collecter_prematch("complet", NOW, journal)
    assert "pinnacle_secours" not in journal


def test_cache_ignore_les_matchs_commences_et_les_caches_trop_vieux(tmp_path):
    S.collecter({29}, NOW, tmp_path, Session(Reponse()))
    assert S.collecter({29}, NOW + timedelta(minutes=10), tmp_path, Session(Reponse())) != []
    assert S.collecter({29}, NOW + timedelta(hours=5, minutes=1), tmp_path, Session(Reponse(statut=503))) == []   # match commencé
    assert S.collecter({29}, NOW + timedelta(hours=3, minutes=1), tmp_path, Session(Reponse(statut=503))) == []   # cache trop vieux
    assert S.collecter({33}, NOW + timedelta(minutes=10), tmp_path, Session(Reponse(statut=503))) == []           # autre sport
    (tmp_path / "pinnacle_secours_cache.json").write_text("{pas du json")
    assert S.collecter({29}, NOW + timedelta(minutes=10), tmp_path, Session(Reponse(statut=503))) == []
