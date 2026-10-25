"""Grok 2 (Pinnacle au lieu de Smarkets) et Grok 3 (preuve du Consensus par ses composantes)."""
import pytest
from cotes.comparaison import comparer
from cotes.marches import cle
from cotes.strategie_grok import GROK_1, GROK_2, GROK_3, GROK_5, motif_refus_grok, paris_grok_2, paris_grok_3
from tests.test_controle import ligne
from tests.test_strategie_jules_v2 import pari

BON = dict(cote=1.6, cote_juste=1.5, ecart=1.6 / 1.5 - 1,
           detecte="2026-10-25T09:00:00Z", debut="2026-10-25T12:00:00Z", lu_reference="2026-10-25T08:59:00Z")
COMPOSANTES = {"Pinnacle": {"ressemblance_noms": .93, "match_id_reference": "pin1"},
               "Polymarket": {"ressemblance_noms": .9, "match_id_reference": "poly1"}}


def consensus(pid="c", composantes=COMPOSANTES, **kw):
    p = pari(pid, reference="Consensus", **{**BON, **kw})
    p["preuve_prise"] = {"match_id_reference": None, "ressemblance_noms": None,
                         "controle": {"statut": "conforme"}, "preuves_composantes": composantes}
    return p


def test_grok2_mesure_contre_pinnacle_et_plus_contre_smarkets():
    assert GROK_2["reference"] == "Pinnacle" and GROK_2["version"] == "2"
    p = pari("a", **BON)
    assert motif_refus_grok(p, GROK_2) is None and paris_grok_2([p]) == {id(p)}
    for abandonnee in ("Smarkets", "Kalshi", "Betfair"):
        assert motif_refus_grok(pari("a", reference=abandonnee, **BON), GROK_2)


def test_grok2_garde_ses_fourchettes():
    assert motif_refus_grok(pari("a", **{**BON, "cote": 2.1, "cote_juste": 2.0, "ecart": .05}), GROK_2)
    assert motif_refus_grok(pari("a", **{**BON, "cote": 1.5, "cote_juste": 1.48, "ecart": 1.5 / 1.48 - 1}), GROK_2)


def test_grok3_accepte_un_consensus_dont_chaque_composante_est_associee():
    p = consensus()
    assert GROK_3["version"] == "2"
    assert motif_refus_grok(p, GROK_3) is None and paris_grok_3([p]) == {id(p)}


@pytest.mark.parametrize("composantes", [
    None,                                                                     # anciens paris : pas de preuve
    {"Pinnacle": COMPOSANTES["Pinnacle"]},                                    # une seule composante
    {**COMPOSANTES, "Polymarket": {"ressemblance_noms": .8, "match_id_reference": "poly1"}},
    {**COMPOSANTES, "Polymarket": {"ressemblance_noms": .9, "match_id_reference": None}},
    {**COMPOSANTES, "Smarkets": {"ressemblance_noms": .99, "match_id_reference": "sm"}},   # abandonnée
    {"Kalshi": {"ressemblance_noms": .99, "match_id_reference": "k"}, "Polymarket": COMPOSANTES["Polymarket"]},
])
def test_grok3_refuse_un_consensus_sans_preuve_complete_ou_hors_references_sharp(composantes):
    assert motif_refus_grok(consensus(composantes=composantes), GROK_3) == "preuve de correspondance insuffisante"


def test_grok3_refuse_un_controle_non_conforme():
    p = consensus()
    p["preuve_prise"]["controle"] = {"statut": "a_verifier"}
    assert motif_refus_grok(p, GROK_3)


def test_grok1_et_grok5_inchanges():
    # Grok 5 garde la preuve classique : un Consensus sans score propre reste refusé.
    assert motif_refus_grok(consensus(), GROK_5) == "preuve de correspondance insuffisante"
    assert GROK_1["version"] == "1" and GROK_5["version"] == "1"
    p = pari("a", reference="Polymarket", **BON)
    assert motif_refus_grok(p, GROK_1) is None


def test_le_consensus_transporte_la_preuve_de_ses_composantes_sans_score_propre():
    fr = [ligne(cote=2.4, issue="PLUS"), ligne(cote=2., issue="MOINS")]
    index = {"Pinnacle": {"m1": {}}, "Polymarket": {"m1": {}}}
    for l in fr:
        for ref, p, score in [("Pinnacle", .4 if l["issue"] == "PLUS" else .6, .97), ("Polymarket", .5, .88)]:
            index[ref]["m1"][cle(l)] = {**l, "proba_juste": p, "cote": 1 / p,
                                        "score_association": score, "match_id": ref + "-id"}
    out = comparer(fr, {"Pinnacle": [], "Polymarket": []}, index=index)
    c = next(o for o in out if o["reference"] == "Consensus")
    assert c["preuves_composantes"] == {
        "Pinnacle": {"ressemblance_noms": .97, "match_id_reference": "Pinnacle-id"},
        "Polymarket": {"ressemblance_noms": .88, "match_id_reference": "Polymarket-id"}}
    # Les champs lus par les règles figées restent vides pour le Consensus.
    assert c["score_association"] is None and c["match_id_reference"] is None
    assert all(o.get("preuves_composantes") is None for o in out if o["reference"] != "Consensus")


def test_la_prise_enregistre_la_preuve_des_composantes():
    from datetime import datetime, timezone
    from cotes.simulation import placer
    o = {"ecart": 0.05, "cote": 2.1, "reference": "Consensus", "match_id": "winamax|1",
         "detecte": "2026-10-07T10:00:00+00:00", "bookmaker": "Winamax", "sport": "football",
         "domicile": "Lens", "exterieur": "Lille", "debut": "2026-10-07T18:00:00+00:00",
         "marche": "RESULTAT_1N2", "periode": "MATCH", "issue": "DOM", "pari": "Lens", "cote_juste": 2.0,
         "composantes": {"Pinnacle": 2.01, "Polymarket": 1.99}, "preuves_composantes": COMPOSANTES,
         "lu_reference": "2026-10-07T10:00:00Z",
         "lectures_references": {"Pinnacle": "2026-10-07T09:59:00Z", "Polymarket": "2026-10-07T10:00:00Z"},
         "controle": {"statut": "conforme", "n": 40, "mediane": 0.93}}
    p = placer([o], [], datetime(2026, 10, 7, 10, tzinfo=timezone.utc))[0]
    assert p["preuve_prise"]["preuves_composantes"] == COMPOSANTES
    assert p["preuve_prise"]["ressemblance_noms"] is None
