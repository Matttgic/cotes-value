"""Dérive des sources : volume, marchés disparus, non reconnus, cotes figées, alerte (cotes/derive.py)."""
from datetime import datetime, timedelta, timezone

from cotes import derive, surveillance

T0 = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


def lignes(matchs=40, marches=("RESULTAT_1N2", "TOTAL"), sport="football", book="betclic", cote=1.9):
    return [{"bookmaker": book, "sport": sport, "match_id": f"{book}|{i}", "marche": m, "periode": "MATCH",
             "ligne": None, "issue": issue, "cote": cote, "joueur": None}
            for i in range(matchs) for m in marches for issue in ("A", "B", "C")]


def rejouer(etat, source, suite, debut=T0, pas=5, inconnus=None):
    """Passe une suite de lectures (une toutes les ``pas`` minutes) ; rend l'état et les constats de chaque cycle."""
    vus = []
    for i, l in enumerate(suite):
        m = derive.mesurer(l)
        if inconnus is not None:
            m["inconnus"], m["frequents"] = inconnus[i], [("Nouveau libellé #", inconnus[i])]
        etat, constats = derive.suivre(etat, {source: m}, debut + timedelta(minutes=pas * i))
        vus.append(constats.get(source, []))
    return etat, vus


def genres(constats):
    return [c["genre"] for c in constats]


def variees(n, tour):
    """Lecture normale : même volume, une cote qui bouge à chaque cycle."""
    l = lignes(n)
    l[0] = {**l[0], "cote": 1.5 + tour / 100}
    return l


def test_mesurer_compte_et_empreinte():
    a = lignes(12)
    m = derive.mesurer(a)
    assert (m["lignes"], m["matchs"], m["sports"]) == (72, 12, {"football": 12})
    assert m["couverture"] == {"football RESULTAT_1N2 MATCH": 1.0, "football TOTAL MATCH": 1.0}
    assert derive.mesurer(list(reversed(a)))["empreinte"] == m["empreinte"]
    assert derive.mesurer([{**a[0], "cote": 2.0}] + a[1:])["empreinte"] != m["empreinte"]
    assert derive.mesurer(lignes(5))["couverture"] == {}           # moins de 10 matchs : marchés non mesurés
    assert derive.mesurer(a, prix=False)["empreinte"] == 0


def test_chute_de_volume_apres_rodage_et_duree():
    normal = [variees(40, i) for i in range(14)]                    # 65 min d'apprentissage
    chute = [variees(12, i) for i in range(6)]
    etat, vus = rejouer({}, "betclic", normal + chute)
    assert all(not v for v in vus[:14])
    assert [genres(v) for v in vus[14:17]] == [[], [], []]          # moins de 15 min : pas encore
    assert genres(vus[17]) == ["volume"] and vus[17][0]["nouveau"] is True
    assert "72 cotes, 240 d'habitude" in vus[17][0]["detail"]
    assert vus[18][0]["nouveau"] is False                            # déjà signalé
    assert etat["betclic"]["series"]["lignes"]["ref"] == 240.0       # l'habitude ne suit pas l'anomalie
    etat, vus = rejouer(etat, "betclic", [variees(40, 50)], debut=T0 + timedelta(minutes=100))
    assert vus == [[]] and etat["betclic"]["alertes"] == {}


def test_lecture_vide_sans_erreur_est_une_chute():
    _, vus = rejouer({}, "pmu", [variees(40, i) for i in range(14)] + [[]] * 5)
    assert genres(vus[-1]) == ["volume"] and "0 cotes" in vus[-1][0]["detail"]


def test_baisse_lente_et_rodage_ne_declenchent_rien():
    lente = [variees(max(60 - i, 20), i) for i in range(40)]         # −2 % par cycle : la soirée se vide
    assert all(not v for v in rejouer({}, "betclic", lente)[1])
    assert all(not v for v in rejouer({}, "betclic", [variees(40, 0), variees(5, 1), variees(5, 2), variees(5, 3)])[1])


def test_nouveau_niveau_adopte_apres_six_heures():
    suite = [variees(40, i) for i in range(14)] + [variees(12, i) for i in range(75)]
    etat, vus = rejouer({}, "betclic", suite)
    assert genres(vus[20]) == ["volume"] and vus[-1] == []
    assert etat["betclic"]["series"]["lignes"]["ref"] == 72.0


def test_marche_disparu_seulement_si_le_sport_est_la():
    normal = [variees(40, i) for i in range(14)]
    sans_total = []
    for i in range(5):
        l = lignes(40, marches=("RESULTAT_1N2",))
        l[0] = {**l[0], "cote": 1.5 + i / 100}
        sans_total.append(l)
    _, vus = rejouer({}, "betclic", normal + sans_total)
    assert "marche" in genres(vus[-1])
    detail = next(c["detail"] for c in vus[-1] if c["genre"] == "marche")
    assert "football TOTAL MATCH (0% des matchs, 100% d'habitude)" in detail
    tennis = [lignes(40, marches=("VAINQUEUR",), sport="tennis") for _ in range(5)]
    _, vus = rejouer({}, "betclic", normal + tennis)                 # plus de football du tout : rien à dire
    assert "marche" not in genres(vus[-1])


def test_hausse_des_marches_non_reconnus():
    suite = [variees(40, i) for i in range(20)]
    _, vus = rejouer({}, "pmu", suite, inconnus=[20] * 14 + [200] * 6)
    assert genres(vus[-1]) == ["inconnus"]
    assert "45% d'offres non reconnues, 8% d'habitude" in vus[-1][0]["detail"] and "« Nouveau libellé # » ×200" in vus[-1][0]["detail"]
    _, vus = rejouer({}, "pmu", suite, inconnus=[20] * 14 + [30] * 6)   # 8 % puis 11 % : pas une dérive
    assert vus[-1] == []


def test_cotes_figees_selon_le_bookmaker():
    memes = [lignes(40)] * 11                                        # 50 min sans aucun changement
    assert genres(rejouer({}, "betclic", memes)[1][-1]) == ["figees"]
    assert rejouer({}, "pmu", memes)[1][-1] == []                    # PMU : 60 min
    assert genres(rejouer({}, "pmu", [lignes(40)] * 14)[1][-1]) == ["figees"]
    assert rejouer({}, "pinnacle", [lignes(40)] * 60)[1][-1] == []   # références : pas de seuil réglé
    assert rejouer({}, "betclic", [lignes(10)] * 12)[1][-1] == []    # trop peu de cotes pour conclure
    bouge = [lignes(40)] * 8 + [variees(40, 1)] + [lignes(40)] * 8   # un changement remet l'horloge à zéro
    assert all(not v for v in rejouer({}, "betclic", bouge)[1])


def test_retour_de_panne_remet_l_horloge_des_prix_a_zero():
    etat, _ = rejouer({}, "betclic", [lignes(40)] * 3)
    etat, vus = rejouer(etat, "betclic", [lignes(40)], debut=T0 + timedelta(minutes=120))
    assert vus == [[]] and etat["betclic"]["prix"]["change"] == (T0 + timedelta(minutes=120)).isoformat(timespec="seconds")


def test_source_non_mesuree_garde_son_etat():
    etat, _ = rejouer({}, "betclic", [lignes(40)] * 2)
    suivant, constats = derive.suivre(etat, {"pmu": derive.mesurer(lignes(40, book="pmu"))}, T0 + timedelta(minutes=10))
    assert suivant["betclic"] == etat["betclic"] and "pmu" in suivant and constats == {}


def test_mesures_du_cycle_ecarte_pannes_caches_et_sources_coupees():
    etapes = {"pmu_direct": {"ok": True}, "betclic_direct": {"ok": False}, "smarkets": {"ok": True, "cache": True},
              "matchbook": {"ok": True, "desactive": True}, "winamax_direct": {"ok": True}, "pinnacle": {"ok": True}}
    m = derive.mesures_du_cycle(etapes, {"pmu": lignes(12, book="pmu"), "pinnacle": lignes(12)},
                                {"pmu": {"Libellé A": 3, "Libellé B": 9}})
    assert set(m) == {"pmu", "winamax", "pinnacle"}
    assert m["pmu"]["inconnus"] == 12 and m["pmu"]["frequents"][0] == ("Libellé B", 9)
    assert m["winamax"]["lignes"] == 0 and m["winamax"]["inconnus"] == 0     # lue sans erreur, vide : mesurée
    assert "inconnus" not in m["pinnacle"] and m["pinnacle"]["empreinte"] == 0


class Reponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_alerte_une_fois_puis_nouvel_essai_si_l_envoi_echoue(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path / "memoire"))
    env = {"PUSHOVER_APP_TOKEN": "jeton", "PUSHOVER_USER_KEY": "cle"}
    envois = []

    def ouvrir(requete, timeout=0):
        envois.append(requete.data.decode())
        if len(envois) == 1:
            raise OSError("réseau")
        return Reponse()

    etapes = {"pmu_direct": {"ok": True}}
    resumes = []
    for i, l in enumerate([variees(40, i) for i in range(14)] + [variees(12, i) for i in range(7)]):
        m = derive.mesures_du_cycle(etapes, {"pmu": l}, {})
        resumes.append(derive.mettre_a_jour(tmp_path, m, T0 + timedelta(minutes=5 * i), env, ouvrir))
    assert [r["alerte_envoyee"] for r in resumes[17:]] == [False, True, False, False]
    assert len(envois) == 2 and "PMU" in envois[1] and "Source+qui+d%C3%A9rive" in envois[1]
    assert resumes[-1]["etapes"] == {"pmu_direct": ["dérive : 72 cotes, 240 d'habitude"]}
    assert (tmp_path / "memoire" / "derive_sources.json.gz").exists()
    assert "erreur" in derive.mettre_a_jour(tmp_path, None, T0)        # ne lève jamais


def test_la_surveillance_voit_une_derive_sur_toute_source():
    etapes = {"netbet": {"ok": True, "degrade": True, "erreurs": ["dérive : 0 cotes, 900 d'habitude", "budget"]},
              "polymarket": {"ok": True, "degrade": True, "erreurs": ["bid/ask invalide"]}}
    assert surveillance.problemes(etapes) == {"netbet": ("alerte", "dérive : 0 cotes, 900 d'habitude")}
    assert surveillance.constats(etapes)["netbet"][1] == "alerte"
