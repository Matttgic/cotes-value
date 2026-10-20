import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("observer_collecte", SCRIPTS / "observer_collecte.py")
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)
NOW = datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc)

class ObservationTests(unittest.TestCase):
    def test_un_appel_et_pas_de_mutation(self):
        calls = []
        pin = {"source": "pinnacle", "sport": "football", "collecte": NOW.isoformat(), "age_cache_s": 10}
        fr = {"source": "Unibet", "bookmaker": "unibet-fr", "collecte": (NOW-timedelta(minutes=10)).isoformat()}
        before = dict(fr)
        def collecter(mode, debut, journal, travail):
            calls.append((mode, debut))
            self.assertEqual(os.environ["PINNODDS_API_KEY"], "")
            self.assertEqual(os.environ["PINBOOK_API_KEY"], "")
            self.assertEqual(json.loads((travail/"horizon_direct.json").read_text()), {"test": 1})
            (travail/"horizon_direct.json").write_text("{}")
            journal["etapes"]["pinnacle"] = {"ok": True, "secondes": 2, "erreur": "secret-interdit"}
            return [pin], [], [fr]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reserve = root/"reserve.json"
            reserve.write_text('{"test": 1}')
            report = o.observer(SimpleNamespace(collecter_prematch=collecter), root/"rapport", reserve, horloge=lambda: NOW)
            self.assertEqual(json.loads(reserve.read_text()), {"test": 1})
            self.assertTrue((root/"rapport"/"fraicheur-cycle.json").is_file())
            self.assertNotIn("secret-interdit", (root/"rapport"/"fraicheur-cycle.json").read_text())
        self.assertEqual(len(calls), 1)
        self.assertEqual(fr, before)
        self.assertEqual(report["sources"]["unibet"]["observations_depuis_debut_essai"], 0)
        self.assertEqual(report["sources"]["pinnacle_direct"]["lignes_presentes"], 1)
        self.assertEqual(report["sources"]["winamax"]["etat"], "aucune_ligne_observee")
    def test_environnement_restaure_meme_si_erreur(self):
        with patch.dict(os.environ, {"PINNODDS_API_KEY": "test-secret"}):
            with self.assertRaises(RuntimeError):
                with o.environnement_essai():
                    self.assertEqual(os.environ["PINNODDS_API_KEY"], "")
                    raise RuntimeError()
            self.assertEqual(os.environ["PINNODDS_API_KEY"], "test-secret")
    def test_origines_separees(self):
        groupes = o.regrouper([{"source": "pinnacle"}, {"source": "pinnacle", "origine": "pinnodds"}], [])
        self.assertEqual(len(groupes["pinnacle_direct"]), 1)
        self.assertEqual(len(groupes["pinnacle_origine_inattendue"]), 1)
    def test_sortie_existante_refusee(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                o.observer(None, tmp)
    def test_pas_de_noms_equipes_dans_rapport(self):
        def collecter(*args):
            return [], [], [{"source": "Winamax", "domicile": "SECRET_EQUIPE", "collecte": NOW.isoformat()}]
        with tempfile.TemporaryDirectory() as tmp:
            report = o.observer(SimpleNamespace(collecter_prematch=collecter), Path(tmp)/"sortie", horloge=lambda: NOW)
            self.assertNotIn("SECRET_EQUIPE", json.dumps(report))
    def test_reserve_absente_refusee(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                o.observer(None, Path(tmp)/"sortie", Path(tmp)/"absent", horloge=lambda: NOW)
    def test_mode_invalide_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                o.observer(None, Path(tmp)/"sortie", mode="inconnu")

if __name__ == "__main__":
    unittest.main()
