"""Échecs non bloquants rendus visibles (cotes/echecs.py) et ajouts gzip atomiques (cotes/ecriture.py)."""
import gzip
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cotes import echecs, historique_cotes
from cotes.ecriture import ajouter_gzip
from scripts import cycle

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
RACINE = Path(__file__).resolve().parents[1]


# --- message court, sans secret --------------------------------------------------------------------------------

def test_message_court_masque_les_secrets_et_tient_sur_une_ligne():
    env = {"PUSHOVER_APP_TOKEN": "abcdef123456", "MODE_COLLECTE": "complet", "ALERTE_WEBHOOK_URL": "https://hook.example/x"}
    e = RuntimeError("échec abcdef123456\nhttps://user:mdp@api.example/v1?apikey=zzz9 token=qqq111 sur https://hook.example/x")
    m = echecs.message_court(e, env)
    assert m.startswith("RuntimeError: échec ***")
    assert "\n" not in m
    for secret in ("abcdef123456", "mdp", "zzz9", "qqq111", "hook.example"):
        assert secret not in m, m
    assert len(echecs.message_court("x" * 1000, {})) == echecs.LONGUEUR
    assert echecs.message_court(KeyError(), {}) == "KeyError"


def test_annotation_warning_echappee():
    sortie = io.StringIO()
    echecs.annoter("qwen", "a%b\nc", sortie)
    assert sortie.getvalue() == "::warning title=Non bloquant %3A qwen::a%25b%0Ac\n"


# --- liste récente et compteur dans etat.json -----------------------------------------------------------------

def test_fusionner_compte_garde_7_jours_et_borne_la_liste():
    vieux = {"quand": (NOW - timedelta(days=8)).isoformat(), "etape": "qwen", "message": "vieux"}
    etat = {"autre": 1, "echecs_recents": {"total": 5, "liste": [vieux]}}
    nouveaux = [{"quand": NOW.isoformat(), "etape": "redecision", "message": f"m{i}"} for i in range(40)]
    bloc = echecs.fusionner(etat, nouveaux, NOW)
    assert etat["autre"] == 1 and etat["echecs_recents"] is bloc
    assert bloc["total"] == 45 and len(bloc["liste"]) == echecs.MAX_LISTE
    assert bloc["liste"][-1]["message"] == "m39" and all(x["message"] != "vieux" for x in bloc["liste"])
    assert bloc["maj"] == NOW.isoformat(timespec="seconds")
    # cycle sans échec : rien n'est compté, la date du dernier échec reste
    assert echecs.fusionner(etat, [], NOW + timedelta(minutes=5))["total"] == 45
    assert etat["echecs_recents"]["maj"] == NOW.isoformat(timespec="seconds")


def test_enregistrer_garde_le_reste_de_etat_et_n_ecrase_pas_un_etat_illisible(tmp_path):
    (tmp_path / "etat.json").write_text(json.dumps({"dernier_cycle": {"debut": "x"}}), encoding="utf-8")
    sortie = io.StringIO()
    assert echecs.enregistrer(tmp_path, "alertes_chrome", "Service notifications HTTP 500", NOW, sortie)
    etat = json.loads((tmp_path / "etat.json").read_text(encoding="utf-8"))
    assert etat["dernier_cycle"] == {"debut": "x"}
    assert etat["echecs_recents"]["total"] == 1
    assert etat["echecs_recents"]["liste"][0] == {"quand": NOW.isoformat(timespec="seconds"), "etape": "alertes_chrome",
                                                  "message": "Service notifications HTTP 500"}
    assert sortie.getvalue().startswith("::warning ")
    (tmp_path / "etat.json").write_text("{abîmé", encoding="utf-8")
    assert echecs.enregistrer(tmp_path, "alertes_chrome", "x", NOW, io.StringIO()) is False
    assert (tmp_path / "etat.json").read_text(encoding="utf-8") == "{abîmé"
    assert not list(tmp_path.glob("*.tmp"))


# --- les try/except du cycle n'avalent plus les erreurs ----------------------------------------------------------

def test_redecision_et_qwen_en_echec_sont_notes_sans_bloquer(tmp_path, monkeypatch, capsys):
    journal = {"debut": NOW.isoformat(), "etapes": {}}

    def casse(*a, **k):
        raise ValueError("registre incohérent")
    cycle.redecider([], NOW, journal, casse)
    from cotes import strategie_qwen
    monkeypatch.setattr(strategie_qwen, "suivre", casse)
    cycle.suivre_qwen(tmp_path, [], [], NOW, journal)
    assert journal["redecision"] == {"erreur": "ValueError: registre incohérent"}
    assert journal["qwen"] == {"erreur": "ValueError: registre incohérent"}
    assert [e["etape"] for e in journal["echecs"]] == ["redecision", "qwen"]
    sortie = capsys.readouterr().out
    assert "::warning title=Non bloquant %3A redecision::ValueError: registre incohérent" in sortie
    assert "::warning title=Non bloquant %3A qwen::" in sortie
    # sans erreur : comportement inchangé, rien de noté
    j2 = {"debut": NOW.isoformat(), "etapes": {}}
    cycle.redecider([], NOW, j2, lambda r, m: 3)
    assert j2["redecision"] == {"ajoutees": 3} and "echecs" not in j2


def test_historique_des_cotes_en_echec_est_note(tmp_path, monkeypatch, capsys):
    from tests.test_stockage_memoire import _cycle_unibet, ligne
    monkeypatch.setenv("MEMOIRE_CHEMIN", str(tmp_path / "memoire"))
    _cycle_unibet(monkeypatch, [ligne()])

    def casse(*a, **k):
        raise OSError("disque plein")
    monkeypatch.setattr(historique_cotes, "ajouter", casse)
    journal = {"etapes": {}}
    _, _, lignes = cycle.collecter_prematch("complet", NOW, journal, tmp_path / "donnees")
    assert len(lignes) == 1                                      # la collecte continue
    assert journal["historique_cotes"] == {"erreur": "OSError: disque plein"}
    assert journal["echecs"][0]["etape"] == "historique_cotes"
    assert "::warning title=Non bloquant %3A historique_cotes::OSError: disque plein" in capsys.readouterr().out


def test_alertes_chrome_en_echec_code_1_annonce_et_note(tmp_path):
    donnees = tmp_path / "donnees"
    donnees.mkdir()
    (donnees / "paris.json").write_text("[]", encoding="utf-8")
    (donnees / "etat.json").write_text(json.dumps({"dernier_cycle": {}}), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ACTIONS_ID_TOKEN", "PUSHOVER", "ALERTE_WEBHOOK"))}

    def lancer():
        return subprocess.run([sys.executable, "scripts/envoyer_notifications.py", "--donnees", str(donnees),
                               "--flux", str(tmp_path / "flux.json")], cwd=RACINE, env=env, capture_output=True,
                              text=True, timeout=120)
    # 1. plantage du script (fichier manquant) : traceback et code 1 comme avant, mais annoncé et noté
    r = lancer()
    assert r.returncode == 1 and "Traceback" in r.stderr
    assert "::warning title=Non bloquant %3A alertes_chrome::FileNotFoundError" in r.stdout
    # 2. envoi refusé (pas d'identité GitHub Actions hors CI) : code 1 inchangé (continue-on-error), annoncé et noté
    (donnees / "opportunites_actuelles.json").write_text("[]", encoding="utf-8")
    r = lancer()
    assert r.returncode == 1, r.stderr
    assert "::warning title=Non bloquant %3A alertes_chrome::Identité GitHub Actions indisponible" in r.stdout
    etat = json.loads((donnees / "etat.json").read_text(encoding="utf-8"))
    assert etat["echecs_recents"]["total"] == 2 and etat["dernier_cycle"] == {}
    assert [e["etape"] for e in etat["echecs_recents"]["liste"]] == ["alertes_chrome"] * 2


def test_workflow_garde_continue_on_error_et_signale_l_echec():
    import yaml
    wf = yaml.safe_load((RACINE / ".github/workflows/collecte.yml").read_text(encoding="utf-8"))
    steps = wf["jobs"]["cycle"]["steps"]
    i = next(i for i, s in enumerate(steps) if s.get("name") == "Envoyer les nouvelles alertes Chrome")
    assert steps[i]["continue-on-error"] is True and steps[i]["id"] == "alertes_chrome"
    suivant = steps[i + 1]
    assert suivant["if"] == "steps.alertes_chrome.outcome == 'failure'"
    assert "::warning" in suivant["run"] and "secrets" not in json.dumps(suivant)


# --- ajouts gzip atomiques ----------------------------------------------------------------------------------------

def _lire(chemin):
    with gzip.open(chemin, "rt", encoding="utf-8") as f:
        return f.read()


def test_ajout_gzip_identique_a_l_ancien_mode_at(tmp_path, monkeypatch):
    monkeypatch.setattr(gzip.time, "time", lambda: 1_790_000_000.0)       # même horodatage d'en-tête
    ancien, nouveau = tmp_path / "a" / "2026-10-30.jsonl.gz", tmp_path / "b" / "2026-10-30.jsonl.gz"
    ancien.parent.mkdir()
    for lot in ('{"x":1}\n', '{"x":2}\n{"é":3}\n'):
        with gzip.open(ancien, "at", encoding="utf-8") as f:
            f.write(lot)
        ajouter_gzip(nouveau, lot)
    assert nouveau.read_bytes() == ancien.read_bytes()                     # octet pour octet
    assert _lire(nouveau) == '{"x":1}\n{"x":2}\n{"é":3}\n'
    ajouter_gzip(nouveau, "")                                               # rien à ajouter : fichier intact
    assert nouveau.read_bytes() == ancien.read_bytes()


@pytest.mark.parametrize("panne", ["copie", "synchronisation", "remplacement"])
def test_ajout_gzip_interrompu_laisse_l_ancien_fichier_intact(tmp_path, monkeypatch, panne):
    f = tmp_path / "opportunites" / "2026-10-30.jsonl.gz"
    ajouter_gzip(f, '{"a":1}\n')
    avant = f.read_bytes()

    def casse(*a, **k):
        raise KeyboardInterrupt("job tué")
    if panne == "copie":                       # tué pendant la copie : moitié du fichier dans le .tmp
        def copie_partielle(src, dst):
            Path(dst).write_bytes(Path(src).read_bytes()[:10])
            casse()
        monkeypatch.setattr("cotes.ecriture.shutil.copyfile", copie_partielle)
    elif panne == "synchronisation":           # tué après l'écriture du nouveau membre, avant le remplacement
        monkeypatch.setattr("cotes.ecriture.os.fsync", casse)
    else:
        monkeypatch.setattr("cotes.ecriture.os.replace", casse)
    with pytest.raises(KeyboardInterrupt):
        ajouter_gzip(f, '{"b":2}\n' * 1000)
    assert f.read_bytes() == avant and _lire(f) == '{"a":1}\n'
    assert not list(f.parent.glob("*.tmp"))


def test_historique_cotes_reste_lisible_apres_plusieurs_ajouts(tmp_path):
    from tests.test_stockage_memoire import ligne
    h1 = {"unibet": {"lignes": [ligne()]}}
    h2 = {"unibet": {"lignes": [ligne(cote=2.1)]}}
    assert historique_cotes.ajouter(tmp_path, {}, h1, NOW) == 2
    assert historique_cotes.ajouter(tmp_path, historique_cotes.index(h1), h2, NOW) == 1
    lignes = [json.loads(x) for x in _lire(tmp_path / "cotes" / "2026-10-30.jsonl.gz").splitlines()]
    assert [x.get("c") for x in lignes] == [None, 2.0, 2.1]
