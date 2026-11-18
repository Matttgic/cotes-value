"""Protocole de validation (docs/protocole.md) : registre scellé, empreintes des règles, test et lectures."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from cotes import protocole

# Scellés successifs du registre : (nombre d'inscriptions couvertes, SHA-256 des règles communes et de ces inscriptions).
# Le registre ne se modifie pas, il s'allonge : inscrire une stratégie ajoute une ligne ici, sans toucher aux précédentes.
SCELLES = [
    (70, "94faa228f06db04aaf16e855c0a9f604ad5dc594617497357672883fdad94651"),      # gel du 15/11/2026
    (71, "6db1d503e2cbfb5612cdc37e21bbba95eab25a821d3c1307185bd65e7a5d5203"),      # Claude · Drop Pinnacle, 18/11/2026
    (72, "11985c81ed9f91a9e5a91e47caad4b251ac1f8dcd8e2fe38405de769bd01acb4"),      # Claude · Drop z-score, 18/11/2026
]


def test_le_registre_est_scelle_et_ne_peut_que_s_allonger():
    doc = protocole.registre()
    for k, sha in SCELLES:
        assert protocole.scelle(doc, k) == sha, f"les règles ou l'une des {k} premières inscriptions ont changé"
    assert SCELLES[-1][0] == len(doc["inscrites"]), "inscription ajoutée sans son scellé"
    assert len(doc["inscrites"]) <= doc["regles"]["places"]
    assert protocole.alpha(doc["regles"]) == pytest.approx(0.00025)


def test_les_regles_de_chaque_strategie_inscrite_n_ont_pas_change():
    """Les sélecteurs rejoués sur le jeu témoin prennent exactement les mêmes paris qu'au gel. Si ce test échoue,
    une règle a changé : la remettre, ou inscrire la nouvelle version (scripts/protocole.py --inscrire), ce qui
    ferme l'ancien protocole et en ouvre un nouveau."""
    doc = protocole.registre()
    actuelles = protocole.empreintes_actuelles(doc)
    assert actuelles is not None, "jeu témoin absent ou différent de celui du registre"
    dernieres = {e["cle"]: e for e in doc["inscrites"]}
    assert {cle: e["empreinte"] for cle, e in dernieres.items() if cle in actuelles} == \
           {cle: actuelles[cle] for cle in dernieres if cle in actuelles}
    assert set(protocole.definitions()) <= set(dernieres), "stratégie suivie sans inscription au protocole"


def test_le_temoin_ne_contient_aucun_resultat():
    temoin, _ = protocole.lire_temoin()
    assert not any(k in p for p in temoin for k in protocole.CHAMPS_HORS_TEMOIN)


def test_student_et_taille_sur_des_valeurs_connues():
    assert protocole.p_student(2.228, 10) == pytest.approx(0.025, abs=2e-5)       # table de Student
    assert protocole.p_student(3.460, 60) == pytest.approx(0.0005, abs=2e-6)
    assert protocole.p_student(-1.96, 1e6) == pytest.approx(0.975, abs=1e-4)
    assert protocole.p_student(0, 7) == pytest.approx(0.5)
    regles = protocole.registre()["regles"]
    assert protocole.taille(0.12, regles) == 680                                  # ((3,481 + 0,842) × 12 / 2)² = 672,8
    assert protocole.taille(0.01, regles) == regles["n_min"]


def test_les_paris_d_un_meme_match_comptent_pour_une_seule_unite():
    seuls = protocole.moyenne_par_match([0.02, 0.04] * 20, list(range(40)))
    groupes = protocole.moyenne_par_match([0.02, 0.04] * 20, [i // 2 * 2 if i % 4 < 2 else i for i in range(40)])
    assert seuls["moyenne"] == pytest.approx(0.03) and seuls["matchs"] == 40
    assert groupes["matchs"] < 40 and groupes["moyenne"] == pytest.approx(0.03)
    assert protocole.moyenne_par_match([0.05], ["a"])["p"] is None


# ---------------------------------------------------------------- suivi : lectures et verdicts sur des paris fabriqués

DEBUT = datetime(2026, 11, 16, tzinfo=timezone.utc)


def _doc(n=40, **regles):
    r = {"version": 1, "debut": DEBUT.isoformat(), "duree_jours": 365, "places": 200, "alpha_famille": 0.05,
         "puissance": 0.8, "effet": 0.02, "part_mi_parcours": 0.5, "couverture_min": 0.5, "alpha_roi": 0.025,
         "matchs_min": 20, "cote_max": 5.0, "n_min": 300, "sigma_defaut": 0.12, "sigma_mesures_min": 50,
         "temoin_sha256": "x", **regles}
    return {"regles": r, "inscrites": [{"cle": "essai", "ligne": "Essai", "nom": "Essai", "version": "1",
                                        "debut": DEBUT.isoformat(), "sigma": 0.1, "sigma_mesures": 0, "n": n,
                                        "empreinte": "abc"}]}


def _pari(i, clv, jour=1, reference="Pinnacle", gagne=None, mesure=True):
    debut = DEBUT + timedelta(days=jour, hours=i % 20, minutes=i % 50)
    gagne = i % 2 == 0 if gagne is None else gagne
    p = {"id": f"p{jour}-{i}", "reference": reference, "bookmaker": "PMU", "sport": "football", "match_id": f"pmu|{jour}-{i}",
         "marche": "VAINQUEUR", "periode": "MATCH", "ligne": None, "issue": "DOM", "cote": 2.0, "mise": 10.0,
         "detecte": (debut - timedelta(hours=3)).isoformat(), "debut": debut.isoformat(),
         "statut": "gagne" if gagne else "perdu", "gain": 10.0 if gagne else -10.0,
         "regle_le": (debut + timedelta(hours=2)).isoformat()}
    if mesure:
        p.update(clv=clv, cote_juste_cloture=round(2.0 / (1 + clv), 4), cloture_lue=(debut - timedelta(minutes=10)).isoformat())
    return p


def _suivre(paris, donnees, doc, jours=30, actuelles=None, **plus):
    return protocole.suivre(paris, {"essai": {id(p) for p in paris}}, donnees, DEBUT + timedelta(days=jours),
                            actuelles, doc=doc, **plus)["lignes"]["Essai"]


def test_aucun_verdict_avant_la_mi_parcours(tmp_path):
    paris = [_pari(i, 0.05) for i in range(19)]
    l = _suivre(paris, tmp_path, _doc())
    assert l["statut"] == "en_cours" and l["mesures"] == 19 and l["mi_parcours"] is None
    assert not (tmp_path / protocole.FICHIER).exists()


def test_succes_a_la_lecture_finale_puis_lecture_jamais_recalculee(tmp_path):
    paris = [_pari(i, 0.05 + 0.01 * (i % 3)) for i in range(40)]            # CLV de +5 à +7 %, 40 matchs
    l = _suivre(paris, tmp_path, _doc())
    assert l["statut"] == "succes" and l["finale"]["n"] == 40 and l["finale"]["p"] < 0.00025
    assert l["mi_parcours"]["n"] == 20 and l["mi_parcours"]["motif"] is None
    ecrit = (tmp_path / protocole.FICHIER).read_text()
    # De nouveaux paris, même très mauvais, ne rouvrent pas un protocole clos.
    encore = _suivre(paris + [_pari(i, -0.30, jour=5) for i in range(60)], tmp_path, _doc(), jours=60)
    assert encore["statut"] == "succes" and encore["finale"] == l["finale"]
    assert (tmp_path / protocole.FICHIER).read_text() == ecrit


def test_echec_si_la_clv_est_positive_mais_pas_au_seuil_du_protocole(tmp_path):
    paris = [_pari(i, 0.30 if i % 2 else -0.26) for i in range(40)]         # moyenne +2 %, très dispersée
    l = _suivre(paris, tmp_path, _doc())
    assert l["statut"] == "echec" and l["finale"]["clv"] == pytest.approx(2.0) and "non prouvée" in l["motif"]


def test_echec_anticipe_si_la_clv_est_negative_a_mi_parcours(tmp_path):
    paris = [_pari(i, -0.02) for i in range(20)] + [_pari(i, 0.20, jour=2) for i in range(20)]
    l = _suivre(paris, tmp_path, _doc())
    assert l["statut"] == "echec" and l["finale"]["anticipe"] and "mi-parcours" in l["motif"]
    assert l["mi_parcours"]["n"] == 20 and l["mi_parcours"]["clv"] == pytest.approx(-2.0)


def test_echec_si_le_rendement_dement_la_clv(tmp_path):
    paris = [_pari(i, 0.06, gagne=i % 8 == 0) for i in range(40)]           # CLV +6 %, mais 5 gagnés sur 40
    l = _suivre(paris, tmp_path, _doc())
    assert l["statut"] == "echec" and "sous leur CLV" in l["motif"]


def test_echec_si_la_cloture_pinnacle_manque_a_plus_de_la_moitie_des_regles(tmp_path):
    paris = [_pari(i, 0.06) for i in range(40)] + [_pari(100 + i, 0, reference="Polymarket", mesure=False) for i in range(60)]
    l = _suivre(paris, tmp_path, _doc())
    assert l["statut"] == "echec" and l["finale"]["couverture"] < 50 and "moins de la moitié" in l["motif"]


def test_les_paris_d_avant_le_debut_et_non_regles_ne_comptent_pas(tmp_path):
    avant = [_pari(i, 0.05, jour=-3) for i in range(40)]
    en_cours = [{**_pari(i, 0.05, jour=2), "statut": "en_cours", "gain": None} for i in range(40)]
    l = _suivre(avant + en_cours, tmp_path, _doc())
    assert l["statut"] == "en_cours" and l["paris"] == 40 and l["regles"] == 0 and l["mesures"] == 0


def test_echeance_sans_volume_puis_lecture_finale_sur_les_paris_disponibles(tmp_path):
    peu = _suivre([_pari(i, 0.05) for i in range(10)], tmp_path / "a", _doc(), jours=366)
    assert peu["statut"] == "echec" and "échéance" in peu["motif"]
    (tmp_path / "b").mkdir()
    paris = [_pari(i, 0.05 + 0.01 * (i % 3)) for i in range(30)]            # mi-parcours passée, 30 mesurés sur 40
    assert _suivre(paris, tmp_path / "b", _doc(), jours=30)["statut"] == "en_cours"
    fin = _suivre(paris, tmp_path / "b", _doc(), jours=366)
    assert fin["statut"] == "succes" and fin["finale"]["n"] == 30


def test_regles_modifiees_le_protocole_est_rompu_et_le_reste(tmp_path):
    paris = [_pari(i, 0.05) for i in range(40)]
    l = _suivre(paris, tmp_path, _doc(), actuelles={"essai": "autre"})
    assert l["statut"] == "rompu" and l["finale"] is None
    # Même si le code revient en arrière, les paris pris entre-temps ne sont plus ceux de la règle inscrite.
    assert _suivre(paris, tmp_path, _doc(), actuelles={"essai": "abc"})["statut"] == "rompu"


def test_une_nouvelle_version_ferme_l_ancien_protocole_et_repart_de_zero(tmp_path):
    doc = _doc()
    depart = DEBUT + timedelta(days=10)
    doc["inscrites"].append({**doc["inscrites"][0], "version": "2", "debut": depart.isoformat(), "empreinte": "def"})
    paris = [_pari(i, 0.05) for i in range(15)] + [_pari(i, 0.05, jour=12) for i in range(5)]
    l = _suivre(paris, tmp_path, doc, actuelles={"essai": "def"})
    assert l["version"] == "2" and l["statut"] == "en_cours" and l["mesures"] == 5
    etat = json.loads((tmp_path / protocole.FICHIER).read_text())["lectures"]
    assert etat["essai@1"]["finale"]["motif"] == "remplacee"


def test_strategie_en_pause_ou_en_erreur(tmp_path, monkeypatch):
    from cotes import pauses
    paris = [_pari(i, 0.05) for i in range(40)]
    assert _suivre(paris, tmp_path / "a", _doc(), indisponibles={"essai"})["statut"] == "en_cours"   # aucune lecture
    monkeypatch.setattr(pauses, "_ACTIVES", {"essai": DEBUT})
    l = _suivre(paris[:5], tmp_path, _doc())
    assert l["statut"] == "echec" and "pause" in l["motif"]


def test_cloture_pinnacle_reprise_du_meme_pari_repere_par_pinnacle():
    pin = _pari(1, 0.05)
    frere = {**_pari(1, 0.0, reference="Polymarket", mesure=False), "id": "frere", "cote": 2.2}
    assert protocole.clv_pinnacle([pin, frere])[id(frere)] == pytest.approx(2.2 / pin["cote_juste_cloture"] - 1)
