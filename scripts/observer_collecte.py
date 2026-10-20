"""Observe une seule collecte existante, sans simulation, notification ni publication."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnostiquer_fraicheur import instant, resumer

CIBLES = ("pinnacle_direct", "winamax", "betclic", "pmu", "unibet")

@contextmanager
def environnement_essai():
    changements = {"PINNODDS_API_KEY": "", "PINBOOK_API_KEY": "",
                    "SOURCE_OLYBET": "off", "SOURCE_NETBET": "off"}
    avant = {k: os.environ.get(k) for k in changements}
    os.environ.update(changements)
    try:
        yield
    finally:
        for k, valeur in avant.items():
            if valeur is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = valeur

def regrouper(pin, francaises):
    groupes = {nom: [] for nom in CIBLES}
    groupes["pinnacle_origine_inattendue"] = []
    groupes["bookmaker_non_identifie"] = []
    for ligne in pin:
        if not isinstance(ligne, dict):
            continue
        origine = ligne.get("origine")
        nom = "pinnacle_direct" if origine in (None, "", "direct") else "pinnacle_origine_inattendue"
        groupes[nom].append(dict(ligne))
    for ligne in francaises:
        if not isinstance(ligne, dict):
            continue
        nom = str(ligne.get("bookmaker") or ligne.get("source") or "").lower()
        nom = {"unibet-fr": "unibet", "unibet_fr": "unibet"}.get(nom, nom)
        if nom not in CIBLES or nom == "pinnacle_direct":
            nom = "bookmaker_non_identifie"
        groupes[nom].append(dict(ligne))
    return groupes

def observer(cycle, sortie, reserve=None, mode="complet", horloge=None):
    horloge = horloge or (lambda: datetime.now(timezone.utc))
    sortie = Path(sortie)
    if sortie.exists():
        raise ValueError("Le dossier de sortie doit etre nouveau")
    if mode not in {"test", "complet"}:
        raise ValueError("Mode inconnu")
    debut = horloge()
    journal = {"debut": debut.isoformat(), "mode": mode, "etapes": {}}
    with tempfile.TemporaryDirectory(prefix="cotes-observation-") as temporaire:
        travail = Path(temporaire)
        if reserve is not None:
            reserve = Path(reserve)
            if not reserve.is_file():
                raise ValueError("Reserve attendue introuvable")
            shutil.copyfile(reserve, travail / "horizon_direct.json")
        with environnement_essai():
            pin, _poly, francaises = cycle.collecter_prematch(mode, debut, journal, travail)
    fin = horloge()
    rapports = {}
    for nom, lignes in regrouper(pin, francaises).items():
        rapport = resumer(lignes, fin, 60)
        rapport["lignes_presentes"] = len(lignes)
        rapport["etat"] = "lignes_presentes" if lignes else "aucune_ligne_observee"
        rapport["observations_depuis_debut_essai"] = sum(
            1 for l in lignes if (t := instant(l.get("collecte_recue")) or instant(l.get("collecte")))
            is not None and debut <= t <= fin)
        rapports[nom] = rapport
    etapes = {}
    for nom in ("pinnacle", "winamax_direct", "betclic_direct", "pmu_direct", "unibet_direct"):
        etape = journal.get("etapes", {}).get(nom, {})
        etapes[nom] = {k: etape[k] for k in ("ok", "secondes", "degrade") if k in etape}
    rapport = {"debut": debut.isoformat(), "fin": fin.isoformat(), "mode": mode,
               "seuil_s": 60, "sources": rapports, "etapes": etapes,
               "secours_pinnacle": "desactives_pour_ne_pas_consommer_de_quota",
               "limites": ["Aucun taux d'exhaustivite sans inventaire attendu independant.",
                           "Les sports francais restent limites par les references du cycle existant.",
                           "Une reserve peut contenir des observations de cycles precedents.",
                           "Pinnacle direct est observe ; ses secours ne sont pas testes.",
                           "Un seul essai ne prouve pas une disponibilite continue.",
                           "Aucun prix amont ou delai navigateur n'est certifie."]}
    sortie.mkdir(parents=True, exist_ok=False)
    (sortie / "fraicheur-cycle.json").write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    return rapport

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sortie", required=True)
    parser.add_argument("--reserve")
    parser.add_argument("--mode", choices=("test", "complet"), default="test")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts import cycle
    try:
        rapport = observer(cycle, args.sortie, args.reserve, args.mode)
    except Exception as exc:
        print("Diagnostic interrompu : " + type(exc).__name__, file=sys.stderr)
        return 1
    print(json.dumps({"debut": rapport["debut"], "fin": rapport["fin"],
                      "lignes_par_source": {k: v["lignes_presentes"] for k, v in rapport["sources"].items()}}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
