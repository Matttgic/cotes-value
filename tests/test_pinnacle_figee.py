"""Garde-fou « cote Pinnacle figée » et âge réel du prix Pinnacle gardé dans l'opportunité et le pari."""
from datetime import datetime, timedelta, timezone

from cotes import mouvement
from cotes.comparaison import comparer
from cotes.marches import cle
from cotes.simulation import placer
from tests.test_controle import ligne

T0 = datetime(2029, 12, 31, 20, 0, tzinfo=timezone.utc)


def _cycle(proba, t, age_cache=420, references=("Pinnacle",)):
    """Une cote française et sa référence Pinnacle (et Polymarket), lues à l'instant t."""
    fr = [ligne(cote=2.4, collecte=t.isoformat())]
    index = {}
    for nom in references:
        ref = {**fr[0], "source": nom.lower(), "proba_juste": proba, "cote": 2.0, "collecte": t.isoformat(),
               "match_id": "p1", "score_association": 1.0, "inverse": False}
        if nom == "Pinnacle":
            ref |= {"mise_max": 1500.0, "marge_pinnacle": .03, "age_cache_s": age_cache}
        index[nom] = {"m1": {cle(fr[0]): ref}}
    return comparer(fr, {n: [] for n in references}, index=index), index


def _deux_cycles(tmp_path, p0, p1, minutes=11, references=("Pinnacle",)):
    chemin = tmp_path / "ancres.json.gz"
    o, index = _cycle(p0, T0, references=references)
    mouvement.annoter(o, index, chemin, T0)
    t1 = T0 + timedelta(minutes=minutes)
    o, index = _cycle(p1, t1, references=references)
    journal = mouvement.annoter(o, index, chemin, t1)
    return {x["reference"]: x for x in o}, journal


def test_cote_pinnacle_inchangee_dix_minutes_rend_l_opportunite_suspecte(tmp_path):
    o, journal = _deux_cycles(tmp_path, .5, .5)
    pin = o["Pinnacle"]
    assert pin["mouvement_pinnacle"] == 0 and pin["mouvement_s"] == 660
    assert pin["suspect"] == mouvement.FIGEE and pin["pariable"] is False
    assert journal["figees"] == 1
    assert placer([pin], [], maintenant=T0 + timedelta(minutes=11)) == []        # ni pari


def test_cote_qui_bouge_ou_mesure_trop_courte_reste_pariable(tmp_path):
    o, journal = _deux_cycles(tmp_path, .5, .505)                           # +1 % : le marché vit
    assert o["Pinnacle"]["mouvement_pinnacle"] == 0.01 and not o["Pinnacle"]["suspect"]
    assert o["Pinnacle"]["pariable"] is True and journal["figees"] == 0
    o, _ = _deux_cycles(tmp_path / "b", .5, .5, minutes=5)                 # moins de 10 min : pas de mesure
    assert "mouvement_pinnacle" not in o["Pinnacle"] and not o["Pinnacle"]["suspect"]


def test_consensus_avec_pinnacle_ecarte_polymarket_seul_garde(tmp_path):
    o, journal = _deux_cycles(tmp_path, .5, .5, references=("Pinnacle", "Polymarket"))
    assert o["Consensus"]["sources"] == "Pinnacle+Polymarket"
    assert o["Pinnacle"]["suspect"] == o["Consensus"]["suspect"] == mouvement.FIGEE
    assert o["Polymarket"]["pariable"] is True and not o["Polymarket"]["suspect"]   # autre référence : intacte
    assert journal["figees"] == 2


def test_une_raison_suspecte_existante_est_conservee():
    o = {"reference": "Pinnacle", "mouvement_pinnacle": 0.0, "mouvement_s": 900, "suspect": "écart trop grand"}
    assert mouvement.est_figee(o)
    o2 = {**o, "reference": "Consensus", "sources": "Polymarket+Smarkets"}
    assert not mouvement.est_figee(o2)
    assert not mouvement.est_figee({**o, "mouvement_s": 599})
    assert not mouvement.est_figee({**o, "mouvement_pinnacle": False})


def test_age_reel_du_prix_pinnacle_garde_dans_l_opportunite_et_le_pari():
    o, _ = _cycle(.5, T0, age_cache=731)
    pin = next(x for x in o if x["reference"] == "Pinnacle")
    assert pin["age_prix_pinnacle_s"] == 731 and pin["lu_reference"] == T0.isoformat()
    nouveaux = placer([pin], [], maintenant=T0 + timedelta(seconds=30))
    assert len(nouveaux) == 1 and nouveaux[0]["age_prix_pinnacle_s"] == 731
    # Une autre référence n'a pas d'âge de prix Pinnacle.
    o, _ = _cycle(.5, T0, references=("Polymarket",))
    assert o[0]["age_prix_pinnacle_s"] is None
