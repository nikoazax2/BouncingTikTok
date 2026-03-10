#!/bin/bash
# Deploy BouncingTikTok export server to VPS
# Usage: ssh root@217.154.121.187 < deploy.sh

set -e

echo "=== Installing system dependencies ==="
apt-get update
apt-get install -y python3 python3-pip python3-venv ffmpeg libsdl2-2.0-0 libsdl2-mixer-2.0-0 libsdl2-image-2.0-0 git

echo "=== Cloning repo ==="
cd /opt
rm -rf BouncingTikTok
git clone https://github.com/nikoazax2/BouncingTikTok.git
cd BouncingTikTok

echo "=== Setting up Python venv ==="
python3 -m venv venv
source venv/bin/activate

echo "=== Installing Python dependencies ==="
pip install flask pygame mido Pillow scipy

echo "=== Setting SDL to dummy video (headless) ==="
cat > /etc/environment.d/sdl.conf <<'ENVEOF'
SDL_VIDEODRIVER=dummy
SDL_AUDIODRIVER=dummy
ENVEOF

echo "=== Creating systemd service ==="
cat > /etc/systemd/system/bouncing.service <<'SVCEOF'
[Unit]
Description=BouncingTikTok Export Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/BouncingTikTok
Environment=SDL_VIDEODRIVER=dummy
Environment=SDL_AUDIODRIVER=dummy
ExecStart=/opt/BouncingTikTok/venv/bin/python server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

echo "=== Starting service ==="
systemctl daemon-reload
systemctl enable bouncing
systemctl restart bouncing

echo "=== Opening firewall port 5000 ==="
ufw allow 5000/tcp 2>/dev/null || iptables -A INPUT -p tcp --dport 5000 -j ACCEPT

echo "=== Done! Server running on http://217.154.121.187:5000 ==="
systemctl status bouncing --no-pager
