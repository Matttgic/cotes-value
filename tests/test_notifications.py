import io
import json
from datetime import timedelta

from cotes.notifications import flux
from scripts.envoyer_notifications import transmettre
from tests.test_theodds import NOW, pari


def selection(**kw):
    return pari(detecte=(NOW-timedelta(minutes=3)).isoformat(), debut=(NOW+timedelta(hours=2)).isoformat(),
                reference="Pinnacle", pari="Paris Basketball vainqueur", **kw)


def test_flux_meme_prise_prix_et_plusieurs_strategies_sans_doublon():
    p=selection(); o=dict(p)
    b=flux([o,{**o,"reference":"Betfair"}],[p],{"strategie":{id(p)},"claude_prudent":{id(p)}},NOW)
    assert len(b['alertes'])==1
    a=b['alertes'][0]
    assert a['strategies']==['claude_prudent','strategie']
    assert a['validations']['strategie']==p['detecte']
    assert not flux([{**o,'cote':2.01}],[p],{'strategie':{id(p)}},NOW)['alertes']
    assert not flux([o],[p],{'strategie':set()},NOW)['alertes']


def test_flux_exclut_anciens_matches_commences_et_suspects():
    p=selection(); ids={'strategie':{id(p)}}
    for o in ({**p,'suspect':True},{**p,'debut':NOW.isoformat()}):
        assert not flux([o],[p],ids,NOW)['alertes']
    p['detecte']=(NOW-timedelta(minutes=16)).isoformat()
    assert not flux([p],[p],ids,NOW)['alertes']


def test_date_de_validation_reste_propre_a_chaque_strategie():
    p=selection(); q={**p,'id':'autre','detecte':NOW.isoformat(),'reference':'Betfair'}
    b=flux([p],[p,q],{'strategie':{id(p)},'gemini':{id(q)}},NOW)['alertes'][0]
    assert b['validations']['strategie']==p['detecte']
    assert b['validations']['gemini']==q['detecte']


def test_identite_github_et_aucun_secret_dans_le_diagnostic():
    appels=[]
    def ouvrir(req,timeout):
        appels.append(req)
        return io.BytesIO(json.dumps({'value':'jeton-secret'} if len(appels)==1 else
             {'ok':True,'sent':0,'devices':0,'subscription':'secret-interdit'}).encode())
    env={'ACTIONS_ID_TOKEN_REQUEST_URL':'https://example.test/token?x=1',
         'ACTIONS_ID_TOKEN_REQUEST_TOKEN':'identite-secrete'}
    r=transmettre({'alertes':[]},env,ouvrir)
    assert r=={'ok':True,'sent':0,'devices':0}
    assert 'audience=cotes-value-notifications' in appels[0].full_url
    assert appels[1].get_header('Authorization')=='Bearer jeton-secret'
    assert 'secret' not in json.dumps(r)
    assert not transmettre({},env={})['ok']


def test_regles_du_laboratoire_alertent_avec_le_nom_de_la_page_strategies(monkeypatch):
    from cotes import notifications as N
    p = selection(); o = dict(p)
    a = flux([o], [p], {"labo:PIN-1.3-2-e2-h36": {id(p)}}, NOW)["alertes"][0]
    assert a["strategies"] == ["labo:PIN-1.3-2-e2-h36"] and a["labels"] == ["Pinnacle 2"]
    assert N.NOMS["labo:PIN-1.3-2-e2-h12"] == "Pinnacle 1" and N.NOMS["labo:POL-1.3-2-e2-h12"] == "Polymarket 1"
    assert N.DETAILS["labo:PIN-1.3-2-e2-h36"] == "Cotes 1,30–2,00 · edge ≥ 2 % · ≤ 36 h avant le match"
    vus = []
    monkeypatch.setattr(N, "selectionner", lambda paris, r, depuis: vus.append((r.id, depuis)) or [p])
    assert N.selections_labo([p])["labo:PIN-1.3-2-e2-h36"] == {id(p)}
    assert len(vus) == 24 and {d for _, d in vus} == {N.DEBUT_SUIVI}


# --- webhook Pinnacle 2 -----------------------------------------------------------------------------------------
PIN2 = "labo:PIN-1.3-2-e2-h36"
URL_WEBHOOK_TEST = "https://hooks.example.test/chemin-secret?token=jeton-dans-l-url"
CLE_WEBHOOK_TEST = "cle-webhook-secrete"


def prise_pin2(**kw):
    base = dict(detecte=(NOW-timedelta(minutes=3)).isoformat(), debut=(NOW+timedelta(hours=2)).isoformat(),
                reference="Pinnacle", pari="Galatasaray SK -7,5", cote=1.93, cote_juste=1.835, cote_reference=1.80,
                ecart=.0516, bookmaker="Betclic", marche="HANDICAP")
    return pari(**{**base, **kw})


def test_alerte_porte_edge_cotes_ligue_et_cote_min():
    p = prise_pin2()
    a = flux([dict(p)], [p], {PIN2: {id(p)}}, NOW)["alertes"][0]
    assert (a["ecart"], a["cote_juste"], a["cote_pinnacle"], a["ligue"]) == (.0516, 1.835, 1.80, "Euroligue")
    assert a["cote_min"] == round(1.835 * 1.02, 3) and a["marche"] == "HANDICAP" and a["selection"] == "Galatasaray SK -7,5"
    bas = prise_pin2(cote_juste=1.20)
    assert flux([dict(bas)], [bas], {PIN2: {id(bas)}}, NOW)["alertes"][0]["cote_min"] == 1.30      # plancher


def test_meme_prise_vue_par_deux_references_garde_les_valeurs_de_pinnacle():
    p = prise_pin2()
    poly = {**p, "reference": "Polymarket", "cote_juste": 1.70, "cote_reference": None}
    for ordre in ([dict(p), poly], [poly, dict(p)]):
        a = flux(ordre, [p], {PIN2: {id(p)}}, NOW)["alertes"][0]
        assert a["cote_juste"] == 1.835 and a["cote_pinnacle"] == 1.80


def test_charge_utile_champs_convenus_et_debut_en_utc():
    from scripts.envoyer_notifications import charge_utile
    p = prise_pin2()
    a = flux([dict(p)], [p], {PIN2: {id(p)}}, NOW)["alertes"][0]
    c = charge_utile({**a, "debut": "2026-10-20T19:00:00+02:00"})
    assert set(c) == {"id", "match", "ligue", "debut", "marche", "selection", "bookmaker", "cote", "cote_min",
                      "cote_juste", "cote_pinnacle", "ecart", "recheck"}
    assert c["debut"] == "2026-10-20T17:00:00Z" and c["recheck"] is False and c["bookmaker"] == "Betclic"


def test_seules_les_alertes_pinnacle_2_non_envoyees_partent():
    from scripts.envoyer_notifications import alertes_webhook
    p, q = prise_pin2(), prise_pin2(id="q", match_id="autre", pari="Autre")
    f = flux([dict(p), dict(q)], [p, q], {PIN2: {id(p)}, "strategie": {id(q)}}, NOW)
    assert [a["selection"] for a in alertes_webhook(f, [], {}, NOW)] == ["Galatasaray SK -7,5"]
    assert alertes_webhook(f, [], {f["alertes"][0]["id"]: "x", f["alertes"][1]["id"]: "x"}, NOW) == []


def test_post_un_par_alerte_avec_la_cle_et_sans_fuite_dans_le_resultat():
    from scripts.envoyer_notifications import poster_webhook
    appels = []

    class Reponse:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def ouvrir_ok(req, timeout):
        appels.append((req, timeout))
        return Reponse()

    env = {"ALERTE_WEBHOOK_URL": URL_WEBHOOK_TEST, "ALERTE_WEBHOOK_KEY": CLE_WEBHOOK_TEST}
    alertes = [{"id": "a" * 64, "match": "A – B", "cote": 1.9}, {"id": "b" * 64, "match": "C – D", "cote": 2.0}]
    r = poster_webhook(alertes, env, ouvrir_ok)
    assert r["envoyees"] == ["a" * 64, "b" * 64] and r["echecs"] == 0 and r["actif"]
    assert len(appels) == 2 and all(t <= 10 for _, t in appels)
    req = appels[0][0]
    assert req.get_method() == "POST" and req.full_url == URL_WEBHOOK_TEST
    assert req.get_header("X-api-key") == CLE_WEBHOOK_TEST and json.loads(req.data)["id"] == "a" * 64
    assert URL_WEBHOOK_TEST not in json.dumps(r) and CLE_WEBHOOK_TEST not in json.dumps(r)
    env2 = {**env, "ALERTE_WEBHOOK_CLE_ENTETE": "Authorization"}
    appels.clear()
    poster_webhook(alertes[:1], env2, ouvrir_ok)
    assert appels[0][0].get_header("Authorization") == CLE_WEBHOOK_TEST


def test_post_erreurs_journalisees_sans_bloquer_ni_fuiter():
    from urllib.error import HTTPError, URLError
    from scripts.envoyer_notifications import poster_webhook
    env = {"ALERTE_WEBHOOK_URL": URL_WEBHOOK_TEST, "ALERTE_WEBHOOK_KEY": CLE_WEBHOOK_TEST}
    alertes = [{"id": c * 64, "cote": 2.0} for c in "abc"]
    pannes = iter([HTTPError(URL_WEBHOOK_TEST, 500, "x " + CLE_WEBHOOK_TEST, {}, None), URLError(URL_WEBHOOK_TEST + CLE_WEBHOOK_TEST), TimeoutError(URL_WEBHOOK_TEST)])

    def ouvrir(req, timeout):
        raise next(pannes)

    r = poster_webhook(alertes, env, ouvrir)
    assert r["envoyees"] == [] and r["echecs"] == 3 and "HTTP 500" in r["erreurs"]
    assert URL_WEBHOOK_TEST not in json.dumps(r) and CLE_WEBHOOK_TEST not in json.dumps(r) and "jeton" not in json.dumps(r)
    assert poster_webhook(alertes, {}, ouvrir)["actif"] is False                                   # pas d'URL : rien
    assert poster_webhook(alertes, {"ALERTE_WEBHOOK_URL": "http://x.test"}, ouvrir)["actif"] is False   # https obligatoire
    horloge = iter([0, 0, 100, 100, 100])
    r = poster_webhook(alertes, env, lambda *a, **k: (_ for _ in ()).throw(OSError()), horloge=lambda: next(horloge))
    assert "budget de temps atteint" in r["erreurs"]


def test_paris_redecides_repris_meme_apres_15_minutes_tant_que_le_match_n_a_pas_commence():
    from cotes.notifications import alertes_recheck
    base = prise_pin2(detecte=(NOW - timedelta(hours=1)).isoformat(), debut=(NOW + timedelta(hours=20)).isoformat(),
                      selections_figees={PIN2: {}}, redecision_lecture_posterieure=NOW.isoformat())
    a, = alertes_recheck([base], PIN2, NOW)
    assert a["recheck"] is True and a["strategies"] == [PIN2] and a["cote_min"] == round(1.835 * 1.02, 3)
    assert a["ligue"] == "Euroligue" and a["cote_pinnacle"] == 1.80 and a["ecart"] == .0516
    assert not alertes_recheck([{**base, "debut": (NOW - timedelta(minutes=1)).isoformat()}], PIN2, NOW)
    assert not alertes_recheck([{**base, "statut": "a_regler"}], PIN2, NOW)
    assert not alertes_recheck([{**base, "selections_figees": {}}], PIN2, NOW)
    assert not alertes_recheck([{k: v for k, v in base.items() if k != "redecision_lecture_posterieure"}], PIN2, NOW)
    assert not alertes_recheck([{**base, "redecision_ajoutees": ["labo:autre"]}], PIN2, NOW)
    assert alertes_recheck([{**base, "redecision_ajoutees": [PIN2]}], PIN2, NOW)


def test_webhook_pinnacle_2_memorise_les_id_et_ne_bloque_jamais(tmp_path, monkeypatch):
    from scripts import envoyer_notifications as E
    p = prise_pin2(detecte=(NOW - timedelta(hours=1)).isoformat(), debut=(NOW + timedelta(hours=20)).isoformat(),
                   selections_figees={PIN2: {}}, redecision_lecture_posterieure=NOW.isoformat(), statut="en_cours")
    (tmp_path / "paris.json").write_text(json.dumps([p]))
    envoyees = []
    monkeypatch.setenv("ALERTE_WEBHOOK_URL", URL_WEBHOOK_TEST)
    monkeypatch.setattr(E, "poster_webhook", lambda al, *a, **k: envoyees.extend(al) or
                        {"actif": True, "envoyees": [x["id"] for x in al], "echecs": 0, "erreurs": []})
    monkeypatch.setattr(E, "datetime", type("D", (E.datetime,), {"now": staticmethod(lambda tz=None: NOW)}))
    r = E.webhook_pinnacle2(tmp_path, {"alertes": []})
    assert r["envoyees"] == 1 and r["recheck"] == 1 and len(envoyees) == 1
    assert list(json.loads((tmp_path / E.ENVOYES).read_text())) == [envoyees[0]["id"]]
    assert E.webhook_pinnacle2(tmp_path, {"alertes": []})["envoyees"] == 0 and len(envoyees) == 1      # pas de doublon
    (tmp_path / "paris.json").write_text("{illisible")
    assert E.webhook_pinnacle2(tmp_path, {"alertes": []})["envoyees"] == 0                            # erreur avalée
