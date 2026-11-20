"""Règlement manuel : source et score (ou motif) obligatoires ; pari « supprime » jamais repris (audit du 20/11)."""
from datetime import datetime, timedelta, timezone

from cotes import simulation as S
from cotes.reglement import appliquer, est_supprime, statut_saisi

T = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
P = {"id": "p1", "match_id": "pmu|1", "sport": "football", "statut": "a_regler", "marche": "RESULTAT_1N2",
     "periode": "MATCH", "issue": "DOM", "mise": 10, "cote": 2.0, "debut": "2026-11-19T18:00:00+00:00"}


def test_statut_sans_preuve_refuse():
    assert statut_saisi("rembourse") == (None, None, "reglement_manuel_sans_preuve")
    assert statut_saisi({"statut": "rembourse", "source": "x"})[2] == "reglement_manuel_sans_preuve"
    assert statut_saisi({"statut": "rembourse", "motif": "annulé"})[2] == "reglement_manuel_sans_preuve"
    s, preuve, alerte = statut_saisi({"statut": "Remboursé", "source": "lequipe.fr", "motif": "match annulé"})
    assert (s, alerte) == ("rembourse", None) and preuve["source"] == "lequipe.fr"
    assert statut_saisi({"statut": "gagné", "source": "x", "score": [1, 0]})[0] == "gagne"
    assert statut_saisi("nimporte")[2] == "statut_reglement_inconnu"
    assert statut_saisi({"score": [1, 0]}) == (None, None, None)          # saisie par match, pas par pari


def test_sans_preuve_le_pari_reste_a_regler_avec_une_alerte():
    p = dict(P)
    appliquer([p], {}, {"p1": "rembourse"}, T)
    assert p["statut"] == "a_regler" and "reglement_manuel_sans_preuve" in p["alertes"]


def test_statut_mal_ecrit_ne_bloque_plus_le_score_du_match():
    p = dict(P)
    appliquer([p], {}, {"p1": "gagnée", "pmu|1": {"score": [2, 0], "source": "flashscore"}}, T)
    assert p["statut"] == "gagne" and "statut_reglement_inconnu" in p["alertes"]


def test_score_de_match_sans_source_refuse():
    p = dict(P)
    appliquer([p], {}, {"pmu|1": {"score": [2, 0]}}, T)
    assert p["statut"] == "a_regler" and "reglement_manuel_sans_source" in p["alertes"]


def test_avec_preuve_regle_et_trace():
    p = dict(P)
    appliquer([p], {}, {"p1": {"statut": "rembourse", "source": "uefa.com", "motif": "match reporté"}}, T)
    assert p["statut"] == "rembourse"
    assert p["preuve_reglement"]["source"] == "uefa.com" and p["preuve_reglement"]["motif"] == "match reporté"


def test_supprime_jamais_repris():
    assert est_supprime("supprime") and est_supprime({"statut": "supprime", "source": "x"})
    o = {"reference": "Pinnacle", "bookmaker": "PMU", "sport": "football", "marche": "RESULTAT_1N2", "cote": 2.2,
         "ecart": 0.04, "detecte": T.isoformat(), "lu_reference": T.isoformat(), "match_id": "pmu|1",
         "debut": (T + timedelta(hours=5)).isoformat(), "domicile": "A", "exterieur": "B", "periode": "MATCH",
         "ligne": None, "issue": "1", "pari": "A", "cote_juste": 2.2 / 1.04}
    pid = S.placer([o], [], T)[0]["id"]
    assert S.placer([o], [], T, exclus={pid}) == []
