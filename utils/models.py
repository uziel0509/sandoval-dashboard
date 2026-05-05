"""
SANDOVAL SaaS - Modelos de Base de Datos
PostgreSQL (producción) / SQLite (fallback desarrollo)
Multi-tenant con taller_id — Fase 1
"""

import os
import logging
_logger = logging.getLogger(__name__)
import json
import hashlib
import hmac
import secrets
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, String, Float, Boolean, Text,
    DateTime, ForeignKey, JSON, UniqueConstraint, event, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from sqlalchemy.pool import StaticPool, NullPool

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'sandoval.db')
os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)

# ─── URL de base de datos desde variable de entorno ───
# En producción: DATABASE_URL=postgresql://sandoval_user:pass@localhost:5432/sandoval_saas
# En desarrollo: no definir DATABASE_URL → usa SQLite automáticamente
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{DB_PATH}')
_IS_PG = DATABASE_URL.startswith('postgresql')

if _IS_PG:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,      # verifica conexiones muertas
        pool_recycle=3600,       # recicla conexiones cada hora
        echo=False,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
        echo=False,
    )

Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


# ─── RLS (Row Level Security) — multi-tenant isolation ─────────────
# La sesión PG necesita conocer el taller_id para que las policies filtren.
# Al abrir una Session via get_db(), aplicamos el setting actual del
# ContextVar utils.rls_session.current_taller_id, vía SELECT set_config(...).
# NOTA: set_config('...', false) no requiere transacción explícita y
# persiste hasta que la conexión vuelve al pool. Suficiente para nuestro uso.
def get_db() -> Session:
    """Abre una sesión SQLAlchemy y aplica el taller_id del contexto actual.

    El ContextVar lo setea TallerContextMiddleware (HTTP) o el helper
    `with_taller(...)` (handlers públicos por token de orden).
    """
    db = SessionLocal()
    if _IS_PG:
        try:
            from utils.rls_session import apply_rls_to_session
            apply_rls_to_session(db)
        except Exception:
            pass
    # 2026-04-29 audit V10: monkey-patch close() para resetear app.taller_id antes de
    # que la conexion vuelva al pool. Asi no hay fuga de contexto entre requests.
    if _IS_PG:
        _orig_close = db.close
        def _patched_close():
            try:
                from sqlalchemy import text as _t
                db.execute(_t("SELECT set_config('app.taller_id', '', false)"))
                db.commit()
            except Exception:
                try: db.rollback()
                except Exception: pass
            _orig_close()
        db.close = _patched_close
    return db


# ── Argon2id (preferido) + compat con bcrypt y PBKDF2 ────────────────────
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, InvalidHash
    _ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)
except ImportError:
    _ph = None


def hash_password(password: str) -> str:
    """Genera hash Argon2id por defecto. PBKDF2 fallback si argon2 no esta disponible."""
    if _ph is not None:
        return _ph.hash(password)
    # Fallback PBKDF2 (no deberia llegar aqui en produccion)
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}:{hashed.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verifica contra Argon2id, bcrypt o PBKDF2 (compat con hashes legacy)."""
    if not stored:
        return False
    try:
        # Argon2id (formato =19$...)
        if stored.startswith('$argon2'):
            if _ph is None:
                return False
            try:
                _ph.verify(stored, password)
                return True
            except (VerifyMismatchError, InvalidHash):
                return False
        # bcrypt (a$ / b$)
        if stored.startswith('$2a$') or stored.startswith('$2b$'):
            import bcrypt
            return bcrypt.checkpw(password.encode(), stored.encode())
        # PBKDF2 (legacy: salt:hex)
        if ':' in stored:
            salt, hashed = stored.split(':', 1)
            check = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
            return hmac.compare_digest(check.hex(), hashed)
    except Exception:
        return False
    return False


def needs_rehash(stored: str) -> bool:
    """Indica si el hash debe ser re-generado tras login exitoso.
    True si esta en bcrypt o PBKDF2 (legacy) o argon2 con parametros viejos."""
    if not stored:
        return False
    if stored.startswith('$argon2') and _ph is not None:
        try:
            return _ph.check_needs_rehash(stored)
        except Exception:
            return True
    return True  # bcrypt o PBKDF2 -> rehash a Argon2


# ─────────────────────── MODELO BASE MULTI-TENANT ───────────────────────

class Taller(Base):
    """Representa un taller mecánico cliente del SaaS."""
    __tablename__ = 'talleres'
    id              = Column(Integer, primary_key=True, autoincrement=True)
    nombre          = Column(String(100), nullable=False)
    subdominio      = Column(String(50), unique=True, nullable=True)   # ej: sandoval
    ruc             = Column(String(20), default='')
    email           = Column(String(100), default='')
    telefono        = Column(String(30), default='')
    direccion       = Column(String(200), default='')
    plan            = Column(String(20), default='basico')    # basico, pro, premium
    activo          = Column(Boolean, default=True)
    fecha_registro  = Column(DateTime, default=datetime.now)
    # Datos de empresa para PDFs y reportes
    empresa_nombre  = Column(String(150), default='')
    empresa_ruc     = Column(String(20), default='')
    empresa_direccion = Column(String(200), default='')
    empresa_telefono  = Column(String(50), default='')
    empresa_email     = Column(String(100), default='')
    igv_porcentaje    = Column(Float, default=18.0)
    moneda            = Column(String(10), default='PEN')


# ─────────────────────── MODELOS TENANT ───────────────────────

class Usuario(Base):
    __tablename__ = 'usuarios'
    id             = Column(Integer, primary_key=True, autoincrement=True)
    taller_id      = Column(Integer, ForeignKey('talleres.id'), default=1, nullable=False, index=True)
    username       = Column(String(50), nullable=False)
    password_hash  = Column(String(200), nullable=False)
    nombre         = Column(String(100), nullable=False)
    rol            = Column(String(30), nullable=False, default='tecnico')
    email          = Column(String(100))
    activo         = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime, default=datetime.now)
    ultimo_login   = Column(DateTime)

    # actividades no tiene back_populates porque usuario_id es BigInteger sin FK

    __table_args__ = (
        UniqueConstraint('taller_id', 'username', name='uq_usuario_taller_username'),
    )


class Cliente(Base):
    __tablename__ = 'clientes'
    id             = Column(String(20), primary_key=True)
    taller_id      = Column(Integer, ForeignKey('talleres.id'), default=1, nullable=False, index=True)
    nombre         = Column(String(100), nullable=False)
    apellidos      = Column(String(100), default='')
    email          = Column(String(100), default='')
    telefono       = Column(String(30), default='')
    direccion      = Column(String(200), default='')
    ciudad         = Column(String(50), default='')
    pais           = Column(String(30), default='PERÚ')
    tipo           = Column(String(20), default='Persona')
    observaciones  = Column(Text, default='')
    fecha_registro = Column(DateTime, default=datetime.now)
    pin_acceso     = Column(String(200), default='')
    notifs_leidas  = Column(Text, default='[]')
    documento      = Column(String(20), default='', index=True)
    tipo_cliente   = Column(String(20), default='individual')

    vehiculos = relationship('Vehiculo', back_populates='propietario')
    ordenes   = relationship('Orden', back_populates='cliente_rel')


class Vehiculo(Base):
    __tablename__ = 'vehiculos'
    placa          = Column(String(20), primary_key=True)
    taller_id      = Column(Integer, ForeignKey('talleres.id'), default=1, nullable=False, index=True)
    cliente_id     = Column(String(20), ForeignKey('clientes.id'), nullable=True)
    marca          = Column(String(50), default='')
    modelo         = Column(String(50), default='')
    año            = Column(String(10), default='')
    color          = Column(String(30), default='')
    tipo           = Column(String(30), default='Sedán')
    responsable    = Column(String(100), default='')
    tel_responsable = Column(String(30), default='')
    vin            = Column(String(50), default='')
    observaciones  = Column(Text, default='')

    # Flota empresarial: conductor asignado al vehículo (jefe de empresa lo gestiona)
    conductor_nombre          = Column(String(120), nullable=True)
    conductor_dni             = Column(String(20),  nullable=True)
    conductor_telefono        = Column(String(20),  nullable=True)
    conductor_email           = Column(String(120), nullable=True)
    conductor_pin_hash        = Column(Text,        nullable=True)
    conductor_pin_must_change = Column(Boolean,     default=True)
    conductor_activo          = Column(Boolean,     default=True)
    conductor_assigned_at     = Column(DateTime,    nullable=True)
    conductor_assigned_by     = Column(String(20),  nullable=True)

    propietario = relationship('Cliente', back_populates='vehiculos')
    ordenes     = relationship('Orden', back_populates='vehiculo_rel')


class ItemInventario(Base):
    __tablename__ = 'inventario'
    codigo        = Column(String(20), primary_key=True)
    taller_id     = Column(Integer, ForeignKey('talleres.id'), default=1, nullable=False, index=True)
    nombre        = Column(String(100), nullable=False)
    categoria     = Column(String(50), default='Otros')
    tipo          = Column(String(30), default='Repuesto')
    descripcion   = Column(Text, default='')
    costo         = Column(Float, default=0)
    rentabilidad  = Column(Float, default=0)
    precio        = Column(Float, default=0)
    stock         = Column(Integer, default=0)
    stock_minimo  = Column(Integer, default=5)


class Proveedor(Base):
    __tablename__ = 'proveedores'
    id          = Column(String(20), primary_key=True)
    taller_id   = Column(Integer, ForeignKey('talleres.id'), default=1, nullable=False, index=True)
    nombre      = Column(String(100), nullable=False)
    email       = Column(String(100), default='')
    telefono    = Column(String(30), default='')
    direccion   = Column(String(200), default='')
    ciudad      = Column(String(50), default='')
    productos   = Column(Text, default='')
    tipo        = Column(String(20), default='Empresa')


class Orden(Base):
    __tablename__ = 'ordenes'
    consecutivo           = Column(String(30), primary_key=True)
    taller_id             = Column(Integer, ForeignKey('talleres.id'), default=1, nullable=False, index=True)
    fecha                 = Column(String(20), nullable=False)
    cliente_id            = Column(String(20), ForeignKey('clientes.id'), nullable=True)
    vehiculo_placa        = Column(String(20), ForeignKey('vehiculos.placa'), nullable=True)
    motivo                = Column(Text, default='')
    diagnostico           = Column(Text, default='')
    estado                = Column(String(20), default='RECEPCIÓN')
    tecnico               = Column(String(50), default='')
    km                    = Column(String(20), default='')
    tipo                  = Column(String(20), default='Express')
    observaciones         = Column(Text, default='')
    diagnostico_requerido = Column(Boolean, default=True)
    items_cotizacion      = Column(JSON, default=list)
    historial             = Column(JSON, default=list)
    approval_token        = Column(String(64), default='')
    approval_status       = Column(String(20), default='pendiente')
    approval_date         = Column(String(30), default='')
    report_token          = Column(String(64), default='')
    checklist_reparacion  = Column(JSON, default=list)
    fotos_evidencia       = Column(JSON, default=list)
    firma_cliente         = Column(Text, default='')
    proximo_mantenimiento = Column(String(30), default='')
    notas_entrega         = Column(Text, default='')
    encuesta              = Column(JSON, default=dict)
    pdf_cotizacion        = Column(String(300), default='')
    factura_sunat         = Column(String(300), default='')
    metodo_pago           = Column(String(30), default='')
    fecha_cobro           = Column(String(20), default='')
    monto_cobrado         = Column(Float, default=0.0)
    pagos                 = Column(JSON, default=list)
    # Timestamps automáticos
    fecha_dt              = Column(DateTime(timezone=True), default=datetime.now)
    updated_at            = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.now)

    cliente_rel  = relationship('Cliente', back_populates='ordenes')
    vehiculo_rel = relationship('Vehiculo', back_populates='ordenes')
    computadoras = relationship('OrdenComputadora', back_populates='orden_servicio_rel', cascade='all, delete-orphan')


class OrdenComputadora(Base):
    __tablename__ = 'ordenes_computadoras'
    id                = Column(Integer, primary_key=True, autoincrement=True)
    taller_id         = Column(Integer, ForeignKey('talleres.id'), default=1, nullable=False, index=True)
    consecutivo       = Column(String(30), unique=True, nullable=False)
    orden_servicio_id = Column(String(30), ForeignKey('ordenes.consecutivo'), nullable=False)
    modulo_nombre     = Column(String(100), nullable=False)
    marca             = Column(String(50), default='')
    modelo            = Column(String(50), default='')
    serie             = Column(String(100), default='')
    diagnostico_lab   = Column(Text, default='')
    trabajo_realizado = Column(Text, default='')
    estado            = Column(String(30), default='RECIBIDO')
    costo_reparacion  = Column(Float, default=0)
    fecha_ingreso     = Column(DateTime, default=datetime.now)
    fecha_entrega     = Column(DateTime, nullable=True)

    orden_servicio_rel = relationship('Orden', back_populates='computadoras')


class Actividad(Base):
    __tablename__ = 'actividades'
    id         = Column(Integer, primary_key=True, autoincrement=True)
    taller_id  = Column(Integer, ForeignKey('talleres.id'), default=1, nullable=False, index=True)
    fecha      = Column(DateTime, default=datetime.now)
    # BigInteger sin FK: puede contener IDs de usuarios locales o IDs de Telegram (64-bit)
    usuario_id = Column(BigInteger, nullable=True)
    accion     = Column(String(200), nullable=False)
    modulo     = Column(String(50), default='')
    detalle    = Column(Text, default='')


class ConfigSistema(Base):
    __tablename__ = 'config_sistema'
    id        = Column(Integer, primary_key=True, autoincrement=True)
    taller_id = Column(Integer, ForeignKey('talleres.id'), default=1, nullable=False, index=True)
    clave     = Column(String(50), nullable=False)
    valor     = Column(Text, default='')

    __table_args__ = (
        UniqueConstraint('taller_id', 'clave', name='uq_config_taller_clave'),
    )


class Cita(Base):
    __tablename__ = 'citas'
    id            = Column(Integer, primary_key=True, autoincrement=True)
    taller_id     = Column(Integer, ForeignKey('talleres.id'), default=1, nullable=False, index=True)
    cliente_id    = Column(String(20), ForeignKey('clientes.id'), nullable=True)
    vehiculo_placa = Column(String(20), nullable=True)
    fecha_cita    = Column(String(20), nullable=False)
    hora          = Column(String(10), default='')
    motivo        = Column(Text, default='')
    estado        = Column(String(20), default='programada')
    notas         = Column(Text, default='')
    vista_admin   = Column(Integer, default=0)


class NotaVenta(Base):
    __tablename__ = 'notas_venta'
    id             = Column(Integer, primary_key=True, autoincrement=True)
    taller_id      = Column(Integer, ForeignKey('talleres.id'), default=1, nullable=False, index=True)
    numero         = Column(String(30), nullable=False)
    fecha          = Column(DateTime, default=datetime.now)
    cliente_id     = Column(String(20), ForeignKey('clientes.id'), nullable=True)
    cliente_nombre = Column(String(150), default='')
    subtotal       = Column(Float, default=0)
    igv            = Column(Float, default=0)
    total          = Column(Float, default=0)
    estado         = Column(String(20), default='pagada')
    notas          = Column(Text, default='')
    metodo_pago    = Column(String(30), default='')
    items          = Column(JSON, default=list)
    monto_pagado   = Column(Float, default=0)
    pagos          = Column(JSON, default=list)

    cliente_rel = relationship('Cliente', foreign_keys=[cliente_id])

    __table_args__ = (
        UniqueConstraint('taller_id', 'numero', name='uq_notaventa_taller_numero'),
    )


class Cotizacion(Base):
    __tablename__ = 'cotizaciones'
    id             = Column(Integer, primary_key=True, autoincrement=True)
    taller_id      = Column(Integer, ForeignKey('talleres.id'), default=1, nullable=False, index=True)
    numero         = Column(String(30), nullable=False)
    cliente_id     = Column(String(20), ForeignKey('clientes.id'), nullable=True)
    nombre_cliente = Column(String(150), nullable=False, default='')
    estado         = Column(String(20), default='PENDIENTE')
    total          = Column(Float, default=0)
    nota           = Column(Text, default='')
    creado_por     = Column(String(100), default='')
    fecha_creacion = Column(DateTime, default=datetime.now)

    cliente_rel = relationship('Cliente', foreign_keys=[cliente_id])
    items       = relationship('CotizacionItem', back_populates='cotizacion', cascade='all, delete-orphan')

    __table_args__ = (
        UniqueConstraint('taller_id', 'numero', name='uq_cotizacion_taller_numero'),
    )


class CotizacionItem(Base):
    __tablename__ = 'cotizacion_items'
    id               = Column(Integer, primary_key=True, autoincrement=True)
    cotizacion_id    = Column(Integer, ForeignKey('cotizaciones.id'), nullable=False)
    descripcion      = Column(String(200), nullable=False)
    tipo             = Column(String(20), default='repuesto')
    cantidad         = Column(Integer, default=1)
    precio_unitario  = Column(Float, default=0)
    subtotal         = Column(Float, default=0)

    cotizacion = relationship('Cotizacion', back_populates='items')


class CierreCaja(Base):
    __tablename__ = 'cierres_caja'
    id                  = Column(Integer, primary_key=True, autoincrement=True)
    taller_id           = Column(Integer, ForeignKey('talleres.id'), default=1, nullable=False, index=True)
    fecha               = Column(String(20), nullable=False)
    apertura_hora       = Column(String(10), default='')
    cierre_hora         = Column(String(10), default='')
    saldo_apertura      = Column(Float, default=0.0)
    saldo_cierre        = Column(Float, default=0.0)
    total_efectivo      = Column(Float, default=0.0)
    total_yape          = Column(Float, default=0.0)
    total_transferencia = Column(Float, default=0.0)
    total_tarjeta       = Column(Float, default=0.0)
    total_ordenes       = Column(Float, default=0.0)
    total_notas         = Column(Float, default=0.0)
    total_creditos      = Column(Float, default=0.0)
    total_mo            = Column(Float, default=0.0)
    total_repuestos     = Column(Float, default=0.0)
    ganancia_neta       = Column(Float, default=0.0)
    num_ordenes         = Column(Integer, default=0)
    num_notas           = Column(Integer, default=0)
    notas_operador      = Column(Text, default='')
    estado              = Column(String(20), default='abierta')
    usuario_apertura    = Column(String(100), default='')
    usuario_cierre      = Column(String(100), default='')


# ─────────────────────── MODELOS GLOBALES (sin taller_id) ───────────────────────

class AgentMemoria(Base):
    """Historial de conversación persistente por usuario de Telegram — global."""
    __tablename__ = 'agent_memoria'
    telegram_user_id = Column(BigInteger, primary_key=True)   # Telegram IDs son 64-bit
    historial_json   = Column(Text, default='[]')
    updated_at       = Column(DateTime, default=datetime.now)


class AgentCorreccion(Base):
    """RAG de correcciones: Jarvis aprende de sus errores — global."""
    __tablename__ = 'agent_correcciones'
    id                 = Column(Integer, primary_key=True, autoincrement=True)
    mensaje_original   = Column(Text, default='')
    respuesta_jarvis   = Column(Text, default='')
    correccion_usuario = Column(Text, default='')
    keywords           = Column(Text, default='')
    fecha              = Column(DateTime, default=datetime.now)


# ─────────────────────── INICIALIZACIÓN ───────────────────────

def init_db():
    """Crea todas las tablas y datos iniciales.

    2026-05-04 BUG-WATCHER FIX: setear app.taller_id=1 ANTES de cualquier
    INSERT, porque las tablas con RLS forzado (incluyendo config_sistema)
    rechazan INSERT si app.taller_id no está seteado en la sesión PG.
    Antes esto generaba `psycopg2.errors.InsufficientPrivilege: new row
    violates row-level security policy for table "config_sistema"` en
    cada restart del servicio.
    """
    Base.metadata.create_all(engine)

    db = get_db()
    try:
        # 2026-05-04 FIX: setear contexto RLS para que los INSERTs cumplan policies
        from sqlalchemy import text as _t
        db.execute(_t("SELECT set_config('app.taller_id', '1', false)"))
        # ── Taller Sandoval por defecto (id=1) ──
        taller = db.query(Taller).filter_by(id=1).first()
        if not taller:
            db.add(Taller(
                id=1,
                nombre='Mecánica y Repuestos Sandoval',
                subdominio='sandoval',
                ruc='20608755111',
                plan='premium',
                activo=True,
                empresa_nombre='MECÁNICA Y REPUESTOS SANDOVAL EIRL',
                empresa_ruc='20608755111',
                empresa_direccion='Av. Principal 123, Piura, Perú',
                empresa_telefono='+51 999 999 999',
                empresa_email='contacto@sandoval.com',
                igv_porcentaje=18.0,
                moneda='PEN',
            ))
            db.commit()
            print("[DB] Taller Sandoval creado (id=1)")

        # ── Usuarios por defecto ──
        admin = db.query(Usuario).filter_by(username='admin', taller_id=1).first()
        if not admin:
            # 2026-04-29 audit fix V2: NO sembrar credenciales por defecto.
            # Para crear el admin inicial: setear BOOTSTRAP_ADMIN_PASSWORD env (>=10 chars con complejidad).
            import os as _os
            _bootstrap_pwd = _os.environ.get('BOOTSTRAP_ADMIN_PASSWORD', '').strip()
            if _bootstrap_pwd:
                from utils.password_policy import validate_password_strength as _vpw
                _ok, _why = _vpw(_bootstrap_pwd, role='admin')
                if not _ok:
                    raise RuntimeError(f'BOOTSTRAP_ADMIN_PASSWORD debil: {_why}')
                db.add(Usuario(taller_id=1, username='admin',
                               password_hash=hash_password(_bootstrap_pwd),
                               nombre='Administrador', rol='admin',
                               email='admin@sandoval.com', activo=True))
                _logger.info('init_db: admin creado desde BOOTSTRAP_ADMIN_PASSWORD env')
            else:
                _logger.warning(
                    'init_db: sin BOOTSTRAP_ADMIN_PASSWORD env; NO se crea admin. '
                    'Para crearlo: BOOTSTRAP_ADMIN_PASSWORD=... python -c "from utils.models import init_db; init_db()"'
                )
            # tecnico1/recepcion eliminados — solo admin se crea bajo env explicito
            db.commit()
            print("[DB] Usuarios por defecto creados")
        else:
            # 2026-04-29 audit V2.c: reactivacion automatica eliminada.
            # Si admin esta inactivo, requiere accion manual explicita (no se reactiva al boot).
            print(f"[DB] Admin verificado (id={admin.id}, activo={admin.activo})")

        # ── Config por defecto (taller_id=1) ──
        defaults = {
            'empresa_nombre':    'MECÁNICA Y REPUESTOS SANDOVAL EIRL',
            'empresa_ruc':       '20608755111',
            'empresa_direccion': 'Av. Principal 123, Piura, Perú',
            'empresa_telefono':  '+51 999 999 999',
            'empresa_email':     'contacto@sandoval.com',
            'igv_porcentaje':    '18',
            'moneda':            'PEN',
        }
        for k, v in defaults.items():
            if not db.query(ConfigSistema).filter_by(clave=k, taller_id=1).first():
                db.add(ConfigSistema(taller_id=1, clave=k, valor=v))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[DB] Error en init_db: {e}")
    finally:
        db.close()

    # ── Migraciones SQLite (solo aplican si usamos SQLite) ──
    if not _IS_PG:
        _run_sqlite_migrations()


def _run_sqlite_migrations():
    """Migraciones ALTER TABLE para bases de datos SQLite antiguas."""
    migrations = [
        "ALTER TABLE ordenes ADD COLUMN report_token VARCHAR(64) DEFAULT ''",
        "ALTER TABLE ordenes ADD COLUMN encuesta JSON DEFAULT '{}'",
        "ALTER TABLE ordenes ADD COLUMN pdf_cotizacion VARCHAR(300) DEFAULT ''",
        "ALTER TABLE clientes ADD COLUMN pin_acceso VARCHAR(200) DEFAULT ''",
        "ALTER TABLE ordenes ADD COLUMN factura_sunat VARCHAR(300) DEFAULT ''",
        "ALTER TABLE clientes ADD COLUMN notifs_leidas TEXT DEFAULT '[]'",
        "ALTER TABLE citas ADD COLUMN vista_admin INTEGER DEFAULT 0",
        "ALTER TABLE ordenes ADD COLUMN metodo_pago VARCHAR(30) DEFAULT ''",
        "ALTER TABLE ordenes ADD COLUMN fecha_cobro VARCHAR(20) DEFAULT ''",
        "ALTER TABLE ordenes ADD COLUMN monto_cobrado FLOAT DEFAULT 0",
        "ALTER TABLE ordenes ADD COLUMN pagos JSON DEFAULT '[]'",
        "ALTER TABLE notas_venta ADD COLUMN metodo_pago VARCHAR(30) DEFAULT ''",
        "ALTER TABLE cierres_caja ADD COLUMN total_creditos FLOAT DEFAULT 0",
        "ALTER TABLE vehiculos ADD COLUMN responsable VARCHAR(100) DEFAULT ''",
        "ALTER TABLE vehiculos ADD COLUMN tel_responsable VARCHAR(30) DEFAULT ''",
    ]
    for sql in migrations:
        try:
            with engine.connect() as conn:
                conn.execute(__import__('sqlalchemy').text(sql))
                conn.commit()
        except Exception:
            pass  # columna ya existe


def migrate_json_to_db():
    """Migra datos existentes de JSON a SQLite preservando todo."""
    data_dir = os.path.join(BASE_DIR, 'data')
    db = get_db()
    try:
        _migrate_file(db, data_dir, 'clientes.json', Cliente, {
            'id': 'id', 'nombre': 'nombre', 'apellidos': 'apellidos',
            'email': 'email', 'telefono': 'telefono', 'direccion': 'direccion',
            'ciudad': 'ciudad', 'pais': 'pais', 'tipo': 'tipo', 'observaciones': 'observaciones'
        })
        _migrate_file(db, data_dir, 'vehiculos.json', Vehiculo, {
            'placa': 'placa', 'cliente_id': 'cliente_id', 'marca': 'marca',
            'modelo': 'modelo', 'año': 'año', 'color': 'color', 'tipo': 'tipo',
            'vin': 'vin', 'observaciones': 'observaciones'
        })
        _migrate_file(db, data_dir, 'proveedores.json', Proveedor, {
            'id': 'id', 'nombre': 'nombre', 'email': 'email',
            'telefono': 'telefono', 'direccion': 'direccion', 'ciudad': 'ciudad',
            'productos': 'productos', 'tipo': 'tipo'
        })
        _migrate_file(db, data_dir, 'inventario.json', ItemInventario, {
            'codigo': 'codigo', 'nombre': 'nombre', 'categoria': 'categoria',
            'tipo': 'tipo', 'descripcion': 'descripcion', 'costo': 'costo',
            'rentabilidad': 'rentabilidad', 'precio': 'precio', 'stock': 'stock'
        })
        _migrate_file(db, data_dir, 'ordenes.json', Orden, {
            'consecutivo': 'consecutivo', 'fecha': 'fecha', 'cliente_id': 'cliente_id',
            'vehiculo_placa': 'vehiculo_placa', 'motivo': 'motivo', 'estado': 'estado',
            'tecnico': 'tecnico', 'km': 'km', 'tipo': 'tipo', 'observaciones': 'observaciones',
            'diagnostico_requerido': 'diagnostico_requerido', 'diagnostico': 'diagnostico',
            'items_cotizacion': 'items_cotizacion', 'historial': 'historial'
        })
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error migrando datos: {e}")
    finally:
        db.close()


def _migrate_file(db, data_dir, filename, model_class, field_map):
    filepath = os.path.join(data_dir, filename)
    if not os.path.exists(filepath):
        return
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            items = json.load(f)
        if not isinstance(items, list):
            return
        pk_field = list(field_map.keys())[0]
        for item in items:
            pk_value = item.get(pk_field)
            if not pk_value:
                continue
            existing = db.query(model_class).get(pk_value)
            if existing:
                continue
            kwargs = {}
            for json_key, db_col in field_map.items():
                if json_key in item:
                    kwargs[db_col] = item[json_key]
            if kwargs:
                db.add(model_class(**kwargs))
    except Exception as e:
        print(f"Error migrando {filename}: {e}")


def get_config(clave: str, default: str = '', taller_id: int = 1) -> str:
    db = get_db()
    try:
        row = db.query(ConfigSistema).filter_by(clave=clave, taller_id=taller_id).first()
        return row.valor if row else default
    finally:
        db.close()


def set_config(clave: str, valor: str, taller_id: int = 1):
    db = get_db()
    try:
        row = db.query(ConfigSistema).filter_by(clave=clave, taller_id=taller_id).first()
        if row:
            row.valor = valor
        else:
            db.add(ConfigSistema(taller_id=taller_id, clave=clave, valor=valor))
        db.commit()
    finally:
        db.close()


def log_actividad(accion: str, modulo: str = '', detalle: str = '', usuario_id: int = None, taller_id: int = 1):
    db = get_db()
    try:
        db.add(Actividad(taller_id=taller_id, accion=accion, modulo=modulo, detalle=detalle, usuario_id=usuario_id))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

class Factura(Base):
    """Facturas de proveedor (compras de mercadería + gastos)."""
    __tablename__ = 'facturas'
    id                  = Column(Integer, primary_key=True, autoincrement=True)
    taller_id           = Column(Integer, ForeignKey('talleres.id'), default=1, nullable=False, index=True)
    tipo                = Column(Text, default='mercaderia')
    subtipo_gasto       = Column(Text, default='')
    proveedor           = Column(Text, default='')
    numero_factura      = Column(Text, default='')
    fecha               = Column(Text, default='')
    subtotal            = Column(Float, default=0)
    igv                 = Column(Float, default=0)
    total               = Column(Float, default=0)
    imagen_path         = Column(Text, default='')
    items_json          = Column(Text, default='[]')
    estado              = Column(Text, default='procesada')
    notas               = Column(Text, default='')
    fecha_registro      = Column(Text, default='')
    agregado_inventario = Column(Integer, default=0)
    ruc_proveedor       = Column(String(20), default='')
    moneda              = Column(String(10), default='PEN')

