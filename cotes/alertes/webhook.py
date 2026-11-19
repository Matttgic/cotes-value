"""Webhook et ntfy (déplacé de scripts/envoyer_notifications.py, E5.1) : charge utile, texte du message, alertes
Pinnacle 2 à envoyer. Aussi la mise en forme commune du message Pushover (`message_ntfy`)."""
from __future__ import annotations

import base64
import math
from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from cotes.notifications import PIN2
from cotes.recap_jouables import mise_arrondie


CHAMPS_WEBHOOK = ("id", "match", "ligue", "debut", "marche", "selection", "bookmaker", "cote", "cote_min",
                  "cote_juste", "cote_pinnacle", "ecart", "recheck")


def charge_utile(a: dict) -> dict:
    """Corps JSON d'une alerte : champs convenus, début du match en UTC."""
    out = {k: a.get(k) for k in CHAMPS_WEBHOOK}
    try:
        d = datetime.fromisoformat(str(a.get("debut")).replace("Z", "+00:00"))
        out["debut"] = d.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except ValueError:
        pass
    out["recheck"] = bool(a.get("recheck"))
    return out


def est_ntfy(url: str) -> bool:
    """ntfy.sh (ou un sous-domaine) : le corps est du texte, pas du JSON."""
    h = (urlparse(url).hostname or "").lower()
    return h == "ntfy.sh" or h.endswith(".ntfy.sh")


def _fr(x, decimales: int) -> str:
    return f"{x:.{decimales}f}".replace(".", ",") if isinstance(x, (int, float)) and not isinstance(x, bool) else "—"


def _min_affichee(x) -> str:
    """Cote minimale arrondie au centième supérieur : le bookmaker affiche 2 décimales, jamais sous le seuil."""
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return "—"
    return _fr(math.ceil(round(x * 100, 6)) / 100, 2)


SPORTS = {"football": "Football", "basket": "Basket", "hockey": "Hockey", "tennis": "Tennis",
          "handball": "Handball", "volley": "Volley", "rugby": "Rugby", "rugby_league": "Rugby à XIII",
          "baseball": "Baseball", "tennis_de_table": "Tennis de table", "football_americain": "Football américain",
          "football_australien": "Football australien", "mma": "MMA", "boxe": "Boxe", "snooker": "Snooker",
          "badminton": "Badminton", "golf": "Golf", "cyclisme": "Cyclisme"}


JOURS = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")


def _sport(s) -> str:
    s = str(s or "").strip()
    return SPORTS.get(s.lower(), s.replace("_", " ").capitalize() or "—")


def _ligne_pinnacle(a: dict) -> list[str]:
    """Confirmation par Pinnacle : l'alerte part dès que la référence qui décide (Polymarket, Matchbook…) la valide,
    Pinnacle dit si lui aussi voit l'écart. Rien d'écrit pour une alerte sans cette mesure (anciennes alertes)."""
    if "pinnacle_ecart" not in a:
        return []
    e, age = a.get("pinnacle_ecart"), a.get("pinnacle_age_s")
    if not isinstance(e, (int, float)) or isinstance(e, bool):
        return ["Pinnacle : pas de prix récent pour confirmer"]
    verdict = "confirme" if e >= 0.02 else "écart faible" if e >= 0 else "contredit"
    ancien = f" (prix de {round(age / 60)} min)" if isinstance(age, (int, float)) and age >= 120 else ""
    return [f"Pinnacle {verdict} : {'+' if e > 0 else ''}{_fr(100 * e, 1)} %{ancien}"]


def message_ntfy(a: dict, mises: int = 1, defaut: float = 10.0) -> tuple[str, str]:
    """(titre, corps) en texte brut ; l'heure du match est celle de Paris (« mar. 20/10 20h00 »).
    ``mises`` > 1 (même pari pris par plusieurs stratégies cochées) : mise totale = mise unitaire × nombre, comme
    web/suivi.js ; sans mise connue, ``defaut`` (10 € à la bankroll des bilans) par stratégie."""
    try:
        d = datetime.fromisoformat(str(a.get("debut")).replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Paris"))
        heure = f'{JOURS[d.weekday()]} {d:%d/%m} {d:%H}h{d:%M}'
    except ValueError:
        heure = "heure inconnue"
    dom, ext = a.get("domicile"), a.get("exterieur")
    match = f"{dom} – {ext}" if dom and ext else str(a.get("match") or "")
    pari = str(a.get("selection") or a.get("pari") or "").split("\n")[0]
    lignes = [match, f'{pari} @ {_fr(a.get("cote"), 2)} (min {_min_affichee(a.get("cote_min"))})', heure]
    age = a.get("age_prix_secondes")
    if isinstance(age, (int, float)) and age > 300:          # match lointain, lu à son rythme : on le dit
        lignes.append(f"Prix relevé il y a {round(age / 60)} min")
    lignes += _ligne_pinnacle(a)
    sources = [s for s in a.get("sources") or [] if s]
    if len(sources) > 1:                     # plusieurs références : la mise est multipliée (pushover.alertes_pushover)
        lignes.append(f"Repéré par {len(sources)} sources : {', '.join(sources)}")
    lignes += _lignes_mise(a.get("mise_kelly"), mises, defaut)
    return f'{a.get("bookmaker") or "—"} – {_sport(a.get("sport"))}', "\n".join(lignes)


def _lignes_mise(kelly, mises: int, defaut: float) -> list[str]:
    """Ligne de mise ; affichage seul (les gains n'en dépendent pas)."""
    connue = isinstance(kelly, (int, float)) and not isinstance(kelly, bool) and kelly > 0
    if not (isinstance(mises, int) and mises > 1):
        return [f"Mise Kelly 1/8 corrigé : {mise_arrondie(kelly)} €"] if connue else []
    u = mise_arrondie(kelly if connue else defaut)
    if u is None:
        return []
    return [f"Mise totale{' Kelly 1/8 corrigé' if connue else ''} : {u * mises} € ({mises} × {u} €)"]


def _entete_utf8(texte: str) -> str:
    """En-tête HTTP non latin-1 (tiret demi-cadratin) : encodage RFC 2047, lu par ntfy."""
    return "=?UTF-8?B?" + base64.b64encode(texte.encode()).decode() + "?="


def alertes_webhook(flux: dict, paris: list[dict], envoyes: dict, maintenant: datetime | None = None) -> list[dict]:
    """Alertes Pinnacle 2 pas encore envoyées, quel que soit le bookmaker : celles du scan, puis les paris
    re-décidés (même s'ils datent)."""
    from cotes.notifications import alertes_recheck
    vues, out = set(envoyes), []
    for a in [x for x in flux.get("alertes", []) if PIN2 in x.get("strategies", [])] + alertes_recheck(paris, PIN2, maintenant):
        if a["id"] not in vues:
            vues.add(a["id"])
            out.append(a)
    return out
