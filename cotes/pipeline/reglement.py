"""Règlement des paris (déplacé de scripts/cycle.py, E3.1) : lecture des résultats, au plus une fois par
REGLEMENT_MINUTES, depuis la collecte ou le cycle « règlement seul » (reglement.yml)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cotes import flashscore, livescore, propline, reglement, resultats_nhl, scores365, theodds, thesportsdb
from cotes import resultats as resultats_mod
from cotes.depot.json_io import ecrire_json, lire_json
from cotes.pipeline.contexte import Contexte
from cotes.pipeline.outils import charger_paris, etape, signaler

# minutes minimum entre deux règlements (le cycle de 5 min ne lit les résultats qu'une fois par heure)
REGLEMENT_MINUTES = float(os.environ.get("REGLEMENT_MINUTES", "55"))


def reglement_echu(etat: dict, maintenant: datetime, mode: str) -> bool:
    """Le cron et la collecte partagent le même délai et le même verrou de données.

    Une date absente ou invalide ne doit pas arrêter le règlement indéfiniment.
    Une petite dérive d'horloge reste tolérée ; une date très future est invalide.
    """
    if mode != "auto":
        return mode == "oui"
    try:
        dernier = datetime.fromisoformat(str(etat.get("dernier_reglement")).replace("Z", "+00:00"))
        if dernier.tzinfo is None or dernier > maintenant + timedelta(minutes=5):
            return True
        return maintenant - dernier >= timedelta(minutes=REGLEMENT_MINUTES)
    except (TypeError, ValueError, OverflowError):
        return True


def conserver_journal_reglement(etat: dict, journal: dict, effectue: bool) -> None:
    """Un cycle sans règlement conserve le dernier diagnostic réel affiché sur le site."""
    if effectue:
        etat["dernier_reglement"] = journal["debut"]
        etat["dernier_cycle_reglement"] = dict(journal)


def _regler_props(donnees: Path, enregistrements: list, maintenant: datetime) -> dict:
    """Feuilles ESPN des props fictifs encore ouverts. Aucun appel s'il n'y a rien à régler."""
    from cotes import props_papier
    from cotes.resultats import _espn_json, lire_espn
    doc = props_papier.lire(donnees)
    ouverts = [p for p in doc.get("paris") or [] if p.get("statut") == "en_cours"
               and (props_papier._heure(p.get("debut")) or maintenant) <= maintenant]
    if not ouverts:
        return {"regles": 0, "feuilles": 0}
    matchs = props_papier.matchs_espn(enregistrements)
    # Relire ESPN pour chaque sport dont un prop ouvert n'a pas son match dans ce qui est déjà lu. Avant le
    # 11/11/2026, un sport déjà présent (matchs du jour) n'était jamais relu : un prop de la veille ne retrouvait
    # plus son match et restait en attente (Cooper Flagg, Darius Acuff).
    orphelins = [p for p in ouverts if props_papier._match_espn(p, matchs) is None]
    for sport in sorted({p.get("sport") for p in orphelins if p.get("sport")}):
        depuis = min((props_papier._heure(p.get("debut")) for p in orphelins if p.get("sport") == sport
                      and props_papier._heure(p.get("debut"))), default=maintenant)
        matchs += props_papier.matchs_espn(lire_espn(sport, depuis - timedelta(hours=12), maintenant))
    ids = props_papier.feuilles_a_lire(doc, matchs, maintenant)
    sport_de = {str(m.get("espn_id")): m.get("sport") for m in matchs}
    feuilles = props_papier.charger_feuilles([(i, sport_de.get(i)) for i in ids if sport_de.get(i)], _espn_json)
    n = props_papier.regler(doc, matchs, feuilles, maintenant)
    props_papier.ecrire(donnees, doc)
    return {"regles": n, "feuilles": len(feuilles)}


def effectuer_reglement(paris, donnees: Path, maintenant: datetime, journal: dict, mode_reglement: str) -> bool:
    # Le règlement ne lit pas Smarkets : les cotes de l'échange ne servent pas à solder un pari.
    # 4. règlement : ESPN, LiveScore, Flashscore, NHL et les secours, plus les résultats
    #    saisis à la main. Environ une fois par heure, depuis le cron ou la collecte : voir REGLEMENT_MINUTES.
    etat_avant = lire_json(donnees / "etat.json", {})
    dernier_reglement = etat_avant.get("dernier_reglement")
    regler = reglement_echu(etat_avant, maintenant, mode_reglement)
    journal["reglement"] = regler
    if regler:
        resultats_mod.reinitialiser_ignores()
        ouverts_avant = {id(p) for p in paris if p.get("statut") in ("en_cours", "a_regler")}
        manuels = lire_json(donnees / "resultats_manuels.json", {})
        # Les corrections vérifiées sont disponibles sans nouvelle requête réseau.
        reglement.appliquer(paris, {}, manuels, maintenant)
        enregistrements = []
        for sport, depuis in resultats_mod.a_lire(paris, maintenant).items():
            n = len(resultats_mod.ERREURS_ESPN)
            enregistrements += etape(f"resultats_espn_{sport}", journal, resultats_mod.lire_espn,
                                     sport, depuis, datetime.now(timezone.utc)) or []
            signaler(journal, f"resultats_espn_{sport}", resultats_mod.ERREURS_ESPN[n:])
        # LiveScore : gratuit, sans clé (football, hockey, basket, tennis)
        for sport, depuis in livescore.a_lire(paris, maintenant).items():
            n = len(livescore.ERREURS)
            enregistrements += etape(f"resultats_livescore_{sport}", journal, livescore.lire, sport,
                                     livescore.jours_a_lire(depuis, maintenant)) or []
            signaler(journal, f"resultats_livescore_{sport}", livescore.ERREURS[n:])
        nhl = etape("resultats_nhl_officiel", journal, resultats_nhl.collecter, paris, maintenant)
        if nhl:
            enregistrements += nhl[0]
            signaler(journal, "resultats_nhl_officiel", nhl[1])
        resultats = {}
        for p in paris:
            if p["statut"] in ("en_cours", "a_regler") and p["match_id"] not in resultats:
                r = resultats_mod.consensus(p, enregistrements, maintenant)
                if r:
                    resultats[p["match_id"]] = r
        # Flashscore : secours gratuit pour ce qu'aucune source n'a validé, et seule source du volley, du handball
        # et du rugby sans PulseScore (une source seule ne règle qu'après 24 h : cotes/resultats.py)
        restants = [p for p in paris if p["statut"] in ("en_cours", "a_regler") and p["match_id"] not in resultats]
        for sport, jours in flashscore.jours_a_lire(restants, maintenant).items():
            n = len(flashscore.ERREURS)
            enregistrements += etape(f"resultats_flashscore_{sport}", journal, flashscore.lire, sport, jours,
                                     maintenant) or []
            signaler(journal, f"resultats_flashscore_{sport}", flashscore.ERREURS[n:])
        # 365Scores : deuxième avis gratuit pour le basket, le volley, le handball et le rugby (score final seul).
        # Deux sources d'accord règlent tout de suite ; en désaccord, le pari attend une saisie à la main.
        for sport, jours in scores365.jours_a_lire(restants, maintenant).items():
            n = len(scores365.ERREURS)
            enregistrements += etape(f"resultats_365scores_{sport}", journal, scores365.lire, sport, jours,
                                     maintenant) or []
            signaler(journal, f"resultats_365scores_{sport}", scores365.ERREURS[n:])
        for p in restants:
            if p["match_id"] not in resultats:
                r = resultats_mod.consensus(p, enregistrements, maintenant)
                if r:
                    resultats[p["match_id"]] = r
        # TheSportsDB : secours gratuit (clé publique), match par match, pour ce qu'aucune source n'a validé.
        # Seul le score final : une source seule ne règle qu'après 24 h, jamais au hockey (cotes/resultats.py).
        restants_tsdb = [p for p in paris if p["statut"] in ("en_cours", "a_regler") and p["match_id"] not in resultats]
        if restants_tsdb:
            cache_ts = lire_json(donnees / "thesportsdb.json", {})
            n = len(thesportsdb.ERREURS)
            enregistrements += etape("resultats_thesportsdb", journal, thesportsdb.collecter,
                                     restants_tsdb, cache_ts, datetime.now(timezone.utc)) or []
            ecrire_json(donnees / "thesportsdb.json", cache_ts)
            signaler(journal, "resultats_thesportsdb", thesportsdb.ERREURS[n:])
            journal["thesportsdb"] = dict(thesportsdb.RESUME)
            for p in restants_tsdb:
                if p["match_id"] not in resultats:
                    r = resultats_mod.consensus(p, enregistrements, maintenant)
                    if r:
                        resultats[p["match_id"]] = r
        # mi-temps ESPN pour les paris qui en ont besoin (mi-temps/fin, 1re ou 2e mi-temps)
        for p in paris:
            r = resultats.get(p["match_id"])
            if r and p["statut"] in ("en_cours", "a_regler") and (
                    p["periode"] in reglement.SOUS_PERIODES or p["marche"] == "HALF_TIME_FULL_TIME"):
                resultats[p["match_id"]] = resultats_mod.completer_periodes(p, r, enregistrements)
        # Secours The Odds API uniquement pour les résultats encore manquants.
        # Les quatre comptes partagent le cache, jamais quatre voix au consensus.
        cles_odds = [os.environ.get(f"THE_ODDS_API_KEY_{i}", "").strip() for i in range(1, 5)]
        journal["theodds"] = {"cles_configurees": sum(bool(c) for c in set(cles_odds))}
        if any(cles_odds):
            cache_odds = lire_json(donnees / "theodds.json", {})
            secours = etape("resultats_theodds", journal, theodds.collecter,
                           paris, resultats, enregistrements, cles_odds, cache_odds, datetime.now(timezone.utc))
            ecrire_json(donnees / "theodds.json", cache_odds)
            if secours:
                resultats.update(secours[0])
                journal["theodds"] = secours[1]
                signaler(journal, "resultats_theodds", secours[1]["erreurs"])
        # Scores gratuits Prop-Line : secours indépendant des clés The Odds API,
        # sans compter ses données ESPN comme une voix supplémentaire au consensus.
        cle_prop = os.environ.get("PROPLINE_API_KEY", "").strip()
        journal["propline"] = {"configure": bool(cle_prop)}
        if cle_prop:
            cache_prop = lire_json(donnees / "propline.json", {})
            secours = etape("resultats_propline", journal, propline.collecter,
                           paris, resultats, enregistrements, cle_prop, cache_prop, datetime.now(timezone.utc))
            ecrire_json(donnees / "propline.json", cache_prop)
            if secours:
                resultats.update(secours[0])
                journal["propline"] = secours[1]
                signaler(journal, "resultats_propline", secours[1]["erreurs"])
        # Même match chez un autre bookmaker, déjà validé (ce cycle ou avant) : son score règle aussi ces paris.
        freres = resultats_mod.par_freres(paris, resultats, maintenant)
        resultats.update(freres)
        journal["resultats"] = {"enregistrements": len(enregistrements), "matchs_valides": len(resultats),
                                "par_match_frere": len(freres)}
        # matchs reportés (vus « à venir » chez ESPN à une date plus tardive) : ils restent en cours
        reportes = {p["match_id"]: d for p in paris
                    if p["statut"] in ("en_cours", "a_regler") and p["match_id"] not in resultats
                    and (d := resultats_mod.reporte(p, enregistrements))}
        journal["resultats"]["reportes"] = len(reportes)
        reglement.appliquer(paris, resultats, manuels, maintenant, reportes)
        # pourquoi les paris « à régler » ne se règlent pas (pour le diagnostic)
        vus = set()
        journal["resultats"]["non_regles"] = [
            resultats_mod.diagnostic(p, enregistrements, maintenant) for p in paris
            if p["statut"] == "a_regler" and p["match_id"] not in vus and not vus.add(p["match_id"])]
        attente = [p for p in paris if p["statut"] == "a_regler"]
        journal["resultats"]["paris_en_attente"] = len(attente)
        journal["resultats"]["paris_regles"] = sum(id(p) in ouverts_avant and p.get("statut") in reglement.GAIN for p in paris)
        # Même regroupement que le compteur « À régler » du site : une sélection
        # commune aux références n'est comptée qu'une fois.
        selections = {tuple(p.get(c) for c in ("match_id", "marche", "periode", "ligne", "issue", "joueur"))
                      for p in attente}
        journal["resultats"]["selections_en_attente"] = len(selections)
        journal["resultats"]["ignores"] = list(resultats_mod.RESULTATS_IGNORES)
        journal["resultats"]["ignores_limite"] = resultats_mod.IGNORES_MAX
        journal["resultats"]["paris_avec_alertes"] = sum(bool(p.get("alertes")) for p in paris
                                                         if p.get("statut") in ("en_cours", "a_regler"))
        # Quelles sources ont réglé les paris de ce cycle
        sources_reglees: dict = {}
        for p in paris:
            if id(p) in ouverts_avant and p.get("statut") in reglement.GAIN:
                for src in (p.get("preuve_reglement") or {}).get("sources") or ["saisie manuelle"]:
                    sources_reglees[src] = sources_reglees.get(src, 0) + 1
        journal["resultats"]["sources_reglement"] = sources_reglees
        # Même match réglé avec deux scores différents chez deux bookmakers : à vérifier à la main
        incoherences = resultats_mod.incoherences_freres(paris)
        journal["resultats"]["incoherences_freres"] = len(incoherences)
        journal["props_reglement"] = _regler_props(donnees, enregistrements, maintenant)
        # Rien ne règle ces matchs : la liste est prête à être complétée à la main
        ecrire_json(donnees / "resultats_a_saisir.json",
                    {"genere": maintenant.isoformat(timespec="seconds"),
                     "aide": "Copier `modele` dans resultats_manuels.json sous chaque clé de `match_ids`, y remplir le score.",
                     "matchs": resultats_mod.a_saisir(paris, enregistrements, maintenant),
                     "aide_incoherences": "Même match, deux scores : vérifier, puis écrire le bon statut (gagne, perdu, "
                                          "rembourse…) sous l'identifiant de chaque pari faux dans resultats_manuels.json.",
                     "incoherences": incoherences})
    else:
        journal["resultats"] = {"saute": True, "dernier_reglement": dernier_reglement}

    return regler


def regler(ctx: Contexte, mode_reglement: str) -> bool:
    """Étape règlement du cycle complet : règle ``ctx.paris`` si c'est le moment (``mode_reglement``)."""
    ctx.regle = effectuer_reglement(ctx.paris, ctx.donnees, ctx.maintenant, ctx.journal, mode_reglement)
    return ctx.regle


def regler_seul(ctx: Contexte, mode_reglement: str) -> bool:
    """Cycle indépendant : aucune collecte ni placement de paris. Écrit paris.json et etat.json ; le site est
    construit par l'appelant."""
    from cotes.pipeline.sauvegarde import sauvegarder
    donnees, maintenant, journal = ctx.donnees, ctx.maintenant, ctx.journal
    paris = charger_paris(donnees, journal)
    manuels = lire_json(donnees / "resultats_manuels.json", {})
    ctx.paris = [p for p in paris if manuels.get(p["id"]) != "supprime"]
    journal["mode"] = "reglement"
    ctx.regle = effectuer_reglement(ctx.paris, donnees, maintenant, journal, mode_reglement)
    sauvegarder(ctx, reglement_seul=True)
    return ctx.regle
