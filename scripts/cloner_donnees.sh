#!/usr/bin/env bash
# Clone de la branche « donnees » pour un cycle (collecte.yml, reglement.yml). Usage : cloner_donnees.sh URL DOSSIER
#
# Clone partiel : les jours passés de cotes/, opportunites/, references/, releves/ et correspondances/ ne sont jamais relus ni réécrits par le cycle (seul le
# fichier du jour UTC reçoit des ajouts). Ils pesaient 65 des 145 Mo le 2/11/2026 et grossissent de 2,5 à 10 Mo par
# jour. Seuls hier, aujourd'hui et demain sont extraits (passage de minuit pendant le cycle) ; le reste de la branche
# l'est entièrement. L'enregistrement utilise « git add -A --sparse » : un fichier écrit hors de ces motifs est
# quand même ajouté, et les jours non extraits restent intacts dans la branche.
# Échec du clone partiel (serveur, version de git…) : clone complet, comme avant.
set -u
url=$1
dossier=$2
journaliers=(cotes opportunites references releves correspondances)   # mêmes dossiers que scripts/serveur_direct.py
motifs=('/*')
for d in "${journaliers[@]}"; do motifs+=("!/$d/*"); done
for jour in "$(date -u -d yesterday +%F)" "$(date -u +%F)" "$(date -u -d tomorrow +%F)"; do
  for d in "${journaliers[@]}"; do motifs+=("/$d/$jour.jsonl.gz"); done
done
if git clone -q --depth 1 --filter=blob:none --no-checkout --branch donnees "$url" "$dossier" \
   && git -C "$dossier" sparse-checkout set --no-cone "${motifs[@]}" \
   && git -C "$dossier" checkout -q donnees; then
  echo "Clone partiel de « donnees » : $(du -sh "$dossier" | cut -f1)"
else
  echo "::warning title=Clone partiel impossible::Clone complet de « donnees »."
  rm -rf "$dossier"
  git clone -q --depth 1 --branch donnees "$url" "$dossier"
fi
