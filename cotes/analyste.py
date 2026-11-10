"""Avis d'analyste d'une courbe de gains, calculé en local à la construction du site.

Pas de modèle de langage, pas d'appel réseau : uniquement les paris déjà réglés de la stratégie
(même coupure, mêmes mises et même ordre que la courbe du bilan). Les seuils sont regroupés dans
``SEUILS`` pour qu'Hugo puisse les revoir sans relire le calcul.

Verdicts, exactement l'un de ces quatre libellés :

- « Trop tôt pour juger » : moins de ``min_paris_regles`` paris réglés, ou moins de ``min_clv``
  CLV mesurées (le test ne porte pas encore sur assez de clôtures) ;
- « Fiable » : profit > 0, bootstrap par match sous ``proba_chance_fiable`` (20 %), CLV moyenne > 0
  sur au moins ``min_clv`` mesures, test unilatéral de cette moyenne (erreur-type groupée par match)
  avec q de Benjamini-Hochberg < ``q_bh_fiable`` parmi les stratégies d'au moins 100 paris, CLV
  positive sur les deux moitiés, et CLV qui reste positive sans les ``part_cotes`` cotes les plus hautes
  (gagnantes et perdantes) ;
- « Chance ou yo-yo » : la CLV elle-même est instable (moitiés de signes opposés, ou elle ne tient
  pas sans les longues cotes), ou bien le profit ressemble au hasard sans CLV significative ;
- « Prometteur mais pas prouvé » : la CLV porte un signal, mais il manque une condition de
  « Fiable » (profit, bootstrap, correction entre stratégies, moitiés ou échantillon de CLV).
"""
from __future__ import annotations

from math import ceil, exp, lgamma, log, sqrt
from random import Random

# Un seul endroit. Défauts volontiers prudents : mieux vaut « Trop tôt » ou « Prometteur »
# qu'un « Fiable » accordé trop vite. Comparaison des probabilités après arrondi à 4 décimales,
# pour que le chiffre affiché et le verdict disent la même chose.
SEUILS = {
    "min_paris_regles": 100,       # en dessous : « Trop tôt pour juger », et hors correction BH
    "proba_chance_fiable": 0.20,   # bootstrap par match : part des tirages dont le profit est ≤ 0
    "proba_chance_yoyo": 0.20,     # à partir de là, un profit positif ressemble encore au hasard
    "min_clv": 100,                # CLV mesurées exigées pour qu'une moyenne positive compte
    "clv_moyenne_min": 0.0,        # fraction : « Fiable » exige une CLV moyenne strictement supérieure
    "q_bh_fiable": 0.05,           # q de Benjamini-Hochberg du test de CLV, entre les stratégies éligibles
    "part_cotes": 0.05,            # part des paris aux cotes les plus hautes retirée (gagnés et perdus)
    "r2_yoyo": 0.25,               # R² du profit cumulé contre l'indice de pari, en dessous : irrégulier
    "sharpe_yoyo": 0.05,           # moyenne / écart-type du P&L par pari, en dessous : peu de pente
    "tirages_bootstrap": 10000,    # rééchantillons de matchs, avec remise
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


def pvalue_clv_matchs(clvs: list[float | None], matchs: list) -> tuple[float | None, float | None, int, int]:
    """Test unilatéral « CLV moyenne > 0 », erreur-type groupée par match.

    La moyenne est celle des paris (chaque CLV mesurée pèse une fois). L'écart-type est celui du
    bootstrap de grappe : les paris d'un même match ne comptent pas comme des essais indépendants.
    Rend (p, moyenne, nombre de CLV, nombre de matchs avec une CLV)."""
    groupes: dict = {}
    for valeur, match in zip(clvs, matchs):
        if valeur is None:
            continue
        groupes.setdefault(match, []).append(valeur)
    if not groupes:
        return None, None, 0, 0
    valeurs = [v for groupe in groupes.values() for v in groupe]
    n, g = len(valeurs), len(groupes)
    moyenne = sum(valeurs) / n
    if g < 2:
        return None, moyenne, n, g
    somme_carres = 0.0
    for groupe in groupes.values():
        ecart = sum(v - moyenne for v in groupe)
        somme_carres += ecart * ecart
    variance = (g / (g - 1)) * somme_carres / (n * n)
    if variance <= 0:
        return (0.0 if moyenne > 0 else 1.0), moyenne, n, g
    return pvalue_student(moyenne / sqrt(variance), g - 1), moyenne, n, g


def benjamini_hochberg(pvals: list[float]) -> list[float]:
    """q-values de Benjamini-Hochberg, même ordre que ``pvals``. Monotones en partant de la plus grande."""
    m = len(pvals)
    if m == 0:
        return []
    ordre = sorted(range(m), key=lambda i: (pvals[i], i))
    brut = [0.0] * m
    for rang, i in enumerate(ordre, start=1):
        brut[i] = pvals[i] * m / rang
    q = [0.0] * m
    courant = 1.0
    for i in reversed(ordre):
        courant = min(courant, brut[i])
        q[i] = min(1.0, courant)
    return q


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


def proba_hasard_matchs(gains: list[float], matchs: list, tirages: int, graine: int) -> float | None:
    """Bootstrap par match : on tire des matchs avec remise, et tous les paris du match suivent.

    La part des tirages dont le profit total est ≤ 0. Un match tiré deux fois compte deux fois."""
    if not gains or tirages < 1:
        return None
    profits: dict = {}
    for gain, match in zip(gains, matchs):
        profits[match] = profits.get(match, 0.0) + gain
    grappes = list(profits.values())
    if all(p > 0 for p in grappes):
        return 0.0
    if all(p <= 0 for p in grappes):
        return 1.0
    rng = Random(graine)
    n = len(grappes)
    sans_profit = 0
    for _ in range(tirages):
        total = 0.0
        for _match in range(n):
            total += grappes[rng.randrange(n)]
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


def moities_clv(clvs: list[float | None]) -> dict:
    """CLV moyenne de la première moitié des paris (ordre de règlement) et de la seconde.

    Un pari sans CLV ne compte pas dans la moyenne, mais il compte dans la coupure. ``memes_signe`` :
    les deux moyennes sont strictement positives, ou toutes les deux strictement négatives."""
    n = len(clvs)
    if n < 2:
        return {"clv_premiere": None, "clv_seconde": None, "memes_signe": None}
    k = n // 2

    def moyenne(partie: list[float | None]) -> float | None:
        valeurs = [c for c in partie if c is not None]
        return sum(valeurs) / len(valeurs) if valeurs else None

    premiere, seconde = moyenne(clvs[:k]), moyenne(clvs[k:])
    meme = None
    if premiere is not None and seconde is not None:
        meme = (premiere > 0 and seconde > 0) or (premiere < 0 and seconde < 0)
    return {"clv_premiere": premiere, "clv_seconde": seconde, "memes_signe": meme}


def clv_sans_hautes_cotes(cotes: list[float], clvs: list[float | None], part: float) -> dict:
    """CLV moyenne une fois retirés les paris aux cotes les plus hautes, gagnés comme perdus.

    Dépendant : la CLV complète est > 0, et la CLV restante est absente ou ≤ 0. Les ex æquo se
    départagent par l'indice du pari."""
    n = len(cotes)
    mesurees = [c for c in clvs if c is not None]
    pleine = sum(mesurees) / len(mesurees) if mesurees else None
    if n == 0:
        return {"clv_sans_cotes": pleine, "cotes_retirees": 0, "depend": False}
    k = min(n, max(1, ceil(part * n)))
    retires = set(sorted(range(n), key=lambda i: (-cotes[i], i))[:k])
    reste = [clvs[i] for i in range(n) if i not in retires and clvs[i] is not None]
    reduite = sum(reste) / len(reste) if reste else None
    depend = bool(pleine is not None and pleine > 0 and (reduite is None or reduite <= 0))
    return {"clv_sans_cotes": reduite, "cotes_retirees": k, "depend": depend}


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
        if n < seuils["min_paris_regles"]:
            phrases = [f"Seulement {n} paris réglés : il en faut au moins {seuils['min_paris_regles']} pour juger."]
        else:
            phrases = [f"Seulement {d['clv_n']} CLV mesurées : il en faut au moins {seuils['min_clv']} pour juger."]
        if d["gain"] > 0:
            phrases.append("Le gain affiché peut encore n'être qu'une bonne série.")
        elif d["gain"] < 0:
            phrases.append("La perte affichée peut encore n'être qu'un mauvais départ.")
        else:
            phrases.append("La courbe est trop courte pour séparer une méthode du hasard.")
        if d["clv_n"] == 0 and n >= seuils["min_paris_regles"]:
            phrases.append("Aucune CLV mesurée : on ne sait pas si les cotes battaient la clôture.")
        elif len(phrases) < 3:
            phrases.append("On attend un suivi plus long avant de trancher.")
        return phrases[:3]
    if verdict == FIABLE:
        return [
            f"CLV moyenne {_pct(d['clv_moyenne'])}, et le test par match reste sous 5 % une fois les stratégies comparées (q { _q(d.get('q_bh')) }).",
            f"{n} paris réglés, et {_phrase_hasard(d['proba_chance'])}.",
            "La CLV est positive sur les deux moitiés, et elle le reste sans les cotes les plus hautes.",
        ]
    if verdict == CHANCE:
        phrases = []
        c1, c2 = d.get("clv_premiere"), d.get("clv_seconde")
        if c1 is not None and c2 is not None and c1 * c2 < 0:
            phrases.append("La CLV change de signe entre les deux moitiés du suivi : la courbe fait le yo-yo.")
        if d["depend_grosses_cotes"]:
            phrases.append("Sans les cotes les plus hautes, gagnantes comme perdantes, la CLV n'est plus positive.")
        if d["gain"] > 0 and d["proba_chance"] is not None and d["proba_chance"] >= seuils["proba_chance_yoyo"]:
            phrases.append(f"Le profit disparaît dans {_pct(d['proba_chance'])} des tirages par match : il ressemble à de la chance.")
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
    phrases = [f"{n} paris réglés et {_eur(d['gain'])} de gain, sans que la CLV soit encore une preuve."]
    if d["gain"] <= 0 or (d["proba_chance"] is not None and d["proba_chance"] >= seuils["proba_chance_fiable"]):
        phrases.append("Le profit n'est pas assez net : la CLV peut porter un signal que les euros n'ont pas encore confirmé.")
    if d.get("q_bh") is not None and d["q_bh"] >= seuils["q_bh_fiable"]:
        phrases.append(f"La CLV moyenne est de {_pct(d['clv_moyenne'])}, mais le test corrigé (q {_q(d['q_bh'])}) ne passe pas 5 %.")
    elif d["clv_n"] < seuils["min_clv"] or d["clv_moyenne"] is None or d["clv_moyenne"] <= seuils["clv_moyenne_min"]:
        phrases.append("La CLV moyenne n'est pas assez établie pour confirmer un avantage sur la clôture.")
    c1, c2 = d.get("clv_premiere"), d.get("clv_seconde")
    if not (c1 is not None and c1 > 0 and c2 is not None and c2 > 0):
        phrases.append("Les deux moitiés du suivi n'ont pas toutes les deux une CLV positive.")
    if len(phrases) < 2:
        phrases.append("On garde la courbe sous les yeux, sans la traiter comme une méthode sûre.")
    return phrases[:3]


def _q(q: float | None) -> str:
    if q is None:
        return "—"
    if 0 < q < 0.0005:
        return "< 0,001"
    return f"{q:.3f}".replace(".", ",")


def _arrondi_ratio(x: float | None, decimales: int = 4) -> float | None:
    return None if x is None else round(x, decimales)


def _details_serie(gains: list[float], mises: list[float], cotes: list[float],
                   clvs: list[float | None], matchs: list, instants: list | None, cfg: dict) -> dict:
    n = len(gains)
    p_brut, moyenne, n_clv, n_matchs = pvalue_clv_matchs(clvs, matchs)
    proba = proba_hasard_matchs(gains, matchs, int(cfg["tirages_bootstrap"]), int(cfg["graine"]))
    baisse = repli(gains, instants)
    moitie = moities_clv(clvs)
    gros = clv_sans_hautes_cotes(cotes, clvs, cfg["part_cotes"])
    return {
        "paris_regles": n,
        "gain": round(sum(gains), 2),
        "roi": _arrondi_ratio(_roi(gains, mises)),
        "proba_chance": _arrondi_ratio(proba),
        "tirages": int(cfg["tirages_bootstrap"]) if n else 0,
        "graine": int(cfg["graine"]),
        "clv_moyenne": _arrondi_ratio(moyenne),
        "clv_n": n_clv,
        "clv_matchs": n_matchs,
        "pvalue_clv": None if p_brut is None else p_brut,
        "q_bh": None,
        "drawdown_max": baisse["max"],
        "drawdown_recupere": baisse["recupere"],
        "drawdown_paris": baisse["paris"],
        "drawdown_jours": baisse["jours"],
        "r2": _arrondi_ratio(r_carre(gains), 3),
        "sharpe": _arrondi_ratio(ratio_sharpe(gains), 3),
        "clv_premiere": _arrondi_ratio(moitie["clv_premiere"]),
        "clv_seconde": _arrondi_ratio(moitie["clv_seconde"]),
        "memes_signe": moitie["memes_signe"],
        "clv_sans_cotes": _arrondi_ratio(gros["clv_sans_cotes"]),
        "cotes_retirees": gros["cotes_retirees"],
        "depend_grosses_cotes": gros["depend"],
    }


def _clv_etablie(details: dict, cfg: dict) -> bool:
    """CLV moyenne > 0, assez de mesures, et q de Benjamini-Hochberg sous le seuil."""
    q = details.get("q_bh")
    return bool(details["clv_n"] >= cfg["min_clv"]
                and details["clv_moyenne"] is not None
                and details["clv_moyenne"] > cfg["clv_moyenne_min"]
                and q is not None and q < cfg["q_bh_fiable"])


def _verdict(details: dict, cfg: dict) -> str:
    """Le verdict lit les chiffres publiés. ``q_bh`` vaut la p brute quand la stratégie est jugée seule."""
    n = details["paris_regles"]
    # Moins de 100 paris, ou moins de 100 CLV mesurées : le test n'a pas de quoi conclure.
    if n < cfg["min_paris_regles"] or details["clv_n"] < cfg["min_clv"]:
        return TROP_TOT
    c1, c2 = details["clv_premiere"], details["clv_seconde"]
    clv_ok = _clv_etablie(details, cfg)
    moities_ok = c1 is not None and c1 > 0 and c2 is not None and c2 > 0
    robuste = details["clv_sans_cotes"] is not None and details["clv_sans_cotes"] > 0
    profit_ok = (details["gain"] > 0 and details["proba_chance"] is not None
                 and details["proba_chance"] < cfg["proba_chance_fiable"])
    if clv_ok and moities_ok and robuste and profit_ok:
        return FIABLE
    # La CLV change de signe ou ne tient qu'aux longues cotes : ce n'est pas un signal stable.
    if (c1 is not None and c2 is not None and c1 * c2 < 0) or details["depend_grosses_cotes"]:
        return CHANCE
    # Sans CLV établie, un profit négatif, trop fragile ou trop irrégulier ressemble au hasard.
    if not clv_ok and (
            details["gain"] <= 0
            or (details["gain"] > 0 and details["proba_chance"] is not None
                and details["proba_chance"] >= cfg["proba_chance_yoyo"])
            or (details["r2"] is not None and details["sharpe"] is not None
                and details["r2"] < cfg["r2_yoyo"] and details["sharpe"] < cfg["sharpe_yoyo"])):
        return CHANCE
    return PROMETTEUR


def _publier(details: dict, cfg: dict) -> dict:
    verdict = _verdict(details, cfg)
    if details["pvalue_clv"] is not None:
        details["pvalue_clv"] = round(details["pvalue_clv"], 6)
    if details["q_bh"] is not None:
        details["q_bh"] = round(details["q_bh"], 6)
    return {"verdict": verdict, "raisons": _raisons(verdict, details, cfg), "details": details}


def analyser_serie(gains: list[float], mises: list[float] | None = None,
                   cotes: list[float] | None = None, clvs: list[float | None] | None = None,
                   instants: list | None = None, matchs: list | None = None,
                   seuils: dict | None = None) -> dict:
    """Avis d'une série seule (q = p : une seule stratégie dans la correction)."""
    cfg = _seuils(seuils)
    n = len(gains)
    mises = list(mises) if mises is not None else [10.0] * n
    cotes = list(cotes) if cotes is not None else [2.0] * n
    clvs = list(clvs) if clvs is not None else [None] * n
    if len(mises) != n or len(cotes) != n or len(clvs) != n:
        raise ValueError("gains, mises, cotes et clvs doivent avoir la même longueur")
    if matchs is None:
        matchs = list(range(n))
    elif len(matchs) != n:
        raise ValueError("matchs doit avoir la même longueur que gains")
    details = _details_serie(gains, mises, cotes, clvs, matchs, instants, cfg)
    # Famille d'une seule stratégie : la correction BH ne change pas la p.
    if details["paris_regles"] >= cfg["min_paris_regles"] and details["pvalue_clv"] is not None:
        details["q_bh"] = details["pvalue_clv"]
    return _publier(details, cfg)


def _serie_reglee(rows: list[dict], cutoff: str) -> dict:
    """Paris réglés connus avant ``cutoff``, dans l'ordre de la courbe, groupés par match."""
    from cotes.evenements import identites
    from cotes.laboratoire import clv, heure, mise_de, regles_avant
    from cotes.reglement import gain

    limite = heure(cutoff)
    regles = regles_avant(rows, limite) if limite is not None else []
    regles.sort(key=lambda p: (heure(p["regle_le"]), str(p.get("id"))))
    liens = identites(regles)
    gains, mises, cotes, clvs, instants, matchs = [], [], [], [], [], []
    for p in regles:
        mise = mise_de(p)
        gains.append(gain(p["statut"], mise, p["cote"]))
        mises.append(mise)
        cote = p.get("cote")
        cotes.append(float(cote) if isinstance(cote, (int, float)) and not isinstance(cote, bool) else 0.0)
        clvs.append(clv(p))
        instants.append(heure(p.get("regle_le")))
        matchs.append(liens.get(id(p), ("ligne", p.get("id"))))
    return {"gains": gains, "mises": mises, "cotes": cotes, "clvs": clvs,
            "instants": instants, "matchs": matchs}


def annoter_avis(series: list[list[dict]], cutoff: str, seuils: dict | None = None) -> list[dict]:
    """Avis de plusieurs stratégies d'un coup : la correction BH se calcule sur celles d'au moins 100 paris.

    ``series`` : une liste de paris par stratégie, dans l'ordre du classement. L'ordre du résultat est le même."""
    cfg = _seuils(seuils)
    details = []
    for rows in series:
        s = _serie_reglee(rows, cutoff)
        details.append(_details_serie(s["gains"], s["mises"], s["cotes"], s["clvs"], s["matchs"],
                                      s["instants"], cfg))
    eligibles = [i for i, d in enumerate(details)
                 if d["paris_regles"] >= cfg["min_paris_regles"] and d["pvalue_clv"] is not None]
    qvals = benjamini_hochberg([details[i]["pvalue_clv"] for i in eligibles])
    for i, q in zip(eligibles, qvals):
        details[i]["q_bh"] = q
    return [_publier(d, cfg) for d in details]


def avis_des_paris(rows: list[dict], cutoff: str) -> dict:
    """Avis d'une stratégie seule. Le site passe par ``annoter_avis`` pour corriger entre stratégies."""
    return annoter_avis([rows], cutoff)[0]


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
