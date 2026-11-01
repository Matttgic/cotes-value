"""Les pauses de réessai et d'espacement des requêtes ne doivent pas ralentir les tests.

Seul `time.sleep` des modules de lecture est neutralisé (chacun reçoit un `time` de remplacement) ;
l'horloge globale, elle, n'est pas touchée : les tests de budgets et de fils gardent leur vrai temps.
Un test qui veut observer les pauses remplace `module.time.sleep` lui-même, comme avant.
"""
import time

import pytest


class _TempsSansPause:
    def __getattr__(self, nom):
        return getattr(time, nom)

    @staticmethod
    def sleep(_secondes):
        return None


@pytest.fixture(autouse=True)
def _sans_pauses_reelles(monkeypatch):
    from cotes import pinnacle, smarkets
    from cotes.direct import matchbook
    for module in (pinnacle, smarkets, matchbook):
        monkeypatch.setattr(module, "time", _TempsSansPause())
