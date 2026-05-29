#!/bin/bash
# Push a code update to the EC2 instance.
# Run this from your LOCAL machine after committing changes.
#
# Usage:
#   ./deploy/deploy.sh ec2-user@<YOUR_IP> /path/to/your-key.pem

set -euo pipefail

SSH_TARGET="${1:?Usage: deploy.sh user@host /path/to/key.pem}"
KEY_FILE="${2:?Usage: deploy.sh user@host /path/to/key.pem}"
BOT_DIR="/opt/botkal"

echo "=== Deploying to $SSH_TARGET ==="

ssh -i "$KEY_FILE" "$SSH_TARGET" bash <<EOF
  set -euo pipefail
  cd $BOT_DIR

  echo "Pulling latest code..."
  git pull origin claude/confident-hypatia-eSW9u

  echo "Updating dependencies..."
  venv/bin/pip install --quiet -r requirements.txt

  echo "Restarting service..."
  sudo systemctl restart kalshi-bot
  sleep 2
  sudo systemctl status kalshi-bot --no-pager
EOF

echo ""
echo "=== Deploy complete. Tail logs with: ==="
echo "  ssh -i $KEY_FILE $SSH_TARGET 'journalctl -u kalshi-bot -f'"
