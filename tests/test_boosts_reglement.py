"""Règlement à la main des boosts « jouer » (cotes/boosts.py, scripts/regler_boosts.py)."""
import json
from datetime import datetime, timezone

from cotes import boosts as B
from cotes.site.construction import boosts_publies
from scripts import regler_boosts as R

T = datetime(2026, 11, 19, 18, tzinfo=timezone.utc)
EP = [{"id": "winamax|1|2", "premier": "2026-11-18T10:00:00+00:00", "dernier": "2026-11-18T19:00:00+00:00",
       "bookmaker": "Winamax", "libelle": "Zverev gagne 2-0", "domicile": "Zverev", "exterieur": "Shelton",
       "debut": "2026-11-18T19:30:00+00:00", "cote": 2.4, "mise_max": 20.0, "verdict_initial": "jouer"},
      {"id": "unibet|3", "premier": "2026-11-18T10:00:00+00:00", "debut": "2026-11-18T19:30:00+00:00", "cote": 3.0,
       "verdict_initial": "passer"},
      {"id": "unibet|4", "premier": "2026-11-19T10:00:00+00:00", "debut": "2026-11-20T19:30:00+00:00", "cote": 3.0,
       "verdict_initial": "jouer"}]


def test_a_regler_seulement_jouer_et_match_commence():
    out = B.boosts_a_regler(EP, {}, T)
    assert [x["id"] for x in out] == ["winamax|1|2"]
    assert out[0]["code"] == B.code_boost("winamax|1|2") and out[0]["mise"] == 20.0


def test_gain_et_bilan():
    g = B.regler_boost(EP[0], "gagne", T, "6-4 6-3")
    p = B.regler_boost({**EP[0], "id": "x", "mise_max": None}, "perdu", T)
    assert g["gain"] == 28.0 and p["gain"] == -10.0 and p["mise"] == 10.0
    s = B.bilan_regles({"a": g, "b": p, "c": B.regler_boost({**EP[0], "id": "y"}, "rembourse", T)})
    assert s == {"n": 3, "gagnes": 1, "mise": 30.0, "gain": 18.0, "roi": 0.6}


def test_script_ecrit_les_resultats_et_le_site_les_publie(tmp_path):
    (tmp_path / "boosts.json").write_text(json.dumps({"episodes": EP}), encoding="utf-8")
    lignes = R.regler(tmp_path, [B.code_boost("winamax|1|2").lower() + "=gagné:6-4 6-3"], T)
    assert "gagné" in lignes[0] and "+28.00" in lignes[0]
    res = json.loads((tmp_path / "boosts_resultats.json").read_text(encoding="utf-8"))
    pub = boosts_publies({"episodes": EP}, T, res)
    assert pub["a_regler"] == [] and pub["bilan_regles"]["gain"] == 28.0 and pub["regles"][0]["score"] == "6-4 6-3"
