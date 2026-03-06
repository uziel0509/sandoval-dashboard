#!/bin/bash
# ============================================================
# SANDOVAL Dashboard — Script de actualización rápida
# Ejecutar en el VPS cuando hayas hecho cambios:
#   bash deploy/actualizar.sh
# ============================================================

echo "🔄 Actualizando SANDOVAL Dashboard..."

cd /var/www/sandoval

# Si usas Git:
echo "📥 Bajando últimos cambios de Git..."
git pull origin main

# Reinstalar dependencias (por si cambiaste requirements.txt)
echo "📦 Verificando dependencias..."
source venv/bin/activate
pip install -r requirements.txt -q

# Reiniciar el bot de Telegram
echo "🤖 Reiniciando Bot de Telegram en 2do plano..."
cp deploy/sandoval-bot.service /etc/systemd/system/sandoval-bot.service
systemctl daemon-reload
systemctl enable sandoval-bot
systemctl restart sandoval-bot

# Reiniciar la aplicación
echo "♻️  Reiniciando servicio dashboard..."
systemctl restart sandoval

# Esperar 3 segundos y mostrar estado
sleep 3
systemctl status sandoval --no-pager
systemctl status sandoval-bot --no-pager

echo ""
echo "✅ ¡Actualización completada!"
echo "Para ver logs: journalctl -u sandoval -f"
