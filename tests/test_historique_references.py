"""Phase 0 de l'analyse du marché : historique des références, relevé des sources, rapprochements, retraits."""
import gzip
import json
from datetime import datetime, timedelta, timezone

from cotes import historique_cotes, historique_references as H

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)


def lu(dt):
    return dt.isoformat(timespec="seconds")


def pin(issue="DOM", p=0.5, t=NOW, mid=111, **kw):
    return {"source": "pinnacle", "match_id": mid, "sport": "football", "ligue": "L1", "domicile": "Lens",
            "exterieur": "Lille", "debut": "2026-11-12T20:00:00Z", "marche": "RESULTAT_1N2", "periode": "MATCH",
            "ligne": None, "issue": issue, "proba_juste": p, "cote_juste": round(1 / p, 4) if p else None, "collecte": lu(t),
            "marge_pinnacle": 0.03, "mise_max": 500, **kw}


def lire(donnees, dossier, jour="2026-11-12"):
    with gzip.open(donnees / dossier / f"{jour}.jsonl.gz", "rt") as f:
        return [json.loads(x) for x in f]


def test_references_ecrites_seulement_au_changement(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path / "memoire"))
    refs = {"Pinnacle": [pin(), pin("EXT", 0.3)]}
    assert H.ajouter_references(tmp_path, refs, NOW) == 3                     # description + 2 cotes
    plus_tard = NOW + timedelta(minutes=5)
    refs = {"Pinnacle": [pin(t=plus_tard), pin("EXT", 0.31, t=plus_tard)]}
    assert H.ajouter_references(tmp_path, refs, plus_tard) == 1
    hist = lire(tmp_path, "references")
    assert hist[0] == {"t": lu(NOW), "b": "Pinnacle", "m": 111, "sport": "football", "ligue": "L1", "dom": "Lens",
                       "ext": "Lille", "debut": "2026-11-12T20:00:00Z"}
    assert hist[-1] == {"t": lu(plus_tard), "b": "Pinnacle", "m": 111, "k": "RESULTAT_1N2|MATCH||EXT",
                        "c": 3.226, "p": 0.31, "mg": 0.03, "max": 500.0}


def test_retrait_seulement_si_le_match_est_relu(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path / "memoire"))
    H.ajouter_references(tmp_path, {"Pinnacle": [pin(), pin("EXT", 0.3), pin(mid=222)]}, NOW)
    plus_tard = NOW + timedelta(minutes=5)
    # match 111 relu sans EXT -> retrait ; match 222 absent du cycle -> rien (absence inconnue)
    assert H.ajouter_references(tmp_path, {"Pinnacle": [pin(t=plus_tard)]}, plus_tard) == 1
    assert lire(tmp_path, "references")[-1] == {"t": lu(plus_tard), "b": "Pinnacle", "m": 111,
                                                "k": "RESULTAT_1N2|MATCH||EXT", "c": None}
    # reprise d'une lecture ancienne (référence en panne) : pas fraîche, pas de retrait
    encore = plus_tard + timedelta(minutes=5)
    lignes, _ = H.changements({"Pinnacle\t111\tRESULTAT_1N2|MATCH||NUL": 3.0}, {"Pinnacle": [pin(t=NOW)]}, encore)
    assert [x for x in lignes if x.get("c") is None] == []


def test_ligne_sans_proba_juste_ignoree_et_champs_des_bourses():
    lignes, etat = H.changements({}, {"Smarkets": [pin(p=None), pin("EXT", 0.4, liquidite=35.5,
                                                                    ecart_achat_vente=0.012, marge_pinnacle=None,
                                                                    mise_max=None)]}, NOW)
    assert len(etat) == 1
    assert lignes[-1] == {"t": lu(NOW), "b": "Smarkets", "m": 111, "k": "RESULTAT_1N2|MATCH||EXT", "c": 2.5,
                          "p": 0.4, "liq": 35.5, "ea": 0.012}


def test_releve_distingue_source_lue_et_non_lue():
    vieux = NOW - timedelta(hours=1)
    francais = [{"source": "PMU", "match_id": "pmu|1", "collecte": lu(NOW + timedelta(seconds=30))},
                {"source": "PMU", "match_id": "pmu|2", "collecte": lu(NOW + timedelta(seconds=40))},
                {"source": "Unibet", "match_id": "u|1", "collecte": lu(vieux)}]
    r = H.releve(francais, {"Pinnacle": [pin()]}, NOW)
    assert r == {"t": lu(NOW), "sources": {"PMU": {"lignes": 2, "fraiches": 2, "matchs": 2},
                                           "Pinnacle": {"lignes": 1, "fraiches": 1, "matchs": 1},
                                           "Unibet": {"lignes": 1, "fraiches": 0, "matchs": 0}}}


def test_correspondances_ecrites_une_fois_par_jour(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path / "memoire"))
    index = {"Pinnacle": {"pmu|1": {"k": {"match_id": 111, "inverse": True, "score_association": 0.93}}},
             "Polymarket": {}}
    assert H.ajouter_correspondances(tmp_path, index, NOW) == 1
    assert H.ajouter_correspondances(tmp_path, {"Pinnacle": {}}, NOW + timedelta(minutes=5)) == 0
    assert H.ajouter_correspondances(tmp_path, index, NOW + timedelta(hours=1)) == 0
    assert H.ajouter_correspondances(tmp_path, index, NOW + timedelta(hours=25)) == 1
    assert lire(tmp_path, "correspondances")[0] == {"t": lu(NOW), "fr": "pmu|1", "b": "Pinnacle", "m": 111,
                                                    "inv": True, "s": 0.93}


def test_enregistrer_les_trois_fichiers(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path / "memoire"))
    out = H.enregistrer(tmp_path, [], {"Pinnacle": [pin()]},
                        {"Pinnacle": {"pmu|1": {"k": {"match_id": 111}}}}, NOW)
    assert out == {"references": 2, "releves": 1, "correspondances": 1}


def test_retrait_d_une_cote_bookmaker_dans_un_match_relu():
    def l(issue, cote, t, mid="pmu|1"):
        return {"source": "PMU", "match_id": mid, "marche": "RESULTAT_1N2", "periode": "MATCH", "ligne": None,
                "issue": issue, "cote": cote, "collecte": lu(t)}
    vieux = NOW - timedelta(minutes=5)
    avant = historique_cotes.index({"pmu": {"lignes": [l("DOM", 2.0, vieux), l("EXT", 3.0, vieux),
                                                       l("DOM", 1.5, vieux, "pmu|2"), l("EXT", 2.5, vieux, "pmu|2")]}})
    # pmu|1 relu sans EXT ; pmu|2 gardé en mémoire sans relecture (lecture tournante) et sans EXT
    horizon = {"pmu": {"lignes": [l("DOM", 2.0, NOW), l("DOM", 1.5, vieux, "pmu|2")]}}
    assert historique_cotes.changements(avant, horizon, NOW) == [
        {"t": lu(NOW), "b": "PMU", "m": "pmu|1", "k": "RESULTAT_1N2|MATCH||EXT", "c": None}]
    assert historique_cotes.changements(avant, horizon) == []                # sans heure de cycle : comme avant


def test_dossiers_journaliers_alignes():
    import scripts.archiver_donnees_brutes as A
    import scripts.serveur_direct as SD
    from pathlib import Path
    assert set(H.DOSSIERS) <= set(SD.JOURNALIERS) == set(A.DOSSIERS)
    script = (Path(__file__).resolve().parent.parent / "scripts" / "cloner_donnees.sh").read_text()
    assert all(d in script for d in SD.JOURNALIERS)
