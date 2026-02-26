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

# Reiniciar la aplicación
echo "♻️  Reiniciando servicio..."
systemctl restart sandoval

# Esperar 3 segundos y mostrar estado
sleep 3
systemctl status sandoval --no-pager

echo ""
echo "✅ ¡Actualización completada!"
echo "Para ver logs: journalctl -u sandoval -f"
