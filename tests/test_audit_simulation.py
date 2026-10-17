"""Prises fraîches, registre persistant et limites des diagnostics exploratoires."""
from copy import deepcopy
from datetime import timedelta
import json

import pytest

from cotes import simulation as S
from cotes.decisions import appliquer, figer_nouveaux
from tests.test_contre_audit import NOW, candidat


@pytest.mark.parametrize('cote', [None, 0, -2, 1, True, '2.0', float('nan'), float('inf'), -float('inf')])
def test_cotes_invalides_identifiables_et_jamais_prises(cote):
    assert S.tranche(cote) == 'cote invalide'
    assert S.simulation_de(.05, cote) is None
    rows = []
    assert S.placer([candidat(cote=cote)], rows, NOW) == []
    assert rows == []


@pytest.mark.parametrize('ecart,cote,attendu', [
    (.0199, 2, None), (.02, 2, 'A'), (.0299, 2, 'A'), (.03, 2, 'B'),
    (.04, 2, 'C'), (.05, 2, 'D'), (.07, 2, 'E'), (.025, 10, 'A'),
    (.035, 10.0001, 'X'), (.025, 10.0001, None)])
def test_bornes_simulations_conservees(ecart, cote, attendu):
    assert S.simulation_de(ecart, cote) == attendu


@pytest.mark.parametrize('champ', ['ecart', 'cote_juste'])
@pytest.mark.parametrize('valeur', [None, 'invalide', True, float('nan'), float('inf')])
def test_un_import_invalide_ne_bloque_pas_les_autres_prises(champ, valeur):
    rows = []
    bad = candidat('bad', **{champ: valeur})
    good = candidat('good', match_id='b|autre')
    assert len(S.placer([bad, good], rows, NOW)) == 1
    assert rows[0]['match_id'] == 'b|autre'


@pytest.mark.parametrize('age_fr,age_ref,accepte', [
    (0, 900, True), (900, 0, True), (0, 901, False), (901, 0, False),
    (3600, 3600, False), (0, -60, True), (0, -61, False),
    (840, -60, True), (841, -60, False)])
def test_fraicheur_absolue_et_relative_aux_bornes(age_fr, age_ref, accepte):
    o = candidat(detecte=(NOW-timedelta(seconds=age_fr)).isoformat(),
                 lu_reference=(NOW-timedelta(seconds=age_ref)).isoformat())
    avant = deepcopy(o)
    assert bool(S.placer([o], [], NOW)) is accepte
    assert o == avant


@pytest.mark.parametrize('champ', ['detecte', 'lu_reference', 'collecte_recue'])
@pytest.mark.parametrize('valeur', ['', 'invalide', '2026-10-17T02:00:00'])
def test_dates_absentes_invalides_ou_sans_fuseau_refusees(champ, valeur):
    assert not S.placer([candidat(**{champ: valeur})], [], NOW)


def test_aucune_date_manquante_ni_reception_recente_ne_masque_une_reference_ancienne():
    for champ in ['detecte', 'lu_reference']:
        p = candidat(); p.pop(champ)
        assert not S.placer([p], [], NOW)
    assert not S.placer([candidat(lu_reference=None)], [], NOW)
    assert not S.placer([candidat(detecte=(NOW-timedelta(hours=1)).isoformat(),
                                 collecte_recue=NOW.isoformat())], [], NOW)
    assert not S.placer([candidat(collecte_recue=(NOW-timedelta(minutes=16)).isoformat())], [], NOW)
    # Une lecture après le début ne passe pas grâce à la tolérance d'horloge.
    assert not S.placer([candidat(debut=(NOW+timedelta(seconds=31)).isoformat(),
                                 lu_reference=(NOW+timedelta(seconds=32)).isoformat())], [], NOW)
    assert S.placer([candidat(detecte='2026-10-17T04:00:00+02:00',
                             lu_reference='2026-10-17T03:59:00+02:00')], [], NOW)


def test_consensus_conserve_et_verifie_les_dates_de_chaque_composante():
    from cotes.comparaison import comparer
    from cotes.marches import cle
    from tests.test_controle import ligne
    fr = ligne(cote=2.2, collecte=NOW.isoformat(), debut=(NOW+timedelta(hours=2)).isoformat())
    index = {n: {fr['match_id']: {cle(fr): {**fr, 'proba_juste': .5}}}
             for n in ('Pinnacle', 'Betfair')}
    out = comparer([fr], {'Pinnacle': [], 'Betfair': []}, index=index, temoin_brut=False)
    consensus = next(o for o in out if o['reference'] == 'Consensus')
    assert consensus['lectures_references'] == {'Pinnacle': NOW.isoformat(), 'Betfair': NOW.isoformat()}
    p = S.placer([consensus], [], NOW)[0]
    assert p['preuve_prise']['lectures_references'] == consensus['lectures_references']
    ancien = {**consensus, 'lectures_references': {**consensus['lectures_references'],
              'Pinnacle': (NOW-timedelta(hours=1)).isoformat()}}
    assert not S.placer([ancien], [], NOW)
    for valeur in [None, {}, {'Pinnacle': NOW.isoformat()}, {'Pinnacle': None, 'Betfair': NOW.isoformat()}]:
        assert not S.placer([{**consensus, 'lectures_references': valeur}], [], NOW)


@pytest.mark.parametrize('statut', ['en_cours', 'a_regler'])
def test_roi_ignore_les_mises_non_reglees_et_clv_non_finale(statut):
    ouvert = candidat('ouvert', statut=statut, clv=.8, cloture_lue='2026-10-17T03:50:00Z')
    gagne = candidat('gagne', match_id='b|2', statut='gagne', mise=10, gain=12)
    b = S.bilan([ouvert, gagne])['C|Pinnacle']
    assert b['mises'] == 10 and b['gains'] == 12 and b['roi'] == 1.2
    assert b['en_cours'] == 1 and b['regles'] == 1 and b['clv_n'] == 0
    assert S.bilan([ouvert])['C|Pinnacle']['roi'] is None


@pytest.mark.parametrize('pid', [None, '', ' ', 123, True])
def test_registre_identifiant_stable_obligatoire_avant_toute_mutation(pid):
    bon, mauvais = candidat('bon'), candidat('bad', id=pid)
    rows = [bon, mauvais]; avant = deepcopy(rows)
    with pytest.raises(ValueError, match='identifiant stable'):
        figer_nouveaux(rows, rows)
    assert rows == avant


def test_registre_refuse_id_absent_copies_et_doublons():
    p = candidat('p')
    for rows, nouveaux in [([], [p]), ([p], [deepcopy(p)]),
                            ([p, deepcopy(p)], [p]), ([p], [p, p])]:
        avant = deepcopy(rows)
        with pytest.raises(ValueError):
            figer_nouveaux(rows, nouveaux)
        assert rows == avant
    q = candidat(); q.pop('id')
    with pytest.raises(ValueError, match='identifiant stable'):
        figer_nouveaux([q], [q])


@pytest.mark.parametrize('valeur', [None, 'invalide', '2026-10-17T02:00:00'])
def test_registre_date_de_decision_obligatoire(valeur):
    p = candidat(decide_le=valeur); avant = deepcopy(p)
    with pytest.raises(ValueError, match='Date de décision'):
        figer_nouveaux([p], [p])
    assert p == avant


def test_registre_persiste_acceptations_et_refus_apres_rechargement():
    ancien = candidat('historique', reference='Kalshi')
    rows = [ancien]
    nouveaux = S.placer([candidat('ok', match_id='b|ok', match_id_reference=123,
                                 score_association=.99, controle={'statut':'conforme'}),
                        candidat('refus', match_id='k|refus', reference='Kalshi')], rows, NOW)
    assert all(isinstance(p['id'], str) and len(p['id']) == 16 for p in nouveaux)
    figer_nouveaux(rows, nouveaux)
    assert 'selections_figees' not in ancien
    assert 'm3' in nouveaux[0]['selections_figees'] and nouveaux[1]['selections_figees'] == {}
    recharges = json.loads(json.dumps(rows))
    assert all(id(a) != id(b) for a, b in zip(rows, recharges))
    # La sélection calculée en mémoire peut changer : le registre prend le relais.
    ids = appliquer(recharges, {id(recharges[2])}, 'm3')
    assert id(recharges[1]) in ids and id(recharges[2]) not in ids
    avant = deepcopy(recharges)
    figer_nouveaux(recharges, recharges[1:])
    assert recharges == avant


def segment_rows(n=30, meme_match=False, **kwargs):
    rows = []
    for i in range(n):
        p = candidat(str(i), match_id='b|commun' if meme_match else f'b|{i}',
                     marche='HANDICAP', ligne=i+.5, statut='gagne', gain=8, cote=1.8, cote_juste=2)
        if not meme_match:
            p.update(domicile=f'Club domicile {i}', exterieur=f'Club extérieur {i}')
        p['preuve_prise'] = {**p['preuve_prise'], 'match_id_reference': 999 if meme_match else i}
        p.update(kwargs)
        rows.append(p)
    return rows


def test_sigma_conditions_necessaires_pas_uniquement_30_tickets():
    s = S.segments(segment_rows())[0]
    assert s['n'] == s['evenements'] == 30 and s['sigma_fiable'] and not s['sigma_limites']
    s = S.segments(segment_rows(meme_match=True))[0]
    assert s['n'] == 30 and s['evenements'] == 1
    assert not s['sigma_fiable'] and 'tickets_meme_evenement' in s['sigma_limites']
    s = S.segments(segment_rows(n=12))[0]
    assert not s['sigma_fiable'] and 'effectif_faible' in s['sigma_limites']
    for statut in ['demi_gagne', 'demi_perdu', 'rembourse']:
        s = S.segments(segment_rows(statut=statut))[0]
        assert not s['sigma_fiable'] and 'reglements_non_binaires' in s['sigma_limites']
    s = S.segments(segment_rows(cote_juste=1.01))[0]
    assert not s['sigma_fiable'] and 'attendus_extremes' in s['sigma_limites']


def test_segments_limite_10_et_chiffres_conserves():
    assert not S.segments(segment_rows(n=9))
    s = S.segments(segment_rows(n=10))[0]
    assert s['n'] == 10 and s['roi'] == .8 and s['gains'] == 80
    assert s['gagnes'] == 10 and s['attendus'] == 5
    assert s['ecart_sigma'] == round(5/(10*.5*.5)**.5, 2)
