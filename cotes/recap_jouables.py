"""Récapitulatif Pushover « encore jouables » : une fois par jour (11 h, heure de Paris, par défaut), les alertes
envoyées depuis le récapitulatif précédent dont la cote est encore jouable.

Pour qui dort ou travaille quand l'alerte arrive : d'après docs/duree-values.md, 55 % des values sont encore
jouables une heure après la détection et 28 % jusqu'au match (PMU tient le plus longtemps). Une alerte est reprise si :

- son match commence dans plus de 10 minutes et le pari n'est pas réglé ;
- la dernière cote relevée chez le bookmaker (historique ``cotes/AAAA-MM-JJ.jsonl.gz``, écrit à chaque changement)
  est au moins la cote minimale (cote juste + 2 %, comme l'alerte d'origine).

Une alerte dont la cote actuelle est inconnue (bookmaker non relevé dans l'historique) n'est pas reprise : on ne
propose rien qu'on n'a pas revérifié. Aucune donnée n'est modifiée ; seul l'état de l'envoi est mémorisé.
"""
from __future__ import annotations

import gzip
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
ETAT = "pushover_recap.json"
HEURE_DEFAUT = 11
MARGE_DEBUT = timedelta(minutes=10)
FENETRE_MAX = timedelta(hours=36)        # premier récapitulatif : les alertes des 36 dernières heures au plus


def mise_arrondie(x) -> int | None:
    """Mise arrondie à l'euro supérieur (8,74 -> 9 ; 9,01 -> 10), 1 € au moins. None si pas de mise."""
    if not isinstance(x, (int, float)) or isinstance(x, bool) or x <= 0:
        return None
    return max(1, math.ceil(round(x, 6)))


def heure_recap(env) -> int | None:
    """``PUSHOVER_RECAP_HEURE`` (heure de Paris, 0–23, défaut 11) ; « non » coupe le récapitulatif."""
    brut = str(env.get("PUSHOVER_RECAP_HEURE", "") or HEURE_DEFAUT).strip().lower()
    if brut in ("non", "off", "0ff", "aucun"):
        return None
    try:
        h = int(brut)
    except ValueError:
        return HEURE_DEFAUT
    return h if 0 <= h <= 23 else HEURE_DEFAUT


def est_l_heure(maintenant: datetime, heure: int, dernier: str | None) -> bool:
    """Vrai pendant l'heure choisie (heure de Paris), une seule fois par jour."""
    local = maintenant.astimezone(PARIS)
    if local.hour != heure:
        return False
    return dernier != local.date().isoformat()


def cle_historique(p: dict) -> tuple:
    texte = lambda v: "" if v is None else str(v)
    k = "|".join(texte(x) for x in (p.get("marche"), p.get("periode"), p.get("ligne"), p.get("issue")))
    if p.get("joueur"):
        k += "|" + texte(p["joueur"])
    return (p.get("bookmaker"), p.get("match_id"), k)


def dernieres_cotes(donnees: Path, cles: set[tuple], maintenant: datetime) -> dict[tuple, tuple[str, float]]:
    """{(bookmaker, match_id, clé): (heure, cote)} : la dernière cote relevée, sur les fichiers d'hier et d'aujourd'hui."""
    out: dict[tuple, tuple[str, float]] = {}
    if not cles:
        return out
    jours = sorted({(maintenant - timedelta(days=d)).date().isoformat() for d in (1, 0)})
    for jour in jours:
        f = Path(donnees) / "cotes" / f"{jour}.jsonl.gz"
        if not f.exists():
            continue
        try:
            with gzip.open(f, "rt", encoding="utf-8") as flux:
                for brut in flux:
                    try:
                        l = json.loads(brut)
                    except ValueError:
                        continue
                    if "c" not in l:
                        continue
                    cle = (l.get("b"), l.get("m"), l.get("k"))
                    if (cle in cles and isinstance(l.get("c"), (int, float))
                            and (cle not in out or str(l.get("t")) >= out[cle][0])):
                        out[cle] = (str(l.get("t")), float(l["c"]))
        except (OSError, EOFError):
            continue
    return out


def candidats(paris: list[dict], envoyes: dict, depuis: datetime, maintenant: datetime) -> list[dict]:
    """Paris dont l'alerte Pushover est partie après ``depuis``, encore ouverts, match à plus de 10 minutes."""
    from .notifications import empreinte_prix
    from .temps import instant_utc
    envoyees = {k: v for k, v in envoyes.items() if isinstance(v, str) and v}
    out, vus = [], set()
    for p in paris:
        if p.get("statut") != "en_cours":
            continue
        e = empreinte_prix(p)
        quand = instant_utc(envoyees.get(e)) if e in envoyees else None
        debut = instant_utc(p.get("debut"))
        if quand is None or quand <= depuis or debut is None or debut <= maintenant + MARGE_DEBUT or e in vus:
            continue
        vus.add(e)
        out.append(p)
    return sorted(out, key=lambda p: str(p.get("debut")))


def jouables(paris: list[dict], cotes: dict[tuple, tuple[str, float]]) -> list[dict]:
    """Les candidats dont la dernière cote relevée atteint la cote minimale, avec la cote actuelle."""
    from .notifications import COTE_MIN_MARGE, COTE_MIN_PLANCHER
    out = []
    for p in paris:
        juste = p.get("cote_juste")
        actuelle = cotes.get(cle_historique(p))
        if not isinstance(juste, (int, float)) or actuelle is None:
            continue
        minimum = max(COTE_MIN_PLANCHER, juste * COTE_MIN_MARGE)
        if actuelle[1] + 1e-9 >= minimum:
            out.append({**p, "cote_actuelle": actuelle[1], "cote_actuelle_le": actuelle[0], "cote_min": minimum})
    return out


def messages(lignes: list[dict], bankroll: float, maintenant: datetime, par_message: int = 6) -> list[dict]:
    """Messages Pushover (HTML) : une ligne par pari, lien cliquable, mise Kelly ¼ ramenée à la bankroll et
    arrondie à l'euro supérieur."""
    from .simulation import mise_kelly
    out = []
    blocs = [lignes[i:i + par_message] for i in range(0, len(lignes), par_message)]
    for n, bloc in enumerate(blocs, 1):
        corps = []
        for p in bloc:
            d = datetime.fromisoformat(str(p["debut"]).replace("Z", "+00:00")).astimezone(PARIS)
            mise = mise_arrondie(mise_kelly(p) * bankroll / 1000.0)
            minimum = math.ceil(round(p["cote_min"] * 100, 6)) / 100
            texte = (f'<b>{_h(p.get("domicile"))} – {_h(p.get("exterieur"))}</b> ({d:%d/%m %Hh%M})<br>'
                     f'{_h(p.get("pari"))} · {_h(p.get("bookmaker"))} @ {_fr(p["cote_actuelle"])} '
                     f'(min {_fr(minimum)})' + (f' · mise {mise} €' if mise else ""))
            lien = p.get("lien")
            if isinstance(lien, str) and lien.startswith("https://"):
                texte += f' · <a href="{_h(lien)}">ouvrir</a>'
            corps.append(texte)
        titre = f"Encore jouables · {maintenant.astimezone(PARIS):%d/%m %Hh}" + (f" ({n}/{len(blocs)})" if len(blocs) > 1 else "")
        out.append({"title": titre, "message": "<br><br>".join(corps)[:1024], "html": "1"})
    return out


def _fr(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _h(texte) -> str:
    return (str(texte or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))
