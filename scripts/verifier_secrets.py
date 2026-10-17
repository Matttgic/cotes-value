"""Recherche ciblée de secrets dans l'arbre suivi et, sur demande, ses blobs Git.

Aucun secret trouvé n'est imprimé. Les résultats exigent une revue ; un résultat
vide n'est pas une preuve d'absence. Les objets inaccessibles aux refs sont exclus.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cotes.securite import detections  # noqa: E402


def git(*args):
    return subprocess.check_output(['git', *args])


def scanner(historique=False, reference="HEAD", chemins=()):
    root = Path(git('rev-parse', '--show-toplevel').decode().strip())
    bilan = {'historique': historique, 'reference': reference, 'chemins': list(chemins), 'historique_complet':
        git('rev-parse', '--is-shallow-repository').strip() == b'false',
        'textes_lus': 0, 'binaires_ignores': 0, 'trop_grands': [], 'alertes': []}
    def lire(nom, contenu, oid=None):
        if len(contenu) > 16*1024*1024:
            bilan['trop_grands'].append({'fichier': nom, 'objet': oid})
            return
        try:
            texte = contenu.decode('utf-8')
        except UnicodeError:
            bilan['binaires_ignores'] += 1
            return
        bilan['textes_lus'] += 1
        bilan['alertes'].extend({'fichier': nom, 'objet': oid, **a} for a in detections(texte))
    if historique:
        objets = {}
        for ligne in git('rev-list', '--objects', reference, '--', *chemins).decode().splitlines():
            oid, _, nom = ligne.partition(' ')
            if nom:
                objets.setdefault(oid, nom)
        # Lecture des types/tailles avant de charger les blobs.
        metas = subprocess.check_output(['git', 'cat-file', '--batch-check'],
            input=('\n'.join(objets)+'\n').encode()).decode().splitlines()
        process = subprocess.Popen(['git', 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            for ligne in metas:
                oid, type_, taille = ligne.split()
                if type_ != 'blob':
                    continue
                if int(taille) > 16*1024*1024:
                    bilan['trop_grands'].append({'fichier': objets[oid], 'objet': oid})
                    continue
                process.stdin.write((oid+'\n').encode()); process.stdin.flush()
                entete = process.stdout.readline().split()
                contenu = process.stdout.read(int(entete[2]))
                process.stdout.read(1)
                lire(objets[oid], contenu, oid)
        finally:
            process.stdin.close(); process.wait()
    else:
        for nom in git('ls-files', '-z').decode().split('\0'):
            if nom and (root/nom).is_file():
                lire(nom, (root/nom).read_bytes())
    return bilan


if __name__ == '__main__':
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('--historique', action='store_true')
    a.add_argument('--sortie', type=Path)
    a.add_argument('--reference', default='HEAD', help='Ref Git, ou --all pour toutes les refs')
    a.add_argument('--chemin', action='append', default=[], help='Restreindre les chemins historiques')
    args = a.parse_args()
    bilan = scanner(args.historique, args.reference, args.chemin)
    contenu = json.dumps(bilan, ensure_ascii=False, indent=2)+'\n'
    if args.sortie:
        args.sortie.parent.mkdir(parents=True, exist_ok=True)
        args.sortie.write_text(contenu)
    print(json.dumps({'textes_lus': bilan['textes_lus'], 'historique_complet': bilan['historique_complet'],
        'trop_grands': len(bilan['trop_grands']),
        'alertes': len(bilan['alertes']), 'types': sorted({a['type'] for a in bilan['alertes']})}))
    # La valeur guest déjà déclarée reste un point ouvert explicite, pas une nouvelle fuite masquée.
    sys.exit(1 if any(a['type'] != 'guest_pinnacle_historique' for a in bilan['alertes'])
             or bilan['trop_grands'] else 0)
