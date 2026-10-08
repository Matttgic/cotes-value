"""Association des matchs entre sources : même sport, heures proches, noms d'équipes ressemblants.

Les noms diffèrent d'un site à l'autre (« Italie (UN) » / « Italy », « D. Vekic » / « Donna Vekic »,
« Atletico Bucaramanga » / « Bucaramanga », « Kraken » / « Seattle Kraken »). On normalise (accents,
mots vides, pays en français -> anglais), puis on compare : identité, inclusion des mots, initiales
de prénom, ressemblance des lettres. Les marqueurs féminin / jeunes doivent coïncider.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from datetime import datetime, timedelta

PAYS = {
    "allemagne": "germany", "angleterre": "england", "ecosse": "scotland", "pays de galles": "wales",
    "irlande": "ireland", "irlande du nord": "northern ireland", "espagne": "spain", "italie": "italy",
    "pays bas": "netherlands", "belgique": "belgium", "suisse": "switzerland", "autriche": "austria",
    "suede": "sweden", "norvege": "norway", "danemark": "denmark", "finlande": "finland", "islande": "iceland",
    "pologne": "poland", "tchequie": "czech republic", "republique tcheque": "czech republic", "czechia": "czech republic",
    "slovaquie": "slovakia", "hongrie": "hungary", "roumanie": "romania", "bulgarie": "bulgaria", "grece": "greece",
    "turquie": "turkey", "turkiye": "turkey", "croatie": "croatia", "serbie": "serbia", "slovenie": "slovenia",
    "bosnie herzegovine": "bosnia and herzegovina", "bosnie": "bosnia and herzegovina", "montenegro": "montenegro",
    "macedoine du nord": "north macedonia", "albanie": "albania", "chypre": "cyprus", "malte": "malta",
    "georgie": "georgia", "armenie": "armenia", "azerbaidjan": "azerbaijan", "bielorussie": "belarus",
    "russie": "russia", "moldavie": "moldova", "lituanie": "lithuania", "lettonie": "latvia", "estonie": "estonia",
    "andorre": "andorra", "saint marin": "san marino", "iles feroe": "faroe islands", "bresil": "brazil",
    "argentine": "argentina", "colombie": "colombia", "mexique": "mexico", "etats unis": "usa",
    "united states": "usa", "chili": "chile", "perou": "peru", "bolivie": "bolivia", "equateur": "ecuador",
    "haiti": "haiti", "republique dominicaine": "dominican republic", "jamaique": "jamaica", "salvador": "el salvador",
    "trinite et tobago": "trinidad and tobago", "maroc": "morocco", "algerie": "algeria", "tunisie": "tunisia",
    "egypte": "egypt", "senegal": "senegal", "cote d ivoire": "ivory coast", "cameroun": "cameroon",
    "afrique du sud": "south africa", "japon": "japan", "coree du sud": "south korea", "chine": "china",
    "australie": "australia", "nouvelle zelande": "new zealand", "arabie saoudite": "saudi arabia", "irak": "iraq",
    "emirats arabes unis": "united arab emirates", "inde": "india", "ouganda": "uganda", "tanzanie": "tanzania",
    "ethiopie": "ethiopia", "libye": "libya", "guinee": "guinea", "rd congo": "dr congo", "zambie": "zambia",
    "namibie": "namibia", "cap vert": "cape verde", "benin": "benin", "mauritanie": "mauritania", "soudan": "sudan",
    "jordanie": "jordan", "liban": "lebanon", "syrie": "syria", "koweit": "kuwait", "bahrein": "bahrain",
    "ouzbekistan": "uzbekistan", "thailande": "thailand", "indonesie": "indonesia", "malaisie": "malaysia",
    "singapour": "singapore", "kazakhstan": "kazakhstan", "kosovo": "kosovo", "rep dom": "dominican republic",
    "rep dominicaine": "dominican republic",
}
# villes et mots en français -> anglais (appliqué mot à mot)
MOTS = {"cordoue": "cordoba", "barbade": "barbados", "bermudes": "bermuda", "valence": "valencia",
        "barcelone": "barcelona", "bologne": "bologna", "salonique": "thessaloniki", "athenes": "athens",
        "verone": "verona", "naples": "napoli", "turin": "torino", "rome": "roma", "seville": "sevilla",
        "lisbonne": "lisbon", "moscou": "moscow", "geneve": "geneva", "munich": "munchen", "ste": "saint",
        "st": "saint", "lucie": "lucia", "cologne": "koln", "mayence": "mainz", "brunswick": "braunschweig"}
VIDES = {"fc", "cf", "sc", "ac", "afc", "cd", "ca", "club", "de", "del", "la", "le", "les", "the", "sk", "fk",
         "bk", "ud", "sd", "rc", "cs", "ss", "ssc", "calcio", "un", "1907", "1909", "y", "et", "and"}
FEMININ = re.compile(r"\((f|w|wom|women|fem|feminin)\)|\b(women|womens|wom|feminin|feminine|femmes|ladies)\b|\s(f|w)$")
JEUNES = re.compile(r"^(u\d{2}|ii|b|reserves?|youth)$")


def normaliser(nom: str | None) -> tuple[tuple[str, ...], bool, frozenset]:
    """(mots significatifs, féminin, marqueurs jeunes/réserve)."""
    s = unicodedata.normalize("NFKD", nom or "").encode("ascii", "ignore").decode().lower().strip()
    s = re.sub(r"\bf\.\s?c\.?", "fc", s)                 # « F.C. » -> fc
    s = re.sub(r"\bb\.\s?c\.?", "bc", s)                 # « AEK B.C. » (club de basket) -> bc, pas l'équipe B
    s = re.sub(r"\((\d{2})\)", r" u\1", s)                 # « Italie(21) » -> italie u21
    fem = bool(FEMININ.search(s))
    s = FEMININ.sub(" ", s)
    s = s.replace("&", " and ").replace("'", " ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    mots = s.split()
    jeunes = frozenset(m for m in mots if JEUNES.match(m))
    mots = [m for m in mots if not JEUNES.match(m)]
    s = " ".join(mots)
    sans_vides = " ".join(m for m in mots if m not in VIDES)
    s = PAYS.get(s) or PAYS.get(sans_vides) or s        # « italie un » (Betclic) -> italy
    s = " ".join(MOTS.get(m, m) for m in s.split())
    mots = [m for m in s.split() if m not in VIDES] or s.split()
    return tuple(mots), fem, jeunes


def ressemblance(a: str | None, b: str | None) -> float:
    (ma, fa, ja), (mb, fb, jb) = normaliser(a), normaliser(b)
    if not ma or not mb:
        return 0.0
    # féminin / jeunes notés d'un seul côté (Pinnacle n'écrit pas toujours « U21 » ni « Women ») : pénalité
    penalite = 0.85 if (fa != fb or ja != jb) else 1.0
    return penalite * _ressemblance_mots(ma, mb)


def _ressemblance_mots(ma: tuple[str, ...], mb: tuple[str, ...]) -> float:
    if ma == mb:
        return 1.0
    sa, sb = set(ma), set(mb)
    if sa <= sb or sb <= sa:
        return 0.9
    # initiales : « d vekic » / « donna vekic »
    longs_a, longs_b = [m for m in ma if len(m) > 1], [m for m in mb if len(m) > 1]
    init_a, init_b = [m for m in ma if len(m) == 1], [m for m in mb if len(m) == 1]
    if longs_a and set(longs_a) <= sb and all(any(x.startswith(i) for x in mb) for i in init_a):
        return 0.88
    if longs_b and set(longs_b) <= sa and all(any(x.startswith(i) for x in ma) for i in init_b):
        return 0.88
    jac = len(sa & sb) / len(sa | sb)
    rat = difflib.SequenceMatcher(None, " ".join(ma), " ".join(mb)).ratio()
    return max(jac, rat)


def _heure(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


LIGUE_JEUNES = re.compile(r"\b(u\d{2})\b", re.I)
LIGUE_FEMININE = re.compile(r"\b(women|womens|feminin|feminine|femmes|ladies)\b|\(w\)", re.I)


def avec_marqueurs_ligue(nom: str | None, ligue: str | None) -> str | None:
    """Pinnacle écrit « U21 » ou « Women » dans la ligue, pas dans le nom (« France - Switzerland » en
    « U21 Euro Championship Qualifiers ») : on reporte le marqueur sur le nom."""
    if not nom or not ligue:
        return nom
    _, fem, jeunes = normaliser(nom)
    m = LIGUE_JEUNES.search(ligue)
    if m and not jeunes:
        nom = f"{nom} {m.group(1).upper()}"
    if LIGUE_FEMININE.search(ligue) and not fem:
        nom = f"{nom} Women"
    return nom


def matchs_de(lignes: list[dict]) -> dict[str, dict]:
    """Un résumé par match (identifiant -> sport, équipes, début, ordre incertain)."""
    out = {}
    for l in lignes:
        ligue = l.get("ligue") if l.get("source") == "pinnacle" else None
        out.setdefault(l["match_id"], {"match_id": l["match_id"], "sport": l["sport"],
                                       "domicile": avec_marqueurs_ligue(l["domicile"], ligue),
                                       "exterieur": avec_marqueurs_ligue(l["exterieur"], ligue),
                                       "debut": _heure(l["debut"]),
                                       "approx": bool(l.get("debut_approximatif")),
                                       "ordre_incertain": bool(l.get("ordre_incertain")) or l["source"] == "polymarket"})
    return out


def associer(matchs_fr: dict[str, dict], matchs_ref: dict[str, dict]) -> dict[str, tuple[str, bool, float]]:
    """Pour chaque match français : (match de référence, inversé ?, score) quand un match correspond."""
    index: dict[tuple[str, int], list[dict]] = {}
    for r in matchs_ref.values():
        if r["debut"]:
            index.setdefault((r["sport"], int(r["debut"].timestamp() // 3600)), []).append(r)
    res = {}
    for mid, f in matchs_fr.items():
        if not f["debut"]:
            continue
        h = int(f["debut"].timestamp() // 3600)
        meilleur = None
        for dh in range(-6, 7):
            for r in index.get((f["sport"], h + dh), []):
                ecart = abs((r["debut"] - f["debut"]).total_seconds()) / 60
                if ecart > 300:
                    continue
                # les deux ordres sont toujours essayés : un bookmaker peut inverser domicile et extérieur
                # (Islanders – Rangers chez NetBet, Rangers – Islanders chez Pinnacle) et deux équipes de la
                # même ville se ressemblent assez (0,82) pour que l'ordre direct passe à tort
                paires = [((ressemblance(f["domicile"], r["domicile"]), ressemblance(f["exterieur"], r["exterieur"])), False),
                          ((ressemblance(f["domicile"], r["exterieur"]), ressemblance(f["exterieur"], r["domicile"])), True)]
                (s1, s2), inverse = max(paires, key=lambda p: (min(p[0]), sum(p[0]), not p[1]))
                score = min(s1, s2)
                # tolérance sur l'heure : 20 min ; plus large si les deux noms sont très proches
                # (heures approximatives : Kalshi, ordre de passage au tennis, erreurs d'horaire)
                limite = 300 if r["approx"] else (180 if f["sport"] == "tennis" else 90) if score >= 0.85 else 20
                if ecart > limite:
                    continue
                if score < 0.75 and not (score >= 0.6 and ecart <= 5):
                    # une équipe identique, même heure, l'autre approchante (noms tronqués ou sponsors)
                    if max(s1, s2) >= 0.9 and score >= 0.3 and ecart <= 10:
                        score = 0.7
                    else:
                        continue
                # à ressemblance égale, l'heure la plus proche (deux matchs des mêmes équipes le même jour)
                if meilleur is None or (score, -ecart) > (meilleur[2], -meilleur[3]):
                    meilleur = (r["match_id"], inverse, score, ecart)
        if meilleur:
            res[mid] = meilleur[:3]
    return res
