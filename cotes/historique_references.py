"""Historique des références (Pinnacle, Polymarket, Smarkets, Matchbook, Betfair), du relevé des sources et des
rapprochements de matchs, en ajout seul. Ajouté le 12/11/2026 pour l'analyse du marché (cotes/analyse_marche/).

Avant, les références n'avaient aucun historique : on ne les retrouvait que dans ``opportunites/``, seulement
quand l'écart dépassait 2 %. Trois fichiers par jour UTC, membres gzip ajoutés de façon atomique comme ``cotes/`` :

``references/AAAA-MM-JJ.jsonl.gz`` — même format que ``cotes/`` (cotes/historique_cotes.py), une ligne par cote
juste nouvelle ou changée (arrondie au millième), plus la description de chaque match nouveau :

    {"t": heure de lecture, "b": référence, "m": match_id, "k": "marché|période|ligne|issue[|joueur]",
     "c": cote juste, "p": probabilité juste, "mg": marge Pinnacle, "liq": liquidité, "ea": écart achat/vente,
     "max": mise maximale Pinnacle, "per": 1 si cote Pinnacle périmée}

  Les champs absents de la source sont omis. Retrait ``"c": null`` d'une cote disparue d'un match relu pendant le
  cycle, comme pour les bookmakers. Une référence en panne garde sa dernière lecture (cotes/reprise.py) : rien ne
  change, rien n'est écrit.

``releves/AAAA-MM-JJ.jsonl.gz`` — une ligne par cycle : pour chaque source (bookmaker ou référence), le nombre de
lignes en main, de lignes et de matchs lus pendant le cycle. C'est ce qui distingue « cote inchangée » (source
lue, rien d'écrit) de « source non lue » (0 ligne fraîche) :

    {"t": début du cycle, "sources": {"Betclic": {"lignes": 41000, "fraiches": 40800, "matchs": 950}, ...}}

``correspondances/AAAA-MM-JJ.jsonl.gz`` — les rapprochements calculés pendant la collecte (comparaison.indexer),
écrits la première fois qu'ils sont vus (puis de nouveau après 24 h) :

    {"t": ..., "fr": match_id français, "b": référence, "m": match_id de la référence, "inv": domicile inversé,
     "s": score de ressemblance}

  Deux matchs français rapprochés du même match Pinnacle sont le même match : c'est le lien entre bookmakers.

Rien de tout cela n'intervient dans la détection ; une erreur ici ne coupe jamais le cycle (scripts/cycle.py).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path

from . import memoire
from .ecriture import ajouter_gzip
from .historique_cotes import fraiche, texte_cle
from .temps import instant_utc

MEMOIRE_REFERENCES = "historique_references"
MEMOIRE_CORRESPONDANCES = "historique_correspondances"
DOSSIERS = ("references", "releves", "correspondances")
RAPPEL_CORRESPONDANCE = timedelta(hours=24)
SEP = "\t"


def _nombre(x) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x):
        return None
    return float(x)


def _ecrire(donnees: Path, dossier: str, lignes: list[dict], maintenant: datetime) -> int:
    if not lignes:
        return 0
    jour = Path(donnees) / dossier / f"{maintenant.astimezone(timezone.utc):%Y-%m-%d}.jsonl.gz"
    jour.parent.mkdir(parents=True, exist_ok=True)
    ajouter_gzip(jour, "".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n" for x in lignes))
    return len(lignes)


def _iso(maintenant: datetime) -> str:
    return maintenant.astimezone(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- cotes justes des références

def _cle(nom: str, l: dict) -> str:
    return SEP.join((nom, str(l.get("match_id")),
                     texte_cle(l.get("marche"), l.get("periode"), l.get("ligne"), l.get("issue"), l.get("joueur"))))


def _ligne(nom: str, l: dict, maintenant: datetime) -> dict | None:
    """Ligne d'historique d'une cote juste, ou None si la ligne n'en a pas de lisible."""
    p = _nombre(l.get("proba_juste"))
    if not l.get("match_id") or p is None or not 0 < p < 1:
        return None
    c = _nombre(l.get("cote_juste")) or 1 / p
    out = {"t": l.get("collecte") or _iso(maintenant), "b": nom, "m": l["match_id"],
           "k": texte_cle(l.get("marche"), l.get("periode"), l.get("ligne"), l.get("issue"), l.get("joueur")),
           "c": round(c, 3), "p": round(p, 5)}
    for champ, cle in (("marge_pinnacle", "mg"), ("liquidite", "liq"), ("ecart_achat_vente", "ea"),
                       ("mise_max", "max")):
        v = _nombre(l.get(champ))
        if v is not None:
            out[cle] = round(v, 4)
    if l.get("cote_perimee"):
        out["per"] = 1
    return out


def changements(avant: dict[str, float], references: dict[str, list[dict]],
                maintenant: datetime) -> tuple[list[dict], dict[str, float]]:
    """(lignes à écrire, nouvel état {clé: cote juste}). Une sélection en double garde sa première ligne."""
    matchs_avant = {c.rsplit(SEP, 1)[0] for c in avant}
    etat: dict[str, float] = {}
    out: list[dict] = []
    decrits: set = set()
    relus: set = set()
    for nom, lignes in (references or {}).items():
        for l in lignes or []:
            if not isinstance(l, dict):
                continue
            h = _ligne(nom, l, maintenant)
            if h is None:
                continue
            cle = _cle(nom, l)
            match = cle.rsplit(SEP, 1)[0]
            if fraiche(l, maintenant):
                relus.add(match)
            if cle in etat:
                continue
            etat[cle] = h["c"]
            if avant.get(cle) == h["c"]:
                continue
            if match not in matchs_avant and match not in decrits:
                decrits.add(match)
                out.append({"t": h["t"], "b": nom, "m": l["match_id"], "sport": l.get("sport"),
                            "ligue": l.get("ligue"), "dom": l.get("domicile"), "ext": l.get("exterieur"),
                            "debut": l.get("debut")})
            out.append(h)
    t = _iso(maintenant)
    for cle in avant:
        if cle not in etat and cle.rsplit(SEP, 1)[0] in relus:
            nom, mid, k = cle.split(SEP, 2)
            out.append({"t": t, "b": nom, "m": _id(mid), "k": k, "c": None})
    return out, etat


def _id(mid: str):
    """Identifiant rendu à son type d'origine (Pinnacle : entier)."""
    return int(mid) if mid.isdigit() and not mid.startswith("0") else mid


def ajouter_references(donnees: Path, references: dict[str, list[dict]], maintenant: datetime) -> int:
    doc = memoire.lire(donnees, MEMOIRE_REFERENCES, {})
    avant = doc.get("cotes") if isinstance(doc, dict) and isinstance(doc.get("cotes"), dict) else {}
    lignes, etat = changements(avant, references, maintenant)
    n = _ecrire(donnees, "references", lignes, maintenant)
    memoire.ecrire(donnees, MEMOIRE_REFERENCES, {"maj": _iso(maintenant), "cotes": etat})
    return n


# --------------------------------------------------------------------------- relevé des sources

def releve(francais: list[dict], references: dict[str, list[dict]], maintenant: datetime) -> dict:
    """{source: {lignes, fraiches, matchs}} : ce que le cycle a réellement lu, source par source."""
    sources: dict[str, dict] = {}
    matchs: dict[str, set] = {}

    def compter(nom, l):
        s = sources.setdefault(nom, {"lignes": 0, "fraiches": 0, "matchs": 0})
        s["lignes"] += 1
        if fraiche(l, maintenant):
            s["fraiches"] += 1
            matchs.setdefault(nom, set()).add(l.get("match_id"))

    for l in francais or []:
        if isinstance(l, dict):
            compter(str(l.get("source") or l.get("bookmaker") or "?"), l)
    for nom, lignes in (references or {}).items():
        for l in lignes or []:
            if isinstance(l, dict):
                compter(nom, l)
    for nom, s in sources.items():
        s["matchs"] = len(matchs.get(nom, ()))
    return {"t": _iso(maintenant), "sources": dict(sorted(sources.items()))}


# --------------------------------------------------------------------------- rapprochements de matchs

def rapprochements(index: dict) -> list[tuple[str, str, object, bool, float | None]]:
    """(match français, référence, match de la référence, inversé, score) lus dans l'index de l'association."""
    out = []
    for nom, par_match in (index or {}).items():
        if not isinstance(par_match, dict):
            continue
        for mid_fr, par_cle in par_match.items():
            ligne = next((x for x in (par_cle or {}).values() if isinstance(x, dict)), None) \
                if isinstance(par_cle, dict) else None
            if ligne is None or ligne.get("match_id") is None:
                continue
            out.append((str(mid_fr), nom, ligne["match_id"], bool(ligne.get("inverse")),
                        _nombre(ligne.get("score_association"))))
    return out


def ajouter_correspondances(donnees: Path, index: dict, maintenant: datetime) -> int:
    doc = memoire.lire(donnees, MEMOIRE_CORRESPONDANCES, {})
    vues = doc.get("vues") if isinstance(doc, dict) and isinstance(doc.get("vues"), dict) else {}
    t = _iso(maintenant)

    def recente(v) -> bool:
        derniere = instant_utc(v)
        return derniere is not None and timedelta(0) <= maintenant - derniere < RAPPEL_CORRESPONDANCE

    lignes = []
    garder = {k: v for k, v in vues.items() if recente(v)}     # un rapprochement absent un cycle n'est pas réécrit
    for fr, nom, mid, inv, score in rapprochements(index):
        cle = SEP.join((fr, nom, str(mid), "1" if inv else "0"))
        if cle in garder:
            continue
        garder[cle] = t
        lignes.append({"t": t, "fr": fr, "b": nom, "m": mid, "inv": inv, "s": score})
    n = _ecrire(donnees, "correspondances", lignes, maintenant)
    memoire.ecrire(donnees, MEMOIRE_CORRESPONDANCES, {"maj": t, "vues": garder})
    return n


def enregistrer(donnees: Path, francais: list[dict], references: dict[str, list[dict]], index: dict,
                maintenant: datetime) -> dict:
    """Les trois ajouts du cycle. Rend le nombre de lignes écrites par fichier (pour le journal)."""
    out = {"references": ajouter_references(donnees, references, maintenant)}
    out["releves"] = _ecrire(donnees, "releves", [releve(francais, references, maintenant)], maintenant)
    out["correspondances"] = ajouter_correspondances(donnees, index, maintenant)
    return out
