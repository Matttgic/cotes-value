"""Décisions prospectives immuables ; aucune migration des prises anciennes.

Un dictionnaire vide signifie « évalué, aucune stratégie retenue ». L'absence
signifie « ancienne prise reconstruite », jamais une décision réelle inventée.
"""
from functools import wraps
from inspect import signature


def appliquer(paris, selection, cle):
    return {id(p) for p in paris if (cle in p['selections_figees']
            if isinstance(p.get('selections_figees'), dict) else id(p) in selection)}


def figer_selecteur(cle):
    def decorer(f):
        @wraps(f)
        def selectionner(paris, *args, **kwargs):
            selection = f(paris, *args, **kwargs)
            # Un début explicite demande un rejeu ; jamais substituer le registre.
            if signature(f).bind_partial(paris, *args, **kwargs).arguments.get('depuis') is not None:
                return selection
            return appliquer(paris, selection, cle)
        return selectionner
    return decorer


def figer_nouveaux(paris, nouveaux):
    """Appel unique avant sauvegarde/envoi, tous les résultats encore inconnus.

    Les dates/prix des prises restent inchangés. Les variantes n'ajoutent aucun
    vote aux convergences. Les refus sont figés par le dictionnaire vide.
    """
    candidats = [p for p in nouveaux if 'selections_figees' not in p]
    if not candidats:
        return
    # Valider tout le lot avant toute écriture : id() n'est qu'une clé en mémoire.
    from collections import Counter
    from datetime import datetime
    objets = {id(p) for p in paris}
    ids = [p.get('id') for p in candidats]
    if any(not isinstance(pid, str) or not pid.strip() for pid in ids):
        raise ValueError("Pari sans identifiant stable : impossible de figer les décisions")
    comptes = Counter(p.get('id') for p in paris if isinstance(p.get('id'), str))
    if len(set(ids)) != len(ids) or any(comptes[pid] != 1 for pid in ids):
        raise ValueError("Identifiant du nouveau pari absent ou dupliqué dans le registre")
    if any(id(p) not in objets for p in candidats):
        raise ValueError("Les nouveaux paris doivent être les objets du registre, pas des copies")
    for p in candidats:
        try:
            decision = datetime.fromisoformat(str(p.get('decide_le')).replace('Z', '+00:00'))
            if decision.tzinfo is None or decision.utcoffset() is None:
                raise ValueError('Date sans fuseau')
        except (TypeError, ValueError) as e:
            raise ValueError("Date de décision absente ou invalide : impossible de figer le pari") from e
    # Imports locaux volontaires : évitent les cycles decisions/convergence/stratégies/laboratoire.
    from .convergence import selections, paris_convergence
    from .strategies_prudentes import selections_prudentes, VARIANTES
    from .laboratoire import REGLES, DEBUT_SUIVI, selectionner
    retenus = selections(paris)
    retenus['convergence'] = paris_convergence(paris, retenus)
    retenus.update(selections_prudentes(paris, bases=retenus))
    retenus.update({'labo:'+r.id: {id(p) for p in selectionner(paris, r, DEBUT_SUIVI)} for r in REGLES})
    from .strategie_jules_v2 import JULES_V2
    versions = {v['cle']: v['version'] for v in VARIANTES}
    versions['jules_v2'] = JULES_V2['version']
    for p in candidats:
        p['selections_figees'] = {cle: {'version': versions.get(cle, '1'), 'decide_le': p['decide_le']}
                                  for cle, ids in retenus.items() if id(p) in ids}
        p['registre_version'] = '1'


REDECISION = "redecision_lecture_posterieure"


def redecider_ouverts(paris, maintenant, depuis_jours=7):
    """Correction unique des refus dus à la règle de fraîcheur à sens unique (corrigée le 19/10/2026).

    Les stratégies refusaient toute référence lue après la cote française, ce qui écartait presque tous les
    paris Betclic, Unibet et PMU (relus moins souvent que Pinnacle). Seuls les paris dont le match n'a pas
    commencé sont revus : la décision ne peut dépendre d'aucun résultat. Elle est recalculée sur les seules
    données de la prise (comme à la prise), ne retire jamais une sélection déjà figée, et n'a lieu qu'une fois
    par pari (marque ``REDECISION``). Retourne le nombre de sélections ajoutées.
    """
    from datetime import datetime, timedelta
    from .laboratoire import heure

    def date(valeur):
        try:
            d = datetime.fromisoformat(str(valeur).replace('Z', '+00:00'))
            return d if d.tzinfo else None
        except ValueError:
            return None

    limite = maintenant - timedelta(days=depuis_jours)
    cibles = [p for p in paris
              if isinstance(p.get('selections_figees'), dict) and not p.get(REDECISION)
              and p.get('statut') == 'en_cours' and date(p.get('decide_le')) is not None
              and (heure(p.get('debut')) or maintenant) > maintenant
              and (heure(p.get('detecte')) or maintenant) >= limite]
    if not cibles:
        return 0
    anciennes = {id(p): p['selections_figees'] for p in cibles}
    for p in cibles:
        del p['selections_figees']
    try:
        figer_nouveaux(paris, cibles)
    except Exception:
        for p in cibles:
            p['selections_figees'] = anciennes[id(p)]
        raise
    ajoutees = 0
    for p in cibles:
        figees = p['selections_figees']
        ajoutees += sum(cle not in anciennes[id(p)] for cle in figees)
        for cle, valeur in anciennes[id(p)].items():
            figees.setdefault(cle, valeur)
        p[REDECISION] = maintenant.isoformat(timespec='seconds')
    return ajoutees
