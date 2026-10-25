"""Dernier bon état des références : reprise d'un sport manquant, âge réel, jamais un match retiré ou commencé."""
import gzip
from datetime import datetime, timedelta, timezone

from cotes import reprise as R
from cotes import simulation as S
from cotes.comparaison import comparer
from cotes.marches import cle
from tests.test_controle import ligne

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def pin(sport="football", match="p1", age=60, lu=T0, debut_h=5, **k):
    return {"sport": sport, "match_id": match, "marche": "TOTAL", "periode": "MATCH", "ligne": 2.5, "issue": "PLUS",
            "cote": 1.95, "debut": (lu + timedelta(hours=debut_h)).isoformat(), "collecte": lu.isoformat(),
            "age_cache_s": age, "cote_perimee": False, **k}


def poly(sport="football", lu=T0, debut_h=5):
    return {"sport": sport, "match_id": "y1", "debut": (lu + timedelta(hours=debut_h)).isoformat(),
            "collecte": lu.isoformat(), "proba_juste": .5}


def test_sport_absent_repris_avec_son_age_reel_et_sa_lecture_d_origine(tmp_path):
    chemin = tmp_path / "r.json.gz"
    R.appliquer(chemin, {"Pinnacle": [pin(), pin("tennis", "t1")], "Polymarket": []}, T0)
    plus_tard = T0 + timedelta(minutes=5)
    repris, resume = R.appliquer(chemin, {"Pinnacle": [pin("tennis", "t1", lu=plus_tard)], "Polymarket": []}, plus_tard)
    assert [l["match_id"] for l in repris["Pinnacle"]] == ["p1"]          # le tennis a été lu : rien de repris
    l = repris["Pinnacle"][0]
    assert l["reprise"] is True and l["collecte"] == T0.isoformat()
    assert l["age_cache_s"] == 60 + 300 and l["cote_perimee"] is False
    assert resume == {"actif": True, "Pinnacle": {"football": 1}}


def test_un_match_retire_d_un_sport_lu_ne_revient_pas(tmp_path):
    chemin = tmp_path / "r.json.gz"
    R.appliquer(chemin, {"Pinnacle": [pin(match="p1"), pin(match="p2")]}, T0)
    repris, _ = R.appliquer(chemin, {"Pinnacle": [pin(match="p1", lu=T0 + timedelta(minutes=5))]},
                            T0 + timedelta(minutes=5))
    assert repris["Pinnacle"] == []


def test_seuils_de_fraicheur_de_pinnacle_proche_et_loin(tmp_path, monkeypatch):
    monkeypatch.delenv("PINNACLE_AGE_MAX_MIN", raising=False)
    monkeypatch.delenv("PINNACLE_AGE_MAX_LOIN_MIN", raising=False)
    stock = {"Pinnacle": {"football": {"lu": T0.isoformat(), "lignes": [pin(match="proche", debut_h=1),
                                                                       pin(match="loin", debut_h=5)]}}}
    ids = lambda minutes: [l["match_id"] for l in
                           R.completer("Pinnacle", [], stock, R.Seuils(T0 + timedelta(minutes=minutes)))[0]]
    assert ids(9) == ["proche", "loin"]                     # 60 s + 9 min : sous les 10 min du seuil court
    assert ids(10) == ["loin"]                              # 11 min : trop vieux pour un match dans les 2 h
    assert ids(15) == ["loin"]                              # 16 min tout juste : seuil long encore tenu
    assert ids(16) == []                                    # 17 min : au-delà du seuil long


def test_polymarket_vieillit_depuis_sa_lecture(tmp_path):
    stock = {"Polymarket": {"football": {"lu": T0.isoformat(), "lignes": [poly()]}}}
    assert len(R.completer("Polymarket", [], stock, R.Seuils(T0 + timedelta(minutes=9)))[0]) == 1
    assert R.completer("Polymarket", [], stock, R.Seuils(T0 + timedelta(minutes=17)))[0] == []


def test_match_commence_lecture_non_datee_ou_age_inconnu_jamais_repris():
    lignes = [pin(debut_h=-1), pin(collecte=None), pin(age=None), pin(age=True),
              pin(collecte=(T0 + timedelta(minutes=5)).isoformat())]
    stock = {"Pinnacle": {"football": {"lu": T0.isoformat(), "lignes": lignes}}}
    assert R.completer("Pinnacle", [], stock, R.Seuils(T0))[0] == []


def test_meme_regle_que_pinnacle_est_perimee(monkeypatch):
    from cotes import pinnacle
    monkeypatch.setenv("PINNACLE_AGE_MAX_MIN", "7")
    monkeypatch.setenv("PINNACLE_AGE_MAX_LOIN_MIN", "13")
    seuils = R.Seuils(T0)
    for debut_min in (30, 119, 120, 121, 600):
        for age in range(0, 1000, 30):
            l = pin(age=age, debut_h=debut_min / 60)
            assert (seuils.age("Pinnacle", l) is None) == pinnacle.est_perimee(age, l["debut"], T0)


def test_une_ligne_reprise_n_est_pas_rememorisee_son_age_continue(tmp_path):
    chemin = tmp_path / "r.json.gz"
    R.appliquer(chemin, {"Pinnacle": [pin()]}, T0)
    for minutes, attendu in ((5, 360), (10, 660), (17, None)):
        repris, _ = R.appliquer(chemin, {"Pinnacle": []}, T0 + timedelta(minutes=minutes))
        assert [l["age_cache_s"] for l in repris["Pinnacle"]] == ([attendu] if attendu else [])
    assert R.lire(chemin) == {}                             # plus rien d'utilisable : fichier vidé


def test_fichier_absent_illisible_ou_desactive_aucune_reprise_sans_erreur(tmp_path):
    assert R.appliquer(None, {"Pinnacle": []}, T0) == ({"Pinnacle": []}, {"actif": False})
    abime = tmp_path / "r.json.gz"
    abime.write_bytes(b"pas du gzip")
    assert R.appliquer(abime, {"Pinnacle": []}, T0)[0] == {"Pinnacle": []}
    tronque = tmp_path / "t.json.gz"
    tronque.write_bytes(gzip.compress(b'{"Pinnacle": {"football": [')[:-4])
    assert R.appliquer(tronque, {"Pinnacle": []}, T0)[0] == {"Pinnacle": []}


def test_une_ecriture_ratee_garde_les_reprises_du_cycle(tmp_path, monkeypatch):
    chemin = tmp_path / "r.json.gz"
    R.appliquer(chemin, {"Pinnacle": [pin()]}, T0)

    def refus(*a, **k):
        raise OSError("disque plein")
    monkeypatch.setattr(R, "ecrire", refus)
    repris, resume = R.appliquer(chemin, {"Pinnacle": []}, T0 + timedelta(minutes=5))
    assert len(repris["Pinnacle"]) == 1 and resume["ecriture"] == "OSError"


def _comparer(reprise_ref: bool):
    maintenant = datetime.now(timezone.utc)
    fr = ligne(cote=2.2, collecte=maintenant.isoformat(), debut=(maintenant + timedelta(hours=2)).isoformat())
    ref = {**fr, "proba_juste": .5, "collecte": (maintenant - timedelta(minutes=5)).isoformat()}
    if reprise_ref:
        ref["reprise"] = True
    index = {"Pinnacle": {fr["match_id"]: {cle(fr): ref}}}
    return comparer([fr], {"Pinnacle": []}, index=index), maintenant


def test_opportunite_et_pari_tracent_une_reference_reprise():
    out, maintenant = _comparer(True)
    assert out[0]["reference_reprise"] is True
    p = S.placer(out, [], maintenant)[0]
    assert p["preuve_prise"]["reference_reprise"] is True


def test_sans_reprise_aucun_champ_ajoute():
    out, maintenant = _comparer(False)
    assert "reference_reprise" not in out[0]
    assert "reference_reprise" not in S.placer(out, [], maintenant)[0]["preuve_prise"]


def test_cycle_pinnacle_en_panne_reprend_le_sport_et_garde_la_panne_visible(tmp_path, monkeypatch):
    from scripts import cycle
    from tests.test_collecte_parallele import _sans_reseau
    demandes = []
    _sans_reseau(monkeypatch, direct=lambda sports, *a, **k: (demandes.append(set(sports)) or [],
                                                               {"ok": True, "erreurs": [], "requetes": 0}))
    monkeypatch.setattr(cycle.pinnacle_secours, "disponible", lambda: False)
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    monkeypatch.setattr(cycle, "harmoniser_pinnacle", lambda x: x)
    chemin = tmp_path / "reprise" / "derniere_lecture.json.gz"
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [pin()])
    cycle.collecter_prematch("complet", T0, {"etapes": {}}, None, chemin)

    def panne():
        raise RuntimeError("HTTP 403")
    monkeypatch.setattr(cycle.pinnacle, "collecter", panne)
    j = {"etapes": {}}
    pin_lu, _, _ = cycle.collecter_prematch("complet", T0 + timedelta(minutes=5), j, None, chemin)
    assert [l["reprise"] for l in pin_lu] == [True]
    assert demandes[-1] == {"football"}                       # PMU lit encore le football
    assert j["etapes"]["pinnacle"]["ok"] is False and j["etapes"]["pinnacle"]["reprise"] == 1
    assert j["reprise"] == {"actif": True, "Pinnacle": {"football": 1}}


def test_cycle_sans_chemin_aucune_reprise(monkeypatch):
    from scripts import cycle
    from tests.test_collecte_parallele import _sans_reseau
    _sans_reseau(monkeypatch)
    monkeypatch.setattr(cycle.pinnacle, "collecter", lambda: [])
    monkeypatch.setattr(cycle.polymarket, "collecter", lambda *a: [])
    j = {"etapes": {}}
    assert cycle.collecter_prematch("complet", T0, j)[0] == [] and j["reprise"] == {"actif": False}
