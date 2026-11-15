"""Couches à sens unique (docs/architecture-cible.md, 2.1 et E0.3).

Chaque module de `cotes/` et `scripts/` appartient à une couche. Un module n'importe que sa couche ou celles à
sa gauche dans `RANG` ; `cotes/` n'importe jamais `scripts/` ; un script d'exploitation n'importe pas un autre
script (les études, elles, le peuvent). Les imports lus dans les fonctions comptent aussi.

Les violations d'aujourd'hui sont listées dans `EXCEPTIONS` : chaque étape de la refonte doit en retirer ou n'en
ajouter aucune. Le test échoue si un module n'est pas classé, si une violation apparaît ou si une exception
n'existe plus (la retirer de la liste).
"""
import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# vocabulaire : traduction des marchés et des noms, partagée par les lecteurs (sources) et le domaine
RANG = ["socle", "vocabulaire", "sources", "domaine", "paris", "strategies", "bilans", "alertes", "site", "cycle",
        "scripts", "etudes"]
RANG = {c: i for i, c in enumerate(RANG)}
RANG["site"] = RANG["alertes"]          # alertes et site : même couche

_PAR_COUCHE = {
    "socle": "cotes cotes.config cotes.temps cotes.delai cotes.connexion cotes.securite cotes.echecs cotes.memoire "
             "cotes.historiques cotes.stockage cotes.fraicheur cotes.protection cotes.surveillance cotes.derive",
    "vocabulaire": "cotes.pulsescore cotes.marches cotes.joueurs cotes.inconnus cotes.marge cotes.correspondance "
                   "cotes.liens",
    "sources": "cotes.pinnacle cotes.pinnacle_secours cotes.polymarket cotes.polymarket_flux cotes.smarkets "
               "cotes.reprise cotes.resultats cotes.livescore cotes.flashscore cotes.scores365 cotes.resultats_nhl "
               "cotes.theodds cotes.propline cotes.thesportsdb cotes.sources_resultats cotes.direct "
               "cotes.direct.betclic cotes.direct.betfair cotes.direct.draftkings cotes.direct.fanduel "
               "cotes.direct.horizon cotes.direct.matchbook cotes.direct.netbet cotes.direct.olybet "
               "cotes.direct.pmu cotes.direct.unibet cotes.direct.winamax",
    "domaine": "cotes.controle cotes.comparaison cotes.mouvement cotes.props",
    "paris": "cotes.simulation cotes.reglement cotes.mises cotes.props_papier",
    "strategies": "cotes.decisions cotes.convergence cotes.laboratoire cotes.memo cotes.pauses "
                  "cotes.strategies_prudentes cotes.strategie_recommandee cotes.strategie_chatgpt "
                  "cotes.strategie_claude_defi cotes.strategie_claude_humain cotes.strategie_claude_opus "
                  "cotes.strategie_claude_signal cotes.strategie_coeur cotes.strategie_commune "
                  "cotes.strategie_conseil cotes.strategie_defi cotes.strategie_eden cotes.strategie_gemini "
                  "cotes.strategie_gemini_defi cotes.strategie_grok cotes.strategie_jules cotes.strategie_jules_v2 "
                  "cotes.strategie_liquidite cotes.strategie_m3 cotes.strategie_qwen",
    "bilans": "cotes.analyste cotes.notation cotes.recommandations cotes.protocole cotes.decision cotes.evenements "
              "cotes.analyse_marche cotes.analyse_marche.cache cotes.analyse_marche.lecture "
              "cotes.analyse_marche.meneurs cotes.analyse_marche.opportunites cotes.analyse_marche.segments",
    "alertes": "cotes.notifications cotes.ordres cotes.recap_jouables",
    "site": "scripts.site_web",
    "cycle": "",                        # futur cotes/pipeline/
    "scripts": "scripts.cycle scripts.envoyer_notifications scripts.envoyes_secours scripts.serveur_direct "
               "scripts.serveur_actif scripts.protocole scripts.verifier_secrets scripts.verifier_strategie_jules "
               "scripts.verifier_strategie_jules_v2 scripts.archiver_donnees_brutes scripts.sonde_betfair "
               "scripts.sonde_sources_us scripts.sonde_unibet scripts.empreinte_site",
    "etudes": "scripts.analyse_chatgpt scripts.analyse_marche scripts.audit_bilans scripts.avantage_reel "
              "scripts.comparer_secours_pinnacle scripts.comparer_strategies scripts.cote_juste scripts.durer "
              "scripts.etude_duree_values scripts.modele_prix scripts.recherche_cloture scripts.strategie_mises",
}
COUCHES = {m: c for c, noms in _PAR_COUCHE.items() for m in noms.split()}

# Violations relevées le 15/11/2026 (23). À faire baisser, jamais monter.
EXCEPTIONS = {
    # sources -> domaine : prix des bourses convertis par comparaison.reference_echange ; résultats -> bilans
    ("cotes.smarkets", "cotes.comparaison"),
    ("cotes.direct.betfair", "cotes.comparaison"),
    ("cotes.direct.matchbook", "cotes.comparaison"),
    ("cotes.resultats", "cotes.evenements"),
    # paris -> stratégies et bilans : la prise marque chaque pari de ses stratégies
    ("cotes.simulation", "cotes.decisions"),
    ("cotes.simulation", "cotes.evenements"),
    ("cotes.simulation", "cotes.strategie_chatgpt"),
    ("cotes.simulation", "cotes.strategie_eden"),
    ("cotes.simulation", "cotes.strategie_gemini"),
    ("cotes.simulation", "cotes.strategie_jules"),
    ("cotes.simulation", "cotes.strategie_jules_v2"),
    ("cotes.simulation", "cotes.strategie_qwen"),
    ("cotes.mises", "cotes.laboratoire"),
    # stratégies -> bilans
    ("cotes.laboratoire", "cotes.evenements"),
    ("cotes.laboratoire", "cotes.notation"),
    ("cotes.strategie_gemini_defi", "cotes.evenements"),
    # scripts qui s'importent entre eux
    ("scripts.cycle", "scripts.site_web"),
    ("scripts.empreinte_site", "scripts.site_web"),
    ("scripts.envoyer_notifications", "scripts.cycle"),
    ("scripts.envoyes_secours", "scripts.cycle"),
    ("scripts.envoyes_secours", "scripts.envoyer_notifications"),
    ("scripts.site_web", "scripts.comparer_strategies"),
    ("scripts.verifier_strategie_jules_v2", "scripts.comparer_strategies"),
}

# importés par sys.path (scripts/ ajouté au chemin) : `from site_web import construire`
NOMS_NUS = {"site_web": "scripts.site_web"}


def modules() -> dict[str, Path]:
    out = {}
    fichiers = list((RACINE / "cotes").rglob("*.py")) + list((RACINE / "scripts").glob("*.py"))
    for f in sorted(fichiers):
        if "__pycache__" in f.parts:
            continue
        parties = f.relative_to(RACINE).with_suffix("").parts
        if parties[-1] == "__init__":
            parties = parties[:-1]
        out[".".join(parties)] = f
    return out


def imports(nom: str, fichier: Path, connus) -> set[str]:
    """Modules internes importés par `nom`, au niveau du fichier comme dans les fonctions."""
    paquet = nom if fichier.name == "__init__.py" else nom.rpartition(".")[0]
    out = set()
    for n in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            cibles = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                base = paquet.split(".")[:len(paquet.split(".")) - (n.level - 1)]
                mod = ".".join(base + ([n.module] if n.module else []))
            else:
                mod = n.module or ""
            mod = NOMS_NUS.get(mod, mod)
            # `from cotes import pinnacle` : le sous-module, sinon le paquet lui-même
            cibles = [f"{mod}.{a.name}" if f"{mod}.{a.name}" in connus else mod for a in n.names]
        else:
            continue
        for c in cibles:
            c = NOMS_NUS.get(c, c)
            while c and c not in connus:              # `import cotes.direct.pmu` -> le module existant
                c = c.rpartition(".")[0]
            if c and c != nom:
                out.add(c)
    return out


def violations() -> set[tuple[str, str]]:
    connus = modules()
    out = set()
    for nom, fichier in connus.items():
        for cible in imports(nom, fichier, connus):
            a, b = COUCHES[nom], COUCHES[cible]
            if (nom.startswith("cotes") and cible.startswith("scripts")) or RANG[b] > RANG[a] or (
                    nom.startswith("scripts.") and cible.startswith("scripts.") and a != "etudes"):
                out.add((nom, cible))
    return out


def test_chaque_module_est_classe():
    connus = modules()
    assert sorted(set(connus) - set(COUCHES)) == [], "module sans couche : l'ajouter à _PAR_COUCHE"
    assert sorted(set(COUCHES) - set(connus)) == [], "module disparu : le retirer de _PAR_COUCHE"


def test_aucune_nouvelle_dependance_a_l_envers():
    nouvelles = sorted(violations() - EXCEPTIONS)
    assert nouvelles == [], "import vers une couche plus à droite (docs/architecture-cible.md, 2.1)"


def test_exceptions_encore_reelles():
    assert sorted(EXCEPTIONS - violations()) == [], "violation corrigée : la retirer d'EXCEPTIONS"


def test_lecture_des_imports_dans_les_fonctions():
    connus = modules()
    # `from site_web import construire` est dans main() : il doit être vu
    assert "scripts.site_web" in imports("scripts.cycle", connus["scripts.cycle"], connus)
    assert "cotes.direct.pmu" in imports("scripts.cycle", connus["scripts.cycle"], connus)
