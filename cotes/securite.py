"""Garde-fous de publication ; détection ciblée, pas certification de tous les secrets."""
from __future__ import annotations

import base64
from collections import Counter
import hashlib
import json
from math import log2
import os
import re

GUEST_SHA256 = '03afa65b49aead916fb17e5e7a075af6ee3a75755838eccd8a3fc8cc562dabc6'
CHAMPS_PRIVES = frozenset(('subscription', 'token', 'tokenhash', 'endpointhash', 'endpoint',
    'p256dh', 'auth', 'authorization', 'apikey', 'xapikey', 'xsecret', 'privatekey',
    'servicerolekey', 'supabaseservicerolekey', 'supabasesecretkey', 'secret',
    'pinnacleapikey', 'pinnoddsapikey', 'pinbookapikey', 'pulsescorekey', 'proplineapikey', 'apisportskey',
    'theoddsapikey', 'theoddsapikey1', 'theoddsapikey2', 'theoddsapikey3', 'theoddsapikey4',
    'password', 'accesstoken', 'refreshtoken'))
FORMATS = {
    'jeton_github': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    'cle_privee_pem': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'secret_dans_url': re.compile(r'(?i)[?&](?:api[_-]?key|token|secret|access_token)=[A-Za-z0-9_%.-]{24,}'),
    'cle_supabase_secrete': re.compile(r'\bsb_secret_[A-Za-z0-9_-]{20,}\b'),
}
AFFECTATION = re.compile(r'''(?ix)
    (?<![a-z0-9_-])(?P<nom>[a-z0-9_-]{0,80}(?:api[_-]?key|private[_-]?key|secret|password|access[_-]?token)[a-z0-9_-]{0,80})
    ["']?\s*[:=]\s*["'](?P<valeur>[^\s"']{24,2048})["']''')
JWT = re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b')
MOTS = re.compile(r'(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{24,}(?![A-Za-z0-9_-])')


def empreinte(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def detections(texte: str) -> list[dict]:
    """Emplacement/type/empreinte uniquement ; ne renvoie jamais la valeur trouvée."""
    trouves = {}
    def noter(type_, valeur, position):
        item = {'type': type_, 'ligne': texte.count('\n', 0, position)+1,
                'empreinte': empreinte(valeur)}
        trouves[(item['ligne'], item['empreinte'])] = item
    for type_, pattern in FORMATS.items():
        for m in pattern.finditer(texte):
            noter(type_, m[0], m.start())
    for m in AFFECTATION.finditer(texte):
        v = m['valeur']
        entropie = -sum((n/len(v))*log2(n/len(v)) for n in Counter(v).values())
        if entropie >= 3.5 and not any(x in v for x in ('${', '{{', 'process.env', 'os.environ')):
            noter('affectation_sensible_possible', v, m.start('valeur'))
    for m in JWT.finditer(texte):
        try:
            payload = m[0].split('.')[1]
            d = json.loads(base64.urlsafe_b64decode(payload + '='*(-len(payload)%4)))
            if isinstance(d, dict) and d.get('role') == 'service_role':
                noter('jwt_service_role', m[0], m.start())
        except (ValueError, UnicodeError):
            pass
    for m in MOTS.finditer(texte):
        if empreinte(m[0]) == GUEST_SHA256:
            noter('guest_pinnacle_historique', m[0], m.start())
    return sorted(trouves.values(), key=lambda x: (x['ligne'], x['type']))


def verifier_public(data, env=None) -> None:
    """Refuse une donnée privée avant écriture d'un artefact public."""
    def parcourir(x):
        if isinstance(x, dict):
            for k, v in x.items():
                nom = re.sub(r'[^a-z0-9]', '', str(k).lower())
                if nom in CHAMPS_PRIVES:
                    raise ValueError('Publication bloquée : champ privé')
                parcourir(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                parcourir(v)
    parcourir(data)
    texte = json.dumps(data, ensure_ascii=False)
    if detections(texte):
        raise ValueError('Publication bloquée : secret possible')
    env = os.environ if env is None else env
    # Complément exact pour les secrets configurés dans le processus courant.
    for nom, valeur in env.items():
        if re.fullmatch(r'(?:PINNACLE_API_KEY|PINNODDS_API_KEY|PINBOOK_API_KEY|PULSESCORE_KEY|PROPLINE_API_KEY|API_SPORTS_KEY|'
                        r'THE_ODDS_API_KEY(?:_[1-4])?|SUPABASE_SERVICE_ROLE_KEY)', nom):
            if isinstance(valeur, str) and len(valeur) >= 8 and valeur in texte:
                raise ValueError('Publication bloquée : secret configuré')


def json_public(data) -> str:
    verifier_public(data)
    # Échappe aussi <script et <!--, pas seulement la balise de fermeture.
    return (json.dumps(data, ensure_ascii=False, separators=(',', ':'))
            .replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e'))
