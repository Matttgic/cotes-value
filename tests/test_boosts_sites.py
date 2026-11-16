"""Lecteurs de cotes boostées Unibet, NetBet et OlyBet (cotes/direct/boosts_sites.py), sur les vraies pages relevées
par le dépôt cotes-boostees (8 et 13/10/2026), sans réseau."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cotes.direct import boosts_sites as S
from cotes.direct import netbet

F = Path(__file__).parent / "fixtures" / "boosts"
LISTE = (F / "unibet_liste_2026-10-08.html").read_text(encoding="utf-8")
EVENEMENT = (F / "unibet_evenement_2026-10-08.html").read_text(encoding="utf-8")


class _Rep:
    def __init__(self, texte, code=200):
        self.text, self.status_code = texte, code


class _Session:
    def __init__(self, code=200):
        self.urls, self.code = [], code

    def get(self, url, **_):
        self.urls.append(url)
        return _Rep(LISTE if url == S.UNIBET_BOOSTS else EVENEMENT, self.code)


def test_unibet_liste_puis_page_du_paquet():
    s = _Session()
    lus = S.lire_unibet(s, "2026-10-08T10:00:00+00:00")
    assert len(lus) == 20 and s.urls[1].endswith("/3381006/paris-trashtalk-26-27")
    b = next(x for x in lus if x["domicile"] == "Montauban")
    assert (b["exterieur"], b["cote"], b["cote_avant"], b["mise_max"]) == ("Brive", 2.75, 2.5, 25.0)
    assert b["libelle"] == "Montauban gagne et Johnny Matthews marque au moins 1 essai" and not b["long_terme"]
    assert b["debut"] == "2026-10-08T19:00:00+00:00"
    assert sum(x["long_terme"] for x in lus) == 19            # paquet NBA « 26/27 » : paris de saison


def test_unibet_page_de_blocage():
    with pytest.raises(S.PageInattendue):
        S.lire_unibet(_Session(code=403), "x")
    with pytest.raises(S.PageInattendue):
        S.etat_unibet("<html>captcha</html>")


def test_netbet_super_cotes():
    """Même plateforme que Genybet (Sportnco) : la page relevée chez Genybet sert d'exemple."""
    etat = netbet.etat_nuxt((F / "genybet_super-cotes_2026-10-13.html").read_text(encoding="utf-8"))
    lus = S.boosts_netbet(etat, "m", datetime(2026, 10, 13, 10, tzinfo=timezone.utc))
    assert [(b["domicile"], b["exterieur"], b["libelle"], b["cote"], b["mise_max"]) for b in lus] == [
        ("Lille", "Arsenal", "Lille (vs Arsenal) marque au moins 1 but", 2.1, 10.0)]
    assert S.boosts_netbet(etat, "m", datetime(2026, 10, 13, 20, tzinfo=timezone.utc)) == []   # match commencé


@pytest.mark.parametrize("label, attendu", [
    ("Lille (vs Arsenal) marque au moins 1 but", "Lille - Arsenal"),
    ("Marseille / Olympiakos : Plus de 2,5 buts", "Marseille - Olympiakos"),
    ("Lens marque dans les 2 mi-temps ? (vs Bruges)", "Lens - Bruges"),
    ("Un intitulé sans affiche", None),
])
def test_affiche_des_super_cotes(label, attendu):
    assert S.separer(label) == attendu


def test_olybet():
    d = json.loads((F / "olybet_2026-10-13.json").read_text(encoding="utf-8"))
    lus = S.boosts_olybet(d["jeux"], S.selections_olybet(d["boosted_selections"]), "m",
                          datetime(2026, 10, 13, 10, tzinfo=timezone.utc))
    assert len(lus) == 4
    rome = next(b for b in lus if b["domicile"] == "AS Rome")
    assert (rome["exterieur"], rome["libelle"], rome["cote"], rome["mise_max"], rome["cote_avant"]) == (
        "Real Madrid", "Real Madrid to win and Vinicius to score", 4.0, 8.33, None)


def test_lire_tous_un_site_en_panne_ou_trop_lent():
    def lent():
        time.sleep(2)
        return [{"id": "x"}]
    boosts, erreurs = S.lire_tous(datetime(2026, 11, 16, tzinfo=timezone.utc), budget=0.5,
                                  lecteurs={"A": lambda: [{"id": "a"}], "B": lambda: 1 / 0, "C": lent})
    assert boosts == [{"id": "a"}]
    assert erreurs["B"].startswith("ZeroDivisionError") and erreurs["C"] == "budget dépassé"
