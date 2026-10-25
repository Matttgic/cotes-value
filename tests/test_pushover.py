"""Pushover : alertes des stratégies cochées, le pari en texte et le lien du match dessous."""
import io
import json
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import parse_qs

from scripts import envoyer_notifications as E

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
ENV = {"PUSHOVER_APP_TOKEN": "tok-secret", "PUSHOVER_USER_KEY": "user-secret", "PUSHOVER_STRATEGIES": "eden, labo:PIN-1.3-2-e2-h36"}


def alerte(ident="a" * 64, strategies=("eden",), **kw):
    return {"id": ident, "strategies": list(strategies), "labels": ["Eden"], "bookmaker": "Winamax", "sport": "football",
            "domicile": "Lens", "exterieur": "Lille", "match": "Lens – Lille", "selection": "Lens", "cote": 2.1,
            "cote_min": 1.995, "debut": (NOW + timedelta(hours=3)).isoformat(),
            "lien": "https://www.winamax.fr/paris-sportifs/match/68932762", **kw}


class Rep:
    def __init__(self, corps=None, status=200):
        self.status = status
        self._c = json.dumps(corps if corps is not None else {"status": 1}).encode()

    def __enter__(self): return self
    def __exit__(self, *a): pass
    def read(self, *a): return self._c


def test_les_cles_cochees_sont_lues_et_les_inconnues_signalees():
    assert E.strategies_pushover({"PUSHOVER_STRATEGIES": "eden, labo:PIN-1.3-2-e2-h36 jules,faute"}) == \
        ({"eden", "labo:PIN-1.3-2-e2-h36", "jules"}, ["faute"])
    assert E.strategies_pushover({}) == (set(), [])


def test_message_le_pari_puis_le_lien_cliquable_dessous():
    m = E.message_pushover(alerte(), ENV, NOW)
    assert m["title"] == "Winamax – Football"
    assert m["message"].startswith("Lens – Lille\nLens @ 2,10 (min 2,00)") and m["message"].endswith("Eden")
    assert m["url"] == "https://www.winamax.fr/paris-sportifs/match/68932762" and m["url_title"] == "Ouvrir chez Winamax"
    assert m["ttl"] == 3600 and m["priority"] == 0                           # plafonné à 1 h ; heures calmes respectées
    court = E.message_pushover(alerte(debut=(NOW + timedelta(minutes=20)).isoformat()), ENV, NOW)
    assert court["ttl"] == 1200


def test_sans_lien_sur_ou_priorite_invalide():
    assert "url" not in E.message_pushover(alerte(lien="http://x.test/"), ENV, NOW)
    assert "url" not in E.message_pushover(alerte(lien=None), ENV, NOW)
    for valeur, attendu in (("1", 1), ("-1", -1), ("2", 0), ("abc", 0), ("", 0)):
        assert E.message_pushover(alerte(), {**ENV, "PUSHOVER_PRIORITY": valeur}, NOW)["priority"] == attendu


def test_seules_les_strategies_cochees_et_les_nouvelles_alertes_partent():
    flux = {"alertes": [alerte("1" * 64, ["eden"]), alerte("2" * 64, ["jules"]), alerte("3" * 64, ["eden", "jules"])]}
    sortie = E.alertes_pushover(flux, [], {"3" * 64: "2026-10-25T11:00:00+00:00"}, {"eden"}, NOW)
    assert [a["id"] for a in sortie] == ["1" * 64]


def test_premier_passage_ne_rejoue_pas_les_re_decisions_anciennes(monkeypatch):
    ancien = alerte("9" * 64, [E.PIN2], recheck=True)
    monkeypatch.setattr("cotes.notifications.alertes_recheck", lambda *a, **k: [ancien])
    envoyes = {}
    assert E.alertes_pushover({"alertes": [alerte()]}, [], envoyes, {E.PIN2, "eden"}, NOW, amorcage=True)[0]["id"] == "a" * 64
    assert envoyes == {"9" * 64: ""}                                        # mémorisée sans envoi
    assert [a["id"] for a in E.alertes_pushover({"alertes": []}, [], {}, {E.PIN2}, NOW, amorcage=False)] == ["9" * 64]


def test_poster_envoie_en_formulaire_et_ne_fuit_ni_jeton_ni_cle():
    vus = []

    def ouvrir(req, timeout):
        vus.append((req.full_url, parse_qs(req.data.decode()), timeout))
        return Rep()
    bilan = E.poster_pushover([alerte()], ENV, ouvrir)
    url, champs, timeout = vus[0]
    assert url == E.PUSHOVER_URL and timeout <= 10 and champs["token"] == ["tok-secret"] and champs["user"] == ["user-secret"]
    assert champs["url"] == ["https://www.winamax.fr/paris-sportifs/match/68932762"]
    assert bilan["envoyees"] == ["a" * 64] and "secret" not in json.dumps(bilan)


def test_erreurs_sans_fuite_et_quota_arrete_la_suite():
    appels = []

    def refus(req, timeout):
        appels.append(1)
        raise HTTPError(E.PUSHOVER_URL, 429, "quota", {}, io.BytesIO(b"tok-secret"))
    bilan = E.poster_pushover([alerte(str(i) * 64) for i in range(5)], ENV, refus)
    assert len(appels) == 1 and bilan["echecs"] == 1 and bilan["erreurs"] == ["HTTP 429"]
    assert "secret" not in json.dumps(bilan)
    inactif = E.poster_pushover([alerte()], {"PUSHOVER_APP_TOKEN": "x"}, lambda *a, **k: 1 / 0)
    assert inactif["actif"] is False
    refus_api = E.poster_pushover([alerte()], ENV, lambda req, timeout: Rep({"status": 0, "errors": ["secret"]}))
    assert refus_api["envoyees"] == [] and refus_api["echecs"] == 1 and "secret" not in json.dumps(refus_api)


def test_cycle_complet_memorise_les_envois_et_ne_renvoie_pas(tmp_path, monkeypatch):
    (tmp_path / "paris.json").write_text("[]")
    envoyes = []
    monkeypatch.setattr(E, "urlopen", lambda req, timeout: envoyes.append(parse_qs(req.data.decode())) or Rep())
    monkeypatch.setattr(E, "poster_pushover", lambda al, env=None, ouvrir=None, horloge=None:
                        {"envoyees": [a["id"] for a in al], "echecs": 0, "erreurs": [], "actif": True})
    flux = {"alertes": [alerte(strategies=["eden"])]}
    premier = E.pushover(tmp_path, flux, ENV)
    assert premier["envoyees"] == 1 and premier["actif"] is True
    assert E.pushover(tmp_path, flux, ENV)["envoyees"] == 0
    assert E.pushover(tmp_path, flux, {**ENV, "PUSHOVER_STRATEGIES": ""})["actif"] is False
    assert E.pushover(tmp_path, flux, {})["actif"] is False
    assert "inconnues" in E.pushover(tmp_path, flux, {**ENV, "PUSHOVER_STRATEGIES": "eden faute"})


# --- Stratégies cochées sur le site (lues auprès du service de notifications) ---

GITHUB = {"ACTIONS_ID_TOKEN_REQUEST_URL": "https://token.actions.test/x?a=1", "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "jeton-gh"}


def faux_service(cles, vus=None, echec_service=None):
    def ouvrir(req, timeout):
        if vus is not None:
            vus.append((req.full_url, dict(req.header_items()), req.data))
        if "token.actions" in req.full_url:
            return Rep({"value": "jeton-oidc"})
        if echec_service:
            raise echec_service
        return Rep({"strategies": cles})
    return ouvrir


def test_cases_du_site_lues_avec_l_identite_github():
    vus = []
    cles = E.strategies_du_site(GITHUB, faux_service(["eden", "labo:PIN-1.3-2-e2-h36"], vus))
    assert cles == ["eden", "labo:PIN-1.3-2-e2-h36"]
    assert vus[0][0].startswith("https://token.actions.test/x?a=1&audience=cotes-value-notifications")
    assert vus[1][0] == E.API + "/strategies" and vus[1][2] == b"{}" and vus[1][1]["Authorization"] == "Bearer jeton-oidc"


def test_service_injoignable_ou_pas_encore_deploye_donne_none():
    erreur = HTTPError(E.API, 404, "inconnue", {}, None)
    assert E.strategies_du_site(GITHUB, faux_service([], echec_service=erreur)) is None
    assert E.strategies_du_site({}, faux_service(["eden"])) is None                       # pas d'identité GitHub
    assert E.strategies_du_site(GITHUB, lambda req, timeout: Rep({"strategies": "x"})) is None


def test_variable_remplie_prime_sinon_les_cases_du_site():
    appels = []
    ouvrir = lambda req, timeout: (appels.append(1), faux_service(["eden", "inconnue", "jules"])(req, timeout))[1]
    env = {**GITHUB, "PUSHOVER_STRATEGIES": "m3, faute"}
    assert E.choix_pushover(env, ouvrir) == ({"m3"}, ["faute"], "variable") and not appels
    for vide in ("", "auto", " AUTO "):
        choisies, inconnues, source = E.choix_pushover({**GITHUB, "PUSHOVER_STRATEGIES": vide}, ouvrir)
        assert (choisies, source) == ({"eden", "jules"}, "site")                          # clés inconnues écartées
    assert E.choix_pushover({"PUSHOVER_STRATEGIES": ""}, ouvrir) == (set(), [], "site indisponible")


def test_cycle_utilise_les_cases_du_site_et_n_appelle_rien_sans_secrets(tmp_path, monkeypatch):
    (tmp_path / "paris.json").write_text("[]")
    monkeypatch.setattr(E, "strategies_du_site", lambda env=None, ouvrir=None: ["eden"])
    monkeypatch.setattr(E, "poster_pushover", lambda al, env=None, ouvrir=None, horloge=None:
                        {"envoyees": [a["id"] for a in al], "echecs": 0, "erreurs": [], "actif": True})
    secrets = {"PUSHOVER_APP_TOKEN": "t", "PUSHOVER_USER_KEY": "u"}
    flux = {"alertes": [alerte(strategies=["eden"]), alerte("2" * 64, ["jules"])]}
    bilan = E.pushover(tmp_path, flux, secrets)
    assert bilan["source"] == "site" and bilan["strategies"] == 1 and bilan["envoyees"] == 1
    monkeypatch.setattr(E, "strategies_du_site", lambda *a, **k: 1 / 0)
    assert E.pushover(tmp_path, flux, {})["source"] == "secrets absents"


def test_message_liste_toutes_les_strategies_avec_leur_nombre():
    from scripts.envoyer_notifications import message_pushover
    a = {**alerte("x", ["labo:A", "labo:B"]), "labels": ["Pinnacle 1", "Pinnacle 2", "Polymarket 5", "Eden"]}
    msg = message_pushover(a)["message"]
    assert msg.endswith("4 stratégies : Pinnacle 1, Pinnacle 2, Polymarket 5, Eden")
    assert "1 stratégie : Eden" in message_pushover({**a, "labels": ["Eden"]})["message"]
