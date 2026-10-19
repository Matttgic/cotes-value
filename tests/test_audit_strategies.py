"""Entrées corrompues, causalité et distinction registre/rejeu des deux sélecteurs."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from cotes.strategie_chatgpt import CHATGPT, motif_refus, paris_chatgpt
from cotes.strategie_eden import motif_refus_eden, paris_eden
from cotes.strategie_jules_v2 import (JULES_V2, _cles, analyser_jules_v2,
    diagnostic_jules_v2, motif_refus_jules_v2, paris_jules_v2)
from cotes.strategie_commune import edge_coherent, ligne_non_quart, issue_valide
from tests.test_strategie_chatgpt import pari as chatgpt
from tests.test_strategie_eden import pari as eden
from tests.test_strategie_jules_v2 import pari as jules, ref

SELECTEURS = [(chatgpt, motif_refus, paris_chatgpt), (jules, motif_refus_jules_v2, paris_jules_v2),
              (eden, motif_refus_eden, paris_eden)]


@pytest.mark.parametrize('fabrique,motif,selectionner', SELECTEURS)
@pytest.mark.parametrize('preuve', [None, {}, [], ['ref'], 'ref', 42, True,
    {'match_id_reference': 'ref', 'ressemblance_noms': .95, 'controle': ['conforme']},
    {'match_id_reference': 'ref', 'ressemblance_noms': .95, 'controle': 'conforme'},
    {'match_id_reference': 'ref', 'ressemblance_noms': 10**400, 'controle': {'statut': 'conforme'}}])
def test_preuve_malformee_refusee_sans_masquer_pari_valide(fabrique, motif, selectionner, preuve):
    bon, mauvais = fabrique('bon'), fabrique('mauvais', preuve_prise=preuve)
    avant = deepcopy([bon, mauvais])
    assert motif(bon) is None and motif(mauvais) is not None
    assert selectionner([mauvais, bon]) == {id(bon)}
    assert [bon, mauvais] == avant


@pytest.mark.parametrize('fabrique,motif,selectionner', SELECTEURS)
@pytest.mark.parametrize('champ,valeur', [('cote', None), ('ecart', None), ('debut', None),
    ('detecte', 'invalide'), ('cote', 10**400), ('ecart', 10**400), ('cote_juste', 10**400)])
def test_donnees_refusees_n_atteignent_pas_tri_ou_identite(fabrique, motif, selectionner, champ, valeur):
    bon, mauvais = fabrique('bon'), fabrique('mauvais', **{champ: valeur})
    assert motif(bon) is None and motif(mauvais) is not None
    assert selectionner([mauvais, bon]) == {id(bon)}


def test_cles_sans_date_ne_fabriquent_pas_identite_equipe():
    p = jules(debut=None)
    cles = _cles(p)
    assert {c[0] for c in cles} == {'reference', 'bookmaker'}
    assert paris_jules_v2([p]) == set()


def test_tri_chatgpt_sans_identifiant_optionnel_ne_plante_pas():
    p = chatgpt()
    del p['id'], p['match_id']
    assert motif_refus(p) is None
    assert paris_chatgpt([p]) == {id(p)}


class InterdireFutur(dict):
    interdits = {'statut', 'gain', 'clv', 'regle_le', 'resultat', 'score',
                 'cote_juste_cloture', 'cloture_lue'}
    def get(self, key, *args):
        assert key not in self.interdits
        return super().get(key, *args)
    def __getitem__(self, key):
        assert key not in self.interdits
        return super().__getitem__(key)
    def __contains__(self, key):
        assert key not in self.interdits
        return super().__contains__(key)


@pytest.mark.parametrize('fabrique,motif,selectionner', SELECTEURS)
def test_selecteurs_ne_lisent_pas_les_champs_futurs(fabrique, motif, selectionner):
    p = InterdireFutur(fabrique())
    assert motif(p) is None
    assert selectionner([p]) == {id(p)}
    if selectionner is paris_jules_v2:
        assert diagnostic_jules_v2([p])['selectionnes'] == 1


def test_diagnostic_complet_serialisable_sans_ids_memoire_ni_mutation():
    p = jules('alpha')
    doublon = {**p, 'id': 'doublon', 'detecte': '2026-10-15T09:01:00Z'}
    mauvais_edge = jules('mauvais', ecart=.20, detecte='2026-10-15T09:02:00Z')
    mauvaise_date = jules('date', debut=None)
    rows = [p, doublon, mauvais_edge, mauvaise_date]
    avant = deepcopy(rows)
    d = diagnostic_jules_v2(rows)
    assert d['mode'] == 'rejeu_diagnostic' and d['version'] == JULES_V2['version']
    assert d['selectionnes'] == 1 and d['doublons_ecartes'] == 1
    assert sum(d['refus'].values()) == 1 and d['hors_correspondance'] == 1
    assert d['lignes_examinees'] == 4
    assert d['lignes_examinees'] == (d['selectionnes'] + d['doublons_ecartes']
        + d['plafond_ecartes'] + sum(d['refus'].values()) + d['hors_correspondance'])
    assert 'selection' not in d and json.loads(json.dumps(d)) == d
    assert rows == avant


def test_diagnostic_rejeu_distinct_du_registre_fige_apres_rechargement():
    p = jules('fige', preuve_prise=None, selections_figees={
        'jules_v2': {'version': JULES_V2['version'], 'decide_le': '2026-10-15T09:00:00Z'}})
    q, r = jules('refuse1', selections_figees={}), jules('refuse2', selections_figees={})
    rows = json.loads(json.dumps([p, q, r]))
    avant = deepcopy(rows)
    assert paris_jules_v2(rows) == {id(rows[0])}
    assert diagnostic_jules_v2(rows)['selectionnes'] == 2
    assert paris_jules_v2(rows, depuis=JULES_V2['debut']) == {id(rows[1]), id(rows[2])}
    assert rows == avant


def test_diagnostic_fusion_tardive_preserve_chaque_prefixe():
    p = jules('alpha', match_reference='')
    q = ref(jules('bravo', detecte='2026-10-15T09:01:00Z', match_reference=''), 'Betfair', 'bet')
    pont = ref({**p, 'id': 'pont', 'detecte': '2026-10-15T09:02:00Z'}, 'Betfair', 'bet')
    rows = [p, q, pont]
    total = analyser_jules_v2(rows)['selection']
    for n in range(1, len(rows) + 1):
        prefixe = rows[:n]
        assert analyser_jules_v2(prefixe)['selection'] == total & {id(p) for p in prefixe}
    assert diagnostic_jules_v2(rows)['fusions_tardives'] == 1


@pytest.mark.parametrize('fabrique,selectionner,maximum', [
    (chatgpt, paris_chatgpt, 5), (jules, paris_jules_v2, 8), (eden, paris_eden, 6)])
def test_plafond_reinitialise_a_minuit_paris_en_hiver(fabrique, selectionner, maximum):
    # UTC+1 après le changement d'heure : le jour français change à 23h UTC.
    t = datetime(2026, 11, 1, 22, tzinfo=timezone.utc)
    debut = (t + timedelta(hours=3)).isoformat()
    rows = [fabrique('equipe'+str(i), detecte=(t + timedelta(minutes=i)).isoformat(),
                    lu_reference=(t + timedelta(minutes=i)).isoformat(), debut=debut)
            for i in range(maximum+1)]
    suivant = fabrique('suivant', detecte=(t + timedelta(hours=1)).isoformat(),
                      lu_reference=(t + timedelta(hours=1)).isoformat(), debut=debut)
    assert selectionner(rows + [suivant]) == {id(p) for p in rows[:maximum] + [suivant]}


def test_primitives_conservent_coherence_et_types_de_marche():
    assert edge_coherent(2.1, 2, .05) and not edge_coherent(2.1, 3, .05)
    assert not edge_coherent(2, float('inf'), .05)
    assert ligne_non_quart(2) and ligne_non_quart(2.5)
    assert not ligne_non_quart(2.25) and not ligne_non_quart(True)
    assert issue_valide('RESULTAT_1N2', 'NUL') and not issue_valide('HANDICAP', 'NUL')
    assert issue_valide('TOTAL', 'PLUS') and not issue_valide('inconnu', 'DOM')


def test_script_rapport_expose_rejeu_et_empreinte_des_validations_partagees():
    from hashlib import sha256
    from pathlib import Path
    from scripts.verifier_strategie_jules_v2 import rapport
    r = rapport([jules()], releve='2026-10-16T00:00:00Z')
    assert r['identite']['mode'] == 'rejeu_diagnostic' and 'selection' not in r['identite']
    helper = Path(__file__).resolve().parent.parent / 'cotes' / 'strategie_commune.py'
    assert r['dependances_selecteur_sha256']['strategie_commune.py'] == sha256(helper.read_bytes()).hexdigest()
    assert json.loads(json.dumps(r))['identite'] == r['identite']
