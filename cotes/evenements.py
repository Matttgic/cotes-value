"""Exposition descriptive par événement relié, indépendamment des résultats."""
from collections import defaultdict
from statistics import mean


def identites(paris):
    from .strategies_prudentes import _cles_match
    parents, par_ligne = {}, {}
    def racine(c):
        parents.setdefault(c,c)
        r=c
        while parents[r]!=r:
            r=parents[r]
        while parents[c]!=c:
            suivant=parents[c];parents[c]=r;c=suivant
        return r
    for p in paris:
        cles=_cles_match(p)
        root=racine(cles[0])
        for c in cles[1:]:
            autre=racine(c)
            if autre!=root:
                parents[autre]=root
        par_ligne[id(p)]=cles[0]
    return {pid:racine(c) for pid,c in par_ligne.items()}


def mesures(rows, regles, clv, contexte=None):
    index=identites(contexte if contexte is not None else rows)
    cle=lambda p:index.get(id(p),('ligne',p.get('id') or id(p)))
    mesures_clv=defaultdict(list)
    for p in regles:
        c=clv(p)
        if c is not None:
            mesures_clv[cle(p)].append(c)
    return {'evenements':len({cle(p) for p in rows}),
            'evenements_regles':len({cle(p) for p in regles}),
            'clv_evenement':round(100*mean(mean(cs) for cs in mesures_clv.values()),2) if mesures_clv else None,
            'clv_evenements_n':len(mesures_clv)}
