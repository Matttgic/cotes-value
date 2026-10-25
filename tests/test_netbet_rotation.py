"""NetBet : lecture tournante (les pages les plus anciennes d'abord) et mémoire de 15 minutes."""
from datetime import timedelta

from cotes.direct import netbet
from tests.test_netbet_direct import MARCHES, NOW, _event, _html, _Reponse

BASE = "https://www.netbet.fr"


class Budget:
    """Échéance qui s'épuise après `n` pages."""

    def __init__(self, n):
        self.n, self.lues = n, 0

    def ok(self):
        return self.lues < self.n

    def reste(self):
        return 30.0 if self.ok() else 0.0


class Site:
    def __init__(self, pages, budget=None, codes=None):
        self.pages, self.budget, self.codes, self.urls = pages, budget, codes or {}, []

    def get(self, url, timeout=None, headers=None):
        chemin = url[len(BASE):]
        self.urls.append(chemin)
        if self.budget is not None:
            self.budget.lues += 1
        return _Reponse(self.codes.get(chemin, 200), self.pages.get(chemin, _html([])))


def _ev(eid, home, start="2026-10-18T20:45:00.000+02:00"):
    return _event(eid, "pm", home, home + " B", MARCHES, start=start)


def _catalogue():
    """Football : 3 compétitions ; tennis : 1. Chaque page a son match."""
    return {
        "/football": _html([_ev(1, "Lyon")], [{"url": "/football/c1", "events": 9}, {"url": "/football/c2", "events": 5},
                                               {"url": "/football/c3", "events": 1}]),
        "/tennis": _html([_ev(2, "Sinner")], [{"url": "/tennis/t1", "events": 3}]),
        "/football/c1": _html([_ev(11, "Paris")]), "/football/c2": _html([_ev(12, "Lens")]),
        "/football/c3": _html([_ev(13, "Brest")]), "/tennis/t1": _html([_ev(21, "Alcaraz")]),
    }


def _cycle(reserve, n, minutes=0, pages=None, codes=None):
    budget = Budget(n)
    site = Site(pages or _catalogue(), budget, codes)
    lignes, meta = netbet.collecter({"football", "tennis"}, 36, session=site, pause=(0, 0),
                                    maintenant=NOW + timedelta(minutes=minutes), echeance=budget, reserve=reserve)
    return site.urls, lignes, meta


def test_premier_passage_pages_de_sport_puis_competitions_tour_a_tour():
    urls, _, meta = _cycle({}, 5)
    assert urls == ["/football", "/tennis", "/football/c1", "/tennis/t1", "/football/c2"]
    assert meta["pages"] == {"lues": 5, "a_lire": 6} and "budget" in meta["erreurs"]


def test_le_passage_suivant_lit_d_abord_ce_qui_ne_l_a_jamais_ete_puis_le_plus_ancien():
    _, _, m1 = _cycle({}, 5)
    urls, _, m2 = _cycle(m1["reserve"], 3, minutes=5)
    assert urls == ["/football/c3", "/football", "/tennis"]          # jamais lue, puis les plus anciennes
    urls, _, _ = _cycle(m2["reserve"], 6, minutes=10)
    assert urls[:3] == ["/football/c1", "/tennis/t1", "/football/c2"]


def test_cotes_des_pages_non_relues_gardees_15_minutes_avec_leur_heure():
    _, l1, m1 = _cycle({}, 6)
    assert {l["domicile"] for l in l1} == {"Lyon", "Sinner", "Paris", "Lens", "Brest", "Alcaraz"}
    _, l2, m2 = _cycle(m1["reserve"], 1, minutes=5)                 # une seule page relue
    assert {l["domicile"] for l in l2} == {"Lyon", "Sinner", "Paris", "Lens", "Brest", "Alcaraz"}
    anciennes = [l for l in l2 if l["domicile"] == "Alcaraz"]
    assert anciennes and all(l["collecte"] == NOW.isoformat(timespec="seconds") for l in anciennes)
    _, l3, _ = _cycle(m2["reserve"], 1, minutes=16)
    assert "Alcaraz" not in {l["domicile"] for l in l3}               # plus de 15 min : oubliée


def test_une_competition_disparue_de_sa_page_de_sport_quitte_la_file():
    _, _, m1 = _cycle({}, 6)
    pages = _catalogue()
    pages["/football"] = _html([_ev(1, "Lyon")], [{"url": "/football/c1", "events": 9}])
    urls, _, m2 = _cycle(m1["reserve"], 10, minutes=5, pages=pages)
    assert "/football/c2" not in urls and "/football/c3" not in urls
    assert m2["reserve"]["liens"]["football"] == ["/football/c1"]
    assert "/football/c2" not in m2["reserve"]["pages"]


def test_page_en_erreur_passe_en_fin_de_file_et_429_arrete():
    urls, _, m1 = _cycle({}, 6, codes={"/football/c1": 500})
    assert "HTTP 500" in m1["erreurs"]
    urls, _, _ = _cycle(m1["reserve"], 1, minutes=5)
    assert urls != ["/football/c1"]                                   # ne bloque pas la tête de file
    urls, _, _ = _cycle({}, 6, codes={"/tennis": 429})
    assert urls == ["/football", "/tennis"]


def test_sans_reserve_le_comportement_d_origine_est_garde():
    budget = Budget(3)
    site = Site(_catalogue(), budget)
    _, meta = netbet.collecter({"football", "tennis"}, 36, session=site, pause=(0, 0), maintenant=NOW, echeance=budget)
    assert site.urls == ["/football", "/tennis", "/football/c1"] and "reserve" not in meta


def test_reserve_abimee_ne_casse_pas_la_lecture():
    for abime in ({"pages": "x", "liens": [1], "lignes": "y"}, {"pages": {"/football": 3}, "liens": {"football": "z"}}):
        urls, lignes, meta = _cycle(abime, 2)
        assert urls == ["/football", "/tennis"] and lignes
