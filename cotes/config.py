"""Catalogue des variables d'environnement (docs/architecture-cible.md, E1.1).

Une entrée par variable lue par le code (`cotes/`, `scripts/`), passée par un workflow ou prévue dans
`.env.example` et `serveur/env.exemple`. `defaut` est la valeur effective du code quand la variable est absente
ou vide (pas celle du YAML : `tests/test_config.py` liste les écarts). Secrets : nom seulement, jamais de valeur.

    python -m cotes.config            # tableau Markdown du catalogue

Les modules lisent encore `os.environ` eux-mêmes ; `lire` servira à les y faire passer un par un (E1.2).
"""
from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Variable:
    defaut: str = ""
    type: Callable = str
    role: str = ""
    secret: bool = False


def _secret(role: str) -> Variable:
    return Variable(role=role, secret=True)


VARIABLES: dict[str, Variable] = {
    # cycle
    "MODE_COLLECTE": Variable("complet", str, "cycle : complet (36 h, toutes les sources) ou test (réduit)"),
    "REGLEMENT": Variable("auto", str, "cycle : règlement auto (si échu), oui ou non"),
    "REGLEMENT_MINUTES": Variable("55", float, "minutes minimum entre deux règlements"),
    "CONTROLE_PUBLICATION_MIN": Variable("55", float, "minutes entre deux publications de controle.json"),
    "REPRISE_CHEMIN": Variable("", str, "fichier de reprise des références (cache Actions) ; vide : aucune reprise"),
    "MEMOIRE_CHEMIN": Variable("", str, "dossier de la mémoire de travail ; vide : le dossier des données"),
    "CYCLE_MINUTES": Variable("5", float, "durée d'un cycle pour les seuils de surveillance (1 sur le serveur)"),
    # Pinnacle
    "PINNACLE_API_KEY": _secret("clé Pinnacle ; absente : clé lue sur le site, puis clé historique"),
    "PINNACLE_AGE_MAX_MIN": Variable("10", float, "âge maximum d'une cote Pinnacle proche du coup d'envoi (min)"),
    "PINNACLE_AGE_MAX_LOIN_MIN": Variable("16", float, "âge maximum d'une cote Pinnacle lointaine (min)"),
    "PINNACLE_CHOIX_PRIX": Variable("", str, "« non » coupe le choix d'orthographe de l'URL des prix"),
    "PINNACLE_PROXY_URL": _secret("relais HTTP vers Pinnacle (facultatif)"),
    "PINNACLE_RECHAUFFEUR_URL": _secret("réchauffeur Pinnacle (Supabase)"),
    "PINNACLE_RECHAUFFEUR_SECRET": _secret("secret du réchauffeur Pinnacle"),
    # secours Pinnacle
    "PINNODDS_API_KEY": _secret("secours Pinnacle Pinnodds"),
    "PINNODDS_HANDICAPS": Variable("non", str, "« oui » : le secours lit aussi les handicaps"),
    "PINNODDS_LIMITE_JOUR": Variable("90", int, "requêtes Pinnodds par jour"),
    "PINNODDS_PAUSE_MIN": Variable("30", int, "pause entre deux secours Pinnodds (min)"),
    "PINBOOK_API_KEY": _secret("secours Pinnacle PinBook"),
    "PINBOOK_LIMITE_JOUR": Variable("16", int, "requêtes PinBook par jour"),
    "PINBOOK_PAUSE_MIN": Variable("60", int, "pause entre deux secours PinBook (min)"),
    "PINBOOK_SPORTS": Variable("football,tennis,basket", str, "sports que PinBook peut combler"),
    "PINNACLE_SECOURS_PERIME": Variable("football", str, "sports secourus quand Pinnacle est périmé ; « non » coupe"),
    # autres sources
    "POLYMARKET_FLUX": Variable("", str, "dossier du flux websocket Polymarket (serveur) ; vide : inactif"),
    "SMARKETS_COLLECTE": Variable("non", str, "« oui » : le cycle lit Smarkets"),
    "SMARKETS_DANS_DECISION": Variable("non", str, "« oui » : Smarkets entre dans le consensus"),
    "SOURCE_MATCHBOOK": Variable("direct", str, "Matchbook : direct, shadow ou off"),
    "SOURCE_BETFAIR": Variable("", str, "Betfair : direct, shadow ou off ; vide : direct si SERVEUR_DIRECT=oui"),
    "SOURCE_FANDUEL": Variable("off", str, "FanDuel (référence props) : direct, shadow ou off"),
    "SOURCE_DRAFTKINGS": Variable("off", str, "DraftKings (référence) : direct, shadow ou off"),
    "SOURCE_OLYBET": Variable("direct", str, "OlyBet : direct ou off"),
    "SOURCE_NETBET": Variable("direct", str, "NetBet : direct ou off"),
    "BETFAIR_AK": _secret("clé d'application Betfair"),
    "PROPLINE_API_KEY": _secret("résultats des props joueurs (PropLine)"),
    "THESPORTSDB_API_KEY": _secret("résultats de secours (TheSportsDB)"),
    "THE_ODDS_API_KEY_1": _secret("résultats de secours (The Odds API), clé 1"),
    "THE_ODDS_API_KEY_2": _secret("résultats de secours (The Odds API), clé 2"),
    "THE_ODDS_API_KEY_3": _secret("résultats de secours (The Odds API), clé 3"),
    "THE_ODDS_API_KEY_4": _secret("résultats de secours (The Odds API), clé 4"),
    "SCORES_365": Variable("oui", str, "« non » coupe la lecture des scores 365Scores"),
    "PROPS_ECART_MIN": Variable("0.02", float, "écart minimum d'un pari papier sur les props"),
    # alertes
    "PUSHOVER_APP_TOKEN": _secret("Pushover : jeton de l'application"),
    "PUSHOVER_USER_KEY": _secret("Pushover : clé de l'utilisateur"),
    "PUSHOVER_STRATEGIES": Variable("", str, "stratégies cochées pour Pushover ; vide : aucune alerte"),
    "PUSHOVER_BANKROLL": Variable("1000", float, "bankroll des mises affichées dans Pushover (€)"),
    "PUSHOVER_PRIORITY": Variable("0", int, "priorité Pushover : 0 (heures calmes) ou 1"),
    "PUSHOVER_RECAP_HEURE": Variable("11", str, "heure de Paris du récapitulatif ; « non » le coupe"),
    "ALERTE_WEBHOOK_URL": _secret("webhook des alertes (https)"),
    "ALERTE_WEBHOOK_KEY": _secret("clé du webhook des alertes"),
    "ALERTE_WEBHOOK_CLE_ENTETE": Variable("x-api-key", str, "en-tête qui porte la clé du webhook"),
    "SUPABASE_URL": _secret("Supabase (fonctions web, abonnements)"),
    "SUPABASE_SERVICE_ROLE_KEY": _secret("Supabase, clé de service (fonctions web)"),
    # serveur en direct
    "SERVEUR_DIRECT": Variable("", str, "« oui » sur le serveur en direct"),
    "PERIODE_S": Variable("60", float, "serveur : secondes entre deux cycles"),
    "PUBLICATION_S": Variable("300", float, "serveur : secondes entre deux push"),
    "DEPOT": Variable("Matttgic/cotes-value", str, "serveur : dépôt GitHub"),
    "BRANCHE_CODE": Variable("", str, "serveur : branche du code ; vide : branche courante"),
    "GITHUB_TOKEN": _secret("jeton GitHub (serveur : push et appel de site.yml)"),
    "HC_PING_URL": _secret("battement Healthchecks"),
    # GitHub Actions et outils
    "ACTIONS_ID_TOKEN_REQUEST_URL": _secret("GitHub Actions : jeton OIDC (Supabase)"),
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN": _secret("GitHub Actions : jeton OIDC (Supabase)"),
    "PYTHONHASHSEED": Variable("", str, "empreinte du site : relancée avec 0"),
}


@dataclass(frozen=True)
class Tache:
    workflow: str            # fichier de .github/workflows/
    cron: str                # ligne `cron:` (UTC)
    role: str


# Calendrier des tâches planifiées (docs/architecture-cible.md, tableau 1.4) : `tests/test_config.py` vérifie que les
# lignes `cron:` des workflows et le tableau du document y correspondent (E6.5).
TACHES: dict[str, Tache] = {
    "collecte": Tache("collecte.yml", "7 * * * *", "redémarre la chaîne de collecte (qui se relance seule toutes les "
                                                   "5 minutes)"),
    "reglement": Tache("reglement.yml", "27 * * * *", "règlement horaire, sauf serveur actif"),
    "surveillance": Tache("surveillance-collecte.yml", "17,47 * * * *", "relance la chaîne arrêtée"),
    "archivage": Tache("archivage-donnees.yml", "17 3 5 * *", "release mensuelle des données brutes"),
}


def lire(nom: str, environ: Mapping[str, str] | None = None):
    """Valeur typée de `nom`, ou son défaut si elle est absente, vide ou illisible. Nom inconnu : KeyError."""
    v = VARIABLES[nom]
    env = os.environ if environ is None else environ
    brut = str(env.get(nom, "") or "").strip()
    if not brut:
        return v.type(v.defaut) if v.defaut or v.type is str else None
    try:
        return v.type(brut)
    except ValueError:
        return v.type(v.defaut) if v.defaut or v.type is str else None


def markdown() -> str:
    lignes = ["| Variable | Défaut | Type | Rôle |", "|---|---|---|---|"]
    for nom, v in VARIABLES.items():
        defaut = "(secret)" if v.secret else (f"`{v.defaut}`" if v.defaut else "—")
        lignes.append(f"| `{nom}` | {defaut} | {v.type.__name__} | {v.role} |")
    return "\n".join(lignes)


if __name__ == "__main__":
    sys.stdout.write(markdown() + "\n")
