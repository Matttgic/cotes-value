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
