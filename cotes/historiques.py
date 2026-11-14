"""Historiques en ajout seul de la branche « donnees » : un fichier par jour UTC, ``<dossier>/AAAA-MM-JJ.jsonl.gz``.

Cinq dossiers, tous écrits par le cycle (scripts/cycle.py) avec ``ajouter_gzip`` :

- ``cotes/`` : cotes des bookmakers gardés en mémoire (section « cotes des bookmakers ») ;
- ``references/`` : cotes justes de Pinnacle, Polymarket, Smarkets, Matchbook et Betfair ;
- ``releves/`` : ce que chaque source a réellement lu pendant le cycle ;
- ``correspondances/`` : rapprochements de matchs entre bookmakers et références ;
- ``opportunites/`` : écarts détectés (écrit directement par le cycle).

Rien de tout cela n'intervient dans la détection ; une erreur ici ne coupe jamais le cycle.

Ajout sûr (``ajouter_gzip``) : jamais de fichier tronqué si le job est tué pendant l'écriture.
``gzip.open(chemin, "at")`` écrit directement à la fin du fichier : un job tué (expiration de 40 min, annulation)
pendant l'écriture laisse un dernier membre gzip incomplet, et toute lecture du fichier échoue ensuite
(``EOFError``). Ici, on copie les octets existants tels quels dans un fichier temporaire du même dossier (aucune
décompression), on y ajoute un nouveau membre gzip complet, on synchronise sur disque puis on remplace le fichier
d'un coup (``os.replace``, atomique sur le même système de fichiers). Interrompu avant le remplacement : l'ancien
fichier est intact (il manque seulement les lignes de ce cycle) ; le ``.tmp`` est ignoré par git (collecte.yml).

Le format est exactement celui de ``gzip.open(..., "at")`` : une suite de membres gzip, lue d'un bloc par
``gzip.open(..., "rt")``. Coût : une copie brute du fichier du jour à chaque ajout (quelques ms par Mo).

Cotes des bookmakers (``cotes/``) — PMU, Unibet, Betclic, NetBet, et depuis le 12/11/2026 Winamax et OlyBet hors
props ; props de tous.
Avant le 30/10/2026, cet historique n'existait que dans les versions successives de ``horizon_direct.json``
de la branche « donnees » (53 Mo réécrits toutes les 5 minutes). Désormais, seules les lignes dont la cote a
changé depuis le cycle précédent (ou nouvelles) sont ajoutées à ``cotes/AAAA-MM-JJ.jsonl.gz`` (jour UTC,
membres gzip ajoutés de façon atomique comme ``opportunites/``), avec des champs réduits :

    {"t": heure de lecture, "b": source, "m": match_id, "k": "marché|période|ligne|issue[|joueur]", "c": cote}

Un match vu pour la première fois reçoit en plus une ligne descriptive (sans ``c``) :

    {"t": ..., "b": ..., "m": match_id, "sport": ..., "ligue": ..., "dom": ..., "ext": ..., "debut": ...}

Aucune ligne n'est écrite si rien ne change. Au démarrage à froid (mémoire absente), toutes les cotes en
mémoire sont écrites une fois : c'est l'état de départ de l'historique.

Depuis le 12/11/2026, une cote qui disparaît reçoit une ligne de retrait ``"c": null``, mais seulement si son
match a été relu pendant le cycle (au moins une ligne du même bookmaker et du même match lue après le début du
cycle). Une source ou un match non relus (panne, lecture tournante) ne donnent jamais de retrait : l'absence
d'une ligne reste alors « inconnue ». Le relevé des sources lues à chaque cycle est dans ``releves/``
(section « relevé des sources »).

Références, relevés et correspondances — ajoutés le 12/11/2026 pour l'analyse du marché (cotes/analyse_marche/).
Avant, les références n'avaient aucun historique : on ne les retrouvait que dans ``opportunites/``, seulement
quand l'écart dépassait 2 %. Trois fichiers par jour UTC, membres gzip ajoutés de façon atomique comme ``cotes/`` :

``references/AAAA-MM-JJ.jsonl.gz`` — même format que ``cotes/``, une ligne par cote
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
"""
from __future__ import annotations

import gzip
import io
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path

from . import memoire
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
    # Un job tué pendant l'écriture ne tronque jamais le fichier du jour (ajouter_gzip).
    ajouter_gzip(jour, "".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n" for x in lignes))
    return len(lignes)


def _iso(maintenant: datetime) -> str:
    return maintenant.astimezone(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- ajout gzip atomique

def ajouter_gzip(chemin: Path, texte: str) -> None:
    """Ajoute ``texte`` (UTF-8) comme nouveau membre gzip à la fin de ``chemin``, de façon atomique."""
    if not texte:
        return
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".tmp")
    try:
        if chemin.exists():
            shutil.copyfile(chemin, tmp)
            mode = "ab"
        else:
            mode = "wb"
        with open(tmp, mode) as brut:
            # Même pile que gzip.open(chemin, "at", encoding="utf-8") (en-tête avec le nom d'origine, niveau 9,
            # flux texte UTF-8) : le membre ajouté est identique octet pour octet à celui de l'ancien code.
            with io.TextIOWrapper(gzip.GzipFile(filename=str(chemin), fileobj=brut, mode="wb"),
                                  encoding="utf-8") as g:
                g.write(texte)
                g.flush()
            brut.flush()
            os.fsync(brut.fileno())
        os.replace(tmp, chemin)
    finally:
        tmp.unlink(missing_ok=True)


# --------------------------------------------------------------------------- cotes des bookmakers

# Lignes lues pendant le cycle : heure de lecture postérieure au début du cycle (petite marge d'horloge).
MARGE_FRAICHEUR = timedelta(seconds=5)


def fraiche(l: dict, maintenant: datetime | None) -> bool:
    """Ligne lue pendant ce cycle (et non reprise d'une mémoire ou d'un cycle précédent)."""
    if maintenant is None:
        return False
    t = instant_utc(l.get("collecte"))
    return t is not None and t >= maintenant - MARGE_FRAICHEUR


def texte_cle(marche, periode, ligne, issue, joueur=None) -> str:
    """« marché|période|ligne|issue[|joueur] » : la clé d'une sélection dans les historiques."""
    k = "|".join(_texte(x) for x in (marche, periode, ligne, issue))
    return k + "|" + _texte(joueur) if joueur else k


def _cle_cote(l: dict) -> tuple:
    return (l.get("source"), l.get("match_id"), l.get("marche"), l.get("periode"), l.get("ligne"),
            l.get("issue"), l.get("joueur"))


def _texte(v) -> str:
    return "" if v is None else str(v)


def index_cotes(horizon: dict | None) -> dict[tuple, object]:
    """{clé de sélection: cote} de toutes les lignes en mémoire (tous bookmakers). Une même sélection présente deux
    fois (une cinquantaine sur 76 000 lignes le 29/10/2026) garde sa première ligne."""
    out: dict[tuple, object] = {}
    for bloc in (horizon or {}).values() if isinstance(horizon, dict) else []:
        for l in (bloc.get("lignes") or []) if isinstance(bloc, dict) else []:
            if isinstance(l, dict) and l.get("match_id") and l.get("cote") is not None:
                out.setdefault(_cle_cote(l), l.get("cote"))      # doublon : la première ligne, comme changements_cotes()
    return out


def changements_cotes(avant: dict[tuple, object], horizon: dict | None, maintenant: datetime | None = None) -> list[dict]:
    """Lignes réduites des cotes nouvelles ou changées, plus la description des matchs nouveaux.

    Avec ``maintenant`` (début du cycle) : retraits ``"c": None`` des cotes disparues d'un match relu."""
    matchs_avant = {k[1] for k in avant}
    decrits: set = set()
    out: list[dict] = []
    vues: set = set()
    relus: set = set()
    for bloc in (horizon or {}).values() if isinstance(horizon, dict) else []:
        for l in (bloc.get("lignes") or []) if isinstance(bloc, dict) else []:
            if not isinstance(l, dict) or not l.get("match_id") or l.get("cote") is None:
                continue
            cle = _cle_cote(l)
            if fraiche(l, maintenant):
                relus.add(cle[:2])
            if cle in vues:
                continue
            vues.add(cle)
            if cle in avant and avant[cle] == l.get("cote"):
                continue
            mid = l["match_id"]
            if mid not in matchs_avant and mid not in decrits:
                decrits.add(mid)
                out.append({"t": l.get("collecte"), "b": l.get("source"), "m": mid, "sport": l.get("sport"),
                            "ligue": l.get("ligue"), "dom": l.get("domicile"), "ext": l.get("exterieur"),
                            "debut": l.get("debut")})
            k = texte_cle(l.get("marche"), l.get("periode"), l.get("ligne"), l.get("issue"), l.get("joueur"))
            out.append({"t": l.get("collecte"), "b": l.get("source"), "m": mid, "k": k, "c": l.get("cote")})
    if maintenant is not None:
        t = maintenant.astimezone(timezone.utc).isoformat(timespec="seconds")
        for cle in avant:
            if cle not in vues and cle[:2] in relus:
                out.append({"t": t, "b": cle[0], "m": cle[1], "k": texte_cle(*cle[2:]), "c": None})
    return out


def ajouter_cotes(donnees: Path, avant: dict[tuple, object], horizon: dict | None, maintenant: datetime) -> int:
    """Ajoute les changements au fichier du jour (UTC). Rend le nombre de lignes écrites ; 0 = fichier intact."""
    lignes = changements_cotes(avant, horizon, maintenant)
    return _ecrire(donnees, "cotes", lignes, maintenant)


# --------------------------------------------------------------------------- cotes justes des références

def _cle_reference(nom: str, l: dict) -> str:
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


def changements_references(avant: dict[str, float], references: dict[str, list[dict]],
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
            cle = _cle_reference(nom, l)
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
    lignes, etat = changements_references(avant, references, maintenant)
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
