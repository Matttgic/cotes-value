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
from datetime import datetime, timedelta, timezone

import requests

from cotes.correspondance import ressemblance
from cotes.direct.horizon import fusionner
from cotes.pulsescore import traduire

BASE = "https://offering.begmedia.com/web/offering.access.api/offering.access.api.MatchService"
LISTE = "GetMatchesBySportWithNotifications"
DETAIL = "GetMatchWithNotification"
PAGE = 40
_OFFSET_MAX = 160
_PRES_H = 6
_FRAIS_LOIN_MIN = 30
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


def _classe(nom: str, domicile: str, exterieur: str) -> str | None:
    bas = nom.strip().lower()
    if any(mot in bas for mot in ("buteur", "décisif", "decisif", "passeur", "mi-temps",
                                  "mi temps", "&", "écart", "ecart", "quand sera", "comment")):
        return None
    if bas.startswith(("résultat du match", "resultat du match", "vainqueur")):
        return "MATCH_RESULT"
    if bas.startswith("double chance"):
        return "DOUBLE_CHANCE"
    if bas.startswith(("les 2 équipes marquent", "les deux équipes marquent", "both teams")):
        return "BOTH_TEAMS_TO_SCORE"
    if bas.startswith("score exact"):
        return "CORRECT_SCORE"
    if " - " in nom and bas.startswith(("total", "nombre total")):
        equipe = nom.split(" - ", 1)[1].strip().lower()
        if equipe == domicile.strip().lower():
            return "HOME_OVER_UNDER"
        if equipe == exterieur.strip().lower():
            return "AWAY_OVER_UNDER"
        return None
    if bas.startswith(("nombre total", "total de buts", "total de points", "total de jeux", "total points")):
        return "OVER_UNDER"
    return None


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


def marche_pulse(marche: dict, domicile: str, exterieur: str) -> dict | None:
    canon = _classe(marche.get("nom") or "", domicile, exterieur)
    if not canon:
        return None
    selections = []
    for offre in marche.get("selections") or []:
        nom = str(offre.get("nom") or "")
        if canon == "CORRECT_SCORE":
            issue, ligne = "SCORE", None
        elif canon in ("OVER_UNDER", "HOME_OVER_UNDER", "AWAY_OVER_UNDER"):
            issue, ligne = _sens_total(nom), _ligne_totale(nom)
        elif canon == "DOUBLE_CHANCE":
            issue, ligne = _double_chance(nom, domicile, exterieur), None
        elif canon == "BOTH_TEAMS_TO_SCORE":
            issue, ligne = _issue(nom, domicile, exterieur), None
            if issue not in ("YES", "NO"):
                issue = None
        else:
            issue, ligne = _issue(nom, domicile, exterieur), None
        if not issue or (canon.endswith("OVER_UNDER") and ligne is None):
            continue
        selections.append({"canonicalOutcome": issue, "rawName": nom, "odds": offre["cote"], "line": ligne})
    if len(selections) < 2:
        return None
    return {"marketId": marche.get("nom"), "canonicalMarket": canon, "rawName": marche.get("nom"),
            "period": "FULL_TIME", "selections": selections}


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
    if match.get("direct"):
        return False
    debut = _heure(match.get("debut"))
    return bool(debut and maintenant < debut <= maintenant + timedelta(hours=heures))


def _charge_liste(slug: str, offset: int = 0) -> bytes:
    return (encode_champ_octets(1, slug) + encode_champ_octets(2, "fr")
            + encode_champ_varint(4, offset) + encode_champ_varint(5, PAGE))


def _offset_suivant(reserve: dict) -> tuple[int, int]:
    """Page 0 à chaque cycle. L'autre page tourne ; un curseur nul part à la page suivante."""
    extra = int(reserve.get("offset") or 0) or PAGE
    if extra <= 0 or extra >= _OFFSET_MAX:
        extra = PAGE
    prochain = extra + PAGE
    if prochain >= _OFFSET_MAX:
        prochain = 0
    return extra, prochain


def _detailler(client: Client, match: dict, moment: str) -> tuple[list[dict], bool]:
    trame = client.poster(DETAIL, encode_champ_varint(1, int(match["id"])) + encode_champ_octets(2, "fr"))
    if client._bloque:
        return [], bool(trame)
    marches = []
    for offre in marches_du_detail(trame):
        traduit = marche_pulse(offre, match["domicile"], match["exterieur"])
        if traduit:
            marches.append(traduit)
    if not marches:
        return [], bool(trame)
    evenement = {"eventId": match["id"], "home": match["domicile"], "away": match["exterieur"],
                 "league": match.get("competition"), "startTime": match.get("debut"), "markets": marches}
    return traduire(evenement, "betclic", match["sport"], moment), bool(trame)


def _collecter_reserve(client: Client, demandes, heures: float, maintenant: datetime,
                       reserve: dict) -> tuple[list[dict], dict]:
    """Page proche à chaque cycle, une page lointaine en plus. L'union reste sur 36 h."""
    moment = maintenant.isoformat(timespec="seconds")
    extra, prochain = _offset_suivant(reserve)
    candidats = []
    vus: set = set()
    lectures = 0
    for sport, slug in demandes:
        for offset in (0, extra):
            if not client._temps():
                break
            trame = client.poster(LISTE, _charge_liste(slug, offset))
            if trame:
                lectures += 1
            if client._bloque:
                break
            for match in matchs_de_la_liste(trame):
                if not _a_venir(match, maintenant, heures):
                    continue
                cle = (sport, match.get("id"))
                if cle in vus:
                    continue
                vus.add(cle)
                candidats.append({**match, "sport": sport})
        if client._bloque or not client._temps():
            break
    frais: dict = {}
    for ligne in reserve.get("lignes") or []:
        if not isinstance(ligne, dict):
            continue
        lu = _heure(ligne.get("collecte"))
        mid = ligne.get("match_id")
        if mid and lu and (mid not in frais or lu > frais[mid]):
            frais[mid] = lu
    limite = maintenant + timedelta(hours=min(_PRES_H, heures))

    def proche(match) -> bool:
        debut = _heure(match.get("debut"))
        return bool(debut and debut <= limite)

    def a_relire(match) -> bool:
        if proche(match):
            return True
        lu = frais.get(f"betclic|{match.get('id')}")
        if lu is not None and maintenant - lu < timedelta(minutes=_FRAIS_LOIN_MIN):
            return False
        return True

    file = [m for m in candidats if proche(m)]
    file.sort(key=lambda match: _heure(match.get("debut")) or maintenant)
    loin = [m for m in candidats if not proche(m) and a_relire(m)]
    loin.sort(key=lambda match: _heure(match.get("debut")) or maintenant)
    lignes: list[dict] = []
    for match in file + loin:
        if not client._temps():
            break
        ajoutees, lue = _detailler(client, match, moment)
        if lue:
            lectures += 1
        lignes += ajoutees
        if client._bloque:
            break
    fusion = fusionner(reserve.get("lignes") or [], lignes, maintenant, heures)
    return fusion, {
        "ok": lectures > 0 or not client.erreurs or bool(fusion),
        "erreurs": list(client.erreurs),
        "requetes": client.requetes,
        "matchs": len({l.get("match_id") for l in fusion}),
        "reserve": {"offset": prochain, "lignes": fusion},
    }


def collecter(sports: set[str] | None = None, heures: float = 36, session=None,
              maintenant: datetime | None = None, echeance=None,
              reserve=None) -> tuple[list[dict], dict]:
    """Lignes déjà passées par ``pulsescore.traduire`` (bookmaker ``betclic``).

    Sans réserve, une seule page (offset 0) puis le détail, comme avant.
    Avec réserve, la page 0 et une page plus loin ; les matchs déjà frais
    ne sont pas redétaillés, et la comparaison reçoit l'union sur l'horizon.
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
                                  reserve if isinstance(reserve, dict) else {})
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
        ajoutees, lue = _detailler(client, match, moment)
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
    for mid_ps, mid_di in couples:
        offres = index.get(mid_di, {})
        for ligne in ps:
            if ligne.get("match_id") != mid_ps:
                continue
            autre = offres.get(_cle_selection(ligne))
            if not autre:
                continue
            communs += 1
            ca, cb = _nombre(ligne.get("cote")), _nombre(autre.get("cote"))
            if ca is not None and cb is not None and abs(ca - cb) <= ECART_COTE + 1e-9:
                egaux += 1
    accord = egaux / communs if communs else None
    pret = bool(couverture is not None and accord is not None
                and couverture + 1e-9 >= COUVERTURE_MIN and accord + 1e-9 >= ACCORD_MIN)
    return {
        "matchs_pulsescore": len(matchs_ps),
        "matchs_direct": len(matchs_di),
        "matchs_communs": len(couples),
        "couverture": None if couverture is None else round(couverture, 4),
        "selections_communes": communs,
        "selections_egales": egaux,
        "accord_cotes": None if accord is None else round(accord, 4),
        "seuil_couverture": COUVERTURE_MIN,
        "seuil_accord": ACCORD_MIN,
        "pret_a_basculer": pret,
    }
