"""Où trouver le score d'un match que les sources automatiques ne règlent pas, par sport et par ligue.

Chaque entrée est un site déjà utilisé pour retrouver un résultat à la main (saisi dans
donnees/resultats_manuels.json) : on regarde là d'abord, avant toute recherche sur le web.
Une ligue est reconnue par un mot-clé contenu dans son nom (sans accents ni casse) ; à défaut, les
sources générales du sport. Pour ajouter une source : une ligne ici, avec le site qui a donné le score.
"""
from __future__ import annotations

import unicodedata

# sport -> [(mots-clés de ligue, [(nom, url), ...])] ; ("*",) = toutes les ligues du sport (en dernier)
SOURCES: dict[str, list[tuple[tuple[str, ...], list[tuple[str, str]]]]] = {
    "football": [
        (("la liga 2", "segunda", "hypermotion"), [
            ("LaLiga (fiche du match)", "https://www.laliga.com/"),
            ("Última Hora (Majorque)", "https://www.ultimahora.es/deportes/real-mallorca/"),
        ]),
        (("virsliga", "virslīga", "lettonie"), [
            ("Sportacentrs", "https://sportacentrs.com/futbols/virsliga/"),
            ("LSM", "https://www.lsm.lv/"),
        ]),
        (("premier league", "efl", "carabao"), [
            ("Sky Sports", "https://www.skysports.com/"),
            ("ESPN", "https://www.espn.com/soccer/"),
        ]),
        (("argentine", "liga profesional"), [("TyC Sports", "https://www.tycsports.com/")]),
        (("*",), [("ESPN", "https://www.espn.com/soccer/")]),
    ],
    "handball": [
        (("ligue des champions", "champions league"), [
            ("EHF Champions League", "https://ehfcl.eurohandball.com/women/2026-27/"),
            ("RTV SLO (Krim)", "https://www.rtvslo.si/sport/rokomet/"),
            ("Digisport (clubs roumains)", "https://www.digisport.ro/handbal/"),
        ]),
        (("ligue europeenne", "european league"), [
            ("EHF", "https://www.eurohandball.com/"),
            ("news.ro (clubs roumains)", "https://www.news.ro/sport/"),
        ]),
        (("coupe d'europe", "european cup"), [
            ("EHF", "https://www.eurohandball.com/"),
            ("Denník Šport (clubs slovaques)", "https://www.denniksport.sk/hadzana/"),
        ]),
        (("*",), [("EHF", "https://www.eurohandball.com/")]),
    ],
    "basket": [
        (("euroligue", "euroleague"), [("Be Basketball", "https://www.be-basketball.com/league/euroleague-feminine")]),
        (("serie a1", "italie"), [
            ("Lega Basket Femminile", "https://www.legabasketfemminile.it/it/serie-a1/"),
            ("LeccoChannelNews (Costa Masnaga, quarts-temps)", "https://www.leccochannelnews.it/"),
        ]),
        (("elite 2", "pro b"), [
            ("Flashscore (quarts-temps)", "https://www.flashscore.com/basketball/france/elite-2/"),
            ("FFBB (feuille de match)", "https://competitions.ffbb.com/competitions/elit2"),
            ("BeBasket", "https://www.bebasket.fr/ligue/pro-b"),
            ("ICI (France Bleu)", "https://www.ici.fr/"),
        ]),
        (("*",), [("ESPN", "https://www.espn.com/")]),
    ],
    "volley": [
        (("coupe challenge", "challenge cup"), [
            ("RTVC (Tenerife)", "https://rtvc.es/"),
            ("Volleybox", "https://women.volleybox.net/"),
        ]),
        (("sv league", "v.league", "japon"), [("Kitanippon Shimbun (webun)", "https://webun.jp/")]),
        (("*",), [("Volleybox", "https://women.volleybox.net/")]),
    ],
    "mma": [
        (("*",), [
            ("Sherdog (déroulé et rounds)", "https://www.sherdog.com/"),
            ("Tapology", "https://www.tapology.com/fightcenter"),
        ]),
    ],
    "snooker": [
        (("*",), [
            ("snooker.org", "https://www.snooker.org/"),
            ("World Snooker Tour", "https://www.wst.tv/matches/"),
        ]),
    ],
    # Paris joueurs (props) : feuille de match, stat par joueur. ESPN est aussi la source du règlement automatique.
    "props": [
        (("nba",), [
            ("ESPN (box score)", "https://www.espn.com/nba/"),
            ("NBC Sports (fiches joueurs)", "https://www.nbcsports.com/fantasy/basketball/player-news"),
        ]),
        (("nhl",), [("ESPN (box score)", "https://www.espn.com/nhl/")]),
        (("*",), [("ESPN", "https://www.espn.com/")]),
    ],
    "football_americain": [(("*",), [("ESPN", "https://www.espn.com/")])],
}


def _norme(texte: str | None) -> str:
    t = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode()
    return " ".join(t.lower().split())


def ou_chercher(sport: str | None, ligue: str | None) -> list[dict]:
    """Les sites où chercher le score : ceux de la ligue d'abord, puis ceux du sport, sans doublon."""
    ligue_n, out, vus = _norme(ligue), [], set()
    for cles, sites in SOURCES.get(sport or "", []):
        if "*" in cles or any(_norme(c) in ligue_n for c in cles):
            for nom, url in sites:
                if url not in vus:
                    vus.add(url)
                    out.append({"nom": nom, "url": url})
    return out
