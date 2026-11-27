"""Audit fiabilité du 26/11/2026 : chaque test échoue sur le code d'avant le correctif."""
from pathlib import Path

import pytest
import requests

from cotes import pinnacle as P, securite, surveillance

RACINE = Path(__file__).resolve().parents[1]


class Reponse:
    def __init__(self, data=None, status=200):
        self.data, self.status_code, self.headers = data, status, {}

    def json(self):
        return self.data


@pytest.fixture(autouse=True)
def pinnacle_isole(monkeypatch):
    P.ERREURS.clear()
    monkeypatch.setattr(P, "_bloque", False)
    monkeypatch.setattr(P, "_reprises_403", 0)
    monkeypatch.setattr(P.time, "sleep", lambda _: None)
    P.choix_prix.clear()
    yield
    P.ERREURS.clear()


def _get_avec(monkeypatch, reponses):
    def get(*a, **kw):
        r = reponses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(P._http, "get", get)
    return P._get("/sports/29/matchups?withSpecials=true")


# --- Pinnacle : un échec passager repris avec succès n'est plus noté (162 cycles d'alerte les 25-26/11)

@pytest.mark.parametrize("premier", [requests.ReadTimeout("délai"), Reponse(status=503), Reponse(status=408)])
def test_pinnacle_echec_passager_repris_sans_erreur(monkeypatch, premier):
    assert _get_avec(monkeypatch, [premier, Reponse([{"id": 1}])]) == [{"id": 1}]
    assert P.ERREURS == []


def test_pinnacle_echec_passager_persistant_reste_note(monkeypatch):
    assert _get_avec(monkeypatch, [requests.ConnectionError()] * 3) is None
    assert P.ERREURS == ["sport 29 matchups : réseau indisponible"]


def test_pinnacle_echec_passager_puis_refus_note_les_deux(monkeypatch):
    # le réseau, puis un 403 répété (reprise comprise) : la requête échoue, les deux causes restent visibles
    assert _get_avec(monkeypatch, [requests.ReadTimeout(), Reponse(status=403), Reponse(status=403)]) is None
    assert P.ERREURS == ["sport 29 matchups : réseau indisponible", "sport 29 matchups : HTTP 403"]


def test_pinnacle_secours_pas_declenche_par_un_5xx_repris(monkeypatch):
    from cotes import pinnacle_secours
    _get_avec(monkeypatch, [Reponse(status=502), Reponse([{"id": 1}])])
    assert pinnacle_secours.sports_a_secourir(list(P.ERREURS), [{"x": 1}]) - pinnacle_secours.sports_en_retard([{"x": 1}]) == set()


# --- Surveillance : le détail d'une alerte est la première erreur non bénigne (163 cycles masqués du 20 au 26/11)

def test_detail_alerte_premiere_erreur_non_benigne():
    etapes = {"pinnacle": {"ok": True, "degrade": True,
                           "erreurs": ["sport 28 matchups : HTTP 403", "marché rejeté : cotes ou issues incohérentes"]}}
    assert surveillance.problemes(etapes) == {"pinnacle": ("alerte", "marché rejeté : cotes ou issues incohérentes")}
    assert surveillance.constats(etapes)["pinnacle"][2] == "marché rejeté : cotes ou issues incohérentes"


def test_refus_seuls_restent_benins():
    etapes = {"pinnacle": {"ok": True, "degrade": True, "erreurs": ["sport 28 matchups : HTTP 403", "budget"]}}
    assert surveillance.problemes(etapes) == {}
    assert surveillance.constats(etapes)["pinnacle"][1] == "refus"


# --- Publication : les secrets de l'environnement du site sans forme reconnaissable sont bloqués à l'identique

@pytest.mark.parametrize("nom", ["PUSHOVER_APP_TOKEN", "PUSHOVER_USER_KEY", "PINNACLE_RECHAUFFEUR_SECRET",
                                 "ALERTE_WEBHOOK_KEY", "HC_PING_URL", "GITHUB_TOKEN", "GH_TOKEN"])
def test_secret_configure_bloque_a_la_publication(nom):
    valeur = "azGdo3kq8wP1xYz9"
    with pytest.raises(ValueError, match="secret configuré"):
        securite.verifier_public({"message": f"texte {valeur} fin"}, env={nom: valeur})


def test_variable_non_secrete_pas_bloquee():
    securite.verifier_public({"message": "x-api-key"}, env={"ALERTE_WEBHOOK_CLE_ENTETE": "x-api-key"})


# --- Workflows et serveur

def test_chaque_tache_des_workflows_a_une_limite_de_temps():
    import yaml
    sans = [f"{wf.name}:{nom}" for wf in sorted((RACINE / ".github/workflows").glob("*.yml"))
            for nom, tache in (yaml.safe_load(wf.read_text(encoding="utf-8"))["jobs"] or {}).items()
            if "timeout-minutes" not in tache]
    assert sans == []


def test_service_direct_durci():
    service = (RACINE / "serveur/cotes-value-direct.service").read_text(encoding="utf-8")
    for directive in ("NoNewPrivileges=yes", "PrivateTmp=yes", "ProtectSystem=full", "RestrictSUIDSGID=yes"):
        assert directive in service
    assert "ProtectSystem=strict" not in service          # /opt/cotes-value doit rester inscriptible (git pull, données)
