"""Historique quotidien des notes : dernier calcul du jour gardé, 60 jours, repères veille et J−7."""
from datetime import datetime, timezone

from cotes import historique_notes as H


def test_notes_du_laboratoire_toutes_les_lignes():
    labo = {"futur": [{"id": "PIN-1", "note": {"total": 70}}, {"id": "PIN-2", "note": None}],
            "comparateurs_futur": {"Eden (rejeu)": {"note": {"total": 55}}},
            "bases_futur": {"Pinnacle": {"note": {"total": 33}}}}
    assert H.notes_du_laboratoire(labo) == {"PIN-1": 70, "Eden (rejeu)": 55, "base:Pinnacle": 33}


def test_jour_remplace_garde_soixante_jours_et_reperes(tmp_path):
    t = lambda j, h=12: datetime(2026, 11, j, h, tzinfo=timezone.utc)
    H.mettre_a_jour(tmp_path, {"a": 50}, t(1))
    H.mettre_a_jour(tmp_path, {"a": 52}, t(1, 20))                 # même jour (Paris) : remplacé
    doc = H.mettre_a_jour(tmp_path, {"a": 60}, t(9))
    assert doc["jours"] == {"2026-11-01": {"a": 52}, "2026-11-09": {"a": 60}}
    r = H.reperes(doc, t(9))
    assert r["veille"] == {"jour": "2026-11-01", "notes": {"a": 52}} and r["semaine"]["jour"] == "2026-11-01"
    vieux = H.mettre_a_jour(tmp_path, {"a": 61}, datetime(2027, 1, 15, tzinfo=timezone.utc))
    assert list(vieux["jours"]) == ["2027-01-15"]                    # au-delà de 60 jours : oublié


def test_fichier_illisible_repart_de_zero(tmp_path):
    (tmp_path / H.FICHIER).write_text("{pas du json")
    doc = H.mettre_a_jour(tmp_path, {"a": 1}, datetime(2026, 11, 3, tzinfo=timezone.utc))
    assert doc == {"version": H.VERSION, "jours": {"2026-11-03": {"a": 1}}}
    assert H.reperes(doc, datetime(2026, 11, 3, tzinfo=timezone.utc)) == {}


def test_notes_d_une_ancienne_formule_oubliees(tmp_path):
    """Les notes v1 (par pari) ne sont pas comparables aux notes v2 (par match) : pas de fausse progression."""
    import json
    (tmp_path / H.FICHIER).write_text(json.dumps({"jours": {"2026-11-01": {"a": 80}}}))
    doc = H.mettre_a_jour(tmp_path, {"a": 40}, datetime(2026, 11, 8, tzinfo=timezone.utc))
    assert doc["jours"] == {"2026-11-08": {"a": 40}}
