from cotes.sources_resultats import SOURCES, ou_chercher


def test_ligue_puis_sport():
    s = ou_chercher("handball", "Ligue des Champions F")
    assert s[0]["nom"] == "EHF Champions League"
    assert s[-1]["url"] == "https://www.eurohandball.com/"


def test_accents_et_casse():
    assert any("sportacentrs" in x["url"] for x in ou_chercher("football", "VIRSLĪGA"))
    assert any("ffbb" in x["url"] for x in ou_chercher("basket", "ÉLITE 2"))


def test_sport_inconnu_ou_ligue_absente():
    assert ou_chercher("curling", "x") == []
    assert ou_chercher("snooker", None)[0]["nom"] == "snooker.org"


def test_registre_bien_forme():
    for regles in SOURCES.values():
        for cles, sites in regles:
            assert cles and sites
            for nom, url in sites:
                assert nom and url.startswith("https://")


def test_liste_a_saisir_donne_ou_chercher():
    from cotes.resultats import a_saisir
    p = {"id": "x", "statut": "a_regler", "match_id": "pmu|1", "sport": "snooker", "ligue": "Champion des Champions",
         "domicile": "A", "exterieur": "B", "debut": "2026-11-09T14:00:00+00:00", "periode": "MATCH",
         "marche": "VAINQUEUR", "bookmaker": "PMU"}
    assert a_saisir([p], [])[0]["ou_chercher"][0]["nom"] == "snooker.org"
