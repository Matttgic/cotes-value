"""Smarkets : fixture locale, même milieu que Betfair, écart affiché, drapeau éteint."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from cotes import comparaison, smarkets
from cotes.live_pauses import REFERENCES as LIVE_REFERENCES
from cotes.simulation import STRATEGIE, moyennes_ecarts
from cotes.strategie_gemini import GEMINI
from cotes.strategie_jules_v2 import JULES_V2
from cotes.strategie_m3 import M3

FIX = json.loads((Path(__file__).parent / "fixtures" / "smarkets_football.json").read_text(encoding="utf-8"))
MAINTENANT = datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc)
FRANCAIS = ("winamax", "betclic", "unibet", "pmu", "olybet")


class Reponse:
    def __init__(self, doc, status=200):
        self.status_code = status
        self._doc = doc
        self.text = json.dumps(doc)

    def json(self):
        return self._doc


class Session:
    def __init__(self, fix=FIX):
        self.fix = fix
        self.urls = []

    def get(self, url, timeout=30, headers=None):
        self.urls.append(url)
        if "/quotes/" in url:
            return Reponse(self.fix["quotes"])
        if "/contracts/" in url:
            return Reponse(self.fix["contracts"])
        if "/markets/" in url:
            return Reponse(self.fix["markets"])
        if "pagination_last_id" in url:
            return Reponse(self.fix["events_suite"])
        if "/events/" in url:
            return Reponse(self.fix["events"])
        return Reponse({"error": "introuvable"}, status=404)


def _collecter(session=None):
    return smarkets.collecter({"football"}, 36, session or Session(), maintenant=MAINTENANT)


def test_prix_publics_milieu_identique_a_betfair():
    session = Session()
    justes, meta = _collecter(session)
    assert meta["ok"] and not meta["erreurs"]
    assert any("pagination_last_id" in u for u in session.urls)
    gagnant = [l for l in justes if l["marche"] == "RESULTAT_1N2"]
    assert {l["issue"] for l in gagnant} == {"DOM", "NUL", "EXT"}
    dom = next(l for l in gagnant if l["issue"] == "DOM")
    assert dom["domicile"] == "Fulham" and dom["exterieur"] == "Crystal Palace"
    assert dom["achat"][0]["price"] == round(10000 / 4808, 4)
    assert dom["vente"][0]["price"] == round(10000 / 4505, 4)
    assert dom["liquidite"] == round(min(1925001, 587593) / 10000, 2)
    assert dom["source"] == "Smarkets" and dom["bookmaker"] == "smarkets"
    assert comparaison._fiable("Smarkets", dom)
    brut = [{k: l[k] for k in ("cle_marche", "marche", "periode", "ligne", "issue", "achat", "vente", "match_id")}
            for l in gagnant]
    betfair = {l["issue"]: l["proba_juste"] for l in comparaison.reference_betfair(brut)}
    sm = {l["issue"]: l["proba_juste"] for l in comparaison.reference_echange(brut, "Smarkets")}
    assert sm == betfair
    assert all(l["source"] == "Smarkets" for l in comparaison.reference_echange(brut, "Smarkets"))
    assert all(l["source"] == "Betfair" for l in comparaison.reference_betfair(brut))


def test_vente_absente_retire_le_marche_spread_et_liquidite_restent_lisibles():
    justes, _ = _collecter()
    assert "TOTAL" not in {l["marche"] for l in justes}
    handicaps = [l for l in justes if l["marche"] == "HANDICAP"]
    assert {l["issue"] for l in handicaps} == {"DOM", "EXT"}
    assert handicaps[0]["ligne"] == -0.5 and handicaps[0]["ecart_achat_vente"] > 0
    dnb = [l for l in justes if l["marche"] == "DRAW_NO_BET"]
    assert dnb and dnb[0]["ecart_achat_vente"] > 0.05
    assert all(not comparaison._fiable("Smarkets", l) for l in dnb)
    btts = [l for l in justes if l["marche"] == "BOTH_TEAMS_TO_SCORE"]
    assert btts and btts[0]["liquidite"] < 20
    assert all(not comparaison._fiable("Smarkets", l) for l in btts)
    assert "CORNERS" not in {l["marche"] for l in justes}
    blob = json.dumps(justes).lower()
    assert all(nom not in blob for nom in FRANCAIS)


def test_periode_sans_prolongation_explicite_reste_ambigue():
    assert smarkets.periode_match("hockey", "Winner", "MATCH") == "MATCH?"
    assert smarkets.periode_match("basket", "Moneyline", "MATCH") == "MATCH?"
    assert smarkets.periode_match("hockey", "Winner including overtime", "MATCH") == "MATCH"
    assert smarkets.periode_match("hockey", "Regular time winner", "MATCH") == "TEMPS_REG"
    assert smarkets.periode_match("football", "Full-time result", "MATCH") == "MATCH"


def test_at_place_lexterieur_devant():
    home, away = smarkets._equipes({"name": "Crystal Palace at Fulham"}, [])
    assert (home, away) == ("Fulham", "Crystal Palace")


def test_drapeau_eteint_par_defaut_et_allume_seulement_si_oui(monkeypatch):
    monkeypatch.delenv("SMARKETS_DANS_DECISION", raising=False)
    assert smarkets.dans_decision() is False
    assert smarkets.hors_consensus() == frozenset({"Smarkets"})
    refs = {"Pinnacle": [], "Betfair": [], "Polymarket": []}
    smarkets.ajouter_table(refs, [{"bookmaker": "smarkets"}])
    assert refs["Smarkets"][0]["bookmaker"] == "smarkets"
    for valeur in ("non", "off", "false", ""):
        monkeypatch.setenv("SMARKETS_DANS_DECISION", valeur)
        assert smarkets.dans_decision() is False and "Smarkets" in smarkets.hors_consensus()
    monkeypatch.setenv("SMARKETS_DANS_DECISION", "oui")
    assert smarkets.dans_decision() is True and smarkets.hors_consensus() == frozenset()
    assert "Smarkets" not in STRATEGIE["references"]
    assert "Smarkets" not in GEMINI["references"]
    assert "Smarkets" not in JULES_V2["references"]
    assert "Smarkets" not in M3["references"]
    assert "Smarkets" not in LIVE_REFERENCES


def test_table_smarkets_separee_du_consensus(monkeypatch):
    """10 € contre Smarkets, même drapeau éteint. Le consensus des autres tables ne bouge pas."""
    from datetime import datetime, timezone

    from cotes.simulation import MISE, placer

    moment = "2030-01-01T19:00:00+00:00"
    debut = "2030-01-01T20:00:00+00:00"
    base = {"sport": "football", "ligue": "L", "domicile": "Fulham", "exterieur": "Crystal Palace",
            "debut": debut, "collecte": moment, "marche": "VAINQUEUR", "periode": "MATCH",
            "ligne": None, "issue": "DOM"}
    fr = [{**base, "source": "winamax", "bookmaker": "winamax", "match_id": "w|1", "cote": 2.10}]

    def ref(mid, proba, source):
        return {**base, "source": source, "match_id": mid, "proba_juste": proba,
                "cote_juste": round(1 / proba, 4), "ecart_achat_vente": 0.02, "liquidite": 50,
                "marge_pinnacle": 0.04}

    refs = {"Pinnacle": [ref("p1", 0.40, "pinnacle")], "Betfair": [ref("b1", 0.40, "betfair")],
            "Smarkets": [{**ref("s1", 0.55, "Smarkets"), "bookmaker": "smarkets"}]}
    monkeypatch.delenv("SMARKETS_DANS_DECISION", raising=False)
    hors = smarkets.hors_consensus()
    op = comparaison.comparer(fr, refs, ecart_min=-1, temoin_brut=False, hors_consensus=hors)
    par = {o["reference"]: o for o in op}
    assert par["Smarkets"]["ecart"] == round(2.10 * 0.55 - 1, 4)
    assert par["Smarkets"]["suspect"] is None
    assert par["Consensus"]["sources"] == "Betfair+Pinnacle"
    assert par["Consensus"]["proba_juste"] == 0.4
    assert par["Pinnacle"]["suspect"] is None
    sans = comparaison.comparer(fr, {k: v for k, v in refs.items() if k != "Smarkets"},
                                ecart_min=-1, temoin_brut=False)
    assert {o["reference"]: (o["proba_juste"], o["ecart"], o["suspect"])
            for o in sans if o["reference"] in ("Pinnacle", "Betfair", "Consensus")} == {
        o["reference"]: (o["proba_juste"], o["ecart"], o["suspect"])
        for o in op if o["reference"] in ("Pinnacle", "Betfair", "Consensus")}
    clos = comparaison.index_cotes_justes(fr, refs, hors_consensus=hors)
    cle = ("w|1", ("VAINQUEUR", "MATCH", None, "DOM"))
    assert abs(clos[cle]["Smarkets"][0] - 0.55) < 1e-9
    assert abs(clos[cle]["Consensus"][0] - 0.4) < 1e-9
    paris = []
    pris = placer([par["Smarkets"]], paris, datetime(2030, 1, 1, 19, 5, tzinfo=timezone.utc))
    assert len(pris) == 1 and pris[0]["reference"] == "Smarkets" and pris[0]["mise"] == MISE == 10
    monkeypatch.setenv("SMARKETS_DANS_DECISION", "oui")
    avec = comparaison.comparer(fr, refs, ecart_min=-1, temoin_brut=False,
                                hors_consensus=smarkets.hors_consensus())
    cons = next(o for o in avec if o["reference"] == "Consensus")
    assert cons["sources"] == "Betfair+Pinnacle+Smarkets"
    assert abs(cons["proba_juste"] - (0.40 + 0.40 + 0.55) / 3) < 1e-5
    assert cons["suspect"] == "références en désaccord"


def test_ecart_affiche_meme_hors_decision():
    moment = "2026-10-18T12:00:00+00:00"
    debut = "2026-10-18T15:00:00+00:00"
    fr = {"source": "winamax", "bookmaker": "winamax", "sport": "football", "match_id": "w|1",
          "domicile": "Fulham", "exterieur": "Crystal Palace", "debut": debut, "collecte": moment,
          "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None, "issue": "DOM", "cote": 2.20}
    sm = {"source": "Smarkets", "bookmaker": "smarkets", "sport": "football", "match_id": "smarkets|1",
          "domicile": "Fulham", "exterieur": "Crystal Palace", "debut": debut, "collecte": moment,
          "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None, "issue": "DOM",
          "proba_juste": 0.48, "cote_juste": 2.0833, "ecart_achat_vente": 0.02, "liquidite": 50}
    opp = {**fr, "detecte": moment, "reference": "Pinnacle", "ecart": 0.05}
    comparaison.annoter_ecarts([opp], [fr], {"Betfair": [], "Polymarket": [], "Smarkets": [sm]})
    assert opp["ecart_smarkets"] == round(2.20 * 0.48 - 1, 4)
    assert opp["ecart_betfair"] is None and opp["ecart_polymarket"] is None
    assert opp["reference"] == "Pinnacle"


def test_moyenne_des_paris_regles_reutilise_lancien_ecart():
    base = {"simulation": "A", "mise": 10, "marche": "VAINQUEUR", "periode": "MATCH", "ligne": None,
            "issue": "DOM", "joueur": None, "cote": 2.2, "bookmaker": "Winamax",
            "detecte": "2026-10-01T10:00:00+00:00"}
    ancien = {**base, "match_id": "m1", "reference": "Betfair", "ecart": 0.04, "statut": "gagne", "gain": 12}
    nouveau = {**base, "match_id": "m2", "reference": "Pinnacle", "ecart": 0.05, "statut": "perdu",
               "gain": -10, "ecart_betfair": 0.02, "ecart_smarkets": 0.03}
    cours = {**base, "match_id": "m3", "reference": "Smarkets", "ecart": 0.9, "statut": "en_cours"}
    out = moyennes_ecarts([ancien, nouveau, cours])
    assert out["Betfair"] == {"moyenne": round((0.04 + 0.02) / 2, 4), "n": 2}
    assert out["Smarkets"] == {"moyenne": 0.03, "n": 1}
    assert out["Polymarket"] == {"moyenne": None, "n": 0}


def test_erreur_http_ne_journalise_pas_le_corps():
    class Panne:
        def get(self, url, timeout=30, headers=None):
            class R:
                status_code = 500
                text = "HsToken secret-ne-pas-journaliser"

                def json(self):
                    return {"secret": "HsToken secret-ne-pas-journaliser"}
            return R()

    lignes, meta = smarkets.collecter({"football"}, 12, Panne(), maintenant=MAINTENANT)
    assert lignes == [] and meta["ok"] is False
    assert meta["erreurs"] == ["HTTP 500"]
    assert "secret" not in json.dumps(meta)


def test_403_coupe_sans_rafale(monkeypatch):
    appels = []

    class Bloque:
        def get(self, url, timeout=30, headers=None):
            appels.append(url)

            class R:
                status_code = 403
                text = "secret-ne-pas-journaliser"

                def json(self):
                    return {"secret": "HsToken secret-ne-pas-journaliser"}

            return R()

    monkeypatch.setattr(smarkets.time, "sleep", lambda s: None)
    lignes, meta = smarkets.collecter({"football", "tennis"}, 12, Bloque(), maintenant=MAINTENANT)
    assert lignes == []
    assert meta["erreurs"] == ["HTTP 403"]
    assert "secret" not in json.dumps(meta)
    assert len(appels) == 2
    assert all("football_match" in u for u in appels)


def test_sports_vides_ne_contactent_pas_le_reseau():
    class Boom:
        def get(self, *args, **kwargs):
            raise AssertionError("réseau")

    lignes, meta = smarkets.collecter(set(), session=Boom(), maintenant=MAINTENANT)
    assert lignes == [] and meta == {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}


def test_bilan_affiche_ecart_vs_smarkets(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import site_web
    pari = {"id": "p1", "simulation": "A", "reference": "Betfair", "match_id": "m1", "marche": "TOTAL",
            "periode": "MATCH", "ligne": 2.5, "issue": "PLUS", "detecte": "2026-10-01T10:00:00+00:00",
            "statut": "gagne", "cote": 2.1, "bookmaker": "Winamax", "sport": "football", "mise": 10,
            "gain": 11, "clv": 0.02, "ecart": 0.04, "ecart_smarkets": 0.03, "domicile": "Fulham",
            "exterieur": "Crystal Palace", "pari": "Plus de 2,5"}
    (tmp_path / "paris.json").write_text(json.dumps([pari]), encoding="utf-8")
    html = site_web.construire(tmp_path, tmp_path / "site").read_text(encoding="utf-8")
    assert "écart vs Smarkets" in html and "écart vs Betfair" in html and "écart vs Polymarket" in html
    d = json.loads(__import__("re").search(r"const D = (\{.*?\});\n", html, __import__("re").S).group(1).replace("<\\/", "</"))
    assert d["ecarts_references"]["Smarkets"] == {"moyenne": 0.03, "n": 1}
    assert d["ecarts_references"]["Betfair"]["n"] == 1
    assert "ecart_smarkets" in d["catalogue"]["champs"]
    assert "Smarkets" in d["references"]
