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
