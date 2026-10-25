"""Cotes Betclic lues sur l'API publique gRPC-web, au format PulseScore.

Pas d'authentification. Référence de forme : le client public TapsHTS/betclic-api.
Une requête de liste par sport, page de 40 (le serveur n'en met pas plus dans
la première trame), puis un détail par match encore à venir, les plus proches
d'abord. Chaque réponse est un flux de notification : on le ferme dès la
première trame, sans pagination et sans attendre la suite.
"""
from __future__ import annotations

import re
import unicodedata
import struct
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

from cotes.direct.horizon import fusionner
from cotes.pulsescore import traduire

BASE = "https://offering.begmedia.com/web/offering.access.api/offering.access.api.MatchService"
LISTE = "GetMatchesBySportWithNotifications"
DETAIL = "GetMatchWithNotification"
PAGE = 40
_LISTE_MAX = 640
# Un détail relu il y a moins longtemps reste en cache : le budget sert
# d'abord aux matchs encore jamais lus. Le cycle dure 5 min : au-delà de 3 min
# de cache, des cotes de 10 min d'âge décidaient des paris.
_FRAIS_MIN = 3
# Mesuré le 25/10/2026 : un match coûte « Le Top » (1 requête) plus 2 à 3 onglets (~65 % des requêtes), mais les
# onglets ne portent que 8 % des paris Betclic (44 sur 545, depuis le 15/10). Avec la réserve, « Le Top » est relu à
# chaque passage et les onglets au plus toutes les ONGLETS_MIN minutes : leurs marchés restent entre-temps avec leur
# heure de lecture, sous la fenêtre de 15 minutes de la comparaison.
ONGLETS_MIN = 10
# Lectures de détail simultanées (5 en parallèle n'ont pas donné de 429).
_CONCURRENCE = 4
# Matchs proches : ceux sur lesquels on parie et on alerte (le prix doit avoir moins de 5 minutes). Une lecture
# ratée ou vide y est retentée une fois dans le même passage ; si le détail revient sans aucun marché, les cotes
# gardées du passage précédent sont retirées : il n'y a plus de prix à comparer, un ancien prix ne vaut rien.
# Constaté le 25/10/2026 : un pari Anglet–Marseille pris sur une cote Betclic de 12 minutes, à 22 min du match.
_PROCHE_H = 2
_RELANCES_MAX = 12
# Onglets lus en plus de « Le Top » : demi-temps, périodes, quarts-temps, sets, jeux.
LIBELLES_ONGLETS = {"résultats", "buts", "points", "sets", "jeux"}
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
    competition = comp_id = sport_id = None
    if 8 in champs and isinstance(champs[8][0], (bytes, bytearray)):
        comp = decode_protobuf(champs[8][0])
        if 2 in comp:
            competition = _texte(comp[2][0])
        if isinstance(comp.get(1, [None])[0], int):
            comp_id = comp[1][0]
        if isinstance(comp.get(3, [None])[0], (bytes, bytearray)):
            sport_id = decode_protobuf(comp[3][0]).get(3, [None])[0]
            sport_id = sport_id if isinstance(sport_id, int) else None
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
            "competition": competition, "direct": direct, "competition_id": comp_id, "sport_id": sport_id}


def _slug(texte) -> str:
    """Minuscules sans accents, tout le reste en tirets (« Australie A-League » -> « australie-a-league »)."""
    base = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")


def chemin_match(match: dict) -> str | None:
    """Chemin de la page du match sur betclic.fr, ``/football-s1/<compétition>-c<id>/<équipes>-m<id>``.

    Football seulement (les autres sports ont un identifiant de sport et un nom de rubrique que la collecte ne
    donne pas). FORMAT NON VÉRIFIÉ EN LIGNE : betclic.fr répond 403 à tout accès automatique, même pour un vrai
    match ; il vient de la forme des adresses du site. Les identifiants viennent de la collecte, les noms servent
    seulement de décor. ``liens.lien_match`` ajoute le domaine et vérifie que l'identifiant du match y figure."""
    if match.get("sport") != "football" or match.get("sport_id") != 1 or not isinstance(match.get("competition_id"), int):
        return None
    comp, equipes = _slug(match.get("competition")), _slug(f"{match.get('domicile')} {match.get('exterieur')}")
    if not comp or not equipes or not isinstance(match.get("id"), int):
        return None
    return f"/football-s1/{comp}-c{match['competition_id']}/{equipes}-m{match['id']}"


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
    # Marchés de « Le Top » : les autres lignes viennent d'un onglet et portent ``onglet`` (voir _collecter_reserve).
    du_top = {f"betclic|{t['marketId']}" for o in offres
              for t in marches_pulse(o, match["domicile"], match["exterieur"], match["sport"])}
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
                 "league": match.get("competition"), "startTime": match.get("debut"), "markets": marches,
                 "slug": chemin_match(match)}
    lignes, vus = [], set()
    for ligne in traduire(evenement, "betclic", match["sport"], moment):
        cle = (ligne["match_id"], ligne["marche"], ligne["periode"], ligne["ligne"], ligne["issue"])
        if cle not in vus:     # « Écart de buts » et « Ecart entre les équipes » donnent les mêmes handicaps
            vus.add(cle)
            if ligne.get("cle_marche") not in du_top:
                ligne["onglet"] = True
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

    onglets_lus = {mid: v for mid, v in (reserve.get("onglets") or {}).items() if isinstance(v, str)} \
        if isinstance(reserve.get("onglets"), dict) else {}
    compte = {"avec_onglets": 0, "sans_onglets": 0}
    verrou = threading.Lock()

    def onglets_dus(mid: str) -> bool:
        """Onglets jamais lus, sans marché gardé, ou lus il y a ``ONGLETS_MIN`` minutes ou plus."""
        lu = _heure(onglets_lus.get(mid))
        if lu is None or not any(l.get("onglet") for l in anciennes.get(mid, [])):
            return True
        return maintenant - lu >= timedelta(minutes=ONGLETS_MIN)

    def lire(match):
        if arret.is_set() or not client._temps():
            return None
        mid = f"betclic|{match.get('id')}"
        dus = onglets_dus(mid)
        ajoutees, lue, complet = _detailler(client, match, moment, onglets=dus)
        if client._bloque:
            arret.set()
        if dus and lue and complet:
            onglets_lus[mid] = moment
        with verrou:
            compte["avec_onglets" if dus else "sans_onglets"] += 1
        if (not complet or not dus) and ajoutees:
            # Onglets pas relus (à leur rythme, ou coupés par le budget) : leurs marchés du passage précédent,
            # avec leur heure de lecture. Seulement des lignes d'onglet : un marché retiré de « Le Top » ne revient
            # pas. Même limite d'âge (2 h) que la fusion du reste du catalogue.
            presentes = {l.get("cle_marche") for l in ajoutees}
            ajoutees = ajoutees + [l for l in anciennes.get(mid, [])
                                   if l.get("onglet") and l.get("cle_marche") not in presentes
                                   and (lu := _heure(l.get("collecte"))) is not None
                                   and maintenant - lu <= timedelta(hours=2)]
        return ajoutees, lue

    def proche(match) -> bool:
        debut = _heure(match.get("debut"))
        return debut is not None and maintenant < debut <= maintenant + timedelta(hours=_PROCHE_H)

    with ThreadPoolExecutor(max(1, concurrence)) as pool:
        resultats = list(pool.map(lire, file))
    # Lecture ratée (aucune réponse) ou vide (aucun marché) d'un match proche : une seconde tentative.
    suivi = {"proches": 0, "relances": 0, "proches_non_lus": 0, "proches_vides": 0}
    vides: set[str] = set()
    for i, match in enumerate(file):
        if not proche(match):
            continue
        suivi["proches"] += 1
        recu = resultats[i]
        if (recu is None or not recu[1] or not recu[0]) and suivi["relances"] < _RELANCES_MAX \
                and not arret.is_set() and client._temps():
            suivi["relances"] += 1
            recu = lire(match) or recu
            resultats[i] = recu
        if recu is None or not recu[1]:
            suivi["proches_non_lus"] += 1             # aucune réponse : les cotes gardées gardent leur âge réel
        elif not recu[0]:
            suivi["proches_vides"] += 1
            vides.add(f"betclic|{match.get('id')}")   # réponse sans marché : plus de prix chez Betclic
    for recu in resultats:
        if recu is None:
            continue
        ajoutees, lue = recu
        if lue:
            lectures += 1
        lignes += ajoutees
    anciennes_gardees = [l for l in (reserve.get("lignes") or [])
                         if not (isinstance(l, dict) and l.get("match_id") in vides)]
    fusion = fusionner(anciennes_gardees, lignes, maintenant, heures, age_max_h=2)
    au_catalogue = {f"betclic|{m.get('id')}" for m in candidats}
    return fusion, {
        "ok": lectures > 0 or not client.erreurs or bool(fusion),
        "erreurs": list(client.erreurs),
        "requetes": client.requetes,
        "matchs": len({l.get("match_id") for l in fusion}),
        "onglets": dict(compte), "proches": suivi,
        "reserve": {"offset": 0, "lignes": fusion,
                    "onglets": {mid: v for mid, v in onglets_lus.items() if mid in au_catalogue}},
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


