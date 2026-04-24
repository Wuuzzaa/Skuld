#!/usr/bin/env bash
# =============================================================================
# fix-helsinki-sudoers.sh
# =============================================================================
# Einmaliges Script um den deploy-User auf Helsinki (SKULD-2) auf das neue
# Deployment-Modell umzustellen: NOPASSWD sudo statt Passwort-basiertem sudo.
#
# AUSFUEHRUNG:
#   1. SSH auf Helsinki:  ssh deploy@204.168.128.55
#   2. Script ausfuehren oder Befehle manuell eingeben:
#      echo '<DEPLOY_PASSWORD>' | sudo -S bash -c 'cat > /etc/sudoers.d/deploy-nopasswd << EOF
#      deploy ALL=(ALL) NOPASSWD:ALL
#      EOF
#      chmod 440 /etc/sudoers.d/deploy-nopasswd'
#   3. Testen: sudo docker ps (sollte OHNE Passwort funktionieren)
#   4. Optional: deploy in die docker-Gruppe aufnehmen (falls nicht schon drin):
#      echo '<DEPLOY_PASSWORD>' | sudo -S usermod -aG docker deploy
#
# NACH DER AUSFUEHRUNG:
#   - DEPLOY_PASSWORD Secret in GitHub kann entfernt werden
#   - Alle Workflows nutzen dann einheitlich 'sudo' ohne Passwort
# =============================================================================

set -euo pipefail

echo "=== Fix Helsinki Sudoers ==="
echo "Dieses Script gibt dem deploy-User NOPASSWD sudo Rechte."
echo ""

# Pruefen ob wir als deploy laufen
CURRENT_USER=$(whoami)
if [ "$CURRENT_USER" != "deploy" ]; then
    echo "WARNUNG: Du bist als '$CURRENT_USER' eingeloggt, nicht als 'deploy'."
    echo "Das Script erwartet den deploy-User."
    read -p "Trotzdem fortfahren? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Sudoers-Datei anlegen (braucht aktuell noch Passwort-sudo)
echo "Erstelle /etc/sudoers.d/deploy-nopasswd ..."
sudo bash -c 'cat > /etc/sudoers.d/deploy-nopasswd << EOF
# Deploy user – passwordless sudo for CI/CD deployment
deploy ALL=(ALL) NOPASSWD:ALL
EOF
chmod 440 /etc/sudoers.d/deploy-nopasswd'

echo "Pruefe ob deploy in der docker-Gruppe ist ..."
if groups deploy | grep -q docker; then
    echo "  -> deploy ist bereits in der docker-Gruppe."
else
    echo "  -> Fuege deploy zur docker-Gruppe hinzu ..."
    sudo usermod -aG docker deploy
    echo "  -> Fertig. (Neuanmeldung noetig fuer Gruppenaenderung)"
fi

# Validierung
echo ""
echo "=== Validierung ==="
echo "Teste sudo ohne Passwort ..."
if sudo -n true 2>/dev/null; then
    echo "  -> NOPASSWD sudo funktioniert!"
else
    echo "  -> FEHLER: sudo verlangt immernoch ein Passwort."
    echo "     Bitte manuell pruefen: cat /etc/sudoers.d/deploy-nopasswd"
    exit 1
fi

echo ""
echo "=== Fertig! ==="
echo "Der deploy-User hat jetzt NOPASSWD sudo Rechte."
echo ""
echo "Naechste Schritte:"
echo "  1. GitHub Secret DEPLOY_PASSWORD kann entfernt werden"
echo "  2. Alle Workflows nutzen jetzt einheitlich 'sudo' ohne Passwort"
echo "  3. Deployment auf Helsinki und Falkenstein funktioniert identisch"
