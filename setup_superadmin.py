"""
Setup del Portal Super Admin — Sandoval SaaS
Crea las tablas necesarias y el usuario super admin por defecto.
Ejecutar UNA sola vez en el VPS.
"""
import sys
sys.path.insert(0, '/var/www/sandoval')

from sqlalchemy import text
from utils.models import get_db
import bcrypt
import os

print("=== SETUP SUPER ADMIN ===\n")

DDL_STATEMENTS = [
    # Columnas adicionales en talleres
    "ALTER TABLE talleres ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'basico'",
    "ALTER TABLE talleres ADD COLUMN IF NOT EXISTS estado TEXT DEFAULT 'activo'",
    "ALTER TABLE talleres ADD COLUMN IF NOT EXISTS subdominio TEXT",
    "ALTER TABLE talleres ADD COLUMN IF NOT EXISTS email TEXT",
    "ALTER TABLE talleres ADD COLUMN IF NOT EXISTS telefono TEXT",
    "ALTER TABLE talleres ADD COLUMN IF NOT EXISTS ruc TEXT",
    "ALTER TABLE talleres ADD COLUMN IF NOT EXISTS precio_mensual REAL DEFAULT 0",
    "ALTER TABLE talleres ADD COLUMN IF NOT EXISTS super_admin_notes TEXT",
    "ALTER TABLE talleres ADD COLUMN IF NOT EXISTS fecha_suspension TIMESTAMP",
    "ALTER TABLE talleres ADD COLUMN IF NOT EXISTS fecha_registro TIMESTAMP DEFAULT NOW()",

    # Tabla super_admin_users
    """CREATE TABLE IF NOT EXISTS super_admin_users (
        id SERIAL PRIMARY KEY,
        nombre TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        activo BOOLEAN DEFAULT TRUE,
        ultimo_acceso TIMESTAMP,
        fecha_registro TIMESTAMP DEFAULT NOW()
    )""",

    # Tabla eventos_seguridad (M21)
    """CREATE TABLE IF NOT EXISTS eventos_seguridad (
        id SERIAL PRIMARY KEY,
        taller_id INTEGER,
        tipo TEXT NOT NULL,
        severidad TEXT DEFAULT 'INFO',
        ip TEXT,
        user_id TEXT,
        endpoint TEXT,
        descripcion TEXT NOT NULL,
        payload_sanitizado TEXT,
        bloqueado BOOLEAN DEFAULT FALSE,
        resuelto BOOLEAN DEFAULT FALSE,
        fecha TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_eventos_seg_fecha ON eventos_seguridad(fecha DESC)",
    "CREATE INDEX IF NOT EXISTS idx_eventos_seg_tipo ON eventos_seguridad(tipo)",
    "CREATE INDEX IF NOT EXISTS idx_eventos_seg_taller ON eventos_seguridad(taller_id)",

    # Tabla ips_bloqueadas
    """CREATE TABLE IF NOT EXISTS ips_bloqueadas (
        id SERIAL PRIMARY KEY,
        ip TEXT NOT NULL,
        motivo TEXT NOT NULL,
        bloqueada_hasta TIMESTAMP,
        bloqueada_por TEXT DEFAULT 'auto',
        taller_id INTEGER,
        fecha_registro TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_ip_bloqueada_unique ON ips_bloqueadas(ip)",

    # Tabla talleres_pagos (facturación SaaS)
    """CREATE TABLE IF NOT EXISTS talleres_pagos (
        id SERIAL PRIMARY KEY,
        taller_id INTEGER NOT NULL,
        monto REAL NOT NULL,
        plan TEXT NOT NULL,
        periodo TEXT NOT NULL,
        estado TEXT DEFAULT 'PENDIENTE',
        fecha_pago TIMESTAMP,
        metodo_pago TEXT,
        notas TEXT,
        fecha_registro TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_pagos_taller ON talleres_pagos(taller_id)",
    "CREATE INDEX IF NOT EXISTS idx_pagos_periodo ON talleres_pagos(periodo)",
]

# Ejecutar cada DDL en su propia transacción
for ddl in DDL_STATEMENTS:
    label = ddl.strip().split('\n')[0][:60]
    db = get_db()
    try:
        db.execute(text(ddl))
        db.commit()
        print(f"  ✅ {label}")
    except Exception as e:
        db.rollback()
        if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
            print(f"  ⚠️  Ya existe: {label}")
        else:
            print(f"  ❌ ERROR: {label}\n     {e}")
    finally:
        db.close()

print("\n=== CREAR USUARIO SUPER ADMIN ===\n")

# Credenciales por defecto
SA_EMAIL = os.environ.get('SUPER_ADMIN_EMAIL', 'admin@sandoval.app')
SA_PASSWORD = os.environ.get('SUPER_ADMIN_PASSWORD', 'SandovalAdmin2026!')
SA_NOMBRE = 'Adbeel Sandoval'

db = get_db()
try:
    existing = db.execute(
        text("SELECT id FROM super_admin_users WHERE email = :email"),
        {'email': SA_EMAIL}
    ).fetchone()

    if existing:
        print(f"  ⚠️  Super admin ya existe: {SA_EMAIL}")
    else:
        hashed = bcrypt.hashpw(SA_PASSWORD.encode(), bcrypt.gensalt()).decode()
        db.execute(text("""
            INSERT INTO super_admin_users (nombre, email, password_hash)
            VALUES (:nombre, :email, :hash)
        """), {'nombre': SA_NOMBRE, 'email': SA_EMAIL, 'hash': hashed})
        db.commit()
        print(f"  ✅ Super admin creado")
        print(f"     Email:    {SA_EMAIL}")
        print(f"     Password: {SA_PASSWORD}")
        print(f"\n  ⚠️  CAMBIA LA CONTRASEÑA en la primera sesión!")
finally:
    db.close()

# Actualizar el taller existente (taller_id=1) con datos básicos
db = get_db()
try:
    db.execute(text("""
        UPDATE talleres
        SET plan = 'premium', estado = 'activo'
        WHERE id = 1 AND (plan IS NULL OR plan = '')
    """))
    db.commit()
    print("\n  ✅ Taller #1 (Sandoval) actualizado con plan=premium")
except Exception as e:
    db.rollback()
    print(f"\n  ⚠️  No se pudo actualizar taller #1: {e}")
finally:
    db.close()

print("\n=== SETUP COMPLETADO ===")
print("Reinicia el servicio: systemctl restart sandoval")
print("Super Admin disponible en: http://187.77.62.67:3000/superadmin")
