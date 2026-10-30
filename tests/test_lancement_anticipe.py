"""Bookmakers français lancés sans attendre Pinnacle (sports du cycle précédent), Matchbook lancé au départ."""
import inspect
import json
import threading
from datetime import timedelta

from scripts import cycle
from tests.test_collecte_parallele import NOW, _sans_reseau, ligne

VIDE = ([], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0})


def montage(monkeypatch, sports_pin=("football",)):
    """Pinnacle bloque jusqu'à ce que Winamax ait démarré (ou 3 s) : on voit qui attend qui."""
    _sans_reseau(monkeypatch)
    winamax_parti, pinnacle_fini = threading.Event(), threading.Event()
    vu = {}

    def pinnacle():
        vu["pinnacle_a_vu_winamax"] = winamax_parti.wait(3)
        pinnacle_fini.set()
        return [ligne(s, "pinnacle") for s in sports_pin]

    def winamax(sports, *a, **k):
        vu["winamax_sports"] = set(sports)
        vu["winamax_apres_pinnacle"] = pinnacle_fini.is_set()
        winamax_parti.set()
        return VIDE

    def unibet(sports, *a, **k):
        vu["unibet_sports"] = set(sports)
        vu["unibet_apres_pinnacle"] = pinnacle_fini.is_set()
        vu["unibet_radar"] = k.get("radar")
        return VIDE

    monkeypatch.setattr(cycle.pinnacle, "collecter", pinnacle)
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    monkeypatch.setattr(cycle.winamax_direct, "collecter", winamax)
    monkeypatch.setattr(cycle.unibet_direct, "collecter", unibet)
    return vu


def test_premier_cycle_sans_fichier_comportement_actuel(monkeypatch, tmp_path):
    vu = montage(monkeypatch, ("football", "tennis"))
    reprise = tmp_path / "reprise" / "derniere_lecture.json.gz"
    j = {"etapes": {}}
    cycle.collecter_prematch("complet", NOW, j, None, reprise)
    # aucun sport perdu : Winamax a attendu Pinnacle et lit tous les sports du cycle
    assert vu["winamax_apres_pinnacle"] is True and vu["pinnacle_a_vu_winamax"] is False
    assert vu["winamax_sports"] == {"football", "tennis"}
    assert j["sports_francais"]["source"] == "références du cycle"
    doc = json.loads((reprise.parent / "sports_cycle.json").read_text())
    assert set(doc["vus"]) == {"football", "tennis"}


def test_cycle_suivant_francais_lances_sans_attendre_pinnacle(monkeypatch, tmp_path):
    reprise = tmp_path / "derniere_lecture.json.gz"
    cycle.memoriser_sports(reprise, {"football"}, NOW - timedelta(minutes=5))
    vu = montage(monkeypatch, ("football", "basket"))
    j = {"etapes": {}}
    cycle.collecter_prematch("complet", NOW, j, None, reprise)
    assert vu["pinnacle_a_vu_winamax"] is True and vu["winamax_apres_pinnacle"] is False
    assert vu["winamax_sports"] == {"football"}
    # Unibet garde la dépendance au radar Pinnacle : il part après, avec les sports du cycle
    assert vu["unibet_apres_pinnacle"] is True and vu["unibet_sports"] == {"football", "basket"}
    # le sport apparu est noté et lu chez les autres au cycle suivant
    assert j["sports_francais"]["source"] == "cycle précédent"
    assert j["sports_francais"]["nouveaux_au_cycle_suivant"] == ["basket"]
    assert cycle.sports_precedents(reprise, NOW + timedelta(minutes=5)) == {"football", "basket"}


def test_sport_absent_un_cycle_reste_lu_deux_heures(tmp_path):
    reprise = tmp_path / "derniere_lecture.json.gz"
    cycle.memoriser_sports(reprise, {"football", "tennis"}, NOW)
    cycle.memoriser_sports(reprise, {"football"}, NOW + timedelta(minutes=5))      # 403 passager sur le tennis
    assert cycle.sports_precedents(reprise, NOW + timedelta(minutes=10)) == {"football", "tennis"}
    assert cycle.sports_precedents(reprise, NOW + timedelta(hours=2, minutes=1)) == {"football"}
    cycle.memoriser_sports(reprise, set(), NOW + timedelta(minutes=15))             # références en panne
    assert cycle.sports_precedents(reprise, NOW + timedelta(minutes=20)) == {"football", "tennis"}


def test_fichier_absent_vieux_ou_illisible(tmp_path):
    assert cycle.sports_precedents(None, NOW) is None
    reprise = tmp_path / "derniere_lecture.json.gz"
    assert cycle.sports_precedents(reprise, NOW) is None
    cycle.memoriser_sports(reprise, {"football"}, NOW - timedelta(hours=3))
    assert cycle.sports_precedents(reprise, NOW) is None
    (tmp_path / "sports_cycle.json").write_text("{pas du json")
    assert cycle.sports_precedents(reprise, NOW) is None
    (tmp_path / "sports_cycle.json").write_text('{"vus": ["football"]}')
    assert cycle.sports_precedents(reprise, NOW) is None
    cycle.memoriser_sports(None, {"football"}, NOW)   # sans reprise : rien, sans erreur


def test_matchbook_lance_au_depart():
    src = inspect.getsource(cycle.main)
    depart = src.index("futur_mb = pool_mb.submit(appliquer_matchbook")
    assert depart < src.index("collecter_prematch(args.mode") < src.index("appliquer_smarkets(")
    assert src.index("appliquer_smarkets(") < src.index("mb_lignes = futur_mb.result()")
    assert src.count("appliquer_matchbook(") == 0
