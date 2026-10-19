import base64
import json
from pathlib import Path

import pytest

from cotes.securite import detections, json_public, verifier_public
from scripts.site_web import construire
from tests.test_strategie_chatgpt import pari


@pytest.mark.parametrize('champ', ['token', 'token_hash', 'subscription', 'endpoint',
    'p256dh', 'privateKey', 'SUPABASE_SERVICE_ROLE_KEY', 'X-Secret', 'X-API-Key',
    'secret', 'PULSESCORE_KEY'])
def test_champs_prives_refuses_meme_profonds_sans_valeur_dans_erreur(champ):
    valeur = 'valeur-a-ne-jamais-afficher'
    with pytest.raises(ValueError) as e:
        verifier_public({'cycles': [{'diagnostic': {champ: valeur}}]})
    assert valeur not in str(e.value)


def test_formats_sensibles_detectes_sans_exposer_leur_valeur():
    github = 'ghp_' + 'aBcD1234'*5
    supabase = 'sb_secret_' + 'aBcD1234'*5
    encode = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip('=')
    jwt = encode({'alg': 'HS256', 'typ': 'JWT'})+'.'+encode({'role': 'service_role'})+'.'+'aB12'*12
    for secret in (github, supabase, jwt):
        d = detections('ligne 1\n'+secret)
        assert len(d) == 1 and d[0]['ligne'] == 2
        assert secret not in json.dumps(d)
        with pytest.raises(ValueError):
            verifier_public({'erreur': secret})


def test_valeur_configuree_dans_message_refusee_sans_contexte_dangereux():
    secret = 'exemple' + '-a-la-place-dune-vraie-cle'
    with pytest.raises(ValueError) as e:
        verifier_public({'erreur': 'requête '+secret}, env={'PULSESCORE_KEY': secret})
    assert secret not in str(e.value)


def test_donnees_sportives_publiques_et_cle_vapid_publique_autorisees():
    d = {'notifications': {'api': 'https://example.test/cv-notifications'},
         'publicKey': 'publique', 'match_id': '1', 'pari': '<!--<script>"équipe"</script>&'}
    texte = json_public(d)
    assert '<' not in texte and '>' not in texte and '&' not in texte
    assert json.loads(texte) == d


def test_site_ne_remplace_pas_page_existante_si_donnee_privee(tmp_path):
    donnees, site = tmp_path/'donnees', tmp_path/'site'
    donnees.mkdir();site.mkdir()
    (site/'index.html').write_text('ancienne page valide')
    (donnees/'etat.json').write_text(json.dumps({'dernier_cycle': {'subscription': {'auth': 'secret'}}}))
    with pytest.raises(ValueError, match='Publication bloquée'):
        construire(donnees, site)
    assert (site/'index.html').read_text() == 'ancienne page valide'
    assert not (site/'notifications.json').exists()


def test_site_echappe_donnees_sans_perdre_match_ou_pari(tmp_path):
    p = pari(pari='<!--<script>alert("test")</script><img src=x onerror="test">')
    (tmp_path/'paris.json').write_text(json.dumps([p]))
    html = construire(tmp_path, tmp_path/'site').read_text()
    # Un seul script : les workflows de publication refusent toute autre valeur (site.yml, collecte.yml, reglement.yml).
    assert html.count('<script>') == html.count('</script>') == 1
    assert html.index('localStorage.getItem("cv-theme-v1")') < html.index('const D = ')
    assert p['pari'] not in html
    assert '\\u003c!--\\u003cscript\\u003e' in html


def test_configuration_locale_ignoree_sans_mauvaises_variables():
    root = Path(__file__).resolve().parent.parent
    exemple = (root/'.env.example').read_text()
    assert 'PULSESCORE_PAUSE=1.1' in exemple
    assert 'THE_ODDS_API_KEY_1=' in exemple and 'THE_ODDS_API_KEYS=' not in exemple
    assert '!.env.example' in (root/'.gitignore').read_text()


def test_scanner_refuse_secret_actuel_et_historique_sans_imprimer_valeur(tmp_path):
    import subprocess
    import sys
    root = Path(__file__).resolve().parent.parent
    script = root/'scripts/verifier_secrets.py'
    secret = 'ghp_' + 'aBcD1234'*5
    def git(*args):
        return subprocess.run(['git', '-c', 'user.name=Security test', '-c',
            'user.email=security@example.test', *args], cwd=tmp_path, check=True, capture_output=True)
    git('init', '-q')
    (tmp_path/'config.txt').write_text(secret)
    git('add', 'config.txt')
    git('commit', '-qm', 'exposition fictive pour test')
    r = subprocess.run([sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1 and secret not in r.stdout+r.stderr
    (tmp_path/'config.txt').write_text('configuration vide')
    git('add', 'config.txt');git('commit', '-qm', 'retrait fictif')
    r = subprocess.run([sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0
    r = subprocess.run([sys.executable, str(script), '--historique'], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1 and secret not in r.stdout+r.stderr


def test_marqueurs_du_gabarit_dans_un_pari_restent_des_donnees(tmp_path):
    import re
    texte = '__INTERFACE_JS__ __VISUELS_JS__ __ACTUALISATION_JS__ __VERSION_SITE__ __DONNEES__'
    p = pari(pari=texte)
    (tmp_path/'paris.json').write_text(json.dumps([p]))
    html = construire(tmp_path, tmp_path/'site').read_text()
    d = json.loads(re.search(r'const D = (\{.*?\});\n', html, re.S).group(1))
    colonne = d['catalogue']['champs'].index('pari')
    assert any(texte == row[colonne] for row in d['catalogue']['lignes'])
