"""Collecte et comparaison des cotes ; le règlement fonctionne aussi en cycle indépendant.

Lancé toutes les 5 minutes par GitHub Actions (.github/workflows/collecte.yml).

    python scripts/cycle.py                 # cycle complet (bookmakers français lus en direct, 36 h)
    python scripts/cycle.py --mode test     # cycle réduit : Winamax + Betclic, foot, 1 page
    python scripts/cycle.py --reglement oui # forcer le règlement des paris à ce cycle

Le règlement des paris (lecture des résultats : environ 6 minutes, 220 requêtes) n'a lieu qu'une fois par
heure (REGLEMENT_MINUTES, 55 par défaut) : les cotes, elles, sont lues à chaque cycle.

Données (branche « donnees ») : paris.json, etat.json, opportunites/AAAA-MM-JJ.jsonl, cotes/AAAA-MM-JJ.jsonl.gz,
references/, releves/ et correspondances/ (cotes/historiques.py),
resultats_manuels.json (règlements faits à la main ; « supprime » retire un pari). Site : dossier site/.
Mémoire de travail (cache Actions, MEMOIRE_CHEMIN) : horizon_direct, caches de secours, contrôle (cotes/memoire.py).

Les arguments et l'enchaînement des étapes (collecte → analyse → prise → règlement → sauvegarde, puis le site) sont
dans cotes/pipeline/cycle.py ; même commande : python -m cotes cycle (ou reglement pour --seulement-reglement).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.pipeline import cycle as pipeline_cycle  # noqa: E402
from cotes.pipeline import reglement as pipeline_reglement  # noqa: E402,F401
from cotes.pipeline.analyse import analyser  # noqa: E402,F401
from cotes.pipeline.collecte import collecter  # noqa: E402,F401
from cotes.pipeline.contexte import Contexte  # noqa: E402,F401
from cotes.pipeline.prise import prendre  # noqa: E402,F401
from cotes.pipeline.sauvegarde import sauvegarder  # noqa: E402,F401

# Noms gardés sur le module pour les tests et les appelants (le code est dans cotes/pipeline/ depuis la phase 3) :
# modules dont les tests remplacent une fonction, et fonctions déplacées.
from cotes import (flashscore, livescore, pinnacle, pinnacle_secours, polymarket, resultats_nhl,  # noqa: E402,F401
                   smarkets)
from cotes import resultats as resultats_mod  # noqa: E402,F401
from cotes.direct import betclic as betclic_direct  # noqa: E402,F401
from cotes.direct import fanduel as fanduel_direct  # noqa: E402,F401
from cotes.direct import netbet as netbet_direct  # noqa: E402,F401
from cotes.direct import olybet as olybet_direct  # noqa: E402,F401
from cotes.direct import pmu as pmu_direct  # noqa: E402,F401
from cotes.direct import unibet as unibet_direct  # noqa: E402,F401
from cotes.direct import winamax as winamax_direct  # noqa: E402,F401
from cotes.depot.json_io import lire_json, ecrire_json  # noqa: E402,F401
from cotes.sources import registre as registre_sources  # noqa: E402,F401
from cotes.pipeline.collecte import (HORIZON_H, BUDGETS, MEMOIRES, SMARKETS_FRAIS_MIN, AGE_REPLI_MIN,  # noqa: E402,F401
                                     SPORTS_PRECEDENTS_GARDE_H, etape_bornee, source_bornee, appliquer_smarkets,
                                     appliquer_matchbook, appliquer_betfair, _appliquer_bourse, _cache_sm, noter_lecture,
                                     _radar_depuis, repli_reserve, sports_precedents, memoriser_sports,
                                     collecter_prematch)
from cotes.pipeline.outils import (etape, signaler, TEMOIN_ABANDONNE, FICHIERS_OBSOLETES,  # noqa: E402,F401
                                   retirer_obsoletes, charger_paris)
from cotes.pipeline.prise import redecider, suivre_qwen  # noqa: E402,F401
from cotes.pipeline.reglement import (REGLEMENT_MINUTES, reglement_echu,  # noqa: E402,F401
                                      conserver_journal_reglement, _regler_props, effectuer_reglement)
from cotes.pipeline.sauvegarde import (CONTROLE_PUBLICATION_MIN, _derniere_mesure,  # noqa: E402,F401
                                       lire_controle, enregistrer_controle)


def _construire_site(donnees: Path, sortie: Path):
    """Le site par `site_web` (chemin de scripts/) : un test peut le remplacer dans sys.modules."""
    from site_web import construire
    return construire(donnees, sortie)


def main() -> int:
    """Arguments et enchaînement dans cotes/pipeline/cycle.py (E6.1) ; même commande : python -m cotes cycle."""
    return pipeline_cycle.main(construire_site=_construire_site)


if __name__ == "__main__":
    sys.exit(main())
