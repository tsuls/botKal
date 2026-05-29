# AWS EC2 Setup Guide

## 1. Launch an EC2 instance

1. Go to AWS Console → EC2 → Launch Instance
2. Settings:
   - **Name:** kalshi-bot
   - **AMI:** Ubuntu 22.04 LTS (free tier eligible)
   - **Instance type:** t3.micro ($8-10/mo) — plenty for this bot
   - **Key pair:** Create new → download the `.pem` file → keep it safe
   - **Security group:** Allow outbound all (default). Inbound: SSH from your IP only.
   - **Storage:** 8 GB gp3 (default is fine)
3. Launch. Note the **Public IPv4** address.

## 2. Connect and bootstrap

From your local machine:

```bash
# Fix key permissions (required by SSH)
chmod 400 your-key.pem

# SSH in
ssh -i your-key.pem ubuntu@<YOUR_IP>
```

Once inside:

```bash
# Download and run the setup script
curl -o setup.sh https://raw.githubusercontent.com/tsuls/botkal/claude/confident-hypatia-eSW9u/deploy/setup.sh
chmod +x setup.sh
sudo bash setup.sh
```

## 3. Upload your credentials

From your **local** machine (separate terminal):

```bash
# Upload .env
scp -i your-key.pem .env ubuntu@<YOUR_IP>:/opt/botkal/.env

# Upload Kalshi private key
scp -i your-key.pem kalshi_private_key.pem ubuntu@<YOUR_IP>:/opt/botkal/kalshi_private_key.pem

# Fix ownership
ssh -i your-key.pem ubuntu@<YOUR_IP> "sudo chown botkal:botkal /opt/botkal/.env /opt/botkal/kalshi_private_key.pem && sudo chmod 600 /opt/botkal/.env /opt/botkal/kalshi_private_key.pem"
```

## 4. Start the bot

```bash
sudo systemctl start kalshi-bot

# Confirm it's running
sudo systemctl status kalshi-bot

# Watch live logs
sudo journalctl -u kalshi-bot -f
```

## 5. Deploying code updates

From your **local** machine, after committing changes:

```bash
./deploy/deploy.sh ubuntu@<YOUR_IP> your-key.pem
```

## 6. Kill switch

To halt all trading immediately (SSH in and run):

```bash
sudo touch /opt/botkal/HALT
```

The bot will cancel all open orders and stop within one loop cycle.
To resume: `sudo rm /opt/botkal/HALT && sudo systemctl restart kalshi-bot`

## 7. Useful commands

| Task | Command |
|------|---------|
| View live logs | `journalctl -u kalshi-bot -f` |
| Restart bot | `sudo systemctl restart kalshi-bot` |
| Stop bot | `sudo systemctl stop kalshi-bot` |
| Check signal history | `sqlite3 /opt/botkal/kalshi_bot.db "SELECT * FROM signals ORDER BY timestamp DESC LIMIT 20;"` |
| Check tick count | `sqlite3 /opt/botkal/kalshi_bot.db "SELECT COUNT(*) FROM ticks;"` |
| Download DB locally | `scp -i your-key.pem ubuntu@<IP>:/opt/botkal/kalshi_bot.db .` |

## Cost estimate

| Resource | Cost |
|----------|------|
| t3.micro EC2 | ~$8.50/mo |
| 8 GB EBS storage | ~$0.80/mo |
| Data transfer | negligible |
| **Total** | **~$9-10/mo** |
