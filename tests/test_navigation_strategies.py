"""Les liens Stratégies → Paris utilisent les sélections exactes, sans troncature."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import site_web  # noqa: E402
from cotes.laboratoire import REGLES  # noqa: E402


def pari(pid, detection, debut, statut):
    cote, juste = 1.75, 1.68
    return {
        "id": pid, "simulation": "C", "reference": "Pinnacle",
        "bookmaker": "Winamax", "sport": "football", "marche": "VAINQUEUR",
        "periode": "MATCH", "issue": "DOM", "ligne": None,
        "match_id": "w|" + pid, "domicile": "A", "exterieur": "B",
        "detecte": detection, "debut": debut, "lu_reference": detection,
        "cote": cote, "cote_juste": juste, "ecart": cote/juste - 1,
        "statut": statut, "gain": 7.5 if statut == "gagne" else None,
        "pari": "A", "mise": 10,
        "preuve_prise": {
            "match_id_reference": pid, "ressemblance_noms": .95,
            "controle": {"statut": "conforme"}
        }
    }


def test_navigation_paris_historique_et_futur():
    passe = pari("ancien", "2026-10-08T09:00:00+00:00",
                 "2026-10-08T12:00:00+00:00", "gagne")
    futur = pari("avenir", "2026-10-14T12:10:00+00:00",
                 "2026-10-14T18:00:00+00:00", "en_cours")
    # Un pari non sélectionné ne doit pas figurer dans les cartes envoyées à Paris.
    autre = {**pari("autre", "2026-10-14T12:10:00+00:00",
                   "2026-10-14T18:00:00+00:00", "en_cours"), "reference": "Kalshi"}
    r = REGLES[0]
    labo = {"releve": "2026-10-14T10:09:28+00:00",
            "resultats": [{"regle": r.dict(), "ids_selections": ["ancien"]}],
            "comparateurs": {}}
    nav = site_web.navigation_strategies([passe, futur, autre], labo,
                                        "2026-10-14T16:00:00+00:00")
    selections = nav["selections"][r.id]
    assert selections["ensemble"] == ["ancien"]
    assert selections["construction"] == ["ancien"]
    assert selections["validation"] == []
    assert selections["futur"] == ["avenir"]
    assert set(nav["paris"]) == {"ancien", "avenir"}
    assert nav["paris"]["ancien"]["statut"] == "gagne"
    assert nav["paris"]["avenir"]["statut"] == "en_cours"


def test_garde_les_paris_hors_limite_des_fiches():
    ancien = pari("historique", "2026-10-08T09:00:00+00:00",
                  "2026-10-08T12:00:00+00:00", "gagne")
    r = REGLES[0]
    # La navigation passe par les IDs d'origine, et non par les 600 dernières fiches.
    labo = {"releve": "2026-10-14T10:09:28+00:00",
            "resultats": [{"regle": r.dict(), "ids_selections": ["historique"]}],
            "comparateurs": {}}
    nav = site_web.navigation_strategies([ancien], labo,
                                        "2026-10-14T16:00:00+00:00")
    assert nav["paris"]["historique"]["bookmaker"] == "Winamax"
