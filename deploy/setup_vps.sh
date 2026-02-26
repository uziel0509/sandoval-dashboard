#!/bin/bash
# ============================================================
# SANDOVAL Dashboard — Script de despliegue en Hostinger VPS
# Ejecutar en el VPS con: bash deploy/setup_vps.sh
# ============================================================

echo "🚀 Iniciando configuración del VPS para SANDOVAL Dashboard..."

# ── 1. Actualizar sistema ──────────────────────────────────
echo ""
echo "📦 [1/7] Actualizando sistema..."
apt update -y && apt upgrade -y

# ── 2. Instalar dependencias del sistema ───────────────────
echo ""
echo "🔧 [2/7] Instalando Python, Git, Nginx..."
apt install -y python3 python3-pip python3-venv git nginx ufw

# ── 3. Configurar Firewall ─────────────────────────────────
echo ""
echo "🔒 [3/7] Configurando firewall..."
ufw allow 22
ufw allow 80
ufw allow 443
ufw --force enable

# ── 4. Crear directorio del proyecto ──────────────────────
echo ""
echo "📁 [4/7] Preparando directorio /var/www/sandoval..."
mkdir -p /var/www/sandoval
# Mover archivos si ya están en el directorio
# (Asume que subiste el proyecto a /var/www/sandoval)

# ── 5. Crear entorno virtual e instalar dependencias ──────
echo ""
echo "🐍 [5/7] Creando entorno virtual Python..."
cd /var/www/sandoval
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# ── 6. Instalar servicio systemd ──────────────────────────
echo ""
echo "⚙️  [6/7] Instalando servicio systemd..."
cp deploy/sandoval.service /etc/systemd/system/sandoval.service
systemctl daemon-reload
systemctl enable sandoval
systemctl start sandoval

# ── 7. Configurar Nginx ───────────────────────────────────
echo ""
echo "🌐 [7/7] Configurando Nginx..."
cp deploy/nginx.conf /etc/nginx/sites-available/sandoval
ln -sf /etc/nginx/sites-available/sandoval /etc/nginx/sites-enabled/sandoval
rm -f /etc/nginx/sites-enabled/default  # Quitar página por defecto
nginx -t && systemctl reload nginx

echo ""
echo "✅ ¡Instalación completa!"
echo ""
echo "Estado del servicio:"
systemctl status sandoval --no-pager
echo ""
echo "📌 Tu app debería estar disponible en: http://$(curl -s ifconfig.me)"
echo ""
echo "Para ver logs en tiempo real:"
echo "  journalctl -u sandoval -f"
