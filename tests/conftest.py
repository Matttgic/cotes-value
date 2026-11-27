"""Les pauses de réessai et d'espacement des requêtes ne doivent pas ralentir les tests.

Seul `time.sleep` des modules de lecture est neutralisé (chacun reçoit un `time` de remplacement) ;
l'horloge globale, elle, n'est pas touchée : les tests de budgets et de fils gardent leur vrai temps.
Un test qui veut observer les pauses remplace `module.time.sleep` lui-même, comme avant.
"""
import hashlib
import time

import pytest


def pytest_make_parametrize_id(config, val, argname):
    """Identifiant stable pour un gzip passé en paramètre : son en-tête porte l'heure de compression, qui changeait
    l'identifiant d'une collecte à l'autre. Avec pytest-xdist (``-n``), deux processus qui collectaient à des secondes
    différentes ne voyaient plus les mêmes tests et la session s'arrêtait."""
    if isinstance(val, bytes) and len(val) >= 10 and val[:3] == b"\x1f\x8b\x08":
        return "gzip-" + hashlib.sha256(val[:4] + bytes(4) + val[8:]).hexdigest()[:12]
    return None


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
