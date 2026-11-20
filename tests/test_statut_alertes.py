"""Statut vivant des alertes (cotes/alertes/statut.py)."""
from datetime import datetime, timedelta, timezone

from cotes.alertes import statut as S
from cotes.alertes.pushover import message_pushover
from cotes.notifications import empreinte_prix

T = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
P = {"statut": "en_cours", "match_id": "pmu|1", "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None,
     "issue": "DOM", "bookmaker": "PMU", "cote": 2.2, "cote_juste": 2.1, "domicile": "A", "exterieur": "B",
     "pari": "A gagne", "debut": (T + timedelta(hours=3)).isoformat()}


def test_statut_selon_la_cote_relue():
    assert S.statut({**P, "prix_revu": 2.2}) is None
    assert S.statut({**P, "prix_revu": 2.15}) == (S.COTE_BAISSEE, 2.15)            # min = 2,1 × 1,02 = 2,142
    assert S.statut({**P, "prix_revu": 2.1}) == (S.PLUS_JOUABLE, 2.1)
    assert S.statut(P) is None


def test_seulement_les_alertes_envoyees_recentes_et_une_relance_par_statut():
    p = {**P, "prix_revu": 2.0}
    aid = empreinte_prix(p)
    assert S.statuts([p], {}, T) == []
    assert S.statuts([p], {aid: (T - timedelta(hours=4)).isoformat()}, T) == []
    liste = S.statuts([p], {aid: (T - timedelta(minutes=20)).isoformat()}, T)
    assert [s["statut"] for s in liste] == [S.PLUS_JOUABLE]
    assert S.relances(liste, {f"{aid}:plus_jouable": "x"}) == []
    assert S.statuts([{**p, "debut": (T - timedelta(minutes=1)).isoformat()}], {aid: T.isoformat()}, T) == []


def test_message_pushover_discret():
    s = {**S.statuts([{**P, "prix_revu": 2.0}], {empreinte_prix(P): T.isoformat()}, T)[0], "type": "statut"}
    m = message_pushover(s)
    assert m["title"] == "Plus jouable · PMU" and m["priority"] == -1 and "2,20 → 2,00" in m["message"]


def test_alerte_avec_liens_du_journal_reel():
    from cotes.alertes.pushover import liens_journal
    a = {"domicile": "A <b>", "exterieur": "B", "debut": "2026-11-20T18:00:00+00:00", "cote": 2.2, "cote_min": 2.1,
         "bookmaker": "PMU", "sport": "football", "selection": "A", "pari_id": "abc123"}
    m = message_pushover(a)
    assert m["html"] == 1 and "A &lt;b&gt;" in m["message"] and m["message"].count("<a href=") == 4
    assert "#notifications?journal=abc123&r=plafonne&cote=2.20" in m["message"]
    assert liens_journal({**a, "pari_id": "../x"}) == "" and "html" not in message_pushover({**a, "pari_id": None})
