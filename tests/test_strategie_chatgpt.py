"""Invariants de sélection : temps, absence de fuite et exposition réelle."""
from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from cotes.simulation import bilan, bilan_bookmakers, bilan_tranches
from cotes.strategie_chatgpt import CHATGPT, motif_refus, paris_chatgpt


def pari(mid="m1", **changes):
    p = {"id": mid, "match_id": "winamax|" + mid, "reference": "Pinnacle", "simulation": "D",
         "bookmaker": "Winamax", "sport": "football", "ligue": "Ligue 1", "domicile": "Paris",
         "exterieur": "Lyon", "marche": "TOTAL", "periode": "MATCH", "ligne": 2.5, "issue": "PLUS",
         "pari": "Plus de 2,5 buts", "detecte": "2026-10-14T10:00:00+00:00",
         "debut": "2026-10-14T13:00:00+00:00", "lu_reference": "2026-10-14T09:57:00+00:00",
         "cote": 2.1, "cote_juste": 2.0, "ecart": .05, "mise": 10.0,
         "statut": "en_cours", "gain": None, "clv": None,
         "preuve_prise": {"match_id_reference": mid, "ressemblance_noms": .9,
                          "controle": {"statut": "conforme", "n": 100}}}
    return {**p, **changes}


def test_regles_figees_et_exclusion_historique():
    ancien = pari(detecte="2026-10-13T10:00:00+00:00", debut="2026-10-13T13:00:00+00:00",
                  lu_reference="2026-10-13T09:59:00+00:00")
    assert not paris_chatgpt([ancien])
    assert paris_chatgpt([ancien], depuis="2026-10-05T00:00:00+00:00") == {id(ancien)}
    assert motif_refus(pari()) is None


@pytest.mark.parametrize("changes", [
    {"reference": "Pinnacle brut"}, {"reference": "Consensus"}, {"bookmaker": "NetBet"},
    {"cote": 1.49}, {"cote": 3.01}, {"cote": float("nan")}, {"ecart": .0299}, {"ecart": .1201},
    {"ecart": float("inf")}, {"cote_juste": 3}, {"suspect": "désaccord"},
    {"debut": "2026-10-14T10:14:59+00:00"}, {"debut": "2026-10-14T16:00:01+00:00"},
    {"detecte": "2026-10-14T10:00:00"}, {"detecte": None},
    {"lu_reference": "2026-10-14T09:54:59+00:00"}, {"lu_reference": "2026-10-14T10:05:01+00:00"},
    {"preuve_prise": {}}, {"periode": "MT1"}, {"marche": "BOTH_TEAMS_TO_SCORE"},
    {"ligne": 2.25}, {"ligne": 2.75}, {"ligne": None}, {"issue": "YES"}, {"sport": "volley"},
])
def test_refus_sans_preuve_ou_hors_regles(changes):
    assert not paris_chatgpt([pari(**changes)])


@pytest.mark.parametrize("edge", [.03, .12])
@pytest.mark.parametrize("cote", [1.5, 3.0])
@pytest.mark.parametrize("minutes", [15, 360])
def test_bornes_incluses(edge, cote, minutes):
    debut = (datetime.fromisoformat("2026-10-14T10:00:00+00:00") + timedelta(minutes=minutes)).isoformat()
    assert motif_refus(pari(ecart=edge, cote=cote, cote_juste=round(cote/(1+edge), 3), debut=debut)) is None


def test_un_match_tous_bookmakers_et_marches_et_pas_la_meilleure_cote_future():
    premier = pari()
    meme_instant = pari(id="pmu1", match_id="pmu|1", bookmaker="PMU", ecart=.06, cote=2.12)
    plus_tard = pari(id="pmu2", match_id="pmu|2", bookmaker="PMU", ecart=.10, cote=2.2,
                     detecte="2026-10-14T10:01:00+00:00", marche="HANDICAP", issue="DOM")
    rows = [plus_tard, premier, meme_instant]
    assert paris_chatgpt(rows) == {id(meme_instant)}
    assert paris_chatgpt(rows[::-1]) == {id(meme_instant)}


def test_resultat_clv_et_ordre_fichier_ne_changent_pas_la_selection():
    rows = [pari(str(i), detecte=f"2026-10-14T10:0{i}:00+00:00",
                 lu_reference=f"2026-10-14T10:0{i}:00+00:00") for i in range(6)]
    selection = paris_chatgpt(rows)
    assert selection == {id(p) for p in rows[:5]}
    for p in rows[:5]:
        p.update(statut="perdu", gain=-10, clv=-.5)
    rows[5].update(statut="gagne", gain=11, clv=.5)
    assert paris_chatgpt(rows[::-1]) == selection


def test_plafond_journalier_en_heure_de_paris():
    rows = [pari(str(i), detecte=f"2026-10-14T21:0{i}:00+00:00",
                 lu_reference=f"2026-10-14T21:0{i}:00+00:00", debut="2026-10-15T01:00:00+00:00")
            for i in range(6)]
    suivant = pari("nouveau_jour", detecte="2026-10-14T22:01:00+00:00",
                   lu_reference="2026-10-14T22:00:00+00:00", debut="2026-10-15T01:00:00+00:00")
    assert paris_chatgpt(rows + [suivant]) == {id(p) for p in rows[:5] + [suivant]}


def test_vainqueur_tennis_et_feminin_admis():
    assert motif_refus(pari(sport="tennis", marche="VAINQUEUR", issue="DOM", ligne=None,
                           ligue="WTA", domicile="Joueuse A", exterieur="Joueuse B")) is None


def test_bilan_courbe_et_fiches_utilisent_exactement_les_memes_paris(tmp_path):
    from scripts.site_web import construire, courbes, selection_paris
    import json
    import re
    rows = [pari("m1", statut="gagne", gain=11, regle_le="2026-10-14T15:00:00+00:00"),
            pari("m2", statut="perdu", gain=-10, regle_le="2026-10-14T15:00:00+00:00")]
    avant = deepcopy(rows)
    b = bilan(rows)
    assert b["D|ChatGPT"]["gains"] == 1 and b["D|ChatGPT"]["regles"] == 2
    assert b["D|Toutes"]["regles"] == 2  # aucune copie de mise dans les autres vues
    assert bilan_bookmakers(rows)["Winamax·D|ChatGPT"]["gains"] == 1
    assert bilan_tranches(rows)["2,01 – 3,00|ChatGPT"]["regles"] == 2
    assert sum(p[1] for p in courbes(rows)["ChatGPT"]) == 1
    assert len(selection_paris(rows, regles=0)[0]) == 2  # pas évincés par les autres simulations
    (tmp_path / "paris.json").write_text(json.dumps(rows))
    html = construire(tmp_path, tmp_path / "site").read_text()
    data = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1).replace("<\\/", "</"))
    assert data["chatgpt"] == json.loads(json.dumps(CHATGPT))
    assert data["bilan"]["D|ChatGPT"]["gains"] == 1
    assert rows == avant  # aucune mutation du suivi de Claude ou des paris sources
