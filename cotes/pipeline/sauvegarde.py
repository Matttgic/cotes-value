"""Sauvegarde du cycle dans « donnees » (déplacée de scripts/cycle.py, E3.2) : paris, contrôle, opportunités,
état et surveillance, dans l'ordre d'écriture d'origine."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cotes import echecs, historiques, liens, memoire, stockage
from cotes.depot.json_io import ecrire_json, lire_json
from cotes.pipeline.contexte import Contexte
from cotes.pipeline.outils import retirer_obsoletes
from cotes.temps import instant_utc


def _instant(valeur):
    return instant_utc(valeur)


# controle.json (3 Mo) n'est publié dans « donnees » qu'une fois par heure ; la version de chaque cycle vit
# dans la mémoire (controle.json.gz). Mémoire perdue : on repart de la dernière publication (moins d'une heure).
CONTROLE_PUBLICATION_MIN = float(os.environ.get("CONTROLE_PUBLICATION_MIN", "55"))


def _derniere_mesure(doc) -> datetime | None:
    groupes = doc.get("groupes") if isinstance(doc, dict) else None
    moments = [_instant(g.get("maj")) for g in groupes.values() if isinstance(g, dict)] if isinstance(groupes, dict) else []
    moments = [m for m in moments if m is not None]
    return max(moments) if moments else None


def lire_controle(donnees: Path) -> dict:
    """État cumulé du contrôle : la mémoire du cycle précédent, ou la publication horaire si elle est plus
    récente (mémoire absente ou restaurée d'un vieux cache). Publication illisible : erreur, comme avant."""
    publie = lire_json(donnees / "controle.json", {})
    publie = publie if isinstance(publie, dict) else {}
    doc = memoire.lire(donnees, "controle", None, ancien_aussi=False)
    if not isinstance(doc, dict) or (_derniere_mesure(publie) or datetime.min.replace(tzinfo=timezone.utc)) > (
            _derniere_mesure(doc) or datetime.min.replace(tzinfo=timezone.utc)):
        doc = publie
    doc.pop("publie", None)
    return doc


def enregistrer_controle(donnees: Path, etat_controle: dict, maintenant: datetime) -> bool:
    """Mémoire à chaque cycle ; copie compacte dans « donnees » si la dernière date d'au moins 55 min."""
    memoire.ecrire(donnees, "controle", etat_controle, retirer_ancien=False)
    publie = donnees / "controle.json"
    try:
        derniere = _instant(json.loads(publie.read_text(encoding="utf-8")).get("publie"))
    except (OSError, ValueError, AttributeError):
        derniere = None
    if derniere is not None and timedelta(0) <= maintenant - derniere < timedelta(minutes=CONTROLE_PUBLICATION_MIN):
        return False
    ecrire_json(publie, {**etat_controle, "publie": maintenant.isoformat(timespec="seconds")}, compact=True)
    return True


def sauvegarder(ctx: Contexte, reglement_seul: bool = False) -> None:
    """Écrit le cycle dans « donnees ». ``reglement_seul`` : chemin du cycle « règlement seul » (paris et état
    seulement, journal du règlement conservé avant la fusion des échecs, comme avant)."""
    # importé ici pour éviter un import circulaire (reglement importe sauvegarde)
    from cotes.pipeline.reglement import conserver_journal_reglement
    donnees, maintenant, journal = ctx.donnees, ctx.maintenant, ctx.journal
    ctx.paris = stockage.archiver(donnees, ctx.paris, maintenant)      # réglés depuis plus de 30 jours -> archives
    liens.completer_liens(ctx.paris)                                  # lien direct vers le match chez le bookmaker
    ecrire_json(donnees / "paris.json", ctx.paris)
    retirer_obsoletes(donnees, journal)
    if reglement_seul:
        etat = lire_json(donnees / "etat.json", {})
        journal["fin"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conserver_journal_reglement(etat, journal, ctx.regle)
        echecs.fusionner(etat, journal.get("echecs", []), maintenant)
        ecrire_json(donnees / "etat.json", etat)
        return
    opportunites, francais = ctx.opportunites, ctx.francais
    journal["controle_publie"] = enregistrer_controle(donnees, ctx.etat_controle, maintenant)
    ecrire_json(donnees / "opportunites_actuelles.json", sorted(opportunites, key=lambda o: -o["ecart"]))
    if opportunites:
        jour = donnees / "opportunites" / f"{maintenant:%Y-%m-%d}.jsonl.gz"
        jour.parent.mkdir(parents=True, exist_ok=True)
        # Ajout atomique (copie + nouveau membre gzip + os.replace) : un job tué ne tronque jamais le fichier.
        historiques.ajouter_gzip(jour, "".join(json.dumps(o, ensure_ascii=False) + "\n" for o in opportunites))
    etat = lire_json(donnees / "etat.json", {})
    journal.update({
        "fin": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cotes": {"francaises": len(francais), "pinnacle": len(ctx.pinnacle), "polymarket": len(ctx.polymarket),
                  "smarkets": len(ctx.smarkets), "matchbook": len(ctx.matchbook),
                  "betfair": len(ctx.betfair)},
        "matchs_francais": len({l["match_id"] for l in francais}),
        "opportunites": sum(not o.get("suspect") for o in opportunites),
        "opportunites_suspectes": sum(bool(o.get("suspect")) for o in opportunites),
        "nouveaux_paris": len(ctx.nouveaux)})
    etat.update({"dernier_cycle": journal})
    echecs.fusionner(etat, journal.get("echecs", []), maintenant)
    conserver_journal_reglement(etat, journal, ctx.regle)
    historique = etat.get("historique", [])[-200:] + [{k: journal[k] for k in ("debut", "mode", "opportunites",
                                                                                "nouveaux_paris")}]
    etat["historique"] = historique
    ecrire_json(donnees / "etat.json", etat)
    from cotes import surveillance                                      # noqa: E402
    journal["surveillance"] = surveillance.surveiller(donnees, journal.get("etapes", {}))
