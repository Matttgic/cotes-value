"""Audit des boosts du 26/11/2026 : intitulés réels relevés du 16 au 26/11 (donnees/boosts.json), règlement à la main
et onglet Bilan › Boosts. Chaque test échoue sur le code d'avant l'audit."""
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cotes import boosts as B
from cotes.direct import boosts_sites as S

RACINE = Path(__file__).resolve().parents[1]
T = datetime(2026, 11, 26, 23, 0, tzinfo=timezone.utc)


# --- 1. Traductions sûres ajoutées (intitulés réels, bookmaker et date de première lecture en commentaire)
@pytest.mark.parametrize("libelle, dom, ext, sport, attendu", [
    # NetBet, 20/11 : le match rappelé en tête
    ("Troyes/Le Havre - Les deux équipes marquent", "Troyes", "Le Havre", "football",
     ("BOTH_TEAMS_TO_SCORE", "MATCH", None, "YES")),
    # OlyBet, 24 et 26/11 : écart sans « d'écart »
    ("Paris SG gagne par au moins 3 buts", "Nice", "Paris SG", "football", ("HANDICAP", "MATCH", 2.5, "EXT")),
    ("Paris SG gagne de 3 buts ou plus", "Paris SG", "AS Rome", "football", ("HANDICAP", "MATCH", -2.5, "DOM")),
    # Winamax : « (hors prol. et TAB) » = temps réglementaire (le match en football)
    ("San Jose Earthquakes gagne par au moins 2 buts d'écart (hors prol. et TAB)", "San Jose Earthquakes",
     "Houston Dynamo", "football", ("HANDICAP", "MATCH", -1.5, "DOM")),
    ("Winnipeg Jets marque au moins 4 buts (hors prol. et TAB)", "Winnipeg Jets", "Ottawa Senators", "hockey",
     ("TOTAL_DOM", "TEMPS_REG", 3.5, "PLUS")),
    # Winamax : premier set, sets, première mi-temps
    ("Arthur Fils gagne le premier set", "Alexander Zverev", "Arthur Fils", "tennis", ("VAINQUEUR", "SET1", None, "EXT")),
    ("Plus de 2,5 sets lors du match", "Alexander Zverev", "Carlos Alcaraz", "tennis", ("SETS_TOTAL", "MATCH", 2.5, "PLUS")),
    ("Les deux équipes marquent en première mi-temps", "FC Barcelone", "Villarreal", "football",
     ("BOTH_TEAMS_TO_SCORE", "MT1", None, "YES")),
    ("Lyon marque au moins 2 buts en première mi-temps", "Lyon", "Lillestrom SK", "football",
     ("TOTAL_DOM", "MT1", 1.5, "PLUS")),
])
def test_traductions_ajoutees(libelle, dom, ext, sport, attendu):
    p = B.traduire(libelle, dom, ext, sport)
    assert len(p) == 1 and (p[0]["marche"], p[0]["periode"], p[0]["ligne"], p[0]["issue"]) == attendu


@pytest.mark.parametrize("libelle, dom, ext, sport", [
    # NetBet, 22/11 : traduit avant en « Marseille/Le Mans - Gouiri Ou Harit Premier : plus de 0,5 buts »
    ("Marseille/Le Mans - Gouiri ou Harit premier buteur ?", "Marseille", "Le Mans", "football"),
    ("Kylian Mbappé premier buteur", "Real Madrid", "PSV Eindhoven", "football"),
    # ambigus, toujours écartés : joueur en 1re mi-temps (pas de référence), « gagne les deux mi-temps », combinés
    ("Davie Selke marque au moins un but en 1ère mi-temps", "Istanbul Basaksehir", "Çorum", "football"),
    ("Athletic Bilbao gagne les deux mi-temps", "Athletic Bilbao", "Espanyol Barcelone", "football"),
    ("Paris SG gagne avec plus de 2 buts", "Paris SG", "AS Rome", "football"),
    ("Marseille gagne & plus de 3.5 buts", "Marseille", "Levski Sofia", "football"),
    ("Arthur Fils gagne le premier set et le match", "Alexander Zverev", "Arthur Fils", "tennis"),
    ("Troyes/Lens - Les deux équipes marquent", "Troyes", "Le Havre", "football"),
])
def test_intitules_ecartes(libelle, dom, ext, sport):
    assert B.traduire(libelle, dom, ext, sport) == []


def test_hors_prolongation_garde_le_temps_reglementaire_seulement():
    p = B.traduire("Florida Panthers gagne (hors prol. et TAB)", "Florida Panthers", "Buffalo Sabres", "hockey")
    assert [(x["marche"], x["periode"]) for x in p] == [("RESULTAT_1N2", "TEMPS_REG")]


# --- 2. Paris de saison : les dates ne sont plus des saisons, les vrais paris de compétition sont reconnus
@pytest.mark.parametrize("texte, attendu", [
    ("Plus de 1,5 buts dans chacun des 5 matchs du jour Ligue 2 - 20/11", False),        # Unibet, 20/11
    ("Au moins 5 équipes marquent 3 buts ou plus CB - ChampionsLeague - Multiplex 21h (23/11)", False),
    ("Cade Cunningham termine meilleur marqueur du match et son équipe gagne", False),
    ("Ligue 1 - 11/12", False),
    ("Marseille podium de Ligue 1 Ligue 1 - 2026/2027", True),                           # Unibet, 25/11
    ("Les San Antonio Spurs champions NBA", True),
    ("La France remporte la Ligue des Nations", True),
    ("La France remporte le Tournoi", True),
    ("NBA - Paris TrashTalk 26/27", True),
])
def test_long_terme(texte, attendu):
    assert S.long_terme(texte) is attendu


def test_pari_de_saison_toujours_passer():
    r = {"libelle": "Marseille podium de Ligue 1", "domicile": "Ligue 1", "exterieur": "2026/2027", "long_terme": True,
         "cote": 6.0, "cote_avant": 4.5, "marge_seuil": 0.25, "value": None}
    assert B.verdict(r) == ("passer", None)


# --- 3. Règlement : un pari de saison n'est pas « à régler », un boost republié n'est réglé qu'une fois
def _ep(ident, libelle, premier, debut="2026-11-26T20:00:00+00:00", **plus):
    return {"id": ident, "bookmaker": "NetBet", "libelle": libelle, "domicile": "Troyes", "exterieur": "Le Havre",
            "debut": debut, "premier": premier, "cote": 1.8, "mise_max": 10.0, "verdict_initial": "jouer", **plus}


def test_a_regler_sans_pari_de_saison_ni_doublon():
    eps = [_ep("netbet|1|a", "Troyes/Le Havre - Les deux équipes marquent", "2026-11-26T09:00:00+00:00"),
           _ep("netbet|1|b", "Troyes/Le Havre - Les deux équipes marquent", "2026-11-26T15:39:00+00:00"),
           _ep("unibet|2|c", "Marseille podium de Ligue 1", "2026-11-25T10:00:00+00:00", bookmaker="Unibet",
               domicile="Ligue 1", exterieur="2026/2027", debut="2026-11-25T22:59:00+00:00")]
    assert [x["id"] for x in B.boosts_a_regler(eps, {}, T)] == ["netbet|1|a"]
    regle = {"netbet|1|a": B.regler_boost(eps[0], "gagne", T)}
    assert B.boosts_a_regler(eps, regle, T) == []                   # la copie republiée ne revient pas


# --- 4. Bilan › Boosts : « à jouer » en tête avec mise conseillée et gain attendu, le reste replié
@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_onglet_boosts_a_jouer_en_tete():
    script = r"""
const vm = require('node:vm'), fs = require('node:fs');
const zones = {};
const el = id => (zones[id] = zones[id] || {id, innerHTML: '', textContent: '', dataset: {}});
const c = vm.createContext({document: {getElementById: el}, lire: () => null, ecrire: () => {},
  e: s => String(s ?? ''), cote: x => x == null ? '—' : Number(x).toFixed(2), pct: x => (100 * x).toFixed(1) + ' %',
  signe: x => x > 0 ? 'pos' : x < 0 ? 'neg' : '', nomSport: s => s, horairePari: () => '', hm: () => '',
  boutonBookmaker: () => '', console, D: {}});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), c);
c.D.boosts = {maj: '2026-11-26T20:00:00+00:00', seuil_alerte: 0.03, actuels: [
  {libelle: 'PASSE', verdict: 'passer', value: -0.07, cote: 2.4, mise_max: 20},
  {libelle: 'JUGE_SANS_JUSTE', verdict: 'jouer', value: null, cote: 3, mise_max: 25, hausse: 0.2, marge_seuil: 0.17},
  {libelle: 'FORT', verdict: 'jouer', value: 0.05, cote: 2.2, mise_max: 20, cote_juste: 2.1, reference: 'Pinnacle'},
  {libelle: 'FAIBLE', verdict: 'jouer', value: 0.01, cote: 3.6, mise_max: 10, cote_juste: 3.5, reference: 'Pinnacle'}]};
vm.runInContext('rendreBoostsListe()', c);
process.stdout.write(zones['bo-actuels'].innerHTML);
"""
    html = subprocess.run(["node", "-e", script, str(RACINE / "web" / "boosts.js")], capture_output=True, text=True,
                          check=True).stdout
    ordre = [html.index(x) for x in ("FORT", "FAIBLE", "JUGE_SANS_JUSTE", "<details", "PASSE")]
    assert ordre == sorted(ordre)                                    # value d'abord, puis sans cote juste, puis replié
    assert "3 à jouer" in html and "+1,10 €" in html                 # 20 × 5 % + 10 × 1 % = 1,10 €
    assert "Mise conseillée <b>20 €</b>" in html and "gain attendu inconnu" in html
    assert html.count("value ≥ 3.0 %") == 1 and "À passer (1)" in html and "value -7.0 %" in html
