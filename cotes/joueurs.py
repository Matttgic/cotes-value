"""Nom, statistique et ligne d'un pari joueur, au même vocabulaire que Pinnacle.

Clé de marché ``JOUEUR:<stat>`` (Points, Rebounds, Assists, PointsReboundsAssists,
Goals, ShotsOnGoal, …), colonne ``joueur``, ligne numérique, issue PLUS ou MOINS.
Le nom sert à la comparaison : accents retirés, initiale de prénom, Jr/Sr conservé
comme suffixe (Kenyon Martin Jr n'est pas Kenyon Martin).
"""
from __future__ import annotations

import re
import unicodedata

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}
_PALIER = re.compile(r"^(?P<nom>.+?)\s+(?P<n>\d+)\+$")
_PLUS_DE = re.compile(
    r"^(?P<nom>.+?)\s+(?:\+\s*de|plus\s+de)\s+(?P<ligne>\d+(?:[.,]\d+)?)\s*$", re.I)
_MOINS_DE = re.compile(
    r"^(?P<nom>.+?)\s+(?:-\s*de|moins\s+de)\s+(?P<ligne>\d+(?:[.,]\d+)?)\s*$", re.I)
_PLUS = re.compile(r"^(?:plus|over)(?:\s+de)?\s+(?P<ligne>\d+(?:[.,]\d+)?)$", re.I)
_MOINS = re.compile(r"^(?:moins|under)(?:\s+de)?\s+(?P<ligne>\d+(?:[.,]\d+)?)$", re.I)


def est_joueur(marche: str | None) -> bool:
    return str(marche or "").startswith("JOUEUR:")


def _ascii(texte: str | None) -> str:
    s = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def stat_canonique(texte: str | None) -> str | None:
    """Statistique commune. None si le libellé n'est pas un total de joueur reconnu."""
    t = _ascii(texte)
    if not t:
        return None
    # Abréviations Pinnacle (« Pts&Rebs&Asts », « ThreesMade »).
    t = (t.replace("threes made", "three points").replace("threesmade", "three points")
         .replace("threepointfieldgoals", "three points")
         .replace("pts", "points").replace("rebs", "rebounds").replace("asts", "assists"))
    point = "point" in t
    rebond = "rebond" in t or "rebound" in t
    passe = "passe" in t or "assist" in t
    # « 3 ou plus » est une ligne, pas un panier à trois points.
    trois = bool(re.search(r"\b3\s*points?\b|\bthree\s*points?\b|\bpaniers?\b", t) or "threepoint" in t
                 or "three points" in t)
    if point and rebond and passe:
        return "PointsReboundsAssists"
    if point and rebond:
        return "PointsRebounds"
    if point and passe:
        return "PointsAssists"
    if rebond and passe:
        return "ReboundsAssists"
    if trois and point and not rebond and not passe:
        return "ThreePoints"
    if rebond:
        return "Rebounds"
    if passe:
        return "Assists"
    if "shotsongoal" in t or "shot on goal" in t or "tirs cadre" in t or "tir cadre" in t:
        return "ShotsOnGoal"
    if re.search(r"\b(buts?|goals?)\b", t):
        return "Goals"
    if point:
        return "Points"
    return None


def cle_joueur(nom: str | None) -> str:
    """Clé stable. Vide si le nom ne désigne personne.

    ``L. James``, ``LeBron James`` et ``Lebron James`` partagent la même clé.
    ``P.J. Washington`` et ``PJ Washington`` aussi. Un suffixe Jr/Sr/II/III/IV
    reste dans la clé.
    """
    brut = str(nom or "").strip()
    if not brut:
        return ""
    if "," in brut:
        gauche, droite = brut.split(",", 1)
        if droite.strip() and gauche.strip():
            brut = f"{droite.strip()} {gauche.strip()}"
    s = unicodedata.normalize("NFKD", brut).encode("ascii", "ignore").decode().lower()
    s = s.replace("'", "").replace("`", "")
    tokens = re.findall(r"[a-z0-9]+\.?", s)
    mots: list[tuple[str, bool]] = []
    for tok in tokens:
        point = tok.endswith(".")
        mot = tok[:-1] if point else tok
        if mot:
            mots.append((mot, point))
    suffixe: list[str] = []
    while mots and mots[-1][0] in _SUFFIXES:
        suffixe.insert(0, mots.pop()[0])
    if not mots:
        return ""
    famille = mots[-1][0]
    initiales: list[str] = []
    for mot, point in mots[:-1]:
        voyelle = bool(re.search(r"[aeiouy]", mot))
        if point or len(mot) == 1 or (len(mot) <= 3 and not voyelle):
            initiales.extend(mot)
        else:
            initiales.append(mot[0])
    return f"{famille}|{''.join(initiales)}|{''.join(suffixe)}"


def _ligne(texte: str) -> float | None:
    try:
        return float(texte.replace(",", "."))
    except (TypeError, ValueError):
        return None


def _apres_tiret(titre: str) -> str:
    if " - " not in (titre or ""):
        return ""
    return titre.rsplit(" - ", 1)[-1].strip(" -")


def _selection(issue: str, libelle: str, cote: float, ligne: float, joueur: str, stat: str) -> dict:
    return {
        "canonicalOutcome": "OVER" if issue == "PLUS" else "UNDER",
        "rawName": libelle,
        "odds": cote,
        "line": ligne,
        "joueur": joueur,
        "stat": stat,
        "libelle": f"{joueur} {stat} {issue} {ligne}",
    }


def marche(market_id, titre: str, selections: list[dict]) -> dict | None:
    if len(selections) < 1:
        return None
    return {
        "marketId": market_id,
        "canonicalMarket": "PLAYER_PROP",
        "rawName": titre,
        "period": "FULL_TIME",
        "selections": selections,
    }


def depuis_titre_et_issues(market_id, titre: str, issues: list[tuple[str, float]]) -> dict | None:
    """``issues`` = (libellé d'issue, cote). None si ce n'est pas un total de joueur."""
    stat = stat_canonique(titre)
    if not stat:
        return None
    joueur_titre = _apres_tiret(titre)
    if joueur_titre and (stat_canonique(joueur_titre) or "joueur" in _ascii(joueur_titre)):
        joueur_titre = ""
    selections = []
    palier_titre = re.search(r"(\d+)\s+ou\s+plus", titre or "", re.I)
    for libelle, cote in issues:
        if not isinstance(cote, (int, float)) or isinstance(cote, bool) or cote <= 1:
            continue
        texte = str(libelle or "").strip()
        m = _PLUS.match(texte) or _PLUS_DE.match(texte)
        if m and m.groupdict().get("ligne"):
            ligne = _ligne(m.group("ligne"))
            joueur = m.groupdict().get("nom") or joueur_titre
            if ligne is None or not str(joueur or "").strip():
                continue
            selections.append(_selection("PLUS", texte, float(cote), ligne, str(joueur).strip(), stat))
            continue
        m = _MOINS.match(texte) or _MOINS_DE.match(texte)
        if m and m.groupdict().get("ligne"):
            ligne = _ligne(m.group("ligne"))
            joueur = m.groupdict().get("nom") or joueur_titre
            if ligne is None or not str(joueur or "").strip():
                continue
            selections.append(_selection("MOINS", texte, float(cote), ligne, str(joueur).strip(), stat))
            continue
        m = _PALIER.match(texte)
        if m:
            n = int(m.group("n"))
            selections.append(_selection("PLUS", texte, float(cote), n - 0.5, m.group("nom").strip(), stat))
            continue
        if palier_titre and joueur_titre == "" and texte and not _PLUS.match(texte):
            n = int(palier_titre.group(1))
            selections.append(_selection("PLUS", texte, float(cote), n - 0.5, texte, stat))
    if not selections and palier_titre and joueur_titre:
        return None
    return marche(market_id, titre, selections)


def est_titre_joueur(titre: str | None) -> bool:
    """Vrai pour un total de joueur, pas pour le total de l'équipe ni un buteur combiné."""
    t = titre or ""
    bas = _ascii(t)
    if not stat_canonique(t):
        return False
    if re.search(r"\bequipe\b|\bclean sheet\b|\bduo\b|\btrio\b|\bdouble chance\b", bas):
        return False
    if re.search(r"\bjoueur\b", bas):
        return True
    if re.match(r"(?i)nombre de (buts?|points?|passes d[ée]cisives) - ", t):
        return True
    if re.match(r"(?i)plus\s*/\s*moins\s+(points?|rebonds?|passes|paniers)", t) and " - " in t:
        reste = _apres_tiret(t)
        return bool(reste) and "equipe" not in _ascii(reste) and _ascii(reste) not in {"match", "mt", "qt"}
    if "performance du joueur" in bas or "performance joueur" in bas:
        return True
    return False
