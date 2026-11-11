"""DraftKings, référence seule : lecture des réponses relevées le 10/11/2026, marge, rapprochement à Pinnacle."""
import json
from datetime import datetime, timezone
from pathlib import Path

from cotes.direct import draftkings as DK
from cotes.props import comparer_matchs, comparer_reference

MAINTENANT = datetime(2026, 11, 10, 22, 10, tzinfo=timezone.utc)
PAGES = json.loads((Path(__file__).parent / "fixtures" / "draftkings.json").read_text(encoding="utf-8"))
DIRECT = {"SOURCE_DRAFTKINGS": "direct"}


class Reponse:
    def __init__(self, status, texte):
        self.status_code = status
        self.text = texte


class Session:
    """Sert les pages relevées ; toute autre adresse reçoit ``defaut`` (404 : sous-catégorie sans marché)."""
    def __init__(self, pages=PAGES, defaut=404):
        self.pages, self.defaut, self.appels = pages, defaut, []

    def get(self, url, timeout=None):
        chemin = url.split("/v1", 1)[1]
        self.appels.append(chemin)
        if chemin in self.pages:
            return Reponse(200, json.dumps(self.pages[chemin]))
        return Reponse(self.defaut, "")


def test_mode_eteint_par_defaut_et_sans_appel():
    assert DK.mode({}) == "off" and DK.mode({"SOURCE_DRAFTKINGS": "nimporte"}) == "off" and DK.mode(DIRECT) == "direct"
    s = Session()
    lignes, meta = DK.collecter(session=s, maintenant=MAINTENANT, environ={})
    assert lignes == [] and meta["mode"] == "off" and s.appels == []


def test_surnom_sans_l_abreviation_de_ville():
    assert DK.surnom("MIL Bucks") == "Bucks" and DK.surnom("NY Knicks") == "Knicks"
    assert DK.surnom("BOS Red Sox") == "Red Sox" and DK.surnom("PHI 76ers") == "76ers"
    assert DK.surnom("Real Madrid") == "Real Madrid" and DK.surnom("Knicks") == "Knicks" and DK.surnom("") == ""


def test_lignes_de_match_nba_nhl_nfl_marge_retiree():
    s = Session()
    lignes, meta = DK.collecter(session=s, heures=72, maintenant=MAINTENANT, environ=DIRECT)
    assert meta["matchs"] == 3 and meta["lignes"] == 18           # 3 matchs × 3 marchés × 2 issues ; MLB : long terme seul
    par = {(l["sport"], l["marche"], l["issue"]): l for l in lignes if not l["marche"].startswith("JOUEUR:")}
    knicks = par[("basket", "VAINQUEUR", "DOM")]
    assert knicks["domicile"] == "Knicks" and knicks["exterieur"] == "Bucks" and knicks["ligue"] == "NBA"
    assert knicks["match_id"] == "draftkings|34983855" and knicks["debut"] == "2026-11-11T00:40:00+00:00"
    assert knicks["cote"] == 1.0962 and knicks["periode"] == "MATCH" and knicks["source"] == "draftkings"
    # la marge est retirée : les deux probabilités justes font 1, et la cote juste dépasse la cote lue
    assert abs(knicks["proba_juste"] + par[("basket", "VAINQUEUR", "EXT")]["proba_juste"] - 1) < 1e-5
    assert knicks["cote_juste"] > knicks["cote"] and 0.03 < knicks["marge_draftkings"] < 0.06
    # handicap : la ligne est celle du domicile pour les deux issues
    assert par[("basket", "HANDICAP", "DOM")]["ligne"] == -15.5 and par[("basket", "HANDICAP", "EXT")]["ligne"] == -15.5
    assert par[("hockey", "HANDICAP", "DOM")]["ligne"] == 1.5 and par[("hockey", "HANDICAP", "DOM")]["cote"] == 1.4202
    assert par[("football_americain", "HANDICAP", "EXT")]["ligne"] == -2.5
    assert par[("basket", "TOTAL", "PLUS")]["ligne"] == 222.5 and par[("hockey", "TOTAL", "MOINS")]["cote"] == 1.8
    assert par[("football_americain", "TOTAL", "PLUS")]["ligne"] == 41.5
    assert not any(l["sport"] == "baseball" for l in lignes)
    # onze appels au plus : 4 ligues, puis les props des ligues qui ont des matchs (4 NBA, 3 NHL)
    assert len(s.appels) == 11 and meta["requetes"] == 11
    assert s.appels[0] == "/leagues/42648" and "/leagues/42133/categories/1189/subcategories/12040" in s.appels


def test_props_joueurs_et_marches_incomplets():
    lignes, meta = DK.collecter({"basket", "hockey"}, 72, Session(), MAINTENANT, DIRECT)
    props = [l for l in lignes if l["marche"].startswith("JOUEUR:")]
    assert meta["props"] == len(props) == 8                       # 3 joueurs NBA et 1 joueur NHL, plus et moins
    brunson = next(l for l in props if l["joueur"] == "Jalen Brunson" and l["issue"] == "PLUS")
    assert brunson["marche"] == "JOUEUR:Points" and brunson["ligne"] == 25.5 and brunson["cote"] == 1.8264
    assert brunson["sport"] == "basket" and brunson["domicile"] == "Knicks"
    caufield = next(l for l in props if l["joueur"] == "Cole Caufield" and l["issue"] == "MOINS")
    assert caufield["marche"] == "JOUEUR:ShotsOnGoal" and caufield["ligne"] == 2.5 and caufield["sport"] == "hockey"
    assert not any(l["joueur"] == "Matt Boldy" for l in props) and meta["ignores"] >= 1      # « moins » absent
    # les 404 des sous-catégories vides sont des avertissements courts, sans adresse
    assert meta["ok"] is False and all("http" not in a.lower().replace("http 404", "") for a in meta["avertissements"])


def test_match_commence_hors_horizon_ou_refus():
    tard = datetime(2026, 11, 11, 0, 20, tzinfo=timezone.utc)      # Wild – Canadiens a commencé à 00:10
    lignes, meta = DK.collecter({"hockey", "basket"}, 72, Session(), tard, DIRECT)
    assert {l["sport"] for l in lignes} == {"basket"}
    lignes, _ = DK.collecter(None, 1, Session(), MAINTENANT, DIRECT)             # horizon d'une heure : rien
    assert lignes == []
    lignes, meta = DK.collecter(None, 72, Session(pages={}, defaut=403), MAINTENANT, DIRECT)
    assert lignes == [] and meta["ok"] is False and meta["erreurs"][0] == "NBA HTTP 403" and meta["requetes"] == 4

    class Panne:
        def get(self, url, timeout=None):
            raise TimeoutError("lent")
    lignes, meta = DK.collecter(None, 72, Panne(), MAINTENANT, DIRECT)
    assert lignes == [] and meta["ok"] is False and "delai" in meta["erreurs"][0]


def pin(sport, dom, ext, marche, issue, proba, ligne=None, joueur=None, debut="2026-11-11T00:40:00+00:00"):
    return {"source": "pinnacle", "sport": sport, "domicile": dom, "exterieur": ext, "debut": debut, "marche": marche,
            "periode": "MATCH", "ligne": ligne, "issue": issue, "proba_juste": proba, "joueur": joueur}


def test_comparaison_des_matchs_a_pinnacle_dans_les_deux_sens():
    lignes, _ = DK.collecter(None, 72, Session(), MAINTENANT, DIRECT)
    pinnacle = [
        pin("basket", "New York Knicks", "Milwaukee Bucks", "VAINQUEUR", "DOM", 0.90),
        pin("basket", "New York Knicks", "Milwaukee Bucks", "HANDICAP", "DOM", 0.52, ligne=-15.5),
        pin("basket", "New York Knicks", "Milwaukee Bucks", "TOTAL", "PLUS", 0.50, ligne=223.5),        # autre ligne
        # Pinnacle liste ce match de hockey dans l'autre sens : Wild à domicile
        pin("hockey", "Minnesota Wild", "Montreal Canadiens", "VAINQUEUR", "DOM", 0.53, debut="2026-11-11T00:10:00+00:00"),
        pin("hockey", "Minnesota Wild", "Montreal Canadiens", "HANDICAP", "DOM", 0.34, ligne=-1.5, debut="2026-11-11T00:10:00+00:00"),
        pin("hockey", "Minnesota Wild", "Montreal Canadiens", "TOTAL", "PLUS", 0.47, ligne=6.5, debut="2026-11-11T00:10:00+00:00"),
    ]
    r = comparer_matchs(lignes, pinnacle, "draftkings")
    assert r["draftkings"] == 9 and r["rapproches"] == 5 and r["non_rapproches"] == 4 and r["reference_seule"] is True
    assert r["par_sport"]["basket"]["rapproches"] == 2 and r["par_sport"]["hockey"]["rapproches"] == 3
    # Canadiens à domicile chez DraftKings : 46,5 % ; chez Pinnacle le Wild à domicile à 53 %, donc 47 % pour eux
    dom = next(l for l in lignes if l["sport"] == "hockey" and l["marche"] == "VAINQUEUR" and l["issue"] == "DOM")
    assert abs(dom["proba_juste"] - 0.4654) < 0.002 and r["par_sport"]["hockey"]["accord"] == 1.0
    assert r["par_sport"]["hockey"]["ecart_absolu_moyen"] < 0.02
    assert comparer_matchs([], pinnacle)["rapproches"] == 0 and comparer_matchs(lignes, [])["non_rapproches"] == 9


def test_comparaison_des_props_a_pinnacle():
    lignes, _ = DK.collecter({"basket"}, 72, Session(), MAINTENANT, DIRECT)
    pinnacle = [pin("basket", "New York Knicks", "Milwaukee Bucks", "JOUEUR:Points", "PLUS", 0.53, ligne=25.5, joueur="Jalen Brunson"),
                pin("basket", "New York Knicks", "Milwaukee Bucks", "JOUEUR:Points", "PLUS", 0.49, ligne=21.5, joueur="Karl-Anthony Towns")]
    r = comparer_reference(lignes, pinnacle, "draftkings")
    assert r["draftkings"] == 3 and r["rapproches"] == 1 and r["non_rapproches"] == 2 and r["accord"] == 1.0
    assert abs(r["ecart_proba_moyen"] - (0.5167 - 0.53)) < 0.002
