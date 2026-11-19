"""Pushover (déplacé de scripts/envoyer_notifications.py, E5.1) : stratégies cochées, alertes à envoyer et champs
du message. L'envoi (`poster_pushover`) reste dans le script."""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone

from cotes.alertes.webhook import _fr, message_ntfy
from cotes.notifications import NOMS, PIN2
from cotes.recap_jouables import mise_arrondie


PUSHOVER_TTL_MAX_S = 86400       # le message reste sur le téléphone jusqu'au coup d'envoi, 24 h au plus (1 h le faisait disparaître avant lecture)


def strategies_pushover(env=None) -> tuple[set[str], list[str]]:
    """(stratégies cochées, clés inconnues) d'après ``PUSHOVER_STRATEGIES`` : clés séparées par des virgules ou
    des espaces. Liste vide : aucune alerte Pushover. Les clés s'obtiennent avec ``--strategies``."""
    from cotes.alertes.promos import SPECIALES
    env = os.environ if env is None else env
    voulues = [x for x in env.get("PUSHOVER_STRATEGIES", "").replace(",", " ").split() if x]
    connues = set(NOMS) | set(SPECIALES)
    return {x for x in voulues if x in connues}, sorted({x for x in voulues if x not in connues})


def alertes_pushover(flux: dict, paris: list[dict], envoyes: dict, choisies: set[str],
                     maintenant: datetime | None = None, amorcage: bool = False) -> list[dict]:
    """Alertes des stratégies cochées pas encore envoyées, les plus récentes d'abord. ``amorcage`` (premier passage,
    aucun fichier d'envois) : les re-décisions anciennes sont seulement mémorisées, pour ne pas inonder le téléphone."""
    from cotes.notifications import alertes_recheck
    vues, out = set(envoyes), []
    rechecks = alertes_recheck(paris, PIN2, maintenant) if PIN2 in choisies else []
    for a in [x for x in flux.get("alertes", []) if set(x.get("strategies", [])) & choisies] + rechecks:
        if a["id"] in vues:
            continue
        vues.add(a["id"])
        if amorcage and a.get("recheck"):
            envoyes[a["id"]] = ""             # mémorisé sans envoi
            continue
        cles, noms = a.get("strategies") or [], a.get("labels") or []
        if len(cles) == len(noms):          # seules les stratégies cochées sont nommées (une mise chacune)
            a = {**a, "labels": [n for k, n in zip(cles, noms) if k in choisies]}
        a = {**a, "mises": max(1, len(set(cles) & choisies))}     # une mise par stratégie cochée
        out.append(a)
    return out


BANKROLL_REFERENCE = 1000.0      # bankroll fictive de mise_kelly (cotes/simulation.py)


def _bankroll(env) -> float:
    """``PUSHOVER_BANKROLL`` en euros (défaut 1 000, la bankroll des bilans) ; valeur absurde : défaut."""
    try:
        b = float(str(env.get("PUSHOVER_BANKROLL", "") or BANKROLL_REFERENCE).replace(",", "."))
    except ValueError:
        return BANKROLL_REFERENCE
    return b if 10 <= b <= 1_000_000 else BANKROLL_REFERENCE


METHODE_CLAUDE = "claude_humain"


METHODE_ECART_MIN = 1.03          # on ne joue plus si l'écart est tombé sous 3 %


METHODE_MISE = 0.01               # 1 % de la bankroll


def ligne_methode_claude(a: dict, env) -> str:
    """Alerte de « Claude · Méthode humaine » : la cote minimale à jouer (écart 3 %) et la mise (1 % de
    ``PUSHOVER_BANKROLL``), déjà calculées. Vide pour les autres stratégies."""
    if METHODE_CLAUDE not in (a.get("strategies") or []):
        return ""
    juste = a.get("cote_juste")
    if not isinstance(juste, (int, float)) or isinstance(juste, bool) or juste <= 1:
        return ""
    cote_min = math.ceil(round(juste * METHODE_ECART_MIN * 100, 6)) / 100
    mise = mise_arrondie(_bankroll(env) * METHODE_MISE)
    return f"Méthode Claude : jouer si cote ≥ {_fr(cote_min, 2)} · mise {mise} €"


def message_pushover(a: dict, env=None, maintenant: datetime | None = None) -> dict:
    """Champs de l'API Pushover : le pari en texte, le lien du match dessous (cliquable). Mise Kelly 1/16 ramenée à
    ``PUSHOVER_BANKROLL``."""
    env = os.environ if env is None else env
    maintenant = maintenant or datetime.now(timezone.utc)
    if a.get("type") in ("surebet", "boost", "couvert", "milieu"):           # cotes/alertes/promos.py
        from cotes.alertes import promos
        champs = (promos.message_surebet(a, _bankroll(env)) if a["type"] == "surebet"
                  else promos.message_milieu(a, _bankroll(env)) if a["type"] == "milieu"
                  else promos.message_couvert(a) if a["type"] == "couvert" else promos.message_boost(a))
        duree = promos.ttl(a, maintenant)
        if duree:
            champs["ttl"] = duree
        try:
            priorite = int(env.get("PUSHOVER_PRIORITY", "0") or 0)
        except ValueError:
            priorite = 0
        champs["priority"] = priorite if priorite in (-1, 0, 1) else 0
        return champs
    kelly = a.get("mise_kelly")
    if isinstance(kelly, (int, float)) and not isinstance(kelly, bool) and kelly > 0:
        a = {**a, "mise_kelly": round(kelly * _bankroll(env) / BANKROLL_REFERENCE, 2)}
    mises = a.get("mises") if isinstance(a.get("mises"), int) and not isinstance(a.get("mises"), bool) else 1
    titre, corps = message_ntfy(a, mises, 10.0 * _bankroll(env) / BANKROLL_REFERENCE)
    methode = ligne_methode_claude(a, env)
    if methode:
        corps = corps + "\n" + methode
    noms = [str(x) for x in (a.get("labels") or [])]
    ligne = f"\n{len(noms)} stratégie{'s' if len(noms) > 1 else ''} : {', '.join(noms)}" if noms else ""
    champs = {"title": titre[:250], "message": (corps[:1000 - len(ligne)] + ligne)[:1000]}
    lien = a.get("lien")
    if isinstance(lien, str) and lien.startswith("https://") and len(lien) <= 500:
        champs["url"] = lien
        chez = a.get('bookmaker') or 'le bookmaker'
        champs["url_title"] = (f"Page du sport chez {chez} (match à chercher)" if a.get("lien_repli")
                               else f"Ouvrir le match chez {chez}")[:100]
    try:
        reste = (datetime.fromisoformat(str(a.get("debut")).replace("Z", "+00:00")) - maintenant).total_seconds()
        champs["ttl"] = int(max(60, min(PUSHOVER_TTL_MAX_S, reste)))
    except ValueError:
        pass
    try:                         # 0 (défaut) respecte les heures calmes ; 1 les ignore. 2 (accusé) est refusé.
        priorite = int(env.get("PUSHOVER_PRIORITY", "0") or 0)
    except ValueError:
        priorite = 0
    champs["priority"] = priorite if priorite in (-1, 0, 1) else 0
    return champs
