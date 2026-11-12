"""Récapitulatif « encore jouables » : heure, sélection, cote actuelle relevée, message, envoi unique par jour."""
import gzip
import io
import json
from datetime import datetime, timezone

from cotes import recap_jouables as R
from cotes.notifications import empreinte_prix
from scripts import envoyer_notifications as E

NOW = datetime(2026, 11, 12, 10, 5, tzinfo=timezone.utc)          # 11h05 à Paris


def pari(pid, cote=2.10, juste=1.95, debut="2026-11-12T19:00:00+00:00", **kw):
    return {"id": pid, "statut": "en_cours", "bookmaker": "PMU", "match_id": f"pmu|{pid}", "marche": "RESULTAT_1N2",
            "periode": "MATCH", "ligne": None, "issue": "DOM", "cote": cote, "cote_juste": juste, "ecart": 0.05,
            "debut": debut, "domicile": "Lens", "exterieur": "Lille", "pari": "Lens", "detecte": "2026-11-12T02:00:00+00:00",
            "lien": "https://www.pmu.fr/sport/event/1", **kw}


def historique(tmp_path, lignes):
    (tmp_path / "cotes").mkdir(exist_ok=True)
    with gzip.open(tmp_path / "cotes" / "2026-11-12.jsonl.gz", "wt") as f:
        for l in lignes:
            f.write(json.dumps(l) + "\n")


def test_heure_et_une_fois_par_jour():
    assert R.est_l_heure(NOW, 11, None) and not R.est_l_heure(NOW, 11, "2026-11-12")
    assert not R.est_l_heure(NOW, 10, None)
    assert R.heure_recap({}) == 11 and R.heure_recap({"PUSHOVER_RECAP_HEURE": "non"}) is None
    assert R.heure_recap({"PUSHOVER_RECAP_HEURE": "8"}) == 8


def test_garde_seulement_ce_qui_est_encore_jouable(tmp_path):
    ok, baisse, inconnu, commence = pari("a"), pari("b"), pari("c"), pari("d", debut="2026-11-12T10:10:00+00:00")
    envoyes = {empreinte_prix(p): "2026-11-12T02:00:00+00:00" for p in (ok, baisse, inconnu, commence)}
    cands = R.candidats([ok, baisse, inconnu, commence], envoyes, datetime(2026, 11, 11, tzinfo=timezone.utc), NOW)
    assert [p["id"] for p in cands] == ["a", "b", "c"]                       # match imminent écarté
    historique(tmp_path, [
        {"t": "2026-11-12T09:00:00+00:00", "b": "PMU", "m": "pmu|a", "k": "RESULTAT_1N2|MATCH||DOM", "c": 2.05},
        {"t": "2026-11-12T08:00:00+00:00", "b": "PMU", "m": "pmu|b", "k": "RESULTAT_1N2|MATCH||DOM", "c": 2.10},
        {"t": "2026-11-12T09:30:00+00:00", "b": "PMU", "m": "pmu|b", "k": "RESULTAT_1N2|MATCH||DOM", "c": 1.90},
    ])
    cotes = R.dernieres_cotes(tmp_path, {R.cle_historique(p) for p in cands}, NOW)
    garde = R.jouables(cands, cotes)
    assert [p["id"] for p in garde] == ["a"] and garde[0]["cote_actuelle"] == 2.05     # 1,95 × 1,02 = 1,989 ≤ 2,05
    m = R.messages(garde, 1000, NOW)[0]
    assert "Lens @ " not in m["message"] and "@ 2,05 (min 1,99)" in m["message"] and "mise" in m["message"]
    assert '<a href="https://www.pmu.fr/sport/event/1">ouvrir</a>' in m["message"] and m["html"] == "1"


class Rep(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_envoi_unique_dans_l_heure(tmp_path):
    p = pari("a")
    historique(tmp_path, [{"t": "2026-11-12T09:00:00+00:00", "b": "PMU", "m": "pmu|a",
                           "k": "RESULTAT_1N2|MATCH||DOM", "c": 2.10}])
    envoyes = {empreinte_prix(p): "2026-11-12T02:00:00+00:00"}
    appels = []
    ouvrir = lambda req, timeout=0: appels.append(req) or Rep(b'{"status": 1}')
    env = {"PUSHOVER_APP_TOKEN": "t", "PUSHOVER_USER_KEY": "u"}
    r = E.recap_pushover(tmp_path, [p], envoyes, env, NOW, ouvrir)
    assert r["envoye"] and r["jouables"] == 1 and len(appels) == 1
    assert not E.recap_pushover(tmp_path, [p], envoyes, env, NOW, ouvrir)["envoye"]        # déjà fait aujourd'hui
    assert len(appels) == 1
