from datetime import datetime, timedelta, timezone

from cotes import inconnus
from cotes.direct import olybet

T = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


def test_noter_regroupe_les_lignes_et_vide():
    inconnus.vider()
    inconnus.noter("pmu", "Total buts 2.5 - Joueur")
    inconnus.noter("pmu", "Total buts 3,5 - Joueur")
    inconnus.noter("betclic", "")
    assert inconnus.vider() == {"pmu": {"Total buts # - Joueur": 2}}
    assert inconnus.vider() == {}


def test_fusion_garde_premier_et_oublie_le_vieux():
    ancien = {"pmu": {"A": {"n": 3, "premier": (T - timedelta(days=3)).isoformat(), "dernier": (T - timedelta(days=1)).isoformat()},
                      "B": {"n": 1, "premier": (T - timedelta(days=9)).isoformat(), "dernier": (T - timedelta(days=8)).isoformat()}}}
    f = inconnus.fusionner(ancien, {"pmu": {"A": 5, "C": 2}}, T)
    assert set(f["pmu"]) == {"A", "C"}
    assert f["pmu"]["A"] == {"n": 5, "premier": (T - timedelta(days=3)).isoformat(), "dernier": T.isoformat(timespec="seconds")}


def test_resume_nouveaux_apres_rodage():
    f = inconnus.fusionner({"pmu": {"A": {"n": 1, "premier": (T - timedelta(days=3)).isoformat(), "dernier": T.isoformat()}}},
                           {"pmu": {"A": 4, "Nouveau #": 2}}, T)
    r = inconnus.resume(f, T)["pmu"]
    assert r["distincts"] == 2 and r["nouveaux"] == ["Nouveau #"] and r["frequents"][0] == ["A", 4]
    # premier relevé : rien n'est « nouveau »
    assert inconnus.resume(inconnus.fusionner({}, {"pmu": {"A": 1}}, T), T)["pmu"]["n_nouveaux"] == 0


def test_lecteur_note_un_marche_non_traduit():
    inconnus.vider()
    assert olybet.marche_depuis({"name": "Buteur 3e but", "type": "Inconnu"}, "football") is None
    assert inconnus.vider() == {"olybet": {"Buteur #e but": 1}}
