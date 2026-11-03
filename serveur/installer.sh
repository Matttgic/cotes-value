#!/usr/bin/env bash
# Installe Cotes Value « en direct » sur un serveur Ubuntu ou Debian (docs/serveur-direct.md). En root :
#
#     bash /opt/cotes-value/serveur/installer.sh
#
# Relançable sans risque : rien n'est écrasé (dépôt déjà cloné, /etc/cotes-value.env déjà rempli).
set -euo pipefail

DOSSIER=${DOSSIER:-/opt/cotes-value}
UTILISATEUR=${UTILISATEUR:-cotes}

if [ "$(id -u)" -ne 0 ]; then echo "À lancer en root (sudo bash $0)." >&2; exit 1; fi
if [ ! -d "$DOSSIER/.git" ]; then echo "Cloner d'abord le dépôt dans $DOSSIER (docs/serveur-direct.md)." >&2; exit 1; fi

echo "1/5 Paquets système"
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y -q git python3-venv python3-pip ca-certificates >/dev/null

echo "2/5 Utilisateur $UTILISATEUR (sans connexion)"
id -u "$UTILISATEUR" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$UTILISATEUR"
chown -R "$UTILISATEUR": "$DOSSIER"

echo "3/5 Environnement Python"
runuser -u "$UTILISATEUR" -- python3 -m venv "$DOSSIER/.venv"
runuser -u "$UTILISATEUR" -- "$DOSSIER/.venv/bin/pip" install -q --upgrade pip
runuser -u "$UTILISATEUR" -- "$DOSSIER/.venv/bin/pip" install -q -r "$DOSSIER/requirements.txt"

echo "4/5 Configuration /etc/cotes-value.env"
if [ ! -f /etc/cotes-value.env ]; then
  install -m 600 -o root -g root "$DOSSIER/serveur/env.exemple" /etc/cotes-value.env
  echo "   créé : à remplir avant le démarrage"
else
  echo "   déjà présent : conservé"
fi

echo "5/5 Service systemd"
install -m 644 "$DOSSIER/serveur/cotes-value-direct.service" /etc/systemd/system/cotes-value-direct.service
systemctl daemon-reload
systemctl enable cotes-value-direct >/dev/null

echo
echo "Installé. Étapes suivantes :"
echo "  nano /etc/cotes-value.env                 # coller le jeton GitHub et les clés (docs/serveur-direct.md)"
echo "  systemctl start cotes-value-direct        # démarrer"
echo "  journalctl -u cotes-value-direct -f       # suivre le journal"
