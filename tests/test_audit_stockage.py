"""Pannes de stockage : aucun écrasement silencieux, reprises sans double comptage."""
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import json

import pytest

from cotes import stockage as S

NOW = datetime(2026, 12, 15, tzinfo=timezone.utc)


def vieux(pid='ancien', mois='08', **kw):
    return {'id':pid, 'statut':'gagne', 'regle_le':f'2026-{mois}-01T12:00:00Z',
            'detecte':f'2026-{mois}-01T10:00:00Z', 'mise':10, 'gain':12, **kw}


def archive(dossier, mois, contenu):
    f = dossier / 'archives' / f'paris-2026-{mois}.json.gz'
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(gzip.compress(json.dumps(contenu).encode()))
    return f


@pytest.mark.parametrize('contenu', [
    b'pas un gzip', gzip.compress(b'[]')[:-5], gzip.compress(b'[{'),
    gzip.compress(b'\xff'), gzip.compress(b'{}'), gzip.compress(b'[null]'),
    gzip.compress(b'[{"id":"x","gain":Infinity}]'),
    gzip.compress(b'[{"statut":"gagne"}]'),
    gzip.compress(b'[{"id":"x","gain":1},{"id":"x","gain":2}]')])
def test_archive_corrompue_stricte_par_defaut_diagnostic_partiel_explicite(tmp_path, caplog, contenu):
    bon = vieux('bon')
    archive(tmp_path,'08',[bon])
    mauvais = archive(tmp_path,'09',[]); mauvais.write_bytes(contenu)
    avant = mauvais.read_bytes()
    with pytest.raises(S.ArchiveInvalide, match='paris-2026-09.json.gz'):
        S.lire_archives(tmp_path)
    erreurs = []
    assert S.lire_archives(tmp_path, erreurs=erreurs) == [bon]
    assert len(erreurs)==1 and erreurs[0]['fichier']==mauvais.name
    assert mauvais.name in caplog.text and mauvais.read_bytes()==avant


def test_reprise_et_fusion_json_identiques_sans_modifier_ni_doubler(tmp_path):
    p = vieux(preuve={'score':(2,1)})
    ouvert = {'id':'ouvert','statut':'en_cours'}
    avant = deepcopy([p, ouvert])
    assert S.archiver(tmp_path, [p, ouvert], NOW) == [ouvert]
    fichiers = {f.name:f.read_bytes() for f in (tmp_path/'archives').iterdir()}
    assert S.archiver(tmp_path, [p, ouvert], NOW) == [ouvert]
    assert fichiers == {f.name:f.read_bytes() for f in (tmp_path/'archives').iterdir()}
    relus = S.lire_archives(tmp_path)
    assert len(S.fusionner_paris([p, ouvert], relus)) == 2
    assert S.fusionner_paris([p], relus)[0] is p
    assert [p, ouvert] == avant


@pytest.mark.parametrize('pid', [None, '', ' ', 123, True, [], {}])
def test_identifiant_invalide_aucune_archive_ecrite(tmp_path, pid):
    rows = [vieux('bon'), vieux(pid)]
    avant = deepcopy(rows)
    with pytest.raises(ValueError, match='identifiant stable'):
        S.archiver(tmp_path, rows, NOW)
    assert rows == avant and not list(tmp_path.rglob('*.gz'))


def test_conflit_actif_ou_archive_detecte_avant_toute_ecriture(tmp_path):
    p = vieux()
    f = archive(tmp_path,'08',[p]); avant = f.read_bytes()
    for rows in [[p, {**p,'gain':999}], [{**p,'gain':999}],
                 [vieux('autre','07'), {**p,'gain':999}]]:
        with pytest.raises(ValueError, match='conflit'):
            S.archiver(tmp_path, rows, NOW)
        assert f.read_bytes()==avant
        assert sorted(x.name for x in (tmp_path/'archives').iterdir()) == [f.name]


def test_identiques_entre_archives_uniques_conflit_explicite(tmp_path):
    p = vieux()
    archive(tmp_path,'08',[p,p]); f = archive(tmp_path,'09',[p])
    assert S.lire_archives(tmp_path)==[p]
    archive(tmp_path,'09',[{**p,'gain':-10}])
    with pytest.raises(S.ArchiveInvalide, match='conflit'):
        S.lire_archives(tmp_path)
    erreurs=[]
    assert S.lire_archives(tmp_path, erreurs=erreurs)==[p]
    assert erreurs[0]['fichier']==f.name


def test_archive_illisible_jamais_ecrasee_meme_si_autre_mois_valide(tmp_path):
    f = archive(tmp_path,'09',[]); f.write_bytes(b'corrompu')
    with pytest.raises(S.ArchiveInvalide):
        S.archiver(tmp_path, [vieux('a','08'),vieux('b','09')], NOW)
    assert f.read_bytes()==b'corrompu'
    assert sorted(x.name for x in f.parent.iterdir())==[f.name]


def test_echec_serialisation_du_second_mois_ne_publie_pas_le_premier(tmp_path):
    f = archive(tmp_path,'08',[vieux()]); avant=f.read_bytes()
    with pytest.raises(ValueError):
        S.archiver(tmp_path,[vieux('a','08'),vieux('b','09',gain=float('inf'))],NOW)
    assert f.read_bytes()==avant and not list(tmp_path.rglob('*.tmp'))
    assert sorted(x.name for x in f.parent.iterdir())==[f.name]


def test_relecture_du_temporaire_detecte_troncature_et_preserve_original(tmp_path, monkeypatch):
    f = archive(tmp_path,'08',[vieux()]); avant=f.read_bytes()
    lire=S._lire_archive
    def tronquer(chemin):
        if chemin.suffix=='.tmp':
            chemin.write_bytes(chemin.read_bytes()[:-5])
        return lire(chemin)
    monkeypatch.setattr(S,'_lire_archive',tronquer)
    with pytest.raises(S.ArchiveInvalide):
        S.archiver(tmp_path,[vieux('nouveau')],NOW)
    assert f.read_bytes()==avant and not list(tmp_path.rglob('*.tmp'))


def test_interruption_entre_deux_remplacements_reprise_sans_perte(tmp_path, monkeypatch):
    rows=[vieux('a','08'),vieux('b','09')];avant=deepcopy(rows)
    remplacer=S.os.replace
    def echouer(source,dest):
        if dest.name=='paris-2026-09.json.gz':
            raise OSError('panne disque simulée')
        remplacer(source,dest)
    monkeypatch.setattr(S.os,'replace',echouer)
    with pytest.raises(OSError,match='panne disque'):
        S.archiver(tmp_path,rows,NOW)
    assert rows==avant and not list(tmp_path.rglob('*.tmp'))
    assert S.fusionner_paris(rows,S.lire_archives(tmp_path))==rows
    monkeypatch.setattr(S.os,'replace',remplacer)
    assert S.archiver(tmp_path,rows,NOW)==[]
    assert S.lire_archives(tmp_path)==rows


def test_dates_invalides_et_statuts_non_regles_restent_actifs(tmp_path):
    rows=[vieux('sans_fuseau',regle_le='2026-08-01T12:00:00'),
          vieux('date_absente',regle_le=None),vieux('inconnue',statut='annule'),
          vieux('ouvert',statut='a_regler')]
    assert S.archiver(tmp_path,rows,NOW)==rows
    assert not list(tmp_path.rglob('*.gz'))
    with pytest.raises(ValueError,match='sans fuseau'):
        S.archiver(tmp_path,rows,NOW.replace(tzinfo=None))


def test_site_refuse_bilan_incomplet_et_conserve_html_precedent(tmp_path):
    from scripts.site_web import construire
    f=archive(tmp_path,'08',[]);f.write_bytes(b'corrompu')
    destination=tmp_path/'site';destination.mkdir()
    html=destination/'index.html';html.write_text('ancienne page valide')
    with pytest.raises(S.ArchiveInvalide):
        construire(tmp_path,destination)
    assert html.read_text()=='ancienne page valide'


def test_site_ne_double_pas_un_pari_archive_encore_actif(tmp_path):
    from scripts.site_web import construire
    from tests.test_navigation_strategies import pari
    import re
    p=pari('repris','2026-10-01T10:00:00Z','2026-10-01T18:00:00Z','gagne')
    p['regle_le']='2026-10-02T10:00:00Z'
    S.archiver(tmp_path,[p],NOW)
    (tmp_path/'paris.json').write_text(json.dumps([p]))
    html=construire(tmp_path,tmp_path/'site').read_text()
    d=json.loads(re.search(r'const D = (\{.*?\});\n',html,re.S).group(1).replace('<\\/','</'))
    b=d['bilan']['C|Pinnacle']
    assert b['paris']==1 and b['mises']==10 and b['gains']==7.5
