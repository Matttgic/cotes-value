from datetime import datetime, timedelta, timezone

from cotes import surveillance as s

T0 = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
PANNE = {"winamax_direct": {"ok": False, "degrade": True, "erreurs": ["sport:1 : réseau", "lecture vide"]}}
BUDGET = {"betclic_direct": {"ok": True, "degrade": True, "erreurs": ["budget"]}}


def test_refus_403_de_pinnacle_avec_reprise_est_benin():
    assert s.problemes({"pinnacle": {"ok": True, "degrade": True, "erreurs": ["HTTP 403", "HTTP 403"]}}) == {}


def test_budget_et_resultats_ne_sont_pas_des_problemes():
    assert s.problemes({**BUDGET, "resultats_espn_tennis": {"ok": False}, "smarkets": {"ok": True, "degrade": True, "erreurs": ["x"]}}) == {}


def test_une_panne_isolee_ne_previent_pas_la_deuxieme_oui_puis_retablie():
    etat, msgs = s.evaluer(PANNE, {}, T0)
    assert msgs == []
    etat, msgs = s.evaluer(PANNE, etat, T0 + timedelta(minutes=5))
    assert [m[0] for m in msgs] == ["Winamax en panne"] and msgs[0][2] == "high"
    etat, msgs = s.evaluer(PANNE, etat, T0 + timedelta(minutes=10))
    assert msgs == []                                            # pas de répétition
    etat, msgs = s.evaluer(PANNE, etat, T0 + timedelta(hours=3, minutes=6))
    assert len(msgs) == 1                                        # rappel
    etat, msgs = s.evaluer({"winamax_direct": {"ok": True}}, etat, T0 + timedelta(hours=4))
    assert [m[0] for m in msgs] == ["Winamax rétablie"] and etat == {}


def test_panne_qui_se_resout_avant_le_seuil_reste_silencieuse():
    etat, _ = s.evaluer(PANNE, {}, T0)
    etat, msgs = s.evaluer({"winamax_direct": {"ok": True}}, etat, T0 + timedelta(minutes=5))
    assert msgs == [] and etat == {}


def test_surveiller_ecrit_l_etat_et_liste_les_messages_sans_rien_envoyer(tmp_path):
    assert s.surveiller(tmp_path, PANNE, T0)["messages"] == []
    r = s.surveiller(tmp_path, PANNE, T0 + timedelta(minutes=5))
    assert r["messages"] == ["Winamax en panne"] and (tmp_path / s.ETAT).exists()


REFUS = {"pinnacle": {"ok": True, "degrade": True, "erreurs": ["sport 45 matchups : HTTP 403", "sport 6 matchups : HTTP 403"]}}


def test_journal_incident_en_cours_puis_termine_avec_sa_duree():
    j = s.journal_incidents(PANNE, {}, T0)
    assert j["en_cours"]["winamax_direct"]["cycles"] == 1 and j["termines"] == []
    j = s.journal_incidents(PANNE, j, T0 + timedelta(minutes=5))
    inc = j["en_cours"]["winamax_direct"]
    assert inc["cycles"] == 2 and inc["debut"] == T0.isoformat(timespec="seconds") and inc["source"] == "Winamax"
    j = s.journal_incidents({"winamax_direct": {"ok": True}}, j, T0 + timedelta(minutes=10))
    assert j["en_cours"] == {}
    fini = j["termines"][0]
    assert fini["cycles"] == 2 and fini["debut"] == T0.isoformat(timespec="seconds") and fini["fin"].endswith("12:10:00+00:00")


def test_refus_releve_mais_budget_ignore_et_refus_bref_oublie():
    assert s.constats({**BUDGET})  == {}
    assert s.constats(REFUS)["pinnacle"][1] == "refus"
    j = s.journal_incidents(REFUS, {}, T0)
    j = s.journal_incidents({"pinnacle": {"ok": True}}, j, T0 + timedelta(minutes=5))
    assert j["termines"] == []                                   # 1 cycle de refus : du bruit, pas un incident
    for i in range(3):
        j = s.journal_incidents(REFUS, j, T0 + timedelta(minutes=5 * i))
    j = s.journal_incidents({"pinnacle": {"ok": True}}, j, T0 + timedelta(minutes=20))
    assert j["termines"][0]["cycles"] == 3 and "403" in j["termines"][0]["detail"]


def test_journal_garde_24_heures_et_survit_a_un_fichier_abime(tmp_path):
    j = s.journal_incidents(PANNE, {}, T0)
    j = s.journal_incidents({"winamax_direct": {"ok": True}}, j, T0 + timedelta(minutes=5))
    assert len(s.journal_incidents({}, j, T0 + timedelta(hours=23))["termines"]) == 1
    assert s.journal_incidents({}, j, T0 + timedelta(hours=25))["termines"] == []
    assert s.journal_incidents(PANNE, "abime", T0)["en_cours"]["winamax_direct"]["cycles"] == 1
    (tmp_path / s.INCIDENTS).write_text("{pas du json")
    assert s.surveiller(tmp_path, PANNE, T0).get("erreur") is None
    assert s.journal_incidents(PANNE, {}, T0)["mis_a_jour"] and (tmp_path / s.INCIDENTS).exists()


def test_archive_garde_les_incidents_termines_une_seule_fois_et_compte_les_cycles():
    from datetime import datetime, timezone
    from cotes import surveillance as sv
    t = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    fini = {"source": "Winamax", "genre": "panne", "debut": "2026-10-25T10:00:00+00:00", "fin": "2026-10-25T10:20:00+00:00"}
    j = {"en_cours": {"pinnacle": {}}, "termines": [fini]}
    h = sv.archiver(j, {}, t)
    h = sv.archiver(j, h, t)
    assert h["incidents"] == [fini]
    assert h["jours"]["2026-10-25"] == {"cycles": 2, "cycles_en_incident": 2}
    assert sv.archiver({"termines": []}, "abîmé", t)["jours"]["2026-10-25"]["cycles"] == 1
