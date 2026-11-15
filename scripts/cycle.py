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

Ce script lit les arguments et enchaîne les étapes de cotes/pipeline/ sur un même Contexte : collecte → analyse →
prise → règlement → sauvegarde, puis le site (scripts/site_web.py).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.pipeline import reglement as pipeline_reglement  # noqa: E402
from cotes.pipeline.analyse import analyser  # noqa: E402
from cotes.pipeline.collecte import collecter  # noqa: E402
from cotes.pipeline.contexte import Contexte  # noqa: E402
from cotes.pipeline.prise import prendre  # noqa: E402
from cotes.pipeline.sauvegarde import sauvegarder  # noqa: E402

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


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--mode", choices=["complet", "test"], default=os.environ.get("MODE_COLLECTE", "complet"))
    a.add_argument("--donnees", default="donnees")
    a.add_argument("--site", default="site")
    a.add_argument("--sans-site", action="store_true",
                   help="Sauvegarder la collecte avant le chemin rapide d'alertes ; site construit ensuite")
    a.add_argument("--reglement", choices=["auto", "oui", "non"], default=os.environ.get("REGLEMENT", "auto"),
                   help="auto = si le dernier règlement date d'au moins REGLEMENT_MINUTES")
    a.add_argument("--reprise", default=os.environ.get("REPRISE_CHEMIN", ""),
                   help="Dernier bon état des références (gzip, hors branche « donnees ») ; vide = aucune reprise")
    a.add_argument("--seulement-reglement", action="store_true",
                   help="Régler les paris sans interroger les cotes ni créer de nouveaux paris")
    args = a.parse_args()
    donnees = Path(args.donnees)
    maintenant = datetime.now(timezone.utc)
    journal = {"debut": maintenant.isoformat(timespec="seconds"), "mode": args.mode, "etapes": {}}

    ctx = Contexte(maintenant=maintenant, mode=args.mode, donnees=donnees,
                   reprise=Path(args.reprise) if args.reprise else None, journal=journal)
    if args.seulement_reglement:
        # Cycle indépendant : aucune collecte ni placement de paris (cotes/pipeline/reglement.py).
        pipeline_reglement.regler_seul(ctx, args.reglement)
        if not args.sans_site:          # serveur en direct : le site est construit par site.yml
            from site_web import construire
            construire(donnees, Path(args.site))
        print(json.dumps({"mode": "reglement", "resultats": journal.get("resultats"), "theodds": journal.get("theodds"),
                          "etapes": journal.get("etapes", {})}, ensure_ascii=False))
        return 0

    # 1-2. collecte : références, bookmakers français, bourses, dérive (cotes/pipeline/collecte.py)
    collecter(ctx)
    # 3. analyse : association, contrôle des intitulés, comparaison, props, mouvement (cotes/pipeline/analyse.py)
    analyser(ctx)
    # 4. prise : placement, décisions figées, Qwen, suivi des prix et de la clôture (cotes/pipeline/prise.py)
    prendre(ctx)
    # La collecte reprend le règlement si le workflow horaire a été retardé.
    pipeline_reglement.regler(ctx, args.reglement)
    # 5. sauvegarde (cotes/pipeline/sauvegarde.py)
    sauvegarder(ctx)

    # 6. site
    if not args.sans_site:
        from site_web import construire                                 # noqa: E402
        construire(donnees, Path(args.site))
    print(json.dumps({k: journal[k] for k in ("mode", "cotes", "matchs_francais", "opportunites", "nouveaux_paris",
                                               "controle", "etapes")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
