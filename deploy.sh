#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Samah Registration System - Portable Deployment Script
# Auto-detects install path & user, generates nginx + systemd
# configs, and isolates the app so it won't clash with other
# systems on the same server.
# ──────────────────────────────────────────────────────────────
set -e

# --- Detect environment ------------------------------------------------
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="${SUDO_USER:-$(whoami)}"
# Port the gunicorn app listens on internally. Change if 8200 is taken.
APP_PORT="${SAMAH_PORT:-8200}"
SERVICE_NAME="samah"

echo "=== Samah System Deployment ==="
echo "    Install dir : $APP_DIR"
echo "    Run as user : $RUN_USER"
echo "    Internal port: $APP_PORT"
echo ""

cd "$APP_DIR"

# --- 1. Virtual environment -------------------------------------------
echo "[1/7] Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# --- 2. Dependencies ---------------------------------------------------
echo "[2/7] Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# --- 3. Directories ----------------------------------------------------
echo "[3/7] Creating directories..."
sudo mkdir -p /var/log/samah
mkdir -p static/qrcodes static/uploads
sudo chown -R "$RUN_USER":"$RUN_USER" /var/log/samah 2>/dev/null || true

# --- 4. Secret key + DB ------------------------------------------------
echo "[4/7] Generating secret key & initializing database..."
SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
python3 -c "from app import create_app; create_app()"
echo "    Database initialized. Admin login: admin / Admin@1234"

# --- 5. Generate gunicorn config (correct port) -----------------------
echo "[5/7] Writing gunicorn config..."
cat > gunicorn.conf.py <<EOF
bind = "127.0.0.1:${APP_PORT}"
workers = 4
worker_class = "sync"
timeout = 120
keepalive = 2
max_requests = 1000
max_requests_jitter = 100
preload_app = True
accesslog = "/var/log/samah/access.log"
errorlog = "/var/log/samah/error.log"
loglevel = "info"
EOF

# --- 6. systemd service (correct paths, random key) -------------------
echo "[6/7] Installing systemd service..."
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=Samah Registration System - Haj Organization
After=network.target

[Service]
User=${RUN_USER}
Group=${RUN_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/venv/bin"
Environment="SECRET_KEY=${SECRET_KEY}"
ExecStart=${APP_DIR}/venv/bin/gunicorn -c gunicorn.conf.py wsgi:application
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl restart ${SERVICE_NAME}

# --- 7. nginx location blocks (path-isolated) -------------------------
echo "[7/7] Writing nginx config..."
sudo tee /etc/nginx/sites-available/samah > /dev/null <<EOF
# Samah - serves ONLY /samah and /samahadmin so it does not
# interfere with other apps/server blocks on this machine.
server {
    listen 80;
    server_name _;
    client_max_body_size 20M;
    charset utf-8;

    location /samah {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120;
    }

    location /samahadmin {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120;
    }

    location /static {
        alias ${APP_DIR}/static;
        expires 7d;
        add_header Cache-Control "public";
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/samah /etc/nginx/sites-enabled/samah
sudo nginx -t && sudo systemctl reload nginx

# --- Done --------------------------------------------------------------
SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo ""
echo "=== Deployment Complete ==="
echo ""
echo "  Registration portal:  http://${SERVER_IP:-YOUR_SERVER_IP}/samah/"
echo "  Admin panel:          http://${SERVER_IP:-YOUR_SERVER_IP}/samahadmin/"
echo "  Admin credentials:    admin / Admin@1234"
echo ""
echo "  Service status:  sudo systemctl status ${SERVICE_NAME}"
echo "  Live logs:       sudo journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "  IMPORTANT: Log into the admin panel and change the admin password."
echo ""
