"""Association des matchs entre sources : même sport, heures proches, noms d'équipes ressemblants.

Les noms diffèrent d'un site à l'autre (« Italie (UN) » / « Italy », « D. Vekic » / « Donna Vekic »,
« Atletico Bucaramanga » / « Bucaramanga », « Kraken » / « Seattle Kraken »). On normalise (accents,
mots vides, pays en français -> anglais), puis on compare : identité, inclusion des mots, initiales
de prénom, ressemblance des lettres. Les marqueurs féminin / jeunes doivent coïncider.
"""
from __future__ import annotations

import difflib
import functools
import re
import unicodedata
from datetime import datetime

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
        "lisbonne": "lisbon", "moscou": "moscow", "varsovie": "warsaw", "cracovie": "krakow", "geneve": "geneva", "munich": "munchen", "ste": "saint",
        "st": "saint", "lucie": "lucia", "cologne": "koln", "mayence": "mainz", "brunswick": "braunschweig"}
VIDES = {"fc", "cf", "sc", "ac", "afc", "cd", "ca", "club", "de", "del", "la", "le", "les", "the", "sk", "fk",
         "bk", "ud", "sd", "rc", "cs", "ss", "ssc", "calcio", "un", "1907", "1909", "y", "et", "and", "vb"}
FEMININ = re.compile(r"\((f|w|wom|women|fem|feminin)\)|\b(women|womens|wom|feminin|feminine|femmes|ladies)\b|\s(f|w)\.?$")
JEUNES = re.compile(r"^(u\d{2}|ii|b|reserves?|youth)$")
RESERVE = {"ii": "b"}


def normaliser(nom: str | None) -> tuple[tuple[str, ...], bool, frozenset]:
    """(mots significatifs, féminin, marqueurs jeunes/réserve).

    Fonction pure (expressions et tables constantes), appelée des centaines de milliers de fois par cycle sur
    quelques milliers de noms : le calcul est mis en cache (``_normaliser``). Le résultat est entièrement
    immuable (tuple de str, bool, frozenset) : il peut être partagé sans risque entre appelants. Toute valeur
    « vide » (None, "", 0, liste vide…) donnait déjà le résultat de "" : elle est ramenée à "" avant le cache,
    si bien qu'une valeur vide non hachable reste acceptée ; une valeur non vide non textuelle lève toujours."""
    return _normaliser(nom or "")


@functools.lru_cache(maxsize=65536)
def _normaliser(nom: str) -> tuple[tuple[str, ...], bool, frozenset]:
    s = unicodedata.normalize("NFKD", nom or "").encode("ascii", "ignore").decode().lower().strip()
    s = re.sub(r"\bf\.\s?c\.?", "fc", s)                 # « F.C. » -> fc
    s = re.sub(r"\bb\.\s?c\.?", "bc", s)                 # « AEK B.C. » (club de basket) -> bc, pas l'équipe B
    s = re.sub(r"\bv\.\s?b\.?(?=\s|$)", "vb", s)       # « Toulouse V.B. » (volley-ball) -> vb, pas l'équipe B
    s = re.sub(r"\((\d{2})\)", r" u\1", s)                 # « Italie(21) » -> italie u21
    # « Woollaston B. » (snooker, tennis) : initiale du prénom, pas l'équipe B ; seulement un nom court, avec le point
    if re.fullmatch(r"[a-z' -]+ b\.", s) and len(s.split()) <= 2:
        s = s[:-2] + "bini"
    fem = bool(FEMININ.search(s))
    s = FEMININ.sub(" ", s)
    s = s.replace("&", " and ").replace("'", " ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    mots = s.split()
    # « B » et « II » désignent la même équipe réserve (Pinnacle écrit « II ») : un seul marqueur. Sinon « Real Sociedad B »
    # (Betclic) et « Real Sociedad II » (Pinnacle) passaient pour deux catégories contradictoires (ressemblance 0)
    # et n'étaient plus associés (cas réels des 10 et 17/10/2026, aussi Porto B, Benfica B, Sporting B, Celta B).
    jeunes = frozenset(RESERVE.get(m, m) for m in mots if JEUNES.match(m))
    mots = ["b" if m == "bini" else m for m in mots if not JEUNES.match(m)]
    s = " ".join(mots)
    sans_vides = " ".join(m for m in mots if m not in VIDES)
    s = PAYS.get(s) or PAYS.get(sans_vides) or s        # « italie un » (Betclic) -> italy
    s = " ".join(MOTS.get(m, m) for m in s.split())
    mots = [m for m in s.split() if m not in VIDES] or s.split()
    return tuple(mots), fem, jeunes


def _premiere_explicite(nom: str | None) -> bool:
    s = unicodedata.normalize("NFKD", nom or "").encode("ascii", "ignore").decode().lower()
    return bool(re.search(r"\b(?:equipe premiere|first team|1st team|seniors?)\b|\((?:i|1)\)", s))


@functools.lru_cache(maxsize=262144)
def ressemblance(a: str | None, b: str | None) -> float:
    """Pure et symétrique en pratique, mais appelée plusieurs fois par couple de noms (association, derbys) : mise en cache."""
    categorie = lambda n: normaliser(re.sub(r"\b(?:u|under)[ -]?(\d{2})\b", r"u\1", n or "", flags=re.I))
    (ma, fa, ja), (mb, fb, jb) = categorie(a), categorie(b)
    if not ma or not mb:
        return 0.0
    # Une catégorie absente est une incertitude ; deux catégories explicites
    # contradictoires sont des équipes différentes, même si les noms coïncident.
    if ((ja and _premiere_explicite(b)) or (jb and _premiere_explicite(a))
            or (ja and jb and ja != jb)):
        return 0.0
    penalite = 0.85 if (fa != fb or bool(ja) != bool(jb)) else 1.0
    return penalite * _ressemblance_mots(ma, mb)


def _abrege(m: str, x: str) -> bool:
    """`m` est une abréviation de `x` : même première lettre, lettres dans l'ordre, au moins deux lettres de moins."""
    if len(m) < 2 or m[0] != x[0] or len(x) < len(m) + 2:
        return False
    it = iter(x)
    return all(c in it for c in m)


def _abrege_tous(petit: set, grand: set) -> bool:
    """Chaque mot de `petit` est dans `grand` ou en est l'abréviation."""
    return all(m in grand or any(_abrege(m, x) for x in grand) for m in petit)


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
    # radicaux : « Aurillac » / « Stade Aurillacois » (un mot en préfixe de l'autre, 5 lettres au moins)
    def _couvert(petit, grand):
        return all(m in grand or any(len(m) >= 5 and (m.startswith(x) or x.startswith(m)) and len(x) >= 5 for x in grand)
                   for m in petit)
    if _couvert(sa, sb) or _couvert(sb, sa):
        return 0.88
    # abréviations (« Nilufer Bld. » / « Nilufer Belediyespor ») : au moins un mot identique, les autres abrégés
    if (sa & sb) and any(len(m) >= 4 for m in sa & sb) and (_abrege_tous(sa, sb) or _abrege_tous(sb, sa)):
        return 0.86
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
        out.setdefault(l["match_id"], {"match_id": l["match_id"], "sport": l["sport"], "source": l.get("source"),
                                       "domicile": avec_marqueurs_ligue(l["domicile"], ligue),
                                       "exterieur": avec_marqueurs_ligue(l["exterieur"], ligue),
                                       "debut": _heure(l["debut"]),
                                       "approx": bool(l.get("debut_approximatif")),
                                       "ordre_incertain": bool(l.get("ordre_incertain")) or l["source"] == "polymarket"})
    return out


def _ordre(paire: tuple) -> tuple:
    """Clé de choix de l'ordre : le nombre de noms identiques (≥ 0,99), puis la moins bonne des deux ressemblances,
    puis leur somme, puis l'ordre direct.

    Un nom identique prime : sinon le nom de la ville seul (« Sydney », « Tokyo », « Cali »), commun aux deux
    équipes, fait gagner l'ordre croisé (cas réels des 14-16/10/2026 : Sydney FC – West. Sydney, Tokyo Verdy –
    FC Tokyo, associés à l'envers et CLV fausse). La règle ne valait d'abord que pour les « derbys » (deux noms
    ressemblants à 0,75) : « America de Cali – Deportivo Cali » (0,62) y échappait et a été associé à l'envers à
    « América de Cali – AD Cali » de Polymarket le 08/11/2026 (0,63 / 0,62 croisé contre 1,0 / 0,57 direct)."""
    (s1, s2), inverse = paire
    return (s1 >= 0.99) + (s2 >= 0.99), min(s1, s2), s1 + s2, not inverse


# Sports individuels : un nom de joueur n'est ni tronqué ni allongé d'un sponsor. Un seul joueur reconnu ne suffit pas.
INDIVIDUELS = {"tennis", "tennis_de_table", "badminton", "snooker", "flechettes", "mma", "boxe", "golf"}
SOLIDE = 0.75


def _double(nom: str | None) -> bool:
    """Paire de double (« A. Kucmova / A. Laboutkova », « Kucmova & Laboutkova »)."""
    return bool(re.search(r"/|&", nom or ""))


def _bookmaker(match: dict) -> str:
    return str(match.get("source") or str(match.get("match_id") or "").split("|")[0])


def associer(matchs_fr: dict[str, dict], matchs_ref: dict[str, dict]) -> dict[str, tuple[str, bool, float]]:
    """Pour chaque match français : (match de référence, inversé ?, score) quand un match correspond.

    Un match de référence ne sert qu'à un seul match par bookmaker (voir ``_exclusifs``)."""
    index: dict[tuple[str, int], list[dict]] = {}
    for r in matchs_ref.values():
        if r["debut"]:
            index.setdefault((r["sport"], int(r["debut"].timestamp() // 3600)), []).append(r)
    # ±3 h couvre le tennis (180 min). Une heure approximative (300 min) garde ±6 h.
    portee = 6 if any(r.get("approx") for r in matchs_ref.values()) else 3
    res = {}
    for mid, f in matchs_fr.items():
        if not f["debut"]:
            continue
        h = int(f["debut"].timestamp() // 3600)
        individuel = f["sport"] in INDIVIDUELS
        meilleur = None
        # Tolérance la plus large possible pour ce match (voir plus bas) : deux instants à Δ minutes d'écart tombent dans
        # des tranches horaires distantes d'au plus ⌈Δ/60⌉. Aller plus loin ne trouverait que des candidats rejetés.
        dh_max = min(portee, -(-(300 if portee == 6 else 180 if f["sport"] == "tennis" else 90) // 60))
        for dh in range(-dh_max, dh_max + 1):
            for r in index.get((f["sport"], h + dh), []):
                ecart = abs((r["debut"] - f["debut"]).total_seconds()) / 60
                if ecart > (300 if r["approx"] else 180 if f["sport"] == "tennis" else 90):
                    continue                  # au-delà de la plus large tolérance ci-dessous : inutile de comparer les noms
                # Simple contre double : la joueuse commune ne fait pas le même match (cas réel du 04/11/2026, OlyBet :
                # « W. Falkowska – M. Rajeshwaran Revathi » associé au double « … / M. Rajeshwaran Revathi » de Pinnacle)
                if individuel and (_double(f["domicile"]) or _double(f["exterieur"])) != (
                        _double(r["domicile"]) or _double(r["exterieur"])):
                    continue
                # les deux ordres sont toujours essayés : un bookmaker peut inverser domicile et extérieur
                # (Islanders – Rangers chez NetBet, Rangers – Islanders chez Pinnacle) et deux équipes de la
                # même ville se ressemblent assez (0,82) pour que l'ordre direct passe à tort
                paires = [((ressemblance(f["domicile"], r["domicile"]), ressemblance(f["exterieur"], r["exterieur"])), False),
                          ((ressemblance(f["domicile"], r["exterieur"]), ressemblance(f["exterieur"], r["domicile"])), True)]
                (s1, s2), inverse = max(paires, key=_ordre)
                score = min(s1, s2)
                # tolérance sur l'heure : 20 min ; plus large si les deux noms sont très proches
                # (heures approximatives : Kalshi, ordre de passage au tennis, erreurs d'horaire)
                limite = 300 if r["approx"] else (180 if f["sport"] == "tennis" else 90) if score >= 0.85 else 20
                if ecart > limite:
                    continue
                # Deux noms seulement approchants (0,6 à 0,75) à la même heure : il faut qu'un des deux soit solide.
                # Sinon des mots communs sans valeur (« County », « City », « JK ») ou des lettres voisines suffisent
                # (cas réels : Derby County – Stoke City associé à Newport County – York City le 17/10/2026, Pärnu JK
                # Vaprus – Nõmme Kalju à Harju JK Laagri – Nõmme United le 13/10, Odense – Silkeborg à Viborg – Horsens
                # le 01/11).
                if score < 0.75 and not (score >= 0.6 and ecart <= 5 and max(s1, s2) >= SOLIDE):
                    # une équipe identique, même heure, l'autre approchante (noms tronqués ou sponsors).
                    # « Identique » à 0,9 seulement si le nom du bookmaker n'a pas de mot en plus : « Carrick
                    # Rangers » n'est pas « Rangers », « Aris Limassol » n'est pas « Aris » (cas réels du
                    # 10/10/2026 : Dungannon – Carrick Rangers associé à Rangers – Kilmarnock).
                    # Jamais pour un sport individuel : un seul joueur reconnu, c'est un autre match (cas réel du
                    # 21/10/2026 : Onclin – Struff associé à Blockx – Struff).
                    fr_fort, ref_fort = ((f["domicile"], r["exterieur" if inverse else "domicile"]) if s1 >= s2
                                         else (f["exterieur"], r["domicile" if inverse else "exterieur"]))
                    inclus = set(normaliser(fr_fort)[0]) <= set(normaliser(ref_fort)[0])
                    if (not individuel and max(s1, s2) >= 0.9 and score >= 0.3 and ecart <= 10
                            and (max(s1, s2) >= 0.99 or inclus or score >= 0.45)):
                        score = 0.7
                    else:
                        continue
                # à ressemblance égale, l'heure la plus proche (deux matchs des mêmes équipes le même jour)
                if meilleur is None or (score, -ecart) > (meilleur[2], -meilleur[3]):
                    meilleur = (r["match_id"], inverse, score, ecart)
        if meilleur:
            res[mid] = meilleur
    return {mid: m[:3] for mid, m in _exclusifs(res, matchs_fr).items()}


def _exclusifs(res: dict[str, tuple], matchs_fr: dict[str, dict]) -> dict[str, tuple]:
    """Un match de référence pour un seul match d'un même bookmaker : le mieux noté le garde, les autres sont retirés.

    Deux matchs différents d'un bookmaker ne peuvent pas être le même match de référence. Le perdant est presque
    toujours un sosie accepté par une règle souple quand son vrai match manque chez la référence (cas réels :
    Betclic, 13/10/2026, « Pärnu JK Vaprus – Nõmme Kalju » à 0,6 et « Harju JK Laagri – FC Nõmme United » à 1,0 sur
    le même match Pinnacle 1637810025 ; « FC Tokyo – Kashiwa Reysol » sur « Yokohama F. Marinos – Tokyo Verdy » de
    Smarkets le 21/10, 74 paris). Un bookmaker peut lister deux fois le même match : à score égal, ou dès 0,9 (les
    deux noms concordent), l'association est gardée."""
    par_ref: dict[tuple, list[str]] = {}
    for mid, m in res.items():
        par_ref.setdefault((_bookmaker(matchs_fr[mid]), m[0]), []).append(mid)
    out = dict(res)
    for mids in par_ref.values():
        if len(mids) < 2:
            continue
        gagnant = max(res[mid][2] for mid in mids)
        for mid in mids:
            if res[mid][2] < min(gagnant, 0.9):
                del out[mid]
    return out
