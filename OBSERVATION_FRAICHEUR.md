# Essai isole de collecte sans API payante

Ce workflow ne modifie que les resultats temporaires de son execution et un artefact de diagnostic. Il ne pousse aucun fichier vers le depot, ne publie pas le site, ne simule ni ne regle de pari et n'envoie aucune notification.

## Declenchement

Le workflow reagit uniquement aux modifications de son propre fichier sur la branche `diagnostic/fraicheur-cotes-2026-10-20`. Pour executer le job sur un push, le message du commit doit aussi contenir `[essai-collecte]`. Sans ce marqueur, le job est ignore. Il n'y a ni cron ni boucle de relance. Un lancement manuel, s'il est disponible, est egalement refuse hors de cette branche. L'ajout approuve de ce declencheur avec le marqueur vise un seul essai reel ; les essais futurs necessitent une nouvelle decision.

## Ressources et isolation

L'essai utilise des minutes GitHub Actions et, si configure, les invocations du rechauffeur Pinnacle existant. Aucune gratuité d'hebergement illimitee n'est promise. Les cles PINNODDS et PINBOOK ne sont pas transmises ; les secours consommant leurs quotas sont desactives par le script d'observation. OlyBet et NetBet sont egalement desactives. Seuls les secrets Pinnacle directs deja configures sont passes au processus. Aucune nouvelle souscription n'est creee.

Le jeton GitHub est en lecture seule. La branche `donnees` est lue pour copier la reserve dans un repertoire temporaire, jamais modifiee. Les autres branches, y compris celle de Claude, ne sont pas mises a jour. Les workflows de production ne sont pas modifies.

## Mesures et limites

Le script d'observation reutilise une seule fois la phase `collecter_prematch` du cycle existant, puis produit un rapport agrege pour Pinnacle direct, Winamax, Betclic, PMU et Unibet. Le mode sur push est `complet`. Les sports restent limites par les references du cycle et les marches restent limites par les traducteurs actuels : cet essai ne recolte donc pas encore toutes les cotes.

Les anciennes lignes gardent leur date. Age d'observation, age de cache et age du prix en amont sont distincts ; le dernier reste inconnu. Une source vide est signalee. Le resume et l'artefact ne contiennent pas les prix bruts ou les noms d'equipes. La collecte et ses journaux existants restent soumis a leurs protections actuelles.

Le workflow relance les 23 tests du diagnostic et les 7 tests de l'observateur avant tout appel reseau. La syntaxe YAML et celle du code Python du resume ont ete verifiees hors ligne. Aucune reussite reseau n'est annoncee avant d'avoir obtenu le resultat de cet essai. Aucun taux d'exhaustivite n'est calculable sans inventaire attendu independant ; un seul passage ne prouve pas une stabilite continue.
