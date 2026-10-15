"""Journal : causalité, vrais délais, refus des inconnues, isolation des données."""
import copy
import json
from datetime import datetime, timedelta, timezone

from cotes.live_papier import (analyser, enregistrer, fusionner, lire, pause, relever,
                               traduire_pulse, vide)

NOW = datetime(2026, 10, 15, 20, tzinfo=timezone.utc)


def frames():
    stamp, start = NOW.isoformat(), (NOW - timedelta(hours=1)).isoformat()
    event = {"eventId": "w1", "sport": "soccer", "home": "Alpha", "away": "Bravo", "startTime": start,
             "score": {"home": "0", "away": "0"}, "updatedAt": stamp,
             "matchClock": {"period": "Mi-temps", "running": False},
             "markets": [{"marketId": "m", "canonicalMarket": "MATCH_RESULT", "period": "FULL_TIME",
                          "isActive": True, "rawName": "Résultat du match", "updatedAt": stamp,
                          "selections": [{"canonicalOutcome": side, "isActive": True, "odds": odds}
                                         for side, odds in zip(("HOME", "DRAW", "AWAY"), (2.4, 3.5, 3.5))]}]}
    pin = {"id": 1, "type": "matchup", "isLive": True, "startTime": start,
           "state": {"score": {"home": 0, "away": 0}, "period": "HT", "updatedAt": stamp},
           "participants": [{"alignment": "home", "name": "Alpha"}, {"alignment": "away", "name": "Bravo"}]}
    market = {"matchupId": 1, "period": 0, "type": "moneyline", "key": "pin-m", "status": "open",
              "updatedAt": stamp, "prices": [{"designation": side, "price": price}
                                               for side, price in zip(("home", "draw", "away"), (100, 300, 300))]}
    common = {"started_at": (NOW - timedelta(seconds=1)).isoformat(), "received_at": stamp,
              "requests": 1, "error": None}
    return [{**common, "source": "winamax", "events": [event]},
            {**common, "source": "Pinnacle", "sport": "football", "events": [pin], "markets": [market]}]


def test_moteur_l1_reellement_appele_sur_deux_observations_verifiees():
    rows, summary = analyser(frames(), NOW, NOW.isoformat())
    home = next(o for o in rows if o["contrat"]["issue"] == "DOM")
    assert home["signal"]
    assert abs(home["edge"] - .2) < 1e-9
    assert home["l1"]["logic"] == "L1" and home["l1"]["mode"] == "paper"
    assert home["l2"]["reason"] == "cloture_complete_ou_profil_absent"
    assert summary["rafale_sous_20s"]


def test_matchup_live_regular_avec_parent_ne_disparait_pas():
    fs = frames()
    fs[1]['events'][0].update(parentId=99, units='Regular')
    fs[1]['events'].append({**fs[1]['events'][0], 'id':99, 'isLive':False, 'state':{}})
    rows,_=analyser(fs,NOW,'cycle')
    assert any(o['l1'].get('accepted') for o in rows)


def test_horodatage_collecte_ne_remplace_jamais_timestamp_source():
    fs = frames()
    fs[0]["events"][0].pop("updatedAt")
    fs[0]["events"][0]["markets"][0].pop("updatedAt")
    rows, _ = analyser(fs, NOW, "cycle")
    assert rows and not any(o["signal"] for o in rows)
    assert not rows[0]["timestamp_source_verifie"]
    assert rows[0]["l1"]["reason"] == "stale_state"


def test_running_false_et_score_fige_ne_sont_pas_des_pauses():
    assert pause("basket", {"period": "Q3", "running": False}) is None
    assert pause("hockey", {"period": "P1", "running": False}) is None
    assert pause("football", {"minute": 45, "running": False}) is None
    fs = frames()
    fs[0]["events"][0]["matchClock"]["period"] = "Q3"
    rows, summary = analyser(fs, NOW, "cycle")
    assert rows == [] and summary["compteurs"]["pause_non_confirmee"] > 0


def test_rafale_lente_refuse_signaux_meme_si_cotes_sont_fraiches():
    fs = frames()
    fs[0]["started_at"] = (NOW - timedelta(seconds=21)).isoformat()
    rows, summary = analyser(fs, NOW, "cycle")
    assert rows and not any(o["signal"] for o in rows)
    assert not summary["rafale_sous_20s"]
    assert all(o["edge"] is None for o in rows)
    assert all(not o['l1']['accepted'] and not o['l2']['accepted'] for o in rows)


def test_prix_plus_15_plus_30_sont_observes_et_delai_reel_conserve():
    fs = frames()
    rows, _ = analyser(fs, NOW, "cycle")
    original = rows[0]
    fs[0]["events"][0]["markets"][0]["selections"][0]["odds"] = 2.1
    follow = relever(original, fs[:1], NOW + timedelta(seconds=18), 15)
    assert follow["cote"] == 2.1 and follow["delai_reel_secondes"] == 18
    assert follow["statut"] == "observe" and not follow.get("hors_fenetre")
    late = relever(original, [], NOW + timedelta(seconds=42), 30)
    assert late["cote"] is None and late["hors_fenetre"]
    fs[0]["events"][0]["matchClock"]["period"] = "2ème mi-temps"
    assert relever(original, fs[:1], NOW + timedelta(seconds=30), 30)["statut"] == "reprise_ou_marche_inactif"


def test_marche_suspendu_meme_prix_autre_issue_n_est_pas_actif():
    fs = frames()
    fs[0]["events"][0]["markets"][0]["selections"][0]["isActive"] = False
    quotes = traduire_pulse(fs[0], "cycle")
    assert not any(r["quote"].market.issue == "DOM" for r in quotes)


def test_journal_idempotent_ne_reecrit_pas_un_signal_et_ne_touche_pas_paris(tmp_path):
    rows, cycle = analyser(frames(), NOW, "cycle-1")
    first = fusionner(vide(), rows, cycle)
    future = copy.deepcopy(rows)
    for o in future:
        o["id"] += "-2"
        o["cote"] = 99
    merged = fusionner(first, future, cycle)
    assert merged["signaux"][0]["cote"] == first["signaux"][0]["cote"]
    assert len(fusionner(first, rows, cycle)["observations"]) == len(rows)
    paris = tmp_path / "paris.json"
    paris.write_text('[{"preuve":"historique"}]')
    before = paris.read_bytes()
    path = tmp_path / "docs/live_papier.json"
    enregistrer(path, merged)
    assert lire(path, {}) == json.loads(path.read_text())
    assert paris.read_bytes() == before and not path.with_suffix(".json.tmp").exists()


def test_l2_est_execute_avec_cloture_complete_et_contexte_verifie():
    fs = frames()
    fs[0]["events"][0]["context_complete"] = True
    rows, _ = analyser(fs, NOW, "cycle")
    event = rows[0]["contrat"]["event_id"]
    models = {event: {"type": "poisson", "closing": {
        "event_id": event, "sport": "football", "reference": "Pinnacle",
        "kickoff": (NOW - timedelta(hours=1)).isoformat(),
        "captured_at": (NOW - timedelta(hours=1, seconds=10)).isoformat(),
        "oldest_component_at": (NOW - timedelta(hours=1, seconds=12)).isoformat(),
        "rules": rows[0]["contrat"]["rules"], "version": "test-synthetique", "scope": "REGULATION"},
        "parameters": {"home_rate": 3, "away_rate": .8, "second_half_share": .55}}}
    rows, _ = analyser(fs, NOW, "cycle", models)
    assert rows[0]["l2"]["logic"] == "L2"
    assert rows[0]["l2"]["reason"] in {"experimental_candidate", "edge_too_small"}


def test_site_journal_absent_et_present_sans_polluer_bilan(tmp_path):
    from scripts.site_web import construire
    (tmp_path / "paris.json").write_text("[]")
    dest = tmp_path / "site"
    html1 = construire(tmp_path, dest).read_text()
    assert 'id="live-papier"' in html1
    rows, cycle = analyser(frames(), NOW, "cycle")
    journal = fusionner(vide(), rows, cycle)
    enregistrer(tmp_path / "docs/live_papier.json", journal)
    html2 = construire(tmp_path, dest).read_text()
    assert '"mode":"papier"' in html2 and '"match":"Alpha – Bravo"' in html2
    assert json.loads((dest / "live_papier.json").read_text())["observations"]
    assert (tmp_path / "paris.json").read_text() == "[]"
