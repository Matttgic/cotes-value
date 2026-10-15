"""Scores NHL officiels, sans clé : match terminé et détail des trois tiers.

Le score final inclut le but crédité au vainqueur des tirs au but. Il ne sert
jamais à remplacer le score des 60 minutes. Une lecture du calendrier par date,
puis une fiche seulement pour les affiches encore en attente.
"""
from datetime import timedelta

import requests

from . import resultats as R

BASE = 'https://api-web.nhle.com/v1'


def capturer(g):
    if g.get('gameState') not in ('OFF', 'FINAL'):
        return None
    try:
        h, a = g['homeTeam'], g['awayTeam']
        nom = lambda t: t['placeName']['default'] + ' ' + t['commonName']['default']
        score = (int(h['score']), int(a['score']))
        if min(score) < 0 or score[0] == score[1]:
            return None
        ps, labels = [], []
        for x in g['summary']['scoring']:
            d = x['periodDescriptor']
            if d['periodType'] == 'SO':
                continue
            if d['periodType'] not in ('REG', 'OT'):
                return None
            label = str(d['number']) if d['periodType'] == 'REG' else 'OT'
            buts = [z['teamAbbrev']['default'] for z in x['goals']]
            if any(b not in (h['abbrev'], a['abbrev']) for b in buts):
                return None
            ps.append((buts.count(h['abbrev']), buts.count(a['abbrev'])))
            labels.append(label)
        if labels[:3] != ['1', '2', '3'] or len(set(labels[:3])) != 3:
            return None
        somme = tuple(sum(p[i] for p in ps) for i in (0, 1))
        fin = g['periodDescriptor']['periodType']
        if fin == 'SO':
            if somme[0] != somme[1] or sum(abs(score[i]-somme[i]) for i in (0, 1)) != 1:
                return None
            ps.append((score[0]-somme[0], score[1]-somme[1]))
            labels.append('SO')
        elif somme != score:
            return None
        return {'source': 'nhl_officiel', 'sport': 'hockey', 'domicile': nom(h), 'exterieur': nom(a),
                'debut': R._heure(g['startTimeUTC']), 'score': score, 'periodes': ps,
                'libelles': labels, 'corners': None,
                'preuve_source': {'url': f"{BASE}/gamecenter/{int(g['id'])}/landing", 'gameState': g['gameState']}}
    except (KeyError, TypeError, ValueError):
        return None


def collecter(paris, maintenant, http=requests):
    ps = [p for p in paris if p.get('statut') in ('en_cours', 'a_regler') and p.get('sport') == 'hockey'
          and str(p.get('ligue')).strip().upper() == 'NHL' and R._heure(p.get('debut'))
          and timedelta(hours=6) <= maintenant-R._heure(p['debut']) < timedelta(days=7)]
    jours = sorted({(R._heure(p['debut'])-timedelta(days=j)).strftime('%Y-%m-%d') for p in ps for j in (0, 1)})
    out, erreurs, vus = [], [], set()
    def lire(chemin):
        try:
            r = http.get(BASE+chemin, timeout=20)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            erreurs.append('lecture NHL officielle indisponible')
            return {}
    for jour in jours:
        for g in lire('/score/'+jour).get('games', []):
            gid = g.get('id')
            if not isinstance(gid, int) or gid in vus or g.get('gameState') not in ('OFF', 'FINAL'):
                continue
            vus.add(gid)
            debut = R._heure(g.get('startTimeUTC'))
            if not debut or not any(abs(debut-R._heure(p['debut'])) <= timedelta(minutes=30) for p in ps):
                continue
            # Le calendrier donne les surnoms seuls. La fiche fournit les noms
            # complets ; au plus les matchs NHL de ces dates (jamais de scan de cotes).
            r = capturer(lire(f'/gamecenter/{gid}/landing'))
            if r and any(R.retrouver(p, [r]) for p in ps):
                out.append(r)
    return out, erreurs
