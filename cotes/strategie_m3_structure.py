"""Variante prospective : trois familles, aucune substitution d'une prise passée."""
from itertools import groupby
from .laboratoire import heure
from .strategie_m3 import motif_refus_m3
from .decisions import appliquer

M3_STRUCTURE = {
    'cle': 'm3_structure', 'nom': 'M3 · Max 3/match', 'court': 'M3 Max 3',
    'debut': '2026-10-17T01:00:00+00:00',  # 03 h Paris, lancement annoncé avant les prises
    'version': '1', 'mise': 10, 'prospectif_seulement': True,
    'regles': 'Critères M3 · 1 vainqueur + 1 handicap + 1 total (match ou équipe) · max 30 €/événement · meilleur edge du lot disponible',
}


def famille_marche(p):
    return {'VAINQUEUR':'vainqueur','HANDICAP':'handicap','TOTAL':'total','TOTAL_EXT':'total'}.get(p.get('marche'))


def paris_m3_structure(paris, depuis=None):
    # Cette variante n'a pas de bilan rétrospectif officiel.
    from .strategies_prudentes import _cles_match
    depart = heure(M3_STRUCTURE['debut'])
    eligibles = {id(p) for p in paris if motif_refus_m3(p) is None}
    parents, utilises, selection = {}, {}, set()
    def racine(c):
        parents.setdefault(c,c)
        r=c
        while parents[r]!=r:
            r=parents[r]
        while parents[c]!=c:
            suivant=parents[c];parents[c]=r;c=suivant
        return r
    def instant(p):
        return heure(p.get('lot_decision') or p.get('decide_le') or p.get('detecte'))
    rows=sorted((p for p in paris if p.get('reference')!='Pinnacle brut' and instant(p)),key=instant)
    for t, batch in groupby(rows,key=instant):
        batch=list(batch)
        for p in batch:
            cles=_cles_match(p); root=racine(cles[0])
            for cle in cles[1:]:
                autre=racine(cle)
                if autre!=root:
                    parents[autre]=root
                    utilises.setdefault(root,set()).update(utilises.get(autre,set()))
        if t<depart:
            continue
        # Les décisions déjà prises occupent leur famille, même après fusion
        # tardive d'alias. Une fusion ne supprime jamais une prise antérieure.
        for p in batch:
            if M3_STRUCTURE['cle'] in p.get('selections_figees',{}):
                utilises.setdefault(racine(_cles_match(p)[0]),set()).add(famille_marche(p))
                selection.add(id(p))
        for p in sorted(batch,key=lambda p:(-(p.get('ecart') or 0),str(p.get('id') or ''))):
            if 'selections_figees' in p or id(p) not in eligibles:
                continue
            famille=famille_marche(p);root=racine(_cles_match(p)[0])
            if famille and famille not in utilises.get(root,set()):
                utilises.setdefault(root,set()).add(famille);selection.add(id(p))
    return appliquer(paris,selection,M3_STRUCTURE['cle'])
