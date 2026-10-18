"""Cotes Betclic lues sur l'API publique gRPC-web, au format PulseScore.

Pas d'authentification. Référence de forme : le client public TapsHTS/betclic-api.
Une requête de liste par sport, page de 40 (le serveur n'en met pas plus dans
la première trame), puis un détail par match encore à venir, les plus proches
d'abord. Chaque réponse est un flux de notification : on le ferme dès la
première trame, sans pagination et sans attendre la suite.

``SOURCE_BETCLIC`` vaut ``pulsescore``, ``direct``, ``auto`` ou ``shadow``
(défaut). En shadow, PulseScore reste la source des décisions.
"""
from __future__ import annotations

import os
import re
import struct
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

from cotes.correspondance import ressemblance
from cotes.direct.horizon import fusionner
from cotes.pulsescore import traduire

BASE = "https://offering.begmedia.com/web/offering.access.api/offering.access.api.MatchService"
LISTE = "GetMatchesBySportWithNotifications"
DETAIL = "GetMatchWithNotification"
PAGE = 40
_LISTE_MAX = 640
_PRES_H = 6
# Un détail relu il y a moins longtemps reste en cache : le budget sert
# d'abord aux matchs encore jamais lus. Le cycle dure 5 min : au-delà de 3 min
# de cache, des cotes de 10 min d'âge décidaient des paris.
_FRAIS_MIN = 3
# Lectures de détail simultanées (5 en parallèle n'ont pas donné de 429).
_CONCURRENCE = 4
# Onglets lus en plus de « Le Top » : demi-temps, périodes, quarts-temps, sets, jeux.
LIBELLES_ONGLETS = {"résultats", "buts", "points", "sets", "jeux"}
COUVERTURE_MIN = 0.95
ACCORD_MIN = 0.99
ECART_COTE = 0.01
MODES = ("pulsescore", "direct", "auto", "shadow")
# sport interne -> slug Betclic
SPORTS = {
    "football": "football",
    "tennis": "tennis",
    "basket": "basketball",
    "hockey": "ice_hockey",
    "handball": "handball",
    "volley": "volleyball",
    "rugby": "rugby_union",
    "football_americain": "american_football",
    "baseball": "baseball",
}
ENTETES = {
    "Content-Type": "application/grpc-web+proto",
    "Accept": "*/*",
    "x-grpc-web": "1",
    "x-bg-ref-platform": "DESKTOP",
    "x-bg-regulation": "FR",
    "x-bg-ref-brand": "BETCLIC",
    "x-bg-ref-regulator-zone": "FR",
    "Origin": "https://www.betclic.fr",
    "Referer": "https://www.betclic.fr/",
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "fr-FR,fr;q=0.9",
}
_echeance = None


def mode_source() -> str:
    """``shadow`` si la variable est absente ou inconnue."""
    valeur = os.environ.get("SOURCE_BETCLIC", "shadow").strip().lower()
    return valeur if valeur in MODES else "shadow"


def sports_demandes(sports: set[str] | None) -> list[tuple[str, str]]:
    """(sport interne, slug), dans un ordre stable. ``None`` : tout le catalogue."""
    return [(interne, slug) for interne, slug in SPORTS.items()
            if sports is None or interne in sports]


def encode_varint(valeur: int) -> bytes:
    sortie = bytearray()
    while valeur > 0x7F:
        sortie.append((valeur & 0x7F) | 0x80)
        valeur >>= 7
    sortie.append(valeur & 0x7F)
    return bytes(sortie)


def encode_champ_varint(numero: int, valeur: int) -> bytes:
    return encode_varint((numero << 3) | 0) + encode_varint(valeur)


def encode_champ_octets(numero: int, valeur) -> bytes:
    brut = valeur.encode("utf-8") if isinstance(valeur, str) else valeur
    return encode_varint((numero << 3) | 2) + encode_varint(len(brut)) + brut


def encode_champ_double(numero: int, valeur: float) -> bytes:
    return encode_varint((numero << 3) | 1) + struct.pack("<d", float(valeur))


def trame_grpc(charge: bytes) -> bytes:
    return b"\x00" + struct.pack(">I", len(charge)) + charge


def decode_varint(data: bytes, pos: int):
    resultat, decalage = 0, 0
    while pos < len(data):
        octet = data[pos]
        resultat |= (octet & 0x7F) << decalage
        pos += 1
        if not (octet & 0x80):
            break
        decalage += 7
        if decalage > 70:
            break
    return resultat, pos


def decode_protobuf(data: bytes) -> dict:
    champs: dict = {}
    pos = 0
    while pos < len(data):
        etiquette, pos = decode_varint(data, pos)
        numero, fil = etiquette >> 3, etiquette & 0x07
        if numero == 0:
            break
        if fil == 0:
            valeur, pos = decode_varint(data, pos)
        elif fil == 1:
            if pos + 8 > len(data):
                break
            valeur = data[pos:pos + 8]
            pos += 8
        elif fil == 2:
            longueur, pos = decode_varint(data, pos)
            if longueur < 0 or pos + longueur > len(data):
                break
            valeur = data[pos:pos + longueur]
            pos += longueur
        elif fil == 5:
            if pos + 4 > len(data):
                break
            valeur = data[pos:pos + 4]
            pos += 4
        else:
            break
        champs.setdefault(numero, []).append(valeur)
    return champs


def _texte(valeur) -> str | None:
    if not isinstance(valeur, (bytes, bytearray)):
        return None
    try:
        texte = valeur.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if texte and all(c.isprintable() or c in "\n\r\t" for c in texte):
        return texte
    return None


def _double(valeur) -> float | None:
    if isinstance(valeur, (bytes, bytearray)) and len(valeur) == 8:
        nombre = struct.unpack("<d", valeur)[0]
        if 1.0 < nombre < 10000:
            return round(nombre, 2)
    return None


def premiere_trame(morceaux) -> bytes | None:
    """Assemble les blocs jusqu'à la première trame complète, puis s'arrête."""
    brut = bytearray()
    for bloc in morceaux:
        if not bloc:
            continue
        brut.extend(bloc)
        if len(brut) < 5:
            continue
        longueur = struct.unpack(">I", brut[1:5])[0]
        if longueur > 2_000_000:
            return None
        if len(brut) >= 5 + longueur:
            return bytes(brut[:5 + longueur])
    return None


def _charge(trame: bytes | None) -> bytes:
    if not trame or len(trame) < 5 or trame[0] == 0x80:
        return b""
    longueur = struct.unpack(">I", trame[1:5])[0]
    return trame[5:5 + longueur]


def _match(data: bytes) -> dict | None:
    champs = decode_protobuf(data)
    ident = champs.get(1, [None])[0]
    if not isinstance(ident, int):
        return None
    nom = None
    for valeur in champs.get(2, []):
        texte = _texte(valeur)
        if texte and " - " in texte:
            nom = texte
            break
        if texte and not nom:
            nom = texte
    debut = None
    for valeur in champs.get(3, []):
        texte = _texte(valeur)
        if texte and ("T" in texte or "-" in texte):
            debut = texte
            break
    direct = False
    if 6 in champs and isinstance(champs[6][0], int):
        direct = champs[6][0] == 1
    competition = None
    if 8 in champs and isinstance(champs[8][0], (bytes, bytearray)):
        comp = decode_protobuf(champs[8][0])
        if 2 in comp:
            competition = _texte(comp[2][0])
    equipes = []
    for equipe in champs.get(12, []):
        if isinstance(equipe, (bytes, bytearray)):
            nom_equipe = _texte(decode_protobuf(equipe).get(3, [b""])[0])
            if nom_equipe:
                equipes.append(nom_equipe)
    domicile, exterieur = (equipes + [None, None])[:2]
    if (not domicile or not exterieur) and nom and " - " in nom:
        gauche, droite = nom.split(" - ", 1)
        domicile = domicile or gauche.strip()
        exterieur = exterieur or droite.strip()
    if not domicile or not exterieur:
        return None
    return {"id": ident, "domicile": domicile, "exterieur": exterieur, "debut": debut,
            "competition": competition, "direct": direct}


def matchs_de_la_liste(trame: bytes | None) -> list[dict]:
    racine = decode_protobuf(_charge(trame))
    sortie = []
    for enveloppe in racine.get(1, []):
        if not isinstance(enveloppe, (bytes, bytearray)):
            continue
        for match in decode_protobuf(enveloppe).get(3, []):
            if isinstance(match, (bytes, bytearray)):
                lu = _match(match)
                if lu:
                    sortie.append(lu)
    return sortie


def _selection(data: bytes) -> dict | None:
    champs = decode_protobuf(data)
    if 14 in champs and champs[14][0] != 1:
        return None
    nom = None
    for numero in (10, 11, 2, 3):
        if numero in champs:
            nom = _texte(champs[numero][0])
            if nom:
                break
    if not nom or 12 not in champs:
        return None
    cote = _double(champs[12][0])
    if cote is None:
        return None
    return {"nom": nom, "cote": cote}


def _selections(marche: bytes) -> list[dict]:
    champs = decode_protobuf(marche)
    sortie = []
    for brut in champs.get(16, []):
        if isinstance(brut, (bytes, bytearray)):
            lu = _selection(brut)
            if lu:
                sortie.append(lu)
    if sortie:
        return sortie
    for groupe in champs.get(10, []):
        if not isinstance(groupe, (bytes, bytearray)):
            continue
        for item in decode_protobuf(groupe).get(1, []):
            if not isinstance(item, (bytes, bytearray)):
                continue
            sous = decode_protobuf(item).get(1, [])
            candidats = sous or [item]
            for candidat in candidats:
                if isinstance(candidat, (bytes, bytearray)):
                    lu = _selection(candidat)
                    if lu:
                        sortie.append(lu)
    return sortie


def _nom_marche(champs: dict) -> str | None:
    for numero in (2, 3):
        if numero in champs:
            texte = _texte(champs[numero][0])
            if texte and len(texte) > 2:
                return texte
    return None


def marches_du_detail(trame: bytes | None) -> list[dict]:
    """Marchés du premier match détaillé : nom et sélections ouvertes."""
    racine = decode_protobuf(_charge(trame))
    sortie = []
    for enveloppe in racine.get(1, []):
        if not isinstance(enveloppe, (bytes, bytearray)):
            continue
        for match in decode_protobuf(enveloppe).get(1, []):
            if not isinstance(match, (bytes, bytearray)):
                continue
            for enveloppe_marche in decode_protobuf(match).get(11, []):
                if not isinstance(enveloppe_marche, (bytes, bytearray)):
                    continue
                champs_enveloppe = decode_protobuf(enveloppe_marche)
                for brut in champs_enveloppe.get(3, []) + champs_enveloppe.get(1, []):
                    if not isinstance(brut, (bytes, bytearray)):
                        continue
                    champs = decode_protobuf(brut)
                    if 9 in champs and champs[9][0] == 3:
                        continue
                    nom = _nom_marche(champs)
                    selections = _selections(brut) if nom else []
                    if nom and selections:
                        sortie.append({"nom": nom, "selections": selections})
    return dedoublonner(sortie)


def dedoublonner(marches: list[dict]) -> list[dict]:
    """Un même marché apparaît dans plusieurs sections d'un onglet, ou dans plusieurs onglets."""
    vus: set = set()
    sortie = []
    for marche in marches:
        cle = (marche["nom"], tuple((s["nom"], s["cote"]) for s in marche["selections"]))
        if cle not in vus:
            vus.add(cle)
            sortie.append(marche)
    return sortie


def _heure(valeur):
    if not valeur:
        return None
    texte = str(valeur).strip().replace("Z", "+00:00")
    if "." in texte:
        tete, reste = texte.split(".", 1)
        chiffres = 0
        while chiffres < len(reste) and reste[chiffres].isdigit():
            chiffres += 1
        texte = f"{tete}.{reste[:min(chiffres, 6)]}{reste[chiffres:]}"
    try:
        instant = datetime.fromisoformat(texte)
    except ValueError:
        return None
    if instant.tzinfo is None:
        return None
    return instant.astimezone(timezone.utc)


def _nombre(valeur) -> float | None:
    if isinstance(valeur, bool) or valeur is None:
        return None
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None


def categories_du_detail(trame: bytes | None) -> list[tuple[str, str]]:
    """(identifiant, libellé) des onglets du match. Le détail par défaut n'a que « Le Top »."""
    racine = decode_protobuf(_charge(trame))
    sortie = []
    for enveloppe in racine.get(1, []):
        if not isinstance(enveloppe, (bytes, bytearray)):
            continue
        for match in decode_protobuf(enveloppe).get(1, []):
            if not isinstance(match, (bytes, bytearray)):
                continue
            for brut in decode_protobuf(match).get(10, []):
                if not isinstance(brut, (bytes, bytearray)):
                    continue
                champs = decode_protobuf(brut)
                ident = _texte(champs.get(2, [b""])[0])
                libelle = _texte(champs.get(3, [b""])[0])
                if ident and libelle:
                    sortie.append((ident, libelle))
    return sortie


def onglets_utiles(trame: bytes | None) -> list[str]:
    """Onglets de marchés comparables (résultats, buts, points, sets, jeux), sans « Le Top »."""
    utiles = []
    for ident, libelle in categories_du_detail(trame):
        if libelle.strip().lower() in LIBELLES_ONGLETS and ident not in utiles:
            utiles.append(ident)
    return utiles


# « 1ère mi-temps (seule) - », « 2ème mi-temps - », « 1er QT - », « 3ème période - », « 1er set - »
_PREFIXE_PERIODE = re.compile(
    r"^\s*(?:1[èe]re|2[èe]me|3[èe]me|[1-4](?:er|è|e|ème|eme)?)\s+"
    r"(?:mi-temps(?:\s*\(seule\))?|p[ée]riode|qt|set)\s+-\s+", re.I)
_NOMS_TOTAL = re.compile(r"\b(?:buts?|points?|jeux)\b")
_EXCLU = ("buteur", "décisif", "decisif", "passeur", "mi-temps", "mi temps", "&", "écart", "ecart",
          "quand sera", "comment", "intervalle", "multi", "choix", "cage", "pénalty", "penalty", "plus prolifique")


def _classe(nom: str, domicile: str, exterieur: str) -> str | None:
    """Marché canonique PulseScore. Un préfixe de période (mi-temps, QT, période, set) reste
    dans le libellé : c'est ``traduire`` qui en déduit la période."""
    m = _PREFIXE_PERIODE.match(nom)
    corps = nom[m.end():] if m else nom
    bas = corps.strip().lower()
    # « Écart de buts », « Écart de points entre les équipes », « Vainqueur avec handicap » :
    # « X gagne de 2 buts ou + » est le handicap X −1,5. Selon le sport, l'unité décide du marché.
    if re.match(r"(?:[ée]cart (?:de (?:buts|points|sets|jeux)(?: entre les [ée]quipes)?|entre les [ée]quipes)|vainqueur avec handicap)\s*(?:\(t\.? ?r[ée]g\.?\))?\s*$", bas):
        return "ECART"
    # « prolong. & pen. inclus » n'est pas une combinaison de marchés.
    sans_abrege = re.sub(r"prolong\w*\.?\s*&\s*pen\w*\.?", "prolongations", bas)
    if any(mot in sans_abrege for mot in _EXCLU):
        return None
    if bas.startswith(("résultat du match (rembours", "resultat du match (rembours")):
        return "DRAW_NO_BET"
    if bas.startswith(("résultat du match", "resultat du match", "vainqueur du match")) or (
            m and bas in ("vainqueur", "résultat", "resultat")):
        return "MATCH_RESULT"
    if bas.startswith("double chance") and not m:
        return "DOUBLE_CHANCE"
    # « Les 2 équipes marquent ou + de 2,5 » est une combinaison : ses cotes
    # Oui/Non ne sont pas celles du marché les deux équipes marquent.
    if bas.startswith(("les 2 équipes marquent", "les deux équipes marquent", "both teams")) and not m:
        if re.search(r"\b(?:ou|or|et|and)\b|&|\+", bas):
            return None
        return "BOTH_TEAMS_TO_SCORE"
    if bas.startswith("score exact") and not m:
        return "CORRECT_SCORE"
    if bas.startswith("nombre de sets") and not m:
        return "TOTAL_SETS"
    if not _NOMS_TOTAL.search(bas):
        return None
    # « Total de buts - Équipe » (football, basket), « Équipe - Nombre total de buts » (hockey,
    # tennis) ou « Nombre de buts - Équipe » (périodes).
    equipe = None
    if " - " in corps and re.match(r"(?:nombre total|nombre|total)\b", bas):
        equipe = corps.split(" - ", 1)[1].strip().lower()
    elif " - " in corps and re.search(r"^.+? - (?:nombre )?total\b", bas):
        equipe = corps.split(" - ", 1)[0].strip().lower()
    if equipe is not None:
        if equipe == domicile.strip().lower():
            return "HOME_OVER_UNDER"
        if equipe == exterieur.strip().lower():
            return "AWAY_OVER_UNDER"
        return None
    if re.match(r"(?:nombre total|total de|total points|nombre de)\b", bas):
        return "OVER_UNDER"
    return None


def _equipe_proche(bas: str, equipe: str) -> bool:
    """Nom exact, ou l'un contenu dans l'autre en mots entiers (« Independiente » / « CA Independiente »)."""
    equipe = equipe.strip().lower()
    if not bas or not equipe:
        return False
    if bas == equipe:
        return True
    court, long_ = sorted((bas, equipe), key=len)
    return len(court) >= 4 and f" {court} " in f" {long_} "


def _issue(nom: str, domicile: str, exterieur: str) -> str | None:
    bas = nom.strip().lower()
    if bas in ("nul", "match nul", "n", "draw", "x"):
        return "DRAW"
    if bas in ("oui", "yes"):
        return "YES"
    if bas in ("non", "no"):
        return "NO"
    if bas == domicile.strip().lower():
        return "HOME"
    if bas == exterieur.strip().lower():
        return "AWAY"
    # Libellé abrégé (double chance surtout) : ambigu si les deux équipes correspondent.
    dom, ext = _equipe_proche(bas, domicile), _equipe_proche(bas, exterieur)
    if dom != ext:
        return "HOME" if dom else "AWAY"
    return None


def _ligne_totale(nom: str) -> float | None:
    trouve = re.search(r"([0-9]+(?:[.,][0-9]+)?)", nom)
    if not trouve:
        return None
    return float(trouve.group(1).replace(",", "."))


def _sens_total(nom: str) -> str | None:
    bas = nom.strip().lower().replace("＋", "+").replace("−", "-").replace("–", "-")
    if bas.startswith("+") or bas.startswith("plus") or bas.startswith("over"):
        return "OVER"
    if bas.startswith("-") or bas.startswith("moins") or bas.startswith("under"):
        return "UNDER"
    return None


def _double_chance(nom: str, domicile: str, exterieur: str) -> str | None:
    morceaux = re.split(r"\s+ou\s+", nom.strip(), maxsplit=1, flags=re.I)
    if len(morceaux) != 2:
        return None
    issues = {_issue(morceau, domicile, exterieur) for morceau in morceaux}
    return {frozenset({"HOME", "DRAW"}): "HOME_DRAW",
            frozenset({"AWAY", "DRAW"}): "DRAW_AWAY",
            frozenset({"HOME", "AWAY"}): "HOME_AWAY"}.get(frozenset(issues))


_GAGNE = re.compile(r"^(.+?)\s+gagne de\s+(\d+)\s*(?:buts?|points?|sets?|jeux)?\s*ou\s*\+\s*$", re.I)
_NE_PERD = re.compile(
    r"^(.+?)\s+ne perd pas(?:\s+ou perd de\s+(\d+)\s*(?:buts?|points?|sets?|jeux)?"
    r"\s*(?:exactement|ou\s*-)?)?\s*$", re.I)


def _canon_handicap(nom: str, sport: str | None) -> str | None:
    """Marché canonique PulseScore d'un écart, d'après l'unité écrite et le sport (None : non comparé)."""
    # l'unité est celle du marché, pas celle du préfixe : « 1er set - Écart de jeux » est un handicap de jeux
    m = _PREFIXE_PERIODE.match(nom)
    bas = (nom[m.end():] if m else nom).lower()
    if sport in ("football", "hockey", "handball"):
        return "ASIAN_HANDICAP" if "point" not in bas and "set" not in bas and "jeu" not in bas else None
    if sport == "basket":
        return "ASIAN_HANDICAP" if "point" in bas else None
    if sport == "tennis":
        return "SET_HANDICAP" if "set" in bas else "GAME_HANDICAP" if "jeu" in bas else None
    if sport == "volley":
        return "SET_HANDICAP" if "set" in bas and "point" not in bas else None
    return None


def _marches_handicap(marche: dict, domicile: str, exterieur: str, sport: str | None) -> list[dict]:
    """« X gagne de N ou + » = X −(N−0,5) ; « Y ne perd pas ou perd de M ou - » = Y +(M+0,5).
    Les deux issues complémentaires forment un marché à deux voies, un par ligne (celle du domicile)."""
    nom = marche.get("nom") or ""
    canon = _canon_handicap(nom, sport)
    if not canon:
        return []
    groupes: dict = {}
    for offre in marche.get("selections") or []:
        texte = str(offre.get("nom") or "").strip()
        gagne = _GAGNE.match(texte)
        if gagne:
            equipe, valeur = gagne.group(1), -(int(gagne.group(2)) - 0.5)
        else:
            perd = _NE_PERD.match(texte)
            if not perd:
                continue
            equipe, valeur = perd.group(1), (int(perd.group(2)) if perd.group(2) else 0) + 0.5
        cote = _issue(equipe, domicile, exterieur)
        if cote not in ("HOME", "AWAY"):
            continue
        ligne_domicile = valeur if cote == "HOME" else -valeur
        groupes.setdefault(ligne_domicile, {})[cote] = {
            "canonicalOutcome": cote, "rawName": texte, "odds": offre["cote"], "line": valeur}
    libelle = _libelle_pulse(nom)
    if sport == "hockey" and not _PREFIXE_PERIODE.match(nom) and "rég" not in libelle.lower():
        libelle += " (tps rég.)"      # écarts du hockey sans mention : Betclic les règle sur 60 min
    return [{"marketId": f"{nom}|{ligne:+g}", "canonicalMarket": canon, "rawName": libelle,
             "period": "FULL_TIME", "selections": [paire["HOME"], paire["AWAY"]]}
            for ligne, paire in groupes.items() if len(paire) == 2]


TOTAUX = ("OVER_UNDER", "HOME_OVER_UNDER", "AWAY_OVER_UNDER", "TOTAL_SETS")


def _libelle_pulse(nom: str) -> str:
    """« 1er QT » -> « 1er quart-temps » : la période est lue dans le libellé par ``traduire``."""
    return re.sub(r"\b([1-4])\s*(?:er|è|e|ème|eme)?\s*QT\b", r"\1er quart-temps", nom, flags=re.I)


def marches_pulse(marche: dict, domicile: str, exterieur: str, sport: str | None = None) -> list[dict]:
    """Marchés au format PulseScore. Un total Betclic regroupe toutes ses lignes
    dans un seul marché : on en fait un marché par ligne, sinon la traduction
    ne garderait que la dernière (la plus haute)."""
    canon = _classe(marche.get("nom") or "", domicile, exterieur)
    if not canon:
        return []
    if canon == "ECART":
        return _marches_handicap(marche, domicile, exterieur, sport)
    selections = []
    for offre in marche.get("selections") or []:
        nom = str(offre.get("nom") or "")
        if canon == "CORRECT_SCORE":
            issue, ligne = "SCORE", None
        elif canon in TOTAUX:
            issue, ligne = _sens_total(nom), _ligne_totale(nom)
        elif canon == "DOUBLE_CHANCE":
            issue, ligne = _double_chance(nom, domicile, exterieur), None
        elif canon == "BOTH_TEAMS_TO_SCORE":
            issue, ligne = _issue(nom, domicile, exterieur), None
            if issue not in ("YES", "NO"):
                issue = None
        else:
            issue, ligne = _issue(nom, domicile, exterieur), None
        if not issue or (canon in TOTAUX and ligne is None):
            continue
        selections.append({"canonicalOutcome": issue, "rawName": nom, "odds": offre["cote"], "line": ligne})
    if canon in TOTAUX:
        par_ligne: dict = {}
        for sel in selections:
            par_ligne.setdefault(sel["line"], []).append(sel)
        groupes = [(f"{marche.get('nom')}|{ligne:g}", sels) for ligne, sels in par_ligne.items()]
    else:
        groupes = [(marche.get("nom"), selections)]
    libelle = _libelle_pulse(marche.get("nom") or "")
    return [{"marketId": ident, "canonicalMarket": canon, "rawName": libelle,
             "period": "FULL_TIME", "selections": sels}
            for ident, sels in groupes if len(sels) >= 2]


def marche_pulse(marche: dict, domicile: str, exterieur: str) -> dict | None:
    """Premier marché traduit (les marchés sans lignes n'en ont qu'un)."""
    traduits = marches_pulse(marche, domicile, exterieur)
    return traduits[0] if traduits else None


class Client:
    """POST gRPC-web. Le corps n'est pas journalisé ; le flux est fermé tout de suite."""

    def __init__(self, session=None, echeance=None):
        self.session = session or requests.Session()
        self.echeance = echeance
        self.requetes = 0
        self.erreurs: list[str] = []
        self._bloque = False

    def _temps(self) -> bool:
        if self._bloque:
            return False
        if self.echeance is None:
            return True
        if not self.echeance.ok():
            if "budget" not in self.erreurs:
                self.erreurs.append("budget")
            return False
        reste = getattr(self.echeance, "reste", None)
        if reste is not None:
            valeur = reste()
            if valeur is not None and valeur < 3:
                if "budget" not in self.erreurs:
                    self.erreurs.append("budget")
                return False
        return True

    def poster(self, methode: str, charge: bytes) -> bytes | None:
        if not self._temps():
            return None
        delai = 8 if self.echeance is None else self.echeance.timeout(8)
        reste = getattr(self.echeance, "reste", None) if self.echeance is not None else None
        if reste is not None:
            valeur = reste()
            if valeur is not None:
                delai = min(delai, max(1.0, valeur - 1))
        self.requetes += 1
        try:
            reponse = self.session.post(
                f"{BASE}/{methode}", data=trame_grpc(charge), headers=ENTETES,
                timeout=(5, delai), stream=True)
        except (requests.RequestException, OSError):
            self.erreurs.append("réseau")
            return None
        try:
            if reponse.status_code == 429:
                self._bloque = True
                self.erreurs.append("HTTP 429")
                return None
            if reponse.status_code != 200:
                self.erreurs.append(f"HTTP {reponse.status_code}")
                return None
            try:
                trame = premiere_trame(reponse.iter_content(65536))
            except (requests.RequestException, OSError):
                trame = None
            if not trame:
                self.erreurs.append("trame incomplète")
                return None
            return trame
        finally:
            fermer = getattr(reponse, "close", None)
            if fermer:
                fermer()


def _a_venir(match: dict, maintenant: datetime, heures: float) -> bool:
    """L'heure décide. Le champ souvent appelé « direct » est aussi levé sur des matchs à venir."""
    debut = _heure(match.get("debut"))
    return bool(debut and maintenant < debut <= maintenant + timedelta(hours=heures))


def _charge_liste(slug: str, offset: int = 0) -> bytes:
    return (encode_champ_octets(1, slug) + encode_champ_octets(2, "fr")
            + encode_champ_varint(4, offset) + encode_champ_varint(5, PAGE))


def _lire_pages(client: Client, slug: str, maintenant: datetime, heures: float) -> list[dict]:
    """Pages d'offset 0 jusqu'à la fin du catalogue ou au-delà de l'horizon."""
    horizon = maintenant + timedelta(hours=heures)
    offset = 0
    trouves = []
    while offset <= _LISTE_MAX:
        if not client._temps():
            break
        trame = client.poster(LISTE, _charge_liste(slug, offset))
        if client._bloque:
            break
        matchs = matchs_de_la_liste(trame) if trame else []
        if not matchs:
            break
        debuts = []
        for match in matchs:
            debut = _heure(match.get("debut"))
            if debut is not None:
                debuts.append(debut)
            if _a_venir(match, maintenant, heures):
                trouves.append(match)
        if len(matchs) < PAGE or (debuts and min(debuts) > horizon):
            break
        offset += PAGE
    return trouves


def _detailler(client: Client, match: dict, moment: str,
               onglets: bool = True) -> tuple[list[dict], bool, bool]:
    """(lignes, lecture réussie, complet). « Le Top » d'abord, puis les onglets utiles
    (demi-temps, périodes, sets, jeux) tant que le budget le permet."""
    charge = encode_champ_varint(1, int(match["id"])) + encode_champ_octets(2, "fr")
    trame = client.poster(DETAIL, charge)
    if client._bloque:
        return [], bool(trame), False
    offres = marches_du_detail(trame)
    complet = bool(trame)
    if onglets and trame:
        for ident in onglets_utiles(trame):
            if client._bloque or not client._temps():
                complet = False
                break
            suite = client.poster(DETAIL, charge + encode_champ_octets(3, ident))
            if not suite:
                complet = False
                continue
            offres = dedoublonner(offres + marches_du_detail(suite))
    marches = []
    for offre in offres:
        for traduit in marches_pulse(offre, match["domicile"], match["exterieur"], match["sport"]):
            # Au hockey le score exact de Betclic n'est pas celui de Pinnacle (+180 % de cote).
            if traduit["canonicalMarket"] == "CORRECT_SCORE" and match["sport"] != "football":
                continue
            marches.append(traduit)
    if not marches:
        return [], bool(trame), complet
    evenement = {"eventId": match["id"], "home": match["domicile"], "away": match["exterieur"],
                 "league": match.get("competition"), "startTime": match.get("debut"), "markets": marches}
    lignes, vus = [], set()
    for ligne in traduire(evenement, "betclic", match["sport"], moment):
        cle = (ligne["match_id"], ligne["marche"], ligne["periode"], ligne["ligne"], ligne["issue"])
        if cle not in vus:     # « Écart de buts » et « Ecart entre les équipes » donnent les mêmes handicaps
            vus.add(cle)
            lignes.append(ligne)
    return lignes, bool(trame), complet


def _collecter_reserve(client: Client, demandes, heures: float, maintenant: datetime,
                       reserve: dict, concurrence: int = _CONCURRENCE) -> tuple[list[dict], dict]:
    """Tout le catalogue dans l'horizon. On détaille d'abord les matchs absents du cache."""
    moment = maintenant.isoformat(timespec="seconds")
    candidats = []
    vus: set = set()
    lectures = 0
    for sport, slug in demandes:
        if not client._temps() or client._bloque:
            break
        avant = client.requetes
        for match in _lire_pages(client, slug, maintenant, heures):
            cle = (sport, match.get("id"))
            if cle in vus:
                continue
            vus.add(cle)
            candidats.append({**match, "sport": sport})
        if client.requetes > avant:
            lectures += 1
        if client._bloque:
            break
    frais: dict = {}
    for ligne in reserve.get("lignes") or []:
        if not isinstance(ligne, dict):
            continue
        lu = _heure(ligne.get("collecte"))
        mid = ligne.get("match_id")
        if mid and lu and (mid not in frais or lu > frais[mid]):
            frais[mid] = lu

    def rang(match):
        lu = frais.get(f"betclic|{match.get('id')}")
        debut = _heure(match.get("debut")) or maintenant
        if lu is None:
            return (0, debut, debut)
        return (1, lu, debut)

    def a_relire(match) -> bool:
        lu = frais.get(f"betclic|{match.get('id')}")
        if lu is None:
            return True
        return maintenant - lu >= timedelta(minutes=_FRAIS_MIN)

    file = [m for m in candidats if a_relire(m)]
    file.sort(key=rang)
    lignes: list[dict] = []
    arret = threading.Event()

    anciennes: dict = {}
    for ligne in reserve.get("lignes") or []:
        if isinstance(ligne, dict) and ligne.get("match_id"):
            anciennes.setdefault(ligne["match_id"], []).append(ligne)

    def lire(match):
        if arret.is_set() or not client._temps():
            return None
        ajoutees, lue, complet = _detailler(client, match, moment)
        if client._bloque:
            arret.set()
        if not complet and ajoutees:
            # Onglets coupés par le budget : on garde les marchés déjà lus au cycle précédent.
            presentes = {l.get("cle_marche") for l in ajoutees}
            # Même limite d'âge (2 h) que la fusion du reste du catalogue.
            ajoutees = ajoutees + [l for l in anciennes.get(f"betclic|{match.get('id')}", [])
                                   if l.get("cle_marche") not in presentes
                                   and (lu := _heure(l.get("collecte"))) is not None
                                   and maintenant - lu <= timedelta(hours=2)]
        return ajoutees, lue

    with ThreadPoolExecutor(max(1, concurrence)) as pool:
        for recu in pool.map(lire, file):
            if recu is None:
                continue
            ajoutees, lue = recu
            if lue:
                lectures += 1
            lignes += ajoutees
    fusion = fusionner(reserve.get("lignes") or [], lignes, maintenant, heures, age_max_h=2)
    return fusion, {
        "ok": lectures > 0 or not client.erreurs or bool(fusion),
        "erreurs": list(client.erreurs),
        "requetes": client.requetes,
        "matchs": len({l.get("match_id") for l in fusion}),
        "reserve": {"offset": 0, "lignes": fusion},
    }


def collecter(sports: set[str] | None = None, heures: float = 36, session=None,
              maintenant: datetime | None = None, echeance=None,
              reserve=None, concurrence: int = _CONCURRENCE) -> tuple[list[dict], dict]:
    """Lignes déjà passées par ``pulsescore.traduire`` (bookmaker ``betclic``).

    Sans réserve, une seule page (offset 0) puis le détail, comme avant.
    Avec réserve, chaque sport est paginé jusqu'à l'horizon. Les matchs déjà
    détaillés depuis moins de trois minutes restent en cache.
    """
    maintenant = maintenant or datetime.now(timezone.utc)
    if echeance is None:
        echeance = _echeance
    demandes = sports_demandes(sports)
    if not demandes:
        return [], {"ok": True, "erreurs": [], "requetes": 0, "matchs": 0}
    client = Client(session, echeance)
    if reserve is not None:
        return _collecter_reserve(client, demandes, heures, maintenant,
                                  reserve if isinstance(reserve, dict) else {}, concurrence)
    moment = maintenant.isoformat(timespec="seconds")
    candidats = []
    lectures = 0
    for sport, slug in demandes:
        if not client._temps():
            break
        trame = client.poster(LISTE, _charge_liste(slug, 0))
        if trame:
            lectures += 1
        if client._bloque:
            break
        for match in matchs_de_la_liste(trame):
            if _a_venir(match, maintenant, heures):
                candidats.append({**match, "sport": sport})
    candidats.sort(key=lambda match: _heure(match.get("debut")) or maintenant)
    lignes: list[dict] = []
    for match in candidats:
        if not client._temps():
            break
        ajoutees, lue, _complet = _detailler(client, match, moment)
        if lue:
            lectures += 1
        lignes += ajoutees
        if client._bloque:
            break
    return lignes, {"ok": lectures > 0 or not client.erreurs, "erreurs": list(client.erreurs),
                    "requetes": client.requetes, "matchs": len(candidats)}


def _cle_selection(ligne: dict):
    valeur = ligne.get("ligne")
    if isinstance(valeur, bool):
        valeur = None
    elif isinstance(valeur, (int, float)):
        valeur = round(float(valeur), 2)
    return (ligne.get("marche"), ligne.get("periode"), valeur, ligne.get("issue"))


class Compteur:
    """Classe les cotes qui ne collent pas, pour savoir quoi corriger.

    Cotes différentes : ``cache_perime`` (la lecture directe date de plus de deux
    minutes de plus que celle de PulseScore), ``issues_permutees`` (le prix
    PulseScore est celui d'une autre issue du même marché, ordre des issues),
    ``mouvement`` (même âge : la cote a bougé, ou l'écart reste à expliquer).
    Sélections PulseScore sans équivalent direct : ``signe_ligne`` (même ligne
    de signe opposé), ``ligne_differente``, ``periode_differente``,
    ``marche_absent``, ``issue_absente``. Aucune clé ni URL n'y figure.
    """

    def __init__(self):
        self.cotes: dict = {}
        self.absentes: dict = {}
        self.exemples: list[dict] = []

    @staticmethod
    def _ajouter(table: dict, cause: str, marche, periode) -> None:
        cle = f"{marche}|{periode}"
        table.setdefault(cause, {})
        table[cause][cle] = table[cause].get(cle, 0) + 1

    def _exemple(self, cause: str, ligne: dict, autre: dict | None) -> None:
        if len(self.exemples) >= 12:
            return
        self.exemples.append({
            "cause": cause, "sport": ligne.get("sport"), "marche": ligne.get("marche"),
            "periode": ligne.get("periode"), "ligne": ligne.get("ligne"), "issue": ligne.get("issue"),
            "cote_pulsescore": ligne.get("cote"),
            "cote_direct": None if autre is None else autre.get("cote"),
        })

    def different(self, ligne: dict, autre: dict, propres: list[dict], offres: dict) -> None:
        cause = "mouvement"
        ta, tb = _heure(ligne.get("collecte")), _heure(autre.get("collecte"))
        if ta and tb and (ta - tb).total_seconds() > 120:
            cause = "cache_perime"
        else:
            cote = _nombre(ligne.get("cote"))
            for voisine in propres:
                if (voisine is ligne or voisine.get("marche") != ligne.get("marche")
                        or voisine.get("periode") != ligne.get("periode")
                        or voisine.get("ligne") != ligne.get("ligne")
                        or voisine.get("issue") == ligne.get("issue")):
                    continue
                reste = offres.get(_cle_selection(voisine))
                valeur = _nombre(reste.get("cote")) if reste else None
                if cote is not None and valeur is not None and abs(cote - valeur) <= ECART_COTE + 1e-9:
                    cause = "issues_permutees"
                    break
        self._ajouter(self.cotes, cause, ligne.get("marche"), ligne.get("periode"))
        self._exemple(cause, ligne, autre)

    def absente(self, ligne: dict, offres: dict) -> None:
        marche, periode = ligne.get("marche"), ligne.get("periode")
        valeur, issue = ligne.get("ligne"), ligne.get("issue")
        causes = set()
        for (m, p, v, i) in offres:
            if m != marche:
                continue
            causes.add("issue_absente")
            if i != issue:
                continue
            if p != periode and v == valeur:
                causes.add("periode_differente")
            elif p == periode and isinstance(v, (int, float)) and isinstance(valeur, (int, float)):
                causes.add("signe_ligne" if v != 0 and abs(v + valeur) < 1e-9 else "ligne_differente")
        cause = next((c for c in ("signe_ligne", "periode_differente", "ligne_differente", "issue_absente")
                      if c in causes), "marche_absent")
        self._ajouter(self.absentes, cause, marche, periode)
        if cause != "marche_absent":
            self._exemple(cause, ligne, None)

    def resume(self) -> dict:
        def total(table):
            return {cause: sum(par.values()) for cause, par in table.items()}
        return {"cotes_differentes": total(self.cotes), "cotes_differentes_par_marche": self.cotes,
                "absentes_du_direct": total(self.absentes), "absentes_par_marche": self.absentes,
                "exemples": self.exemples}


def rapport(pulse: list[dict], direct: list[dict]) -> dict:
    """Couverture des matchs PulseScore et part des cotes communes à ±0,01."""
    ps = [l for l in pulse if isinstance(l, dict) and l.get("bookmaker") == "betclic"]
    di = [l for l in direct if isinstance(l, dict) and l.get("bookmaker") == "betclic"]
    matchs_ps, matchs_di = {}, {}
    for ligne in ps:
        matchs_ps.setdefault(ligne.get("match_id"), ligne)
    for ligne in di:
        matchs_di.setdefault(ligne.get("match_id"), ligne)
    couples = []
    pris = set()
    for mid, a in matchs_ps.items():
        meilleur = None
        for did, b in matchs_di.items():
            if did in pris or a.get("sport") != b.get("sport"):
                continue
            ta, tb = _heure(a.get("debut")), _heure(b.get("debut"))
            if not ta or not tb or abs((ta - tb).total_seconds()) > 90 * 60:
                continue
            score = min(ressemblance(a.get("domicile"), b.get("domicile")),
                        ressemblance(a.get("exterieur"), b.get("exterieur")))
            if meilleur is None or score > meilleur[0]:
                meilleur = (score, did)
        if meilleur and meilleur[0] >= 0.85:
            pris.add(meilleur[1])
            couples.append((mid, meilleur[1]))
    couverture = len(couples) / len(matchs_ps) if matchs_ps else None
    index = {}
    for ligne in di:
        index.setdefault(ligne.get("match_id"), {})[_cle_selection(ligne)] = ligne
    communs = egaux = 0
    ecarts = Compteur()
    for mid_ps, mid_di in couples:
        offres = index.get(mid_di, {})
        propres = [l for l in ps if l.get("match_id") == mid_ps]
        for ligne in propres:
            autre = offres.get(_cle_selection(ligne))
            if not autre:
                ecarts.absente(ligne, offres)
                continue
            communs += 1
            ca, cb = _nombre(ligne.get("cote")), _nombre(autre.get("cote"))
            if ca is not None and cb is not None and abs(ca - cb) <= ECART_COTE + 1e-9:
                egaux += 1
            else:
                ecarts.different(ligne, autre, propres, offres)
    accord = egaux / communs if communs else None
    pret = bool(couverture is not None and accord is not None
                and couverture + 1e-9 >= COUVERTURE_MIN and accord + 1e-9 >= ACCORD_MIN)
    associes = {mid for mid, _did in couples}
    manques = []
    for mid, ligne in matchs_ps.items():
        if mid in associes or len(manques) >= 20:
            continue
        manques.append({
            "sport": ligne.get("sport"),
            "domicile": ligne.get("domicile"),
            "exterieur": ligne.get("exterieur"),
            "ligue": ligne.get("ligue"),
            "debut": ligne.get("debut"),
        })
    return {
        "matchs_pulsescore": len(matchs_ps),
        "matchs_direct": len(matchs_di),
        "matchs_communs": len(couples),
        "manques": manques,
        "couverture": None if couverture is None else round(couverture, 4),
        "selections_communes": communs,
        "selections_egales": egaux,
        "accord_cotes": None if accord is None else round(accord, 4),
        "seuil_couverture": COUVERTURE_MIN,
        "seuil_accord": ACCORD_MIN,
        "pret_a_basculer": pret,
        "diagnostic": ecarts.resume(),
    }
