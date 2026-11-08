"""Chaque stratégie isolée pendant la construction du site (cotes/protection.py)."""
import pytest

from cotes import strategies_prudentes
from cotes.decisions import figer_selecteur
from cotes.protection import calculer, proteger_strategies


def _boum(*_a, **_k):
    raise ZeroDivisionError("division par zéro")


def test_hors_site_l_erreur_remonte():
    # Le cycle ne doit jamais figer un faux refus : l'erreur arrête le cycle, comme avant.
    with pytest.raises(ZeroDivisionError):
        calculer("x", _boum)
    selecteur = figer_selecteur("test_boum")(_boum)
    with pytest.raises(ZeroDivisionError):
        selecteur([{"id": "a"}])


def test_dans_le_site_l_erreur_est_notee_une_fois(capsys):
    with proteger_strategies() as echecs:
        assert calculer("grok_1", _boum) == set()
        assert calculer("grok_1", _boum) == set()
        assert calculer("liste", _boum, list) == []
        assert calculer("ok", lambda: {1}) == {1}
    assert set(echecs) == {"grok_1", "liste"}
    assert echecs["grok_1"]["etape"] == "stratégie grok_1"
    assert "ZeroDivisionError" in echecs["grok_1"]["message"]
    assert capsys.readouterr().out.count("::warning") == 2
    with pytest.raises(ZeroDivisionError):      # contexte refermé : comportement normal
        calculer("x", _boum)


def test_les_decisions_figees_restent_affichees():
    selecteur = figer_selecteur("test_boum")(_boum)
    fige = {"id": "a", "selections_figees": {"test_boum": {"version": "1"}}}
    autre = {"id": "b", "selections_figees": {}}
    with proteger_strategies() as echecs:
        assert selecteur([fige, autre]) == {id(fige)}
    assert "test_boum" in echecs


def test_une_variante_en_erreur_n_arrete_pas_les_autres(monkeypatch):
    monkeypatch.setattr(strategies_prudentes, "paris_grok", _boum)
    with proteger_strategies() as echecs:
        resultat = strategies_prudentes.selections_prudentes([])
    for g in strategies_prudentes.GROKS:
        assert resultat[g["cle"]] == set()
        assert g["cle"] in echecs
    for cle in ("claude_prudent", "convergence_3", "qwen_persistence", "coeur_value", "liquidite_sure"):
        assert cle in resultat and cle not in echecs


def test_le_site_se_construit_malgre_une_strategie_en_erreur(tmp_path, monkeypatch):
    import json
    import re
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import site_web
    monkeypatch.setattr(strategies_prudentes, "paris_grok", _boum)
    paris = [{"id": f"p{i}", "simulation": "A", "reference": "Pinnacle", "match_id": f"m{i}", "marche": "TOTAL",
              "periode": "MATCH", "ligne": 2.5, "issue": "PLUS", "detecte": f"2026-10-01T10:{i:02d}",
              "statut": "en_cours", "cote": 2.0, "bookmaker": "Winamax", "sport": "football", "mise": 10,
              "gain": None, "clv": None} for i in range(3)]
    (tmp_path / "paris.json").write_text(json.dumps(paris), encoding="utf-8")
    html = site_web.construire(tmp_path, tmp_path / "site").read_text(encoding="utf-8")
    d = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1).replace("<\\/", "</"))
    etapes = {e["etape"] for e in d["etat"]["echecs_recents"]["liste"]}
    assert {f"stratégie {g['cle']}" for g in strategies_prudentes.GROKS} <= etapes
    assert d["bilan"]["A|Toutes"]["en_cours"] == 3
