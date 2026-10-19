"""Betclic gRPC-web : première trame seulement, budget, shadow."""
from datetime import datetime, timezone

from cotes.delai import Echeance
from cotes.direct import betclic

MAINTENANT = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
DEBUT = "2026-10-18T20:00:00Z"


def _sel(nom, cote, actif=True):
    corps = betclic.encode_champ_octets(10, nom) + betclic.encode_champ_double(12, cote)
    corps += betclic.encode_champ_varint(14, 1 if actif else 2)
    return corps


def _match(ident, domicile, exterieur, debut=DEBUT, direct=False):
    corps = (betclic.encode_champ_varint(1, ident)
             + betclic.encode_champ_octets(3, debut)
             + betclic.encode_champ_octets(8, betclic.encode_champ_octets(2, "Ligue 1"))
             + betclic.encode_champ_octets(12, betclic.encode_champ_octets(3, domicile))
             + betclic.encode_champ_octets(12, betclic.encode_champ_octets(3, exterieur)))
    if direct:
        corps += betclic.encode_champ_varint(6, 1)
    return corps


def _liste(*matchs):
    enveloppe = b"".join(betclic.encode_champ_octets(3, match) for match in matchs)
    return betclic.trame_grpc(betclic.encode_champ_octets(1, enveloppe))


def _detail(nom, selections):
    marche = betclic.encode_champ_octets(2, nom)
    for selection in selections:
        marche += betclic.encode_champ_octets(16, selection)
    enveloppe = betclic.encode_champ_octets(3, marche)
    match = betclic.encode_champ_octets(11, enveloppe)
    return betclic.trame_grpc(betclic.encode_champ_octets(1, betclic.encode_champ_octets(1, match)))


class Reponse:
    def __init__(self, corps, status=200):
        self.status_code = status
        self._corps = corps
        self.fermee = False

    def iter_content(self, _n=None):
        if isinstance(self._corps, list):
            yield from self._corps
            return
        yield self._corps

    def close(self):
        self.fermee = True


class Session:
    def __init__(self, reponses):
        self._reponses = list(reponses)
        self.urls = []
        self.fermees = []

    def post(self, url, data=None, headers=None, timeout=None, stream=None):
        self.urls.append(url)
        corps, status = self._reponses.pop(0)
        reponse = Reponse(corps, status)
        self.fermees.append(reponse)
        return reponse


def _lens():
    return _detail("Résultat du match (t. rég)", [
        _sel("Lens", 1.8), _sel("Nul", 3.4), _sel("Lille", 4.2, actif=False), _sel("Lille", 4.5),
    ])


def test_combinaison_n_est_pas_les_deux_equipes_marquent():
    vrai = betclic.marche_pulse({
        "nom": "Les 2 équipes marquent (t. rég)",
        "selections": [{"nom": "Oui", "cote": 1.8}, {"nom": "Non", "cote": 1.9}],
    }, "Lens", "Lille")
    assert vrai["canonicalMarket"] == "BOTH_TEAMS_TO_SCORE"
    combo = betclic.marche_pulse({
        "nom": "Les 2 équipes marquent ou + de 2,5 buts dans le match (t. rég)",
        "selections": [{"nom": "Oui", "cote": 1.4}, {"nom": "Non", "cote": 2.6}],
    }, "Lens", "Lille")
    assert combo is None
    a_venir = {"debut": DEBUT, "direct": True}
    assert betclic._a_venir(a_venir, MAINTENANT, 36)
    assert not betclic._a_venir({"debut": "2026-10-18T08:00:00Z", "direct": False}, MAINTENANT, 36)


def test_premiere_trame_ignore_la_suivante():
    premiere = _liste(_match(1, "Lens", "Lille"))
    suite = _liste(_match(2, "Nice", "Rennes"))
    brut = premiere + suite
    assert betclic.premiere_trame([brut[:10], brut[10:]]) == premiere
    assert [m["id"] for m in betclic.matchs_de_la_liste(brut)] == [1]


def test_collecte_traduit_le_resultat_et_ferme_apres_la_premiere_trame():
    autre = _detail("Résultat du match (t. rég)", [_sel("Nice", 99), _sel("Nul", 99), _sel("Rennes", 99)])
    session = Session([
        (_liste(_match(7, "Lens", "Lille"),
                _match(8, "Angers", "Marseille", debut="2026-10-18T08:00:00Z", direct=True)) + autre, 200),
        (_lens() + autre, 200),
    ])
    lignes, meta = betclic.collecter({"football"}, 36, session=session, maintenant=MAINTENANT)
    assert meta["ok"] is True and meta["requetes"] == 2 and meta["matchs"] == 1
    assert all(rep.fermee for rep in session.fermees)
    assert session.urls[0].endswith(betclic.LISTE) and session.urls[1].endswith(betclic.DETAIL)
    issues = {l["issue"]: l["cote"] for l in lignes}
    assert issues == {"DOM": 1.8, "NUL": 3.4, "EXT": 4.5}
    assert {l["bookmaker"] for l in lignes} == {"betclic"}
    assert lignes[0]["domicile"] == "Lens" and lignes[0]["periode"] == "MATCH"


def test_total_groupe_est_lu_sans_le_champ_16():
    selection = _sel("+ de 2,5", 1.9)
    autre = _sel("- de 2,5", 1.85)
    item = betclic.encode_champ_octets(1, selection) + betclic.encode_champ_octets(1, autre)
    groupe = betclic.encode_champ_octets(1, item)
    marche = betclic.encode_champ_octets(2, "Nombre total de buts (t. rég)") + betclic.encode_champ_octets(10, groupe)
    enveloppe = betclic.encode_champ_octets(3, marche)
    match = betclic.encode_champ_octets(11, enveloppe)
    trame = betclic.trame_grpc(betclic.encode_champ_octets(1, betclic.encode_champ_octets(1, match)))
    session = Session([(_liste(_match(7, "Lens", "Lille")), 200), (trame, 200)])
    lignes, meta = betclic.collecter({"football"}, 36, session=session, maintenant=MAINTENANT)
    assert meta["ok"] is True
    assert {(l["issue"], l["ligne"], l["cote"]) for l in lignes} == {("PLUS", 2.5, 1.9), ("MOINS", 2.5, 1.85)}
    assert {l["marche"] for l in lignes} == {"TOTAL"}


def test_total_et_budget_coupe_avant_le_detail():
    total = _detail("Nombre total de buts (t. rég)", [_sel("+ de 2,5", 1.91), _sel("- de 2,5", 1.89)])
    session = Session([(_liste(_match(7, "Lens", "Lille")), 200), (total, 200)])

    class UneListe:
        def __init__(self):
            self.n = 0

        def ok(self):
            self.n += 1
            return self.n <= 2

        def timeout(self, plafond):
            return 1

    lignes, meta = betclic.collecter({"football"}, 36, session=session, maintenant=MAINTENANT,
                                     echeance=UneListe())
    assert lignes == [] and meta["requetes"] == 1 and meta["matchs"] == 1
    assert meta["erreurs"] == ["budget"] and meta["ok"] is True
    assert len(session.urls) == 1


def test_echeance_deja_depassee_ne_contacte_pas():
    session = Session([])
    lignes, meta = betclic.collecter({"football"}, 36, session=session, maintenant=MAINTENANT,
                                     echeance=Echeance(0))
    assert lignes == [] and meta["requetes"] == 0 and session.urls == []
    assert meta["ok"] is False and meta["erreurs"] == ["budget"]


def test_429_coupe_sans_deuxieme_appel():
    session = Session([(b"", 429), (_lens(), 200)])
    lignes, meta = betclic.collecter({"football", "tennis"}, 36, session=session, maintenant=MAINTENANT)
    assert lignes == [] and meta["requetes"] == 1 and meta["erreurs"] == ["HTTP 429"]
    assert meta["ok"] is False and session.fermees[0].fermee
    assert "429" not in str(session.urls)


def test_total_multi_lignes_donne_un_marche_par_ligne():
    marche = {"nom": "Nombre total de buts (t. rég)", "selections": [
        {"nom": "+ de 1,5", "cote": 1.4}, {"nom": "- de 1,5", "cote": 2.9},
        {"nom": "+ de 2,5", "cote": 2.1}, {"nom": "- de 2,5", "cote": 1.7}]}
    traduits = betclic.marches_pulse(marche, "Lens", "Lille")
    assert [m["selections"][0]["line"] for m in traduits] == [1.5, 2.5]
    assert len({m["marketId"] for m in traduits}) == 2
    session = Session([(_liste(_match(7, "Lens", "Lille")), 200),
                       (_detail(marche["nom"], [_sel(s["nom"], s["cote"]) for s in marche["selections"]]), 200)])
    lignes, _ = betclic.collecter({"football"}, 36, session=session, maintenant=MAINTENANT)
    assert {(l["issue"], l["ligne"]) for l in lignes} == {
        ("PLUS", 1.5), ("MOINS", 1.5), ("PLUS", 2.5), ("MOINS", 2.5)}


def test_double_chance_nom_abrege():
    marche = {"nom": "Double chance (t. rég)", "selections": [
        {"nom": "Racing Club ou Nul", "cote": 1.28}, {"nom": "Racing Club ou Independiente", "cote": 1.32},
        {"nom": "Nul ou CA Independiente", "cote": 1.45}]}
    issues = {s["canonicalOutcome"] for s in betclic.marche_pulse(marche, "Racing Club", "CA Independiente")["selections"]}
    assert issues == {"HOME_DRAW", "HOME_AWAY", "DRAW_AWAY"}


def test_total_equipe_hockey_et_abrege_prolongations():
    nom = "Texas Stars - Nombre total de buts (prolong. & pen. inclus)"
    assert betclic._classe(nom, "Manitoba Moose", "Texas Stars") == "AWAY_OVER_UNDER"
    assert betclic._classe("Buteur & passeur", "A", "B") is None
    assert betclic._classe("Nombre total de buts - Autre", "A", "B") is None


def test_lecture_en_parallele_garde_toutes_les_lignes():
    detail = _lens()
    matchs = [_match(i, "Lens", "Lille") for i in range(1, 7)]
    session = Session([(_liste(*matchs), 200)] + [(detail, 200)] * 6)
    lignes, meta = betclic.collecter({"football"}, 36, session=session, maintenant=MAINTENANT,
                                     reserve={"lignes": []})
    assert meta["ok"] is True and meta["matchs"] == 6
    assert {l["match_id"] for l in lignes} == {f"betclic|{i}" for i in range(1, 7)}


def test_429_en_parallele_arrete_la_suite():
    matchs = [_match(i, "Lens", "Lille") for i in range(1, 9)]
    session = Session([(_liste(*matchs), 200)] + [(b"", 429)] * 8)
    lignes, meta = betclic.collecter({"football"}, 36, session=session, maintenant=MAINTENANT,
                                     reserve={"lignes": []}, concurrence=1)
    assert lignes == [] and "HTTP 429" in meta["erreurs"]
    assert meta["requetes"] == 2


def test_classement_des_marches_par_periode():
    c = betclic._classe
    assert c("1ère mi-temps (seule) - Nombre total de buts", "A", "B") == "OVER_UNDER"
    assert c("2ème mi-temps (seule) - Nombre total de buts - B", "A", "B") == "AWAY_OVER_UNDER"
    assert c("1er QT - Nombre total de Points - A", "A", "B") == "HOME_OVER_UNDER"
    assert c("1ère période - Nombre de buts - B", "A", "B") == "AWAY_OVER_UNDER"
    assert c("1er set - Nombre total de jeux", "A", "B") == "OVER_UNDER"
    assert c("A - Nombre total de jeux gagnés", "A", "B") == "HOME_OVER_UNDER"
    assert c("1ère mi-temps - Vainqueur", "A", "B") == "MATCH_RESULT"
    assert c("Résultat du match (remboursé si match nul)", "A", "B") == "DRAW_NO_BET"
    assert c("Nombre de sets", "A", "B") == "TOTAL_SETS"
    assert c("2ème période - Vainqueur avec handicap", "A", "B") == "ECART"
    for exclu in ("Nombre total de tirs", "Mi-temps avec le plus de buts", "Nombre total de points - Intervalle",
                  "1ère mi-temps (seule) - Cage inviolée pour A",
                  "Vainqueur du 1er set / Vainqueur du match", "Nombre total de sets"):
        assert c(exclu, "A", "B") is None, exclu
    libelle = betclic.marches_pulse({"nom": "1er QT - Nombre total de points", "selections": [
        {"nom": "+ de 41,5", "cote": 1.7}, {"nom": "- de 41,5", "cote": 1.7}]}, "A", "B")[0]["rawName"]
    assert "quart-temps" in libelle


def test_onglets_utiles_et_lecture_complete():
    def onglet(ident, libelle):
        return betclic.encode_champ_octets(10, betclic.encode_champ_octets(2, ident) + betclic.encode_champ_octets(3, libelle))
    marche = betclic.encode_champ_octets(2, "Nombre total de buts (t. rég)") + b"".join(
        betclic.encode_champ_octets(16, x) for x in (_sel("+ de 2,5", 1.9), _sel("- de 2,5", 1.85)))
    match = betclic.encode_champ_octets(11, betclic.encode_champ_octets(3, marche)) + onglet("ca_top", "Le Top") + onglet("ca_buts", "Buts") + onglet("ca_x", "Joueurs")
    top = betclic.trame_grpc(betclic.encode_champ_octets(1, betclic.encode_champ_octets(1, match)))
    assert betclic.onglets_utiles(top) == ["ca_buts"]
    mi_temps = _detail("1ère mi-temps (seule) - Nombre total de buts", [_sel("+ de 0,5", 1.2), _sel("- de 0,5", 3.9)])
    session = Session([(_liste(_match(7, "Lens", "Lille")), 200), (top, 200), (mi_temps, 200)])
    lignes, meta = betclic.collecter({"football"}, 36, session=session, maintenant=MAINTENANT)
    assert meta["requetes"] == 3
    assert {(l["periode"], l["ligne"]) for l in lignes} == {("MATCH", 2.5), ("MT1", 0.5)}


def test_ecart_est_un_handicap():
    marche = {"nom": "Écart de buts (t. rég)", "selections": [
        {"nom": n, "cote": c} for n, c in [
            ("Lyon gagne de 2 buts ou +", 3.0), ("Nice ne perd pas ou perd de 1 but exactement", 1.4),
            ("Lyon gagne de 1 but exactement", 3.1), ("Nice gagne de 1 ou +", 4.0),
            ("Lyon ne perd pas", 1.2), ("J. Duranville décisif", 2.4)]]}
    traduits = betclic.marches_pulse(marche, "Lyon", "Nice", "football")
    assert {m["marketId"].split("|")[1] for m in traduits} == {"-1.5", "+0.5"}
    gros = next(m for m in traduits if m["marketId"].endswith("-1.5"))
    assert {(s["canonicalOutcome"], s["line"]) for s in gros["selections"]} == {("HOME", -1.5), ("AWAY", 1.5)}
    assert all(m["canonicalMarket"] == "ASIAN_HANDICAP" for m in traduits)
    # le domicile qui perd : Nice gagne de 2 ou + = Nice −1,5 = ligne du domicile +1,5
    ext = betclic.marches_pulse({"nom": "Écart de buts", "selections": [
        {"nom": "Nice gagne de 2 buts ou +", "cote": 6.0},
        {"nom": "Lyon ne perd pas ou perd de 1 but exactement", "cote": 1.1}]}, "Lyon", "Nice", "football")
    assert [s["line"] for s in ext[0]["selections"]] == [1.5, -1.5] and ext[0]["marketId"].endswith("+1.5")
    # unités : jeux et sets au tennis, rien pour les points du volley
    jeux = {"nom": "Écart de jeux", "selections": [{"nom": "A gagne de 3 ou +", "cote": 1.7},
                                                   {"nom": "B ne perd pas ou perd de 2 ou -", "cote": 2.0}]}
    assert betclic.marches_pulse(jeux, "A", "B", "tennis")[0]["canonicalMarket"] == "GAME_HANDICAP"
    assert betclic.marches_pulse({**jeux, "nom": "Écart de points"}, "A", "B", "volley") == []
    assert betclic.marches_pulse({**jeux, "nom": "Écart de points (3 options)"}, "A", "B", "basket") == []
def test_ecart_de_jeux_du_premier_set_reste_un_handicap_de_jeux():
    marche = {"nom": "1er set - Écart de jeux", "selections": [
        {"nom": "A gagne de 2 ou +", "cote": 2.1}, {"nom": "B ne perd pas ou perd de 1 exactement", "cote": 1.7}]}
    assert betclic.marches_pulse(marche, "A", "B", "tennis")[0]["canonicalMarket"] == "GAME_HANDICAP"


def test_ecart_hockey_sans_mention_se_regle_sur_60_minutes():
    from cotes.pulsescore import traduire
    marche = {"nom": "Ecart entre les équipes", "selections": [
        {"nom": "A gagne de 1 ou +", "cote": 2.12}, {"nom": "B ne perd pas", "cote": 1.58},
        {"nom": "A gagne de 2 ou +", "cote": 2.72}, {"nom": "B ne perd pas ou perd de 1", "cote": 1.34}]}
    evenement = {"eventId": 1, "home": "A", "away": "B", "markets": betclic.marches_pulse(marche, "A", "B", "hockey")}
    lignes = traduire(evenement, "betclic", "hockey", "2026-10-18T22:00:00+00:00")
    # ±0,5 : temps réglementaire ; ±1,5 : la prolongation ne change rien, donc match entier
    assert {(l["ligne"], l["periode"]) for l in lignes} == {(-0.5, "TEMPS_REG"), (-1.5, "MATCH")}


def test_ecart_de_points_entre_les_equipes_est_un_handicap_basket():
    assert betclic._classe("Écart de points entre les équipes", "A", "B") == "ECART"
    marche = {"nom": "Écart de points entre les équipes", "selections": [
        {"nom": "A gagne de 7 ou +", "cote": 1.76}, {"nom": "B ne perd pas ou perd de 6 ou -", "cote": 1.71}]}
    traduits = betclic.marches_pulse(marche, "A", "B", "basket")
    assert [m["canonicalMarket"] for m in traduits] == ["ASIAN_HANDICAP"]
    assert betclic.marches_pulse({**marche, "nom": "Écart de points (3 options)"}, "A", "B", "basket") == []
