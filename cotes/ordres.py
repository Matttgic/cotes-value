"""Ordres de pari : ce que vous (ou une IA avec ordinateur) devez jouer, avec ses garde-fous.

Le fichier ``ordres.json`` reprend les alertes du moment avec ce qu'il faut pour parier sans se tromper :
le match exact, le marché, l'issue, la cote minimale acceptable, la mise, l'heure limite et le lien vers
le bookmaker quand il est connu. Ce module ne place aucun pari et ne contient aucun identifiant de compte.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .laboratoire import heure
from .liens import lien_info
from .notifications import empreinte_prix

MISE_EUR = 10.0               # mise de la simulation ; à régler ici avant tout pari réel
TOLERANCE_COTE = 0.03         # on accepte une cote jusqu'à 3 % plus basse que celle relevée
VALIDITE_MIN = 10             # un ordre n'est plus valable 10 minutes après le relevé du prix
AVANT_DEBUT_MIN = 3           # ni dans les 3 dernières minutes avant le coup d'envoi
REGLES = [
    "Jouer seulement si la cote affichée chez le bookmaker est au moins « cote_min » ; sinon abandonner.",
    "Miser exactement « mise » euros, jamais plus. Jamais de dépôt, de crédit, de bonus ni de pari combiné.",
    "Un seul pari par « id » : ne jamais rejouer un id déjà traité, même après une erreur.",
    "Ne pas jouer après « expire_le ».",
    "Le match, le marché, l'issue et la ligne doivent correspondre exactement ; au moindre doute, ne pas jouer.",
    "Arrêter si le solde est inférieur à la mise, ou si le site demande un code, un captcha ou une vérification.",
    "Ne faire aucune autre action sur le compte (retrait, changement de paramètres, offres).",
]


def lien_ordre(a: dict, o: dict) -> dict:
    """Lien de l'alerte (déjà calculé), sinon celui du prix ; ``lien_repli`` : page du sport, match à chercher."""
    if a.get("lien"):
        return {"lien": a["lien"], "lien_repli": bool(a.get("lien_repli"))}
    lien, repli = lien_info({**o, "bookmaker": a.get("bookmaker")})
    return {"lien": lien, "lien_repli": repli}


def construire(flux: dict, actuelles: list[dict], maintenant: datetime | None = None) -> dict:
    """Un ordre par alerte encore valable ; ``flux`` vient de ``notifications.flux``."""
    maintenant = maintenant or datetime.now(timezone.utc)
    par_id = {empreinte_prix(o): o for o in actuelles if isinstance(o, dict)}
    ordres = []
    for a in flux.get("alertes", []):
        o = par_id.get(a.get("id"))
        recue, debut = heure(a.get("collecte_le")), heure(a.get("debut"))
        cote = a.get("cote")
        if not o or not recue or not debut or not isinstance(cote, (int, float)) or isinstance(cote, bool):
            continue
        expire = min(recue + timedelta(minutes=VALIDITE_MIN), debut - timedelta(minutes=AVANT_DEBUT_MIN))
        if expire <= maintenant:
            continue
        ordres.append({
            "id": a["id"], "bookmaker": a.get("bookmaker"), "sport": o.get("sport"), "ligue": o.get("ligue"),
            "domicile": o.get("domicile"), "exterieur": o.get("exterieur"), "debut": debut.isoformat(),
            "marche": o.get("marche"), "periode": o.get("periode"), "ligne": o.get("ligne"), "issue": o.get("issue"),
            "pari": o.get("pari"), "libelle_bookmaker": o.get("libelle_bookmaker"),
            "cote_relevee": cote, "cote_min": round(cote * (1 - TOLERANCE_COTE), 2), "mise": MISE_EUR,
            "mise_kelly": a.get("mise_kelly"),
            "expire_le": expire.isoformat(), "strategies": a.get("labels", []),
            **lien_ordre(a, o),
            "recherche": f'{o.get("domicile")} – {o.get("exterieur")} · {o.get("ligue")}',
        })
    return {"genere_le": maintenant.isoformat(timespec="seconds"), "regles": REGLES,
            "ordres": sorted(ordres, key=lambda x: x["expire_le"])}
