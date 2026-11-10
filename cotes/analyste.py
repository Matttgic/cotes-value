"""Avis d'analyste d'une courbe de gains, calculé en local à la construction du site.

Pas de modèle de langage, pas d'appel réseau : uniquement les paris déjà réglés de la stratégie
(même coupure, mêmes mises et même ordre que la courbe du bilan). Les seuils sont regroupés dans
``SEUILS`` pour qu'Hugo puisse les revoir sans relire le calcul.

Verdicts, exactement l'un de ces quatre libellés :

- « Trop tôt pour juger » : moins de ``min_paris_regles`` paris réglés ;
- « Fiable » : profit > 0, probabilité bootstrap que ce profit soit ≤ 0 sous ``proba_chance_fiable``,
  CLV moyenne strictement positive sur assez de mesures, les deux moitiés du suivi gagnantes, et le
  ROI qui reste positif sans les plus longues cotes gagnantes ni les plus gros gains ;
- « Chance ou yo-yo » : suivi assez long, et au moins un signal faible (moitiés de signes opposés,
  profit porté par quelques grosses cotes, profit compatible avec le hasard, courbe très irrégulière,
  ou profit ≤ 0 — parmi les quatre formules, ce n'est pas un avantage à suivre) ;
- « Prometteur mais pas prouvé » : le reste (souvent un gain encore trop proche du hasard).
"""
from __future__ import annotations

from math import ceil, exp, lgamma, log, sqrt
from random import Random

# Un seul endroit. Défauts volontiers prudents : mieux vaut « Trop tôt » ou « Prometteur »
# qu'un « Fiable » accordé trop vite. Comparaison des probabilités après arrondi à 4 décimales,
# pour que le chiffre affiché et le verdict disent la même chose.
SEUILS = {
    "min_paris_regles": 100,       # en dessous : « Trop tôt pour juger », quel que soit le gain
    "proba_chance_fiable": 0.05,   # part des rééchantillons dont le profit est ≤ 0
    "proba_chance_yoyo": 0.20,     # au-dessus, un profit positif ressemble encore au hasard
    "min_clv": 30,                 # CLV mesurées exigées pour qu'une moyenne positive compte
    "clv_moyenne_min": 0.0,        # fraction : « Fiable » exige une CLV moyenne strictement supérieure
    "part_cotes_gagnantes": 0.05,  # part des paris gagnants aux cotes les plus hautes, retirée du ROI
    "nb_gros_gains": 3,            # plus gros gains retirés pour le second ROI
    "r2_yoyo": 0.25,               # R² du profit cumulé contre l'indice de pari, en dessous : irrégulier
    "sharpe_yoyo": 0.05,           # moyenne / écart-type du P&L par pari, en dessous : peu de pente
    "tirages_bootstrap": 1000,     # rééchantillons avec remise, même taille que la série
    "graine": 20261110,            # graine fixe : le même suivi redonne le même avis
}

FIABLE = "Fiable"
PROMETTEUR = "Prometteur mais pas prouvé"
CHANCE = "Chance ou yo-yo"
TROP_TOT = "Trop tôt pour juger"
VERDICTS = (FIABLE, PROMETTEUR, CHANCE, TROP_TOT)


def _seuils(seuils: dict | None) -> dict:
    return {**SEUILS, **(seuils or {})}


def _betacf(a: float, b: float, x: float) -> float:
    """Fraction continue de la bêta incomplète (Numerical Recipes)."""
    max_iter, eps, fpmin = 200, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Bêta incomplète régularisée I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_prefix = lgamma(a + b) - lgamma(a) - lgamma(b) + a * log(x) + b * log(1.0 - x)
    prefix = exp(ln_prefix)
    if x < (a + 1.0) / (a + b + 2.0):
        return prefix * _betacf(a, b, x) / a
    return 1.0 - prefix * _betacf(b, a, 1.0 - x) / b


def pvalue_student(t: float, df: int) -> float:
    """p unilatérale P(T ≥ t) sous H0, loi de Student à ``df`` degrés de liberté."""
    if df < 1:
        raise ValueError("degrés de liberté")
    x = df / (df + t * t)
    deux = betainc(df / 2.0, 0.5, x)
    p = deux / 2.0 if t >= 0 else 1.0 - deux / 2.0
    return min(1.0, max(0.0, p))


def pvalue_clv(valeurs: list[float]) -> float | None:
    """t-test unilatéral : la CLV moyenne est-elle > 0 ? None s'il y a moins de deux mesures.

    Écart-type nul : 0 si la moyenne est > 0, 1 sinon (rien à départager du zéro)."""
    n = len(valeurs)
    if n < 2:
        return None
    moyenne = sum(valeurs) / n
    variance = sum((v - moyenne) ** 2 for v in valeurs) / (n - 1)
    if variance <= 0:
        return 0.0 if moyenne > 0 else 1.0
    t = moyenne / sqrt(variance / n)
    return pvalue_student(t, n - 1)


def proba_hasard(gains: list[float], tirages: int, graine: int) -> float | None:
    """Part des rééchantillons (remise, même taille, graine fixe) dont le profit total est ≤ 0.

    C'est la probabilité que ce profit soit un coup de chance au sens du bootstrap : si tous les
    paris gagnent, elle vaut 0 ; s'ils perdent tous, elle vaut 1. None sur une série vide."""
    n = len(gains)
    if n == 0 or tirages < 1:
        return None
    if all(g > 0 for g in gains):
        return 0.0
    if all(g <= 0 for g in gains):
        return 1.0
    rng = Random(graine)
    sans_profit = 0
    for _ in range(tirages):
        total = 0.0
        for _pari in range(n):
            total += gains[rng.randrange(n)]
        if total <= 0:
            sans_profit += 1
    return sans_profit / tirages


def repli(gains: list[float], instants: list | None = None) -> dict:
    """Plus fort repli du profit cumulé, et le temps pour retrouver ce plus haut.

    ``paris`` : nombre de paris entre le sommet et le nouveau plus haut (le sommet de départ, avant
    tout pari, compte comme indice −1). ``jours`` : du pari du sommet au pari du nouveau plus haut,
    ou None si le sommet est le départ ou si une date manque. ``recupere`` faux si le plus haut
    n'est pas revenu."""
    if not gains:
        return {"max": 0.0, "recupere": True, "paris": 0, "jours": 0.0}
    cumul = pic = 0.0
    i_pic = -1
    max_dd = 0.0
    i_pic_dd = -1
    i_creux = -1
    valeur_pic = 0.0
    for i, g in enumerate(gains):
        cumul += g
        if cumul >= pic - 1e-9:
            pic = cumul
            i_pic = i
        else:
            dd = pic - cumul
            if dd > max_dd + 1e-9:
                max_dd = dd
                i_pic_dd = i_pic
                i_creux = i
                valeur_pic = pic
    if max_dd <= 1e-9:
        return {"max": 0.0, "recupere": True, "paris": 0, "jours": 0.0}
    cumul = 0.0
    i_recup = None
    for i, g in enumerate(gains):
        cumul += g
        if i > i_creux and cumul >= valeur_pic - 1e-9:
            i_recup = i
            break
    if i_recup is None:
        return {"max": round(max_dd, 2), "recupere": False, "paris": None, "jours": None}
    jours = None
    if instants and i_pic_dd >= 0 and i_recup < len(instants):
        debut, fin = instants[i_pic_dd], instants[i_recup]
        if debut is not None and fin is not None:
            jours = round((fin - debut).total_seconds() / 86400, 1)
    return {"max": round(max_dd, 2), "recupere": True, "paris": i_recup - i_pic_dd, "jours": jours}


def r_carre(gains: list[float]) -> float | None:
    """R² de la régression du profit cumulé sur l'indice du pari (0, 1, 2…). None sous 2 paris."""
    n = len(gains)
    if n < 2:
        return None
    y = []
    cumul = 0.0
    for g in gains:
        cumul += g
        y.append(cumul)
    moy_x = (n - 1) / 2.0
    moy_y = sum(y) / n
    sxx = sum((i - moy_x) ** 2 for i in range(n))
    syy = sum((v - moy_y) ** 2 for v in y)
    if sxx <= 0:
        return None
    if syy <= 1e-12:
        return 1.0
    sxy = sum((i - moy_x) * (v - moy_y) for i, v in enumerate(y))
    return sxy * sxy / (sxx * syy)


def ratio_sharpe(gains: list[float]) -> float | None:
    """Moyenne / écart-type (n − 1) du P&L par pari. None si moins de 2 paris ou écart-type nul."""
    n = len(gains)
    if n < 2:
        return None
    moyenne = sum(gains) / n
    variance = sum((g - moyenne) ** 2 for g in gains) / (n - 1)
    if variance <= 0:
        return None
    return moyenne / sqrt(variance)


def _roi(gains: list[float], mises: list[float]) -> float | None:
    mise = sum(mises)
    if mise <= 0 or not gains:
        return None
    return sum(gains) / mise


def moities(gains: list[float], mises: list[float]) -> dict:
    """ROI de la première moitié des paris (ordre de règlement) et de la seconde.

    ``memes_signe`` : les deux ROI sont strictement positifs, ou tous les deux strictement négatifs.
    None s'il n'y a pas de quoi couper."""
    n = len(gains)
    if n < 2 or len(mises) != n:
        return {"roi_premiere": None, "roi_seconde": None, "memes_signe": None}
    k = n // 2
    premiere, seconde = _roi(gains[:k], mises[:k]), _roi(gains[k:], mises[k:])
    meme = None
    if premiere is not None and seconde is not None:
        meme = (premiere > 0 and seconde > 0) or (premiere < 0 and seconde < 0)
    return {"roi_premiere": premiere, "roi_seconde": seconde, "memes_signe": meme}


def dependance_grosses_cotes(gains: list[float], mises: list[float], cotes: list[float],
                             part: float, nb_gains: int) -> dict:
    """ROI une fois retirés les paris gagnants aux plus hautes cotes, puis les plus gros gains.

    Dépendant : le ROI complet est > 0, et l'un des deux ROI réduits est absent ou ≤ 0.
    Les ex æquo se départagent par le gain puis par l'indice, pour que le retrait soit stable."""
    n = len(gains)
    plein = _roi(gains, mises)
    gagnants = [i for i in range(n) if gains[i] > 1e-9]
    if not gagnants:
        return {"roi_sans_cotes": plein, "roi_sans_gains": plein, "cotes_retirees": 0,
                "gains_retires": 0, "depend": False}

    def sans(indices: list[int], nombre: int) -> tuple[float | None, int]:
        if nombre <= 0:
            return plein, 0
        nombre = min(nombre, len(indices))
        retires = set(indices[:nombre])
        garde_g = [g for i, g in enumerate(gains) if i not in retires]
        garde_m = [m for i, m in enumerate(mises) if i not in retires]
        return _roi(garde_g, garde_m), nombre

    par_cote = sorted(gagnants, key=lambda i: (-cotes[i], -gains[i], i))
    par_gain = sorted(gagnants, key=lambda i: (-gains[i], -cotes[i], i))
    k_cotes = max(1, ceil(part * len(gagnants)))
    roi_cotes, n_cotes = sans(par_cote, k_cotes)
    roi_gains, n_gains = sans(par_gain, nb_gains)
    depend = bool(plein is not None and plein > 0 and (
        roi_cotes is None or roi_cotes <= 0 or roi_gains is None or roi_gains <= 0))
    return {"roi_sans_cotes": roi_cotes, "roi_sans_gains": roi_gains, "cotes_retirees": n_cotes,
            "gains_retires": n_gains, "depend": depend}


def _pct(x: float | None) -> str:
    if x is None:
        return "—"
    p = 100 * x
    if 0 < abs(p) < 0.05:
        return "moins de 0,1 %"
    return f"{p:.1f}".replace(".", ",") + " %"


def _phrase_hasard(proba: float | None) -> str:
    if proba == 0:
        return "aucun tirage au hasard n'efface le profit"
    if proba is None:
        return "le poids du hasard n'a pas été mesuré"
    return f"un tirage au hasard efface le profit dans {_pct(proba)} des cas"


def _eur(x: float) -> str:
    n = round(x)
    return f"+{n} €" if n > 0 else f"{n} €"


def _raisons(verdict: str, d: dict, seuils: dict) -> list[str]:
    """Deux ou trois phrases, dans l'ordre du signal le plus parlant."""
    n = d["paris_regles"]
    if verdict == TROP_TOT:
        phrases = [f"Seulement {n} paris réglés : il en faut au moins {seuils['min_paris_regles']} pour juger."]
        if d["gain"] > 0:
            phrases.append("Le gain affiché peut encore n'être qu'une bonne série.")
        elif d["gain"] < 0:
            phrases.append("La perte affichée peut encore n'être qu'un mauvais départ.")
        else:
            phrases.append("La courbe est trop courte pour séparer une méthode du hasard.")
        if d["clv_n"] == 0:
            phrases.append("Aucune CLV mesurée : on ne sait pas si les cotes battaient la clôture.")
        elif len(phrases) < 3:
            phrases.append("On attend un suivi plus long avant de trancher.")
        return phrases[:3]
    if verdict == FIABLE:
        return [
            f"{n} paris réglés, et {_phrase_hasard(d['proba_chance'])}.",
            f"La CLV moyenne est de {_pct(d['clv_moyenne'])} : les cotes prises battaient la clôture.",
            "Les deux moitiés du suivi gagnent, et le résultat tient encore sans les plus grosses cotes.",
        ]
    if verdict == CHANCE:
        phrases = []
        r1, r2 = d["roi_premiere"], d["roi_seconde"]
        if r1 is not None and r2 is not None and r1 * r2 < 0:
            phrases.append("Une moitié du suivi gagne et l'autre perd : la courbe fait le yo-yo.")
        if d["depend_grosses_cotes"]:
            phrases.append("Sans les plus gros gains ou les plus longues cotes gagnantes, le ROI n'est plus positif.")
        if d["gain"] > 0 and d["proba_chance"] is not None and d["proba_chance"] >= seuils["proba_chance_yoyo"]:
            phrases.append(f"Le profit disparaît dans {_pct(d['proba_chance'])} des tirages : il ressemble à de la chance.")
        if d["gain"] <= 0:
            phrases.append("Le suivi est en perte : la courbe ne montre pas une méthode gagnante.")
        if d["r2"] is not None and d["r2"] < seuils["r2_yoyo"]:
            phrases.append("Le profit cumulé ne suit pas une pente régulière.")
        if len(phrases) < 2:
            if d["drawdown_recupere"] is False:
                phrases.append(f"Le repli maximal ({_eur(-d['drawdown_max'])}) n'a pas été rattrapé.")
            else:
                phrases.append(f"Repli maximal de {_eur(-d['drawdown_max'])}, sur {n} paris réglés.")
        if len(phrases) < 2:
            phrases.append("Rien ici ne permet de suivre cette courbe comme une méthode.")
        return phrases[:3]
    phrases = [f"{n} paris réglés et {_eur(d['gain'])} de gain, sans que ce soit encore une preuve."]
    if d["proba_chance"] is not None and d["proba_chance"] >= seuils["proba_chance_fiable"]:
        phrases.append(f"Le profit disparaît encore dans {_pct(d['proba_chance'])} des tirages : au-dessus du seuil de {_pct(seuils['proba_chance_fiable'])}.")
    if d["clv_n"] < seuils["min_clv"] or d["clv_moyenne"] is None or d["clv_moyenne"] <= seuils["clv_moyenne_min"]:
        phrases.append("La CLV moyenne n'est pas assez établie pour confirmer un avantage sur la clôture.")
    r1, r2 = d["roi_premiere"], d["roi_seconde"]
    if not (r1 is not None and r1 > 0 and r2 is not None and r2 > 0):
        phrases.append("Les deux moitiés du suivi ne sont pas toutes les deux gagnantes.")
    if len(phrases) < 2:
        phrases.append("On garde la courbe sous les yeux, sans la traiter comme une méthode sûre.")
    return phrases[:3]


def _arrondi_ratio(x: float | None, decimales: int = 4) -> float | None:
    return None if x is None else round(x, decimales)


def analyser_serie(gains: list[float], mises: list[float] | None = None,
                   cotes: list[float] | None = None, clvs: list[float | None] | None = None,
                   instants: list | None = None, seuils: dict | None = None) -> dict:
    """Avis sur une série déjà ordonnée (un pari réglé par ligne, dans l'ordre du graphique)."""
    cfg = _seuils(seuils)
    n = len(gains)
    mises = list(mises) if mises is not None else [10.0] * n
    cotes = list(cotes) if cotes is not None else [2.0] * n
    if len(mises) != n or len(cotes) != n:
        raise ValueError("gains, mises et cotes doivent avoir la même longueur")
    clv_mesurees = [c for c in (clvs or []) if c is not None]
    proba = proba_hasard(gains, int(cfg["tirages_bootstrap"]), int(cfg["graine"]))
    if proba is not None:
        proba = round(proba, 4)
    baisse = repli(gains, instants)
    moitie = moities(gains, mises)
    gros = dependance_grosses_cotes(gains, mises, cotes, cfg["part_cotes_gagnantes"], int(cfg["nb_gros_gains"]))
    r2 = r_carre(gains)
    sharpe = ratio_sharpe(gains)
    clv_moy = sum(clv_mesurees) / len(clv_mesurees) if clv_mesurees else None
    p_clv = pvalue_clv(clv_mesurees)
    gain = sum(gains)
    details = {
        "paris_regles": n,
        "gain": round(gain, 2),
        "roi": _arrondi_ratio(_roi(gains, mises)),
        "proba_chance": proba,
        "tirages": int(cfg["tirages_bootstrap"]) if n else 0,
        "graine": int(cfg["graine"]),
        "clv_moyenne": _arrondi_ratio(clv_moy),
        "clv_n": len(clv_mesurees),
        "pvalue_clv": _arrondi_ratio(p_clv),
        "drawdown_max": baisse["max"],
        "drawdown_recupere": baisse["recupere"],
        "drawdown_paris": baisse["paris"],
        "drawdown_jours": baisse["jours"],
        "r2": _arrondi_ratio(r2, 3),
        "sharpe": _arrondi_ratio(sharpe, 3),
        "roi_premiere": _arrondi_ratio(moitie["roi_premiere"]),
        "roi_seconde": _arrondi_ratio(moitie["roi_seconde"]),
        "memes_signe": moitie["memes_signe"],
        "roi_sans_cotes": _arrondi_ratio(gros["roi_sans_cotes"]),
        "roi_sans_gains": _arrondi_ratio(gros["roi_sans_gains"]),
        "cotes_retirees": gros["cotes_retirees"],
        "gains_retires": gros["gains_retires"],
        "depend_grosses_cotes": gros["depend"],
    }
    # Le verdict lit les chiffres publiés (déjà arrondis), pas une seconde fois les bruts.
    r1, r2 = details["roi_premiere"], details["roi_seconde"]
    if n < cfg["min_paris_regles"]:
        verdict = TROP_TOT
    elif (details["gain"] > 0 and proba is not None and proba < cfg["proba_chance_fiable"]
          and details["clv_n"] >= cfg["min_clv"]
          and details["clv_moyenne"] is not None and details["clv_moyenne"] > cfg["clv_moyenne_min"]
          and r1 is not None and r1 > 0 and r2 is not None and r2 > 0
          and not details["depend_grosses_cotes"]):
        verdict = FIABLE
    elif ((r1 is not None and r2 is not None and r1 * r2 < 0)
          or details["depend_grosses_cotes"]
          or (details["gain"] > 0 and proba is not None and proba >= cfg["proba_chance_yoyo"])
          or (details["r2"] is not None and details["sharpe"] is not None
              and details["r2"] < cfg["r2_yoyo"] and details["sharpe"] < cfg["sharpe_yoyo"])
          or details["gain"] <= 0):
        verdict = CHANCE
    else:
        verdict = PROMETTEUR
    return {"verdict": verdict, "raisons": _raisons(verdict, details, cfg), "details": details}


def avis_des_paris(rows: list[dict], cutoff: str) -> dict:
    """Avis des paris réglés connus avant ``cutoff``, dans l'ordre de la courbe du bilan."""
    from cotes.laboratoire import clv, heure, mise_de, regles_avant
    from cotes.reglement import gain

    limite = heure(cutoff)
    regles = regles_avant(rows, limite) if limite is not None else []
    regles.sort(key=lambda p: (heure(p["regle_le"]), str(p.get("id"))))
    gains, mises, cotes, clvs, instants = [], [], [], [], []
    for p in regles:
        mise = mise_de(p)
        gains.append(gain(p["statut"], mise, p["cote"]))
        mises.append(mise)
        cote = p.get("cote")
        cotes.append(float(cote) if isinstance(cote, (int, float)) and not isinstance(cote, bool) else 0.0)
        clvs.append(clv(p))
        instants.append(heure(p.get("regle_le")))
    return analyser_serie(gains, mises, cotes, clvs, instants)


def _note(ligne: dict):
    stats = ligne.get("stats") or {}
    note = stats.get("note")
    if not isinstance(note, dict):
        return None
    total = note.get("total")
    if isinstance(total, bool) or not isinstance(total, (int, float)):
        return None
    return float(total)


def trier_par_note(lignes: list[dict]) -> list[dict]:
    """Meilleure note d'abord. À égalité : plus de paris réglés, puis le nom, puis l'ordre d'origine.

    Sans note (moins de 10 matchs, ou note absente) : tout à la fin, avec le même départage."""
    def cle(item):
        index, ligne = item
        stats = ligne.get("stats") or {}
        note = _note(ligne)
        regles = stats.get("regles") or 0
        if isinstance(regles, bool) or not isinstance(regles, (int, float)):
            regles = 0
        nom = str(ligne.get("nom") or "").casefold()
        return (note is None, -(note or 0.0), -regles, nom, index)
    return [ligne for _, ligne in sorted(enumerate(lignes), key=cle)]
