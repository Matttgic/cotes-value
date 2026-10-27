"""Matchbook : connecteur public, mêmes seuils de pari que les autres références, hors stratégies."""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from cotes import comparaison
from cotes.controle import ORDRE_REFERENCES
from cotes.direct import matchbook as mb
from cotes.laboratoire import REGLES
from cotes.simulation import MISE, REFERENCES, STRATEGIE, bilan, placer
from cotes.strategie_chatgpt import CHATGPT, paris_chatgpt
from cotes.strategie_coeur import COEUR
from cotes.strategie_conseil import CONSEIL_RETARD
from cotes.strategie_defi import REFERENCES_DEFI_1, REFERENCES_DEFI_4, paris_defi_1, paris_defi_4
from cotes.strategie_eden import EDEN, paris_eden
from cotes.strategie_gemini import GEMINI, paris_gemini
from cotes.strategie_grok import (GROK_9, GROK_10, REFERENCES_SHARP, paris_grok_9, paris_grok_10)
from cotes.strategie_jules import JULES, paris_jules
from cotes.strategie_jules_v2 import JULES_V2, paris_jules_v2
from cotes.strategie_liquidite import LIQUIDITE
from cotes.strategie_m3 import M3, paris_m3
from cotes.strategie_qwen import REGLE as QWEN
from cotes.strategies_prudentes import selections_prudentes
from scripts import cycle
from tests.test_strategie_defi import PIN, PIN4
from tests.test_strategie_jules_v2 import pari

ICI = Path(__file__).parent
DOC = json.loads((ICI / "fixtures" / "matchbook_events.json").read_text())
LILLE = DOC["events"][0]
TENNIS = DOC["events"][1]
AVANT_LILLE = datetime(2026, 10, 30, 8, 0, tzinfo=timezone.utc)
MARQUE = "corps-interdit"


class Rep:
    def __init__(self, code, doc=None, text=MARQUE):
        self.status_code, self._doc, self.text = code, doc, text

    def json(self):
        if self._doc is None:
            raise ValueError(MARQUE)
        return self._doc


class Session:
    def __init__(self, reponses):
        self.reponses, self.appels = list(reponses), []

    def get(self, url, params=None, timeout=None, headers=None):
        self.appels.append((url, dict(params or {}), dict(headers or {})))
        return self.reponses.pop(0)


def _par(lignes, marche, periode="MATCH", ligne=None):
    return {l["issue"]: l for l in lignes
            if l["marche"] == marche and l["periode"] == periode and l["ligne"] == ligne}


def test_1n2_back_lay_lille_lens():
    l = _par(mb.lignes_brutes([LILLE], "football", AVANT_LILLE), "RESULTAT_1N2")
    assert set(l) == {"DOM", "NUL", "EXT"}
    assert l["DOM"]["achat"] == [{"price": 2.52, "liquidity": 11.95}]
    assert l["DOM"]["vente"] == [{"price": 2.58, "liquidity": 23.41}]
    assert l["NUL"]["achat"][0]["price"] == 3.7 and l["EXT"]["vente"][0]["price"] == 2.98
    assert l["DOM"]["ligue"] == "France Ligue 1" and l["DOM"]["source"] == "Matchbook"


def test_total_handicap_quart_et_mi_temps():
    b = mb.lignes_brutes([LILLE], "football", AVANT_LILLE)
    t = _par(b, "TOTAL", ligne=2.5)
    assert t["PLUS"]["achat"][0]["price"] == 1.76 and t["MOINS"]["vente"][0]["price"] == 2.32
    assert _par(b, "TOTAL", "MT1", 1.5)
    lignes_h = {l["ligne"] for l in b if l["marche"] == "HANDICAP"}
    assert {-0.5, 0.0, 0.25, -0.25} <= lignes_h
    assert _par(b, "RESULTAT_1N2", "MT1")
    assert {l["issue"] for l in b if l["marche"] == "HALF_TIME_FULL_TIME"} >= {"DOM/DOM", "NUL/EXT"}


def test_quart_de_but_depuis_le_nom():
    assert mb._handicap_runner({"name": "Lille OSC (-0.5/1.0)"}) == -0.75
    assert mb._handicap_runner({"name": "RC Lens (+0.0/0.5)"}) == 0.25
    assert mb._handicap_runner({"name": "Lille OSC -1.5", "handicap": -1.5}) == -1.5


def test_cote_juste_par_reference_echange():
    j = comparaison.reference_echange(mb.lignes_brutes([LILLE], "football", AVANT_LILLE), mb.NOM_SOURCE)
    dom = [l for l in j if l["marche"] == "RESULTAT_1N2" and l["periode"] == "MATCH" and l["issue"] == "DOM"][0]
    assert 2.52 <= dom["cote_juste"] <= 2.58
    for l in j:
        assert 1 < l["achat"][0]["price"] <= l["vente"][0]["price"]


def test_cote_manquante_vide_issue():
    ev = copy.deepcopy(LILLE)
    mo = [m for m in ev["markets"] if m["name"] == "Match Odds"][0]
    mo["runners"][0]["prices"] = [p for p in mo["runners"][0]["prices"] if p["side"] == "back"]
    j = comparaison.reference_echange(mb.lignes_brutes([ev], "football", AVANT_LILLE), mb.NOM_SOURCE)
    assert not [l for l in j if l["marche"] == "RESULTAT_1N2" and l["periode"] == "MATCH"]


def test_horizon_et_live_exclus():
    assert mb.lignes_brutes([LILLE], "football", datetime(2026, 10, 27, 1, tzinfo=timezone.utc), 36) == []
    ev = dict(LILLE, **{"in-running-flag": True})
    assert mb.lignes_brutes([ev], "football", AVANT_LILLE) == []


def test_tennis_vainqueur_et_jeux():
    b = mb.lignes_brutes([TENNIS], "tennis", datetime(2026, 10, 27, 0, 0, tzinfo=timezone.utc))
    v = _par(b, "VAINQUEUR")
    assert set(v) == {"DOM", "EXT"} and v["DOM"]["achat"][0]["price"] >= 3.0
    assert any(l["marche"] == "JEUX_TOTAL" for l in b) and any(l["marche"] == "JEUX_HANDICAP" for l in b)


def test_off_aucune_requete_direct_par_defaut():
    s = Session([])
    justes, info = mb.collecter(session=s, environ={"SOURCE_MATCHBOOK": "off"})
    assert justes == [] and info["mode"] == "off" and info["ok"] and s.appels == []
    assert mb.mode({}) == "direct"
    assert mb.mode({"SOURCE_MATCHBOOK": "  Direct "}) == "direct"
    assert mb.mode({"SOURCE_MATCHBOOK": "inconnu"}) == "direct"
    assert mb.hors_consensus() == frozenset({"Matchbook"})


def test_collecte_une_requete_par_sport_sans_identifiant():
    s = Session([Rep(200, {"total": 1, "events": [LILLE]}), Rep(200, {"total": 0, "events": []})])
    justes, info = mb.collecter(session=s, maintenant=AVANT_LILLE,
                                environ={"SOURCE_MATCHBOOK": "shadow"}, pause=(0, 0))
    assert info["requetes"] == 2 and info["erreurs"] == [] and justes
    url, params, headers = s.appels[0]
    assert url.endswith("/edge/rest/events") and params["sport-ids"] == 15 and params["per-page"] == 200
    assert params["before"] == int(AVANT_LILLE.timestamp()) + 36 * 3600
    assert headers["Accept"] == "application/json"
    assert not any("session" in k.lower() or "auth" in k.lower() for k in headers)
    assert MARQUE not in str(info)


def test_direct_par_defaut_lit_les_deux_sports():
    s = Session([Rep(200, {"total": 1, "events": [LILLE]}), Rep(200, {"total": 0, "events": []})])
    justes, info = mb.collecter(session=s, maintenant=AVANT_LILLE, environ={}, pause=(0, 0))
    assert info["mode"] == "direct" and info["requetes"] == 2 and justes
    assert s.appels[0][1]["sport-ids"] == 15 and s.appels[1][1]["sport-ids"] == 9


def test_pagination():
    page = {"total": 250, "events": [LILLE]}
    s = Session([Rep(200, page), Rep(200, page), Rep(200, {"total": 0, "events": []})])
    _, info = mb.collecter(session=s, maintenant=AVANT_LILLE,
                           environ={"SOURCE_MATCHBOOK": "direct"}, pause=(0, 0))
    assert [a[1]["offset"] for a in s.appels] == [0, 200, 0]
    assert info["erreurs"] == []


def test_403_429_401_arretent_sans_corps():
    for code in (401, 403, 429):
        s = Session([Rep(code)])
        justes, info = mb.collecter(session=s, maintenant=AVANT_LILLE,
                                    environ={"SOURCE_MATCHBOOK": "direct"}, pause=(0, 0))
        assert justes == [] and info["erreurs"] == [f"HTTP {code}"] and len(s.appels) == 1
        assert info["ok"] is False and MARQUE not in str(info)


def test_500_trois_essais_sans_journaliser_le_corps():
    s = Session([Rep(500), Rep(500), Rep(500)])
    justes, info = mb.collecter(sports={"football"}, session=s, maintenant=AVANT_LILLE,
                                environ={"SOURCE_MATCHBOOK": "direct"}, pause=(0, 0))
    assert justes == [] and info["erreurs"] == ["HTTP 500"] and info["requetes"] == 3
    assert MARQUE not in str(info)


def _ligne(mid, proba, source, domicile, exterieur):
    return {"source": source, "sport": "football", "ligue": "L", "domicile": domicile,
            "exterieur": exterieur, "debut": "2030-01-01T20:00:00+00:00",
            "collecte": "2030-01-01T19:00:00+00:00", "marche": "VAINQUEUR", "periode": "MATCH",
            "ligne": None, "issue": "DOM", "match_id": mid, "proba_juste": proba,
            "cote_juste": round(1 / proba, 4), "ecart_achat_vente": 0.01, "liquidite": 50,
            "marge_pinnacle": 0.04}


def _opp(cote, proba, domicile="Lille", exterieur="Lens"):
    moment = "2030-01-01T19:00:00+00:00"
    debut = "2030-01-01T20:00:00+00:00"
    fr = [{"source": "winamax", "bookmaker": "Winamax", "sport": "football", "ligue": "L",
           "match_id": "w|" + domicile, "domicile": domicile, "exterieur": exterieur,
           "debut": debut, "collecte": moment, "marche": "VAINQUEUR", "periode": "MATCH",
           "ligne": None, "issue": "DOM", "cote": cote}]
    refs = {"Pinnacle": [_ligne("p|" + domicile, 0.40, "pinnacle", domicile, exterieur)],
            "Betfair": [_ligne("b|" + domicile, 0.40, "betfair", domicile, exterieur)],
            "Matchbook": [_ligne("m|" + domicile, proba, "Matchbook", domicile, exterieur)]}
    return comparaison.comparer(fr, refs, hors_consensus=mb.hors_consensus())


def test_seuils_2_et_5_pourcent_bilan_global():
    """Mêmes tranches que Pinnacle : 2 % en A, 5 % en D, les deux dans « Toutes »."""
    bas = _opp(2.10, 1.02 / 2.10, "Lille", "Lens")
    haut = _opp(2.10, 0.5, "Paris", "Lyon")
    mb2 = next(o for o in bas if o["reference"] == "Matchbook")
    mb5 = next(o for o in haut if o["reference"] == "Matchbook")
    assert mb2["ecart"] == 0.02 and mb2["suspect"] is None
    assert mb5["ecart"] == 0.05 and mb5["suspect"] is None
    sous = _opp(2.10, 1.019 / 2.10, "Nice", "Rennes")
    assert not any(o["reference"] == "Matchbook" and o["ecart"] >= 0.02 for o in sous)
    paris = []
    pris = placer([mb2, mb5], paris, datetime(2030, 1, 1, 19, 5, tzinfo=timezone.utc))
    assert [p["simulation"] for p in pris] == ["D", "A"]
    assert {p["reference"] for p in pris} == {"Matchbook"}
    assert {p["mise"] for p in pris} == {MISE} == {10}
    resume = bilan(paris)
    assert resume["A|Matchbook"]["paris"] == 1 and resume["D|Matchbook"]["paris"] == 1
    assert resume["A|Toutes"]["paris"] == 1 and resume["D|Toutes"]["paris"] == 1


def test_table_separee_du_consensus():
    """Un prix Matchbook très différent ne rend pas Pinnacle suspect et ne change pas le Consensus."""
    moment = "2030-01-01T19:00:00+00:00"
    debut = "2030-01-01T20:00:00+00:00"
    base = {"sport": "football", "ligue": "L", "domicile": "Lille", "exterieur": "Lens",
            "debut": debut, "collecte": moment, "marche": "VAINQUEUR", "periode": "MATCH",
            "ligne": None, "issue": "DOM"}
    fr = [{**base, "source": "winamax", "bookmaker": "winamax", "match_id": "w|1", "cote": 2.10}]
    refs = {"Pinnacle": [_ligne("p1", 0.40, "pinnacle", "Lille", "Lens")],
            "Betfair": [_ligne("b1", 0.40, "betfair", "Lille", "Lens")],
            "Matchbook": [_ligne("m1", 0.55, "Matchbook", "Lille", "Lens")]}
    hors = mb.hors_consensus()
    op = comparaison.comparer(fr, refs, ecart_min=-1, hors_consensus=hors)
    par = {o["reference"]: o for o in op}
    assert par["Matchbook"]["ecart"] == round(2.10 * 0.55 - 1, 4)
    assert par["Matchbook"]["suspect"] is None
    assert par["Consensus"]["sources"] == "Betfair+Pinnacle"
    assert par["Consensus"]["proba_juste"] == 0.4
    assert "Matchbook" not in par["Consensus"]["sources"]
    assert par["Pinnacle"]["suspect"] is None
    sans = comparaison.comparer(fr, {k: v for k, v in refs.items() if k != "Matchbook"}, ecart_min=-1)
    assert {o["reference"]: (o["proba_juste"], o["ecart"], o["suspect"])
            for o in sans if o["reference"] in ("Pinnacle", "Betfair", "Consensus")} == {
        o["reference"]: (o["proba_juste"], o["ecart"], o["suspect"])
        for o in op if o["reference"] in ("Pinnacle", "Betfair", "Consensus")}


def _choisis(fonction, paris):
    retenus = fonction(paris)
    return {p["id"] for p in paris if id(p) in retenus}


def _jumeau(reference, pid="pin"):
    return pari(pid, **{**PIN, "reference": reference})


def test_strategies_sans_matchbook_selections_inchangees():
    comme_pinnacle = _jumeau("Pinnacle", "seul")
    assert paris_grok_9([comme_pinnacle]) == {id(comme_pinnacle)}
    assert paris_defi_1([comme_pinnacle]) == {id(comme_pinnacle)}
    mb_seul = _jumeau("Matchbook", "seul")
    assert paris_grok_9([mb_seul]) == set()
    assert paris_grok_10([mb_seul]) == set()
    assert paris_defi_1([mb_seul]) == set()
    vrai = pari("gros", **PIN4)
    gros = pari("gros", **{**PIN4, "reference": "Matchbook"})
    assert paris_defi_4([vrai]) == {id(vrai)}
    assert paris_defi_4([gros]) == set()

    def fiche(reference, pid):
        p = pari(pid, **{**PIN, "reference": reference})
        return p

    pin = fiche("Pinnacle", "pin")
    mb_pari = fiche("Matchbook", "mbx")
    mb_pari.update(domicile=pin["domicile"], exterieur=pin["exterieur"],
                   match_reference=pin["match_reference"], match_id=pin["match_id"])
    seul = {cle: {p["id"] for p in [pin] if id(p) in ids}
            for cle, ids in selections_prudentes([pin]).items()}
    pin2 = fiche("Pinnacle", "pin")
    mb2 = fiche("Matchbook", "mbx")
    mb2.update(domicile=pin2["domicile"], exterieur=pin2["exterieur"],
               match_reference=pin2["match_reference"], match_id=pin2["match_id"])
    avec = {cle: {p["id"] for p in [pin2, mb2] if id(p) in ids}
            for cle, ids in selections_prudentes([pin2, mb2]).items()}
    assert avec == seul
    assert all("mbx" not in ids for ids in avec.values())

    selecteurs = (paris_chatgpt, paris_gemini, paris_jules, paris_jules_v2,
                  paris_eden, paris_m3)
    for fonction in selecteurs:
        a = fiche("Pinnacle", "pin")
        b = fiche("Pinnacle", "pin")
        c = fiche("Matchbook", "mbx")
        c.update(domicile=b["domicile"], exterieur=b["exterieur"],
                 match_reference=b["match_reference"], match_id=b["match_id"])
        assert _choisis(fonction, [b, c]) == _choisis(fonction, [a])
        assert "mbx" not in _choisis(fonction, [b, c])

    assert STRATEGIE["references"] == ("Pinnacle", "Betfair", "Polymarket")
    assert REFERENCES_SHARP == ("Pinnacle", "Betfair", "Polymarket")
    assert GROK_9["reference"] == "Pinnacle" and GROK_10["reference"] == "Polymarket"
    assert REFERENCES_DEFI_1 == ("Pinnacle", "Betfair", "Polymarket")
    assert REFERENCES_DEFI_4 == ("Pinnacle",)
    for regle in (GEMINI, JULES_V2, M3, EDEN, CONSEIL_RETARD):
        assert "Matchbook" not in regle["references"]
    assert CHATGPT["reference"] == "Pinnacle"
    assert JULES["reference"] == "Pinnacle"
    assert COEUR["reference"] == "Pinnacle"
    assert LIQUIDITE["reference"] == "Pinnacle"
    assert QWEN["references"] == {"Pinnacle"}
    assert {r.reference for r in REGLES} <= {"Pinnacle", "Polymarket"}
    assert "Matchbook" not in ORDRE_REFERENCES


def test_filtre_reference_et_liste_des_bilans():
    assert REFERENCES == ["Pinnacle", "Betfair", "Polymarket", "Matchbook", "Smarkets", "Kalshi", "Consensus"]
    texte = Path("scripts/site_web.py").read_text()
    assert 'Matchbook:"Mb "' in texte
    assert 'champ === "reference" ? [...(D.references || []), ...depuisFiches]' in texte
    assert 'k === "reference") return p.unique_bilan === true && p.reference === v' in texte
    assert "<option>Matchbook</option>" not in texte.split('id="strategies-ref"')[1].split("</select>")[0]


def test_cycle_off_shadow_403_et_exception(monkeypatch):
    monkeypatch.setenv("SOURCE_MATCHBOOK", "off")
    journal = {"etapes": {}}
    assert cycle.appliquer_matchbook({"football"}, 36, AVANT_LILLE, journal) == []
    assert journal["etapes"]["matchbook"]["desactive"] is True
    assert journal["matchbook"]["mode"] == "off"

    monkeypatch.setenv("SOURCE_MATCHBOOK", "shadow")

    def lu(*_a, **_k):
        return [{"ligne": 1}], {"ok": True, "requetes": 1, "erreurs": [], "matchs": 1, "mode": "shadow"}

    monkeypatch.setattr(mb, "collecter", lu)
    journal = {"etapes": {}}
    assert cycle.appliquer_matchbook({"football"}, 36, AVANT_LILLE, journal) == []
    assert journal["etapes"]["matchbook"]["shadow"] is True
    assert journal["matchbook"]["lignes"] == 1

    monkeypatch.delenv("SOURCE_MATCHBOOK", raising=False)

    def direct(*_a, **_k):
        return [{"cote_juste": 2.5}], {"ok": True, "requetes": 1, "erreurs": [], "matchs": 1, "mode": "direct"}

    monkeypatch.setattr(mb, "collecter", direct)
    journal = {"etapes": {}}
    lignes = cycle.appliquer_matchbook({"football"}, 12, AVANT_LILLE, journal)
    assert lignes == [{"cote_juste": 2.5}]
    assert journal["matchbook"]["ok"] is True and journal["matchbook"]["erreurs"] == []

    def refuse(*_a, **_k):
        return [], {"ok": False, "erreurs": ["HTTP 403"], "requetes": 1, "matchs": 0, "mode": "direct"}

    monkeypatch.setattr(mb, "collecter", refuse)
    journal = {"etapes": {}}
    assert cycle.appliquer_matchbook({"football"}, 36, AVANT_LILLE, journal) == []
    assert journal["matchbook"]["erreurs"] == ["HTTP 403"]
    assert journal["etapes"]["matchbook"]["ok"] is False
    assert MARQUE not in str(journal)

    def casse(*_a, **_k):
        raise RuntimeError("coupure")

    monkeypatch.setattr(mb, "collecter", casse)
    journal = {"etapes": {}}
    assert cycle.appliquer_matchbook({"football"}, 36, AVANT_LILLE, journal) == []
    assert journal["matchbook"]["erreurs"] == ["lecture interrompue"]
    assert journal["etapes"]["matchbook"]["ok"] is False
