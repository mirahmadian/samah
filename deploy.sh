#!/bin/bash
# Samah Deployment Script
set -e

echo "=== Samah System Deployment ==="
APP_DIR="/home/user/samah"
cd "$APP_DIR"

# Create virtual environment
echo "[1/6] Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "[2/6] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create log directory
echo "[3/6] Creating directories..."
mkdir -p /var/log/samah
mkdir -p static/qrcodes
mkdir -p static/uploads
chown -R www-data:www-data /var/log/samah 2>/dev/null || true

# Initialize database
echo "[4/6] Initializing database..."
python3 -c "from app import create_app; create_app()"
echo "    Database initialized. Admin: admin / Admin@1234"

# Copy nginx config
echo "[5/6] Setting up nginx..."
cp nginx.conf /etc/nginx/sites-available/samah
ln -sf /etc/nginx/sites-available/samah /etc/nginx/sites-enabled/samah
nginx -t && systemctl reload nginx
echo "    Nginx configured."

# Install and start systemd service
echo "[6/6] Starting service..."
cp samah.service /etc/systemd/system/samah.service
systemctl daemon-reload
systemctl enable samah
systemctl restart samah

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "  Registration portal:  http://YOUR_SERVER_IP/samah/"
echo "  Admin panel:          http://YOUR_SERVER_IP/samahadmin/"
echo "  Admin credentials:    admin / Admin@1234"
echo ""
echo "  IMPORTANT: Change the admin password and SECRET_KEY in samah.service"
echo ""
