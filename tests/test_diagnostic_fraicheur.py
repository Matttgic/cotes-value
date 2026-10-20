import unittest
import importlib.util
from pathlib import Path
from datetime import datetime, timezone
_spec = importlib.util.spec_from_file_location("diagnostiquer_fraicheur", Path(__file__).resolve().parents[1] / "scripts" / "diagnostiquer_fraicheur.py")
d = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d)

NOW = datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc)

def row(**kw):
    return {"source": "pinnacle", "collecte": "2026-10-20T00:59:40+00:00", "age_cache_s": 10,
            "sport": "football", "marche": "TOTAL", "periode": "MATCH", "match_id": 1, **kw}

class FraicheurTests(unittest.TestCase):
    def evaluate(self, **kw):
        return d.examiner(row(**kw), NOW)
    def test_recent(self):
        self.assertTrue(self.evaluate()["observation_et_cache_dans_objectif"])
    def test_cache_accumule(self):
        self.assertEqual(self.evaluate(age_cache_s=50)["statut"], "cache_ancien")
    def test_lecture_ancienne(self):
        self.assertEqual(self.evaluate(collecte="2026-10-20T00:58:00Z")["statut"], "observation_ancienne")
    def test_sans_date(self):
        self.assertEqual(self.evaluate(collecte=None)["statut"], "horodatage_invalide")
    def test_sans_fuseau(self):
        self.assertEqual(self.evaluate(collecte="2026-10-20T00:59:40")["statut"], "horodatage_invalide")
    def test_future(self):
        self.assertEqual(self.evaluate(collecte="2026-10-20T01:00:01Z")["statut"], "horloge_incoherente")
    def test_cache_inconnu(self):
        self.assertEqual(self.evaluate(age_cache_s=None)["statut"], "cache_inconnu_pinnacle")
    def test_cache_negatif(self):
        self.assertEqual(self.evaluate(age_cache_s=-1)["statut"], "age_cache_invalide")
    def test_cache_booleen(self):
        self.assertEqual(self.evaluate(age_cache_s=True)["statut"], "age_cache_invalide")
    def test_cache_infini(self):
        self.assertEqual(self.evaluate(age_cache_s=float("inf"))["statut"], "age_cache_invalide")
    def test_perimee(self):
        self.assertEqual(self.evaluate(cote_perimee=True)["statut"], "perimee_signalee")
    def test_suspendue(self):
        self.assertEqual(self.evaluate(status="suspended")["statut"], "suspendue")
        self.assertFalse(self.evaluate(status="suspended")["observation_et_cache_dans_objectif"])
    def test_book_age_source_inconnu(self):
        self.assertEqual(self.evaluate(source="winamax", age_cache_s=None)["statut"], "observation_recente_age_source_inconnu")
    def test_borne_60(self):
        self.assertTrue(self.evaluate(age_cache_s=40)["observation_et_cache_dans_objectif"])
    def test_borne_depassee(self):
        self.assertFalse(self.evaluate(age_cache_s=40.001)["observation_et_cache_dans_objectif"])
    def test_debut_telechargement(self):
        self.assertEqual(self.evaluate(collecte_debut="2026-10-20T00:59:00Z")["age_cache_estime_s"], 70)
    def test_debut_apres_reception(self):
        self.assertEqual(self.evaluate(collecte_debut="2026-10-20T00:59:50Z")["statut"], "horloge_incoherente")
    def test_source_amont_non_certifiee(self):
        self.assertFalse(self.evaluate()["prix_amont_verifie"])
    def test_fuseaux(self):
        self.assertEqual(self.evaluate(collecte="2026-10-20T02:59:40+02:00")["age_observation_s"], 20)
    def test_now_sans_fuseau(self):
        with self.assertRaises(ValueError):
            d.examiner(row(), NOW.replace(tzinfo=None))
    def test_seuil_invalide(self):
        with self.assertRaises(ValueError):
            d.examiner(row(), NOW, -1)
    def test_resume(self):
        out = d.resumer([row(), row(match_id=2), row(source="pmu", age_cache_s=None), None], NOW)
        self.assertEqual(len(out["groupes"]), 2)
        self.assertEqual(out["objets_non_lignes"], 1)
        self.assertEqual(out["groupes"][0]["matchs_distincts"], 2)
    def test_statistiques(self):
        self.assertEqual(d.mediane([30, 10, 20, 40]), 25)
        self.assertEqual(d.p95(list(range(1, 101))), 95)

if __name__ == "__main__":
    unittest.main()
