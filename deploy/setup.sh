#!/bin/bash
# Run this ONCE on a fresh EC2 instance (Amazon Linux 2023 or Ubuntu 22.04)
# as the default ec2-user / ubuntu user.
#
# Usage:
#   chmod +x setup.sh && sudo ./setup.sh

set -euo pipefail

REPO_URL="https://github.com/tsuls/botkal.git"   # update if different
BOT_USER="botkal"
BOT_DIR="/opt/botkal"
PYTHON="python3.11"

echo "=== Installing system packages ==="
if command -v dnf &>/dev/null; then
    # Amazon Linux 2023
    dnf install -y python3.11 python3.11-pip git
else
    # Ubuntu 22.04+
    apt-get update -q
    apt-get install -y python3.11 python3.11-venv python3-pip git
fi

echo "=== Creating bot user ==="
id "$BOT_USER" &>/dev/null || useradd -r -s /usr/sbin/nologin -d "$BOT_DIR" "$BOT_USER"

echo "=== Cloning repo ==="
mkdir -p "$BOT_DIR"
git clone "$REPO_URL" "$BOT_DIR" || (cd "$BOT_DIR" && git pull)
chown -R "$BOT_USER:$BOT_USER" "$BOT_DIR"

echo "=== Installing Python dependencies ==="
sudo -u "$BOT_USER" $PYTHON -m venv "$BOT_DIR/venv"
sudo -u "$BOT_USER" "$BOT_DIR/venv/bin/pip" install --quiet -r "$BOT_DIR/requirements.txt"

echo "=== Installing systemd service ==="
cp "$BOT_DIR/deploy/kalshi-bot.service" /etc/systemd/system/kalshi-bot.service
systemctl daemon-reload
systemctl enable kalshi-bot

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Copy your .env file to $BOT_DIR/.env"
echo "     scp .env ec2-user@<YOUR_IP>:/opt/botkal/.env"
echo "  2. Copy your Kalshi private key:"
echo "     scp kalshi_private_key.pem ec2-user@<YOUR_IP>:/opt/botkal/"
echo "  3. Start the bot:"
echo "     sudo systemctl start kalshi-bot"
echo "  4. Watch live logs:"
echo "     sudo journalctl -u kalshi-bot -f"
