"""utils/cron_push.py -- Cron 20:00 Lima: resumen diario de caja a admin/staff.

Se invoca desde crontab del sistema:
  0 20 * * * cd /var/www/sandoval && /usr/bin/python3 utils/cron_push.py >> /var/log/sandoval/cron_push.log 2>&1

Itera todos los taller_id activos con caja abierta o con movimiento hoy.
Llama notify_admin_resumen_dia(db, taller_id) por cada uno.
"""
from __future__ import annotations
import sys
import os
import logging
from datetime import datetime

# Cargar .env antes de cualquier import del proyecto
try:
    from dotenv import load_dotenv
    load_dotenv("/var/www/sandoval/.env")
except Exception:
    pass

sys.path.insert(0, "/var/www/sandoval")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CRON_PUSH] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cron_push")


def main() -> None:
    from sqlalchemy import text
    from utils.models import get_db
    from utils.notifications import notify_admin_resumen_dia

    hora = datetime.now().strftime("%H:%M")
    logger.info("Iniciando cron resumen dia -- hora Lima: %s", hora)

    db = get_db()
    taller_ids = []
    try:
        # Talleres con caja abierta o con ordenes cerradas hoy
        rows = db.execute(text(
            "SELECT DISTINCT taller_id FROM ("
            "  SELECT taller_id FROM cierres_caja WHERE fecha = CURRENT_DATE AND estado = 'abierto'"
            "  UNION"
            "  SELECT taller_id FROM ordenes"
            "  WHERE estado IN ('ENTREGA', 'ARCHIVADO') AND DATE(fecha) = CURRENT_DATE"
            ") AS activos"
        )).fetchall()
        taller_ids = [r[0] for r in rows if r[0]]
    except Exception as e:
        logger.error("No se pudo consultar taller_ids: %s", e)
    finally:
        db.close()

    if not taller_ids:
        logger.info("Sin talleres activos hoy -- no se envia resumen")
        return

    logger.info("Talleres activos hoy: %s", taller_ids)

    for taller_id in taller_ids:
        try:
            db2 = get_db()
            notify_admin_resumen_dia(db2, taller_id)
            db2.close()
            logger.info("Resumen enviado taller_id=%s", taller_id)
        except Exception as e:
            logger.error("Error taller_id=%s: %s", taller_id, e)

    logger.info("Cron resumen dia completado")


if __name__ == "__main__":
    main()
