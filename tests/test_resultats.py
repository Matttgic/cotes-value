from datetime import datetime, timezone

from cotes import resultats as R

T = datetime(2026, 10, 6, 2, 0, tzinfo=timezone.utc)


def enr(source, dom, ext, score, periodes=(), corners=None, libelles=None, sport="football"):
    return {"source": source, "sport": sport, "domicile": dom, "exterieur": ext, "debut": T, "score": score,
            "periodes": list(periodes), "libelles": libelles or R.libelles_periodes(sport, None, len(periodes)),
            "corners": corners}


PARI = {"sport": "football", "domicile": "Honduras", "exterieur": "Jamaïque", "debut": "2026-10-06T02:00:00Z"}


def test_deux_sources_concordantes_dont_une_inversee():
    E = [enr("draftkings", "Honduras", "Jamaica", (1, 1)), enr("orbitxch", "Jamaica", "Honduras", (1, 1)),
         enr("interwetten-de", "Honduras", "Jamaica", (1, 1), periodes=[(0, 1), (1, 0)], corners=(4, 6)),
         enr("betmgm", "Honduras", "Jamaica", (1, 1), corners=(4, 6))]
    r = R.consensus(PARI, E)
    assert r["score"] == (1, 1) and r["periodes"] == [(0, 1), (1, 0)] and r["corners"] == (4, 6)
    assert r["sources"] == ["betmgm", "draftkings", "interwetten-de", "orbitxch"]


def test_une_seule_source_ou_desaccord_on_attend():
    assert R.consensus(PARI, [enr("betmgm", "Honduras", "Jamaica", (1, 1))]) is None
    assert R.consensus(PARI, [enr("betmgm", "Honduras", "Jamaica", (1, 1)),
                              enr("pmu", "Honduras", "Jamaica", (2, 1))]) is None


def test_corners_betfair_zero_ignores():
    E = [enr("orbitxch", "Honduras", "Jamaica", (1, 1), corners=(0, 0)),
         enr("betmgm", "Honduras", "Jamaica", (1, 1), corners=(4, 6))]
    assert R.consensus(PARI, E)["corners"] is None          # une seule source fiable pour les corners


def test_libelles_deduits_au_hockey():
    assert R.libelles_periodes("hockey", None, 5) == ["1", "2", "3", "OT", "SO"]
    assert R.libelles_periodes("hockey", ["P1", "P2", "P3"], 3) == ["P1", "P2", "P3"]


def test_espn_validateur_et_mi_temps():
    tableau = {"events": [{"id": "9", "date": "2026-10-06T00:15Z", "competitions": [{
        "status": {"type": {"name": "STATUS_FULL_TIME"}},
        "competitors": [{"homeAway": "home", "score": "1", "team": {"displayName": "Banfield"}},
                        {"homeAway": "away", "score": "1", "team": {"displayName": "Rosario Central"}}]}]}]}
    fiche = {"header": {"competitions": [{"competitors": [
        {"homeAway": "home", "linescores": [{"displayValue": "1"}, {"displayValue": "0"}]},
        {"homeAway": "away", "linescores": [{"displayValue": "0"}, {"displayValue": "1"}]}]}]}}
    lire = lambda chemin, params=None: fiche if chemin.endswith("summary") else (    # noqa: E731
        tableau if params["dates"] == "20261005" else {})
    t0 = datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc)
    E = R.lire_espn("football", t0, datetime(2026, 10, 6, 10, tzinfo=timezone.utc), lire)
    E.append(enr("betmgm", "Banfield", "Rosario Central", (1, 1)))
    E[-1]["debut"] = E[0]["debut"]
    pari = {"sport": "football", "domicile": "Banfield", "exterieur": "Rosario Central", "debut": "2026-10-06T00:15:00Z"}
    r = R.consensus(pari, E)
    assert r["score"] == (1, 1) and r["sources"] == ["betmgm", "espn"] and r["periodes"] == []
    assert R.completer_periodes(pari, r, E, lire)["periodes"] == [(1, 0), (0, 1)]


def test_source_unique_fiable_apres_6_heures():
    seul = [enr("espn", "Honduras", "Jamaica", (1, 1))]
    assert R.consensus(PARI, seul, datetime(2026, 10, 6, 4, tzinfo=timezone.utc)) is None        # 2 h après
    assert R.consensus(PARI, seul, datetime(2026, 10, 6, 9, tzinfo=timezone.utc))["score"] == (1, 1)
    assert R.consensus(PARI, [enr("betmgm", "Honduras", "Jamaica", (1, 1))],
                       datetime(2026, 10, 6, 9, tzinfo=timezone.utc)) is None                     # pas assez fiable seul


def test_tennis_sets_espn():
    from cotes.reglement import scores_par_periode, regler
    pari = {"sport": "tennis", "domicile": "K.Muchova", "exterieur": "N.Osaka", "debut": "2026-10-06T07:00:00Z"}
    e = enr("espn", "Karolina Muchova", "Naomi Osaka", (2, 1), periodes=[(7, 5), (1, 6), (7, 6)], sport="tennis")
    e["debut"] = datetime(2026, 10, 6, 7, 10, tzinfo=timezone.utc)
    r = R.consensus(pari, [e], datetime(2026, 10, 6, 14, tzinfo=timezone.utc))
    sc = scores_par_periode("tennis", r["score"], r["periodes"], r["libelles"])
    assert regler({**pari, "marche": "JEUX_TOTAL", "periode": "SET1", "ligne": 8.5, "issue": "PLUS"}, sc) == "gagne"
    assert regler({**pari, "marche": "JEUX_TOTAL", "periode": "SET1", "ligne": 12.5, "issue": "PLUS"}, sc) == "perdu"


def test_tennis_scores_en_cours_de_betfair_et_pmu_ignores():
    # cas réel : Betfair figé à 1-1 et PMU à 0-0 alors qu'ESPN et Unibet UK donnent le match fini 2-1
    pari = {"sport": "tennis", "domicile": "K.Muchova", "exterieur": "N.Osaka", "debut": "2026-10-06T07:00:00Z"}
    E = [enr("orbitxch", "Karolina Muchova", "Naomi Osaka", (1, 1), sport="tennis"),
         enr("pmu", "Karolina Muchova", "Naomi Osaka", (30, 40), sport="tennis"),
         enr("unibet-uk", "Karolina Muchova", "Naomi Osaka", (2, 1), sport="tennis"),
         enr("espn", "Karolina Muchova", "Naomi Osaka", (2, 1), periodes=[(7, 5), (1, 6), (7, 6)], sport="tennis")]
    for e in E:
        e["debut"] = datetime(2026, 10, 6, 7, 10, tzinfo=timezone.utc)
    r = R.consensus(pari, E)
    assert r["score"] == (2, 1) and r["periodes"] == [(7, 5), (1, 6), (7, 6)]
    assert r["sources"] == ["espn", "unibet-uk"]
    # Betfair seul ne suffit jamais au tennis
    assert R.consensus(pari, [enr("orbitxch", "Karolina Muchova", "Naomi Osaka", (2, 0), sport="tennis")],
                       datetime(2026, 10, 6, 20, tzinfo=timezone.utc)) is None


def test_baseball_neuvieme_manche_non_jouee():
    # cas réel KBO : DraftKings liste la 9e manche à 0-0 (non jouée), Interwetten ne la liste pas
    pari = {"sport": "baseball", "domicile": "Hanwha Eagles", "exterieur": "SSG Landers", "debut": "2026-10-06T02:00:00Z"}
    m = [(0, 1), (3, 1), (0, 0), (0, 0), (5, 0), (0, 0), (1, 0), (0, 0)]
    E = [enr("draftkings", "Hanwha Eagles", "SSG Landers", (9, 2), periodes=m + [(0, 0)], sport="baseball"),
         enr("interwetten-de", "Hanwha Eagles", "SSG Landers", (9, 2), periodes=m, sport="baseball")]
    r = R.consensus(pari, E)
    assert r["periodes"][:5] == m[:5]
    from cotes.reglement import scores_par_periode, regler
    sc = scores_par_periode("baseball", r["score"], r["periodes"], r["libelles"])
    assert regler({**pari, "marche": "HANDICAP", "periode": "5_MANCHES", "ligne": -0.5, "issue": "DOM"}, sc) == "gagne"


def test_manuel_par_manches_baseball():
    from cotes.reglement import appliquer
    p = {"id": "x", "match_id": "pmu|1", "sport": "baseball", "statut": "a_regler", "marche": "HANDICAP",
         "periode": "5_MANCHES", "issue": "EXT", "ligne": -0.5, "mise": 10, "cote": 2.0, "debut": "2026-10-06T09:30:00Z"}
    m = {"pmu|1": {"score": [1, 3], "periodes": [[0, 0], [0, 0], [0, 0], [0, 1], [0, 0], [1, 0], [0, 0], [0, 0], [0, 2]]}}
    appliquer([p], {}, m)
    assert p["statut"] == "gagne"


def test_noms_francais_retrouves_par_la_reference():
    # cas réel : « Angleterre – Rép.Tchèque » chez Unibet, « England – Czechia » chez ESPN et Pinnacle
    pari = {"sport": "football", "domicile": "Angleterre", "exterieur": "Rép.Tchèque", "debut": "2026-10-06T02:00:00Z",
            "match_reference": "England - Czechia"}
    assert R.retrouver(pari, [enr("espn", "England", "Czechia", (3, 0))])[0]["score"] == (3, 0)
    # référence dans l'autre sens que le bookmaker : le score reste orienté comme le pari
    pari_inv = {**pari, "match_reference": "Czechia - England"}
    assert R.retrouver(pari_inv, [enr("espn", "England", "Czechia", (3, 0))])[0]["score"] == (3, 0)
    # espoirs : le marqueur U21 du bookmaker est reporté sur le nom Pinnacle, l'équipe A n'est pas prise
    u21 = {**pari, "domicile": "Portugal (U21)", "exterieur": "Rép. Tchèque (U21)", "match_reference": "Portugal - Czechia"}
    E = [enr("espn", "Portugal", "Czechia", (1, 0)), enr("orbitxch", "Portugal U21", "Czechia U21", (2, 0))]
    assert [r["source"] for r in R.retrouver(u21, E)] == ["orbitxch"]


def test_nette_majorite_contre_une_source_isolee():
    E = [enr("orbitxch", "Honduras", "Jamaica", (1, 1)), enr("draftkings", "Honduras", "Jamaica", (1, 1)),
         enr("espn", "Honduras", "Jamaica", (1, 1)), enr("unibet-uk", "Honduras", "Jamaica", (0, 0))]
    r = R.consensus(PARI, E)
    assert r["score"] == (1, 1) and "unibet-uk" not in r["sources"]
    assert R.consensus(PARI, E[:2] + E[3:]) is None                   # 2 contre 1 : pas assez net
    assert R.consensus(PARI, E + [enr("betmgm", "Honduras", "Jamaica", (0, 0))]) is None   # 3 contre 2


def test_hockey_tirs_au_but_sans_detail_de_la_seance():
    # revue externe (R2) : final 2-3 validé, périodes 1-0, 1-1, 0-1, prolongation 0-0, séance non détaillée :
    # le but des tirs au but ne doit pas disparaître du score « prolongation incluse »
    from cotes.reglement import scores_par_periode, regler
    pari = {"sport": "hockey", "domicile": "Rangers", "exterieur": "Bruins", "debut": "2026-10-06T02:00:00Z"}
    ps = [(1, 0), (1, 1), (0, 1), (0, 0)]
    E = [enr(s, "Rangers", "Bruins", (2, 3), periodes=ps, sport="hockey") for s in ("draftkings", "betmgm")]
    r = R.consensus(pari, E)
    sc = scores_par_periode("hockey", r["score"], r["periodes"], r["libelles"])
    assert sc["TEMPS_REG"] == (2, 2) and sc["MATCH"] == (2, 3)
    m = lambda marche, issue, ligne=None, periode="MATCH": {**pari, "marche": marche, "issue": issue,  # noqa: E731
                                                           "ligne": ligne, "periode": periode}
    assert regler(m("VAINQUEUR", "EXT"), sc) == "gagne"
    assert regler(m("TOTAL", "PLUS", 4.5), sc) == "gagne"
    assert regler(m("RESULTAT_1N2", "NUL", periode="TEMPS_REG"), sc) == "gagne"
    # un but d'écart sans égalité dans le temps réglementaire n'est pas une séance de tirs au but
    faux = [enr(s, "Rangers", "Bruins", (2, 3), periodes=[(1, 0), (1, 1), (0, 0)], sport="hockey")
            for s in ("draftkings", "betmgm")]
    assert R.consensus(pari, faux)["periodes"] == []


def test_resultat_a_l_heure_la_plus_proche():
    # revue externe (R5) : même affiche deux fois dans la fenêtre de 45 min, l'ordre de la liste ne décide plus
    from datetime import timedelta
    pari = {**PARI, "debut": "2026-10-06T02:30:00Z"}
    for sens in (1, -1):
        E = []
        for s in ("draftkings", "betmgm"):
            a, b = enr(s, "Honduras", "Jamaica", (0, 1)), enr(s, "Honduras", "Jamaica", (1, 0))
            b["debut"] = T + timedelta(minutes=30)
            E += [a, b][::sens]
        assert R.consensus(pari, E)["score"] == (1, 0)


def test_panne_d_un_validateur_visible_dans_le_journal(monkeypatch):
    # revue externe (R6) : un HTTP 500 sur draftkings/results apparaissait comme une lecture saine et vide
    import sys
    from pathlib import Path
    from cotes import pulsescore as P
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import cycle
    monkeypatch.setattr(P.time, "sleep", lambda s: None)

    class Rep:
        def __init__(self, code, corps=None):
            self.status_code, self.headers, self.corps = code, {}, corps

        def json(self):
            return self.corps

    c = P.Client("cle", pause=0)
    reponses = [Rep(500), Rep(200, {"results": []})]
    monkeypatch.setattr(c.s, "get", lambda *a, **k: reponses.pop(0))
    journal = {"etapes": {}}
    for bm in ("draftkings", "betmgm"):
        n = len(c.erreurs)
        assert cycle.etape(f"resultats_{bm}_football", journal, R.lire, c, bm, "soccer", "football", T) == []
        cycle.signaler(journal, f"resultats_{bm}_football", c.erreurs[n:])
    assert journal["etapes"]["resultats_draftkings_football"]["degrade"]
    assert "HTTP 500" in journal["etapes"]["resultats_draftkings_football"]["erreurs"][0]
    assert "degrade" not in journal["etapes"]["resultats_betmgm_football"]        # vraie liste vide : saine
