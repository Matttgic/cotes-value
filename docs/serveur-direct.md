# Serveur en direct (environ 6 €/mois)

Un petit serveur fait tourner Cotes Value en continu, à la place de la chaîne GitHub Actions :

| | GitHub Actions (aujourd'hui) | Serveur en direct |
|---|---|---|
| Fréquence des cycles | toutes les 5 min, parfois retardés ou sautés | dès qu'un cycle finit (environ 1 à 1,5 min) |
| Délai cote → alerte | jusqu'à 5 min + 1 min 40 | environ 1 à 2 min |
| Alertes | Pushover et Chrome | Pushover seulement (voir Limites) |
| Clone des données | à chaque cycle | une fois, puis mises à jour |
| Site | à chaque cycle | toutes les 5 min (workflow site.yml) |

GitHub reste la **roue de secours**. Le serveur pousse un battement (`serveur_direct.json`) dans la branche
`donnees` toutes les 5 minutes. Tant qu'il a moins de 15 minutes, GitHub ne relance plus sa chaîne de collecte et
ne règle plus les paris. Si le serveur s'arrête ou tombe, GitHub reprend tout seul à sa prochaine surveillance
(toutes les 30 minutes).

## 1. Commander le serveur

[Hetzner Cloud](https://www.hetzner.com/cloud/) → nouveau projet → **Add server** :

- emplacement : Allemagne ou Finlande ;
- image : **Ubuntu 24.04** ;
- type : **CX23** (2 vCPU, 4 Go, 40 Go). 5,99 €/mois affichés par Hetzner le 2/11/2026 ; vérifier le prix à la
  commande ;
- clé SSH : la tienne (ou mot de passe root envoyé par e-mail) ;
- pare-feu conseillé : n'autoriser en entrée que SSH (port 22). Le serveur ne reçoit rien, il ne fait qu'appeler.

Note l'adresse IP du serveur.

## 2. Créer le jeton GitHub

github.com → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate :

- Repository access : **Only select repositories** → `Matttgic/cotes-value` ;
- Permissions : **Contents : Read and write**, **Actions : Read and write** ;
- Expiration : 1 an (le renouveler ensuite).

Copie le jeton (il ne s'affiche qu'une fois).

## 3. Installer

Depuis ton ordinateur ou ton téléphone (Termux, JuiceSSH…) :

```bash
ssh root@ADRESSE_IP
git clone https://github.com/Matttgic/cotes-value /opt/cotes-value
bash /opt/cotes-value/serveur/installer.sh
```

## 4. Configurer

```bash
nano /etc/cotes-value.env
```

- `GITHUB_TOKEN` : le jeton de l'étape 2.
- Les autres lignes : les mêmes valeurs que les secrets GitHub du même nom. GitHub ne permet pas de relire un
  secret : reprends-les à la source (tableau de bord Pushover, comptes des API).
- `PUSHOVER_BANKROLL` : ta bankroll, pour la ligne MacroDroid (docs/pari-rapide-android.md).
- `PUSHOVER_STRATEGIES` : laisse vide. Le serveur suit les cases du bloc « Alertes Pushover » du site (page
  Notifications) ; enregistre-les là une fois avec ton code personnel.
- `HC_PING_URL` (facultatif) : l'adresse de ping d'un check Healthchecks, la même que le secret GitHub
  `HC_PING_URL`. Voir « Alerte si plus rien ne collecte » ci-dessous.

Enregistrer : Ctrl+O, Entrée, Ctrl+X.

## 5. Démarrer et vérifier

```bash
systemctl start cotes-value-direct
journalctl -u cotes-value-direct -f        # journal en direct (Ctrl+C pour quitter)
```

Au démarrage, le serveur pousse son battement, attend la fin du cycle GitHub en cours, puis enchaîne ses cycles.
Ce qu'il faut voir :

- dans le journal : « démarrage : cycle toutes les 60 s », puis des enregistrements toutes les 5 minutes ;
- sur GitHub → Actions : les runs « Collecte et comparaison » s'arrêtent, « Publier le site » tourne toutes les
  5 minutes ;
- sur le site : la page Santé indique des relevés toutes les minutes environ.

## Arrêter, revenir à GitHub

```bash
systemctl stop cotes-value-direct          # rend la main à GitHub (battement « inactif »)
systemctl disable cotes-value-direct       # ne plus démarrer au redémarrage du serveur
```

GitHub reprend à sa prochaine surveillance (30 minutes au plus). Pour reprendre tout de suite : Actions →
« Collecte et comparaison » → Run workflow.

## Ce que fait le serveur tout seul

- **Code** : chaque heure, il récupère le code fusionné sur GitHub et redémarre dessus. Rien à faire après une PR.
- **Données** : il ne télécharge que les fichiers utiles (clone partiel). Les jours passés de `cotes/` et
  `opportunites/` restent intacts sur GitHub.
- **Conflits** : si quelqu'un écrit dans `donnees` en même temps (un résultat saisi à la main, par exemple), ses
  changements sont repris ; sur un même fichier, la version du serveur l'emporte.
- **Flux Polymarket** : un processus à part (`cotes/polymarket_flux.py`) reste abonné au websocket des carnets
  Polymarket et écrit le meilleur achat / vente toutes les 2 s dans `flux_polymarket/prix.json`. Chaque cycle prend
  ce prix à la place de celui de l'API gamma quand il est plus récent (`prix_flux` sur la ligne, compteur
  `polymarket_flux` dans le journal du cycle). Sans message depuis 30 s, le prix du flux est ignoré et gamma reprend.
  Coupure : reconnexion seule, attente de 1 à 60 s ; processus arrêté : relancé au cycle suivant.
  `POLYMARKET_FLUX=non` le coupe. Sur GitHub Actions, rien ne change.
- **Page Santé** : les seuils d'alerte sont ajustés aux cycles d'une minute : même durée qu'avant avant une
  alerte, environ 10 minutes.

## Alerte si plus rien ne collecte (Healthchecks)

La page Santé et la relance GitHub tournent sur GitHub ou sur le serveur. Si les deux s'arrêtent, ou si la boucle
reste bloquée, personne ne prévient. Healthchecks reçoit un signal de vie et alerte quand il cesse.

1. Créer un compte sur healthchecks.io (offre gratuite) ou utiliser une instance auto-hébergée.
2. Créer un check : période 5 minutes, délai de grâce 30 minutes (les cycles GitHub sont parfois retardés).
3. Intégrations : ajouter Pushover (ou un autre canal).
4. Copier l'adresse de ping du check dans le secret GitHub `HC_PING_URL` et, si le serveur tourne, dans
   `/etc/cotes-value.env` (même valeur), puis `sudo systemctl restart cotes-value-direct`.

Le signal part seulement après un cycle réussi suivi d'un enregistrement poussé : par la chaîne GitHub
(étape « Signal de vie ») ou par le serveur (toutes les 5 minutes). Sans `HC_PING_URL`, rien n'est envoyé.
Un arrêt volontaire de plus de 30 minutes donne une alerte : mettre le check en pause sur Healthchecks.

## Limites

- Le serveur ne règle pas les paris plus souvent : le règlement reste horaire.
- Les notifications Chrome ne partent pas du serveur : le service qui les envoie n'accepte que GitHub Actions.
  Les alertes arrivent par Pushover (stratégies du bloc « Alertes Pushover »). Elles reviennent dès que
  GitHub reprend la main.
- Lancer « Collecte et comparaison » à la main pendant que le serveur tourne ferait écrire deux moteurs en même
  temps. À éviter ; la surveillance et le règlement automatiques, eux, s'effacent d'eux-mêmes.
- Si le serveur reste joignable mais ne pousse plus (jeton expiré, par exemple), GitHub reprend 15 minutes après
  le dernier battement. Le journal (`journalctl`) donne la cause.
