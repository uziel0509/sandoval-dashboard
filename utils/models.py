"""
SANDOVAL Dashboard - Modelos de Base de Datos SQLite
Modelos SQLAlchemy con relaciones completas
"""

import os
import json
import hashlib
import secrets
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, Text,
    DateTime, ForeignKey, JSON, event
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from sqlalchemy.pool import StaticPool

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'sandoval.db')
os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)

engine = create_engine(
    f'sqlite:///{DB_PATH}',
    connect_args={'check_same_thread': False},
    poolclass=StaticPool,
    echo=False,
)

Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Session:
    return SessionLocal()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}:{hashed.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, hashed = stored.split(':')
        check = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return check.hex() == hashed
    except Exception:
        return False


# ─────────────────────── MODELOS ───────────────────────

class Usuario(Base):
    __tablename__ = 'usuarios'
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    nombre = Column(String(100), nullable=False)
    rol = Column(String(30), nullable=False, default='tecnico')  # admin, tecnico, recepcionista
    email = Column(String(100))
    activo = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime, default=datetime.now)
    ultimo_login = Column(DateTime)

    actividades = relationship('Actividad', back_populates='usuario')


class Cliente(Base):
    __tablename__ = 'clientes'
    id = Column(String(20), primary_key=True)
    nombre = Column(String(100), nullable=False)
    apellidos = Column(String(100), default='')
    email = Column(String(100), default='')
    telefono = Column(String(30), default='')
    direccion = Column(String(200), default='')
    ciudad = Column(String(50), default='')
    pais = Column(String(30), default='PERÚ')
    tipo = Column(String(20), default='Persona')
    observaciones = Column(Text, default='')
    fecha_registro = Column(DateTime, default=datetime.now)
    pin_acceso = Column(String(200), default='')  # PIN hasheado para portal cliente
    notifs_leidas = Column(Text, default='[]')   # JSON lista de IDs de notificaciones leídas

    vehiculos = relationship('Vehiculo', back_populates='propietario')
    ordenes = relationship('Orden', back_populates='cliente_rel')


class Vehiculo(Base):
    __tablename__ = 'vehiculos'
    placa = Column(String(20), primary_key=True)
    cliente_id = Column(String(20), ForeignKey('clientes.id'), nullable=True)
    marca = Column(String(50), default='')
    modelo = Column(String(50), default='')
    año = Column(String(10), default='')
    color = Column(String(30), default='')
    tipo = Column(String(30), default='Sedán')
    vin = Column(String(50), default='')
    observaciones = Column(Text, default='')

    propietario = relationship('Cliente', back_populates='vehiculos')
    ordenes = relationship('Orden', back_populates='vehiculo_rel')


class ItemInventario(Base):
    __tablename__ = 'inventario'
    codigo = Column(String(20), primary_key=True)
    nombre = Column(String(100), nullable=False)
    categoria = Column(String(50), default='Otros')
    tipo = Column(String(30), default='Repuesto')
    descripcion = Column(Text, default='')
    costo = Column(Float, default=0)
    rentabilidad = Column(Float, default=0)
    precio = Column(Float, default=0)
    stock = Column(Integer, default=0)
    stock_minimo = Column(Integer, default=5)


class Proveedor(Base):
    __tablename__ = 'proveedores'
    id = Column(String(20), primary_key=True)
    nombre = Column(String(100), nullable=False)
    email = Column(String(100), default='')
    telefono = Column(String(30), default='')
    direccion = Column(String(200), default='')
    ciudad = Column(String(50), default='')
    productos = Column(Text, default='')
    tipo = Column(String(20), default='Empresa')


class Orden(Base):
    __tablename__ = 'ordenes'
    consecutivo = Column(String(30), primary_key=True)
    fecha = Column(String(20), nullable=False)
    cliente_id = Column(String(20), ForeignKey('clientes.id'), nullable=True)
    vehiculo_placa = Column(String(20), ForeignKey('vehiculos.placa'), nullable=True)
    motivo = Column(Text, default='')
    diagnostico = Column(Text, default='')
    estado = Column(String(20), default='RECEPCIÓN')
    tecnico = Column(String(50), default='')
    km = Column(String(20), default='')
    tipo = Column(String(20), default='Express')
    observaciones = Column(Text, default='')
    diagnostico_requerido = Column(Boolean, default=True)
    # Cotización / ítems guardados como JSON
    items_cotizacion = Column(JSON, default=list)
    historial = Column(JSON, default=list)
    # Token de aprobación pública
    approval_token = Column(String(64), default='')
    approval_status = Column(String(20), default='pendiente')  # pendiente, aprobado, rechazado
    approval_date = Column(String(30), default='')
    # Token de reporte de entrega
    report_token = Column(String(64), default='')
    # Campos extras
    checklist_reparacion = Column(JSON, default=list)
    fotos_evidencia = Column(JSON, default=list)
    firma_cliente = Column(Text, default='')
    proximo_mantenimiento = Column(String(30), default='')
    notas_entrega = Column(Text, default='')
    encuesta = Column(JSON, default=dict)
    # PDF combinado (diagnóstico + cotización) guardado al aprobar
    pdf_cotizacion = Column(String(300), default='')
    # Factura SUNAT subida por el administrador
    factura_sunat = Column(String(300), default='')


    cliente_rel = relationship('Cliente', back_populates='ordenes')
    vehiculo_rel = relationship('Vehiculo', back_populates='ordenes')


class Actividad(Base):
    __tablename__ = 'actividades'
    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha = Column(DateTime, default=datetime.now)
    usuario_id = Column(Integer, ForeignKey('usuarios.id'), nullable=True)
    accion = Column(String(200), nullable=False)
    modulo = Column(String(50), default='')
    detalle = Column(Text, default='')

    usuario = relationship('Usuario', back_populates='actividades')


class ConfigSistema(Base):
    __tablename__ = 'config_sistema'
    clave = Column(String(50), primary_key=True)
    valor = Column(Text, default='')


class Cita(Base):
    __tablename__ = 'citas'
    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String(20), ForeignKey('clientes.id'), nullable=True)
    vehiculo_placa = Column(String(20), nullable=True)
    fecha_cita = Column(String(20), nullable=False)
    hora = Column(String(10), default='')
    motivo = Column(Text, default='')
    estado = Column(String(20), default='programada')  # programada, confirmada, completada, cancelada
    notas = Column(Text, default='')
    vista_admin = Column(Integer, default=0)  # 0=no vista, 1=ya vista por admin


class NotaVenta(Base):
    __tablename__ = 'notas_venta'
    id             = Column(Integer, primary_key=True, autoincrement=True)
    numero         = Column(String(30), unique=True, nullable=False)
    fecha          = Column(DateTime, default=datetime.now)
    cliente_id     = Column(String(20), ForeignKey('clientes.id'), nullable=True)
    cliente_nombre = Column(String(150), default='')   # Para clientes sin registro
    subtotal       = Column(Float, default=0)
    igv            = Column(Float, default=0)
    total          = Column(Float, default=0)
    estado         = Column(String(20), default='pagada')  # borrador, pagada, anulada
    notas          = Column(Text, default='')
    items          = Column(JSON, default=list)   # [{codigo, nombre, cantidad, precio, subtotal}]

    cliente_rel = relationship('Cliente', foreign_keys=[cliente_id])



# ─────────────────────── COTIZACIONES ───────────────────────

class Cotizacion(Base):
    __tablename__ = 'cotizaciones'
    id              = Column(Integer, primary_key=True, autoincrement=True)
    numero          = Column(String(30), unique=True, nullable=False)
    cliente_id      = Column(Integer, ForeignKey('clientes.id'), nullable=True)
    nombre_cliente  = Column(String(150), nullable=False, default='')
    estado          = Column(String(20), default='PENDIENTE')
    total           = Column(Float, default=0)
    nota            = Column(Text, default='')
    creado_por      = Column(String(100), default='')
    fecha_creacion  = Column(DateTime, default=datetime.now)

    cliente_rel = relationship('Cliente', foreign_keys=[cliente_id])
    items       = relationship('CotizacionItem', back_populates='cotizacion', cascade='all, delete-orphan')


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


# ─────────────────────── INICIALIZACIÓN ───────────────────────

def init_db():
    """Crea todas las tablas y datos iniciales"""
    Base.metadata.create_all(engine)

    # Migración: crear tabla notas_venta si no existe (bases de datos antiguas)
    try:
        with engine.connect() as conn:
            conn.execute(__import__('sqlalchemy').text("""
                CREATE TABLE IF NOT EXISTS notas_venta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero VARCHAR(30) UNIQUE NOT NULL,
                    fecha DATETIME,
                    cliente_id VARCHAR(20),
                    cliente_nombre VARCHAR(150) DEFAULT '',
                    subtotal FLOAT DEFAULT 0,
                    igv FLOAT DEFAULT 0,
                    total FLOAT DEFAULT 0,
                    estado VARCHAR(20) DEFAULT 'pagada',
                    notas TEXT DEFAULT '',
                    items JSON DEFAULT '[]'
                )
            """))
            conn.commit()
    except Exception:
        pass
    # Migración segura: agregar report_token si no existe
    try:
        with engine.connect() as conn:
            conn.execute(__import__('sqlalchemy').text(
                "ALTER TABLE ordenes ADD COLUMN report_token VARCHAR(64) DEFAULT ''"
            ))
            conn.commit()
    except Exception:
        pass  # La columna ya existe

    # Migración: agregar encuesta si no existe
    try:
        with engine.connect() as conn:
            conn.execute(__import__('sqlalchemy').text(
                "ALTER TABLE ordenes ADD COLUMN encuesta JSON DEFAULT '{}'"
            ))
            conn.commit()
    except Exception:
        pass

    # Migración: agregar pdf_cotizacion si no existe
    try:
        with engine.connect() as conn:
            conn.execute(__import__('sqlalchemy').text(
                "ALTER TABLE ordenes ADD COLUMN pdf_cotizacion VARCHAR(300) DEFAULT ''"
            ))
            conn.commit()
    except Exception:
        pass

    # Migración: agregar pin_acceso a clientes si no existe
    try:
        with engine.connect() as conn:
            conn.execute(__import__('sqlalchemy').text(
                "ALTER TABLE clientes ADD COLUMN pin_acceso VARCHAR(200) DEFAULT ''"
            ))
            conn.commit()
    except Exception:
        pass  # La columna ya existe

    # Migración: agregar factura_sunat a ordenes si no existe
    try:
        with engine.connect() as conn:
            conn.execute(__import__('sqlalchemy').text(
                "ALTER TABLE ordenes ADD COLUMN factura_sunat VARCHAR(300) DEFAULT ''"
            ))
            conn.commit()
    except Exception:
        pass  # La columna ya existe

    # Migración: agregar notifs_leidas a clientes (JSON lista de IDs leídos)
    try:
        with engine.connect() as conn:
            conn.execute(__import__('sqlalchemy').text(
                "ALTER TABLE clientes ADD COLUMN notifs_leidas TEXT DEFAULT '[]'"
            ))
            conn.commit()
    except Exception:
        pass  # La columna ya existe

    # Migración: agregar notifs_leidas_admin a citas (para que admin sepa cuáles vio)
    try:
        with engine.connect() as conn:
            conn.execute(__import__('sqlalchemy').text(
                "ALTER TABLE citas ADD COLUMN vista_admin INTEGER DEFAULT 0"
            ))
            conn.commit()
    except Exception:
        pass  # La columna ya existe

    db = get_db()
    try:
        # Crear admin por defecto si no existe
        admin = db.query(Usuario).filter_by(username='admin').first()
        if not admin:
            db.add(Usuario(
                username='admin',
                password_hash=hash_password('admin123'),
                nombre='Administrador',
                rol='admin',
                email='admin@sandoval.com',
                activo=True,
            ))
            db.add(Usuario(username='tecnico1', password_hash=hash_password('tec123'), nombre='Juan Técnico', rol='tecnico', activo=True))
            db.add(Usuario(username='recepcion', password_hash=hash_password('rec123'), nombre='María Recepción', rol='recepcionista', activo=True))
            db.commit()
            print("[DB] Usuarios por defecto creados")
        else:
            # Siempre resetear contraseña admin para asegurar acceso
            admin.password_hash = hash_password('admin123')
            admin.activo = True
            db.commit()
            print(f"[DB] Admin verificado (id={admin.id})")

        # Config por defecto
        defaults = {
            'empresa_nombre': 'MECÁNICA Y REPUESTOS SANDOVAL EIRL',
            'empresa_ruc': '20608755111',
            'empresa_direccion': 'Av. Principal 123, Piura, Perú',
            'empresa_telefono': '+51 999 999 999',
            'empresa_email': 'contacto@sandoval.com',
            'igv_porcentaje': '18',
            'moneda': 'PEN',
        }
        for k, v in defaults.items():
            if not db.query(ConfigSistema).filter_by(clave=k).first():
                db.add(ConfigSistema(clave=k, valor=v))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def migrate_json_to_db():
    """Migra datos existentes de JSON a SQLite preservando todo"""
    data_dir = os.path.join(BASE_DIR, 'data')
    db = get_db()
    try:
        # Clientes
        _migrate_file(db, data_dir, 'clientes.json', Cliente, {
            'id': 'id', 'nombre': 'nombre', 'apellidos': 'apellidos',
            'email': 'email', 'telefono': 'telefono', 'direccion': 'direccion',
            'ciudad': 'ciudad', 'pais': 'pais', 'tipo': 'tipo', 'observaciones': 'observaciones'
        })
        # Vehículos
        _migrate_file(db, data_dir, 'vehiculos.json', Vehiculo, {
            'placa': 'placa', 'cliente_id': 'cliente_id', 'marca': 'marca',
            'modelo': 'modelo', 'año': 'año', 'color': 'color', 'tipo': 'tipo',
            'vin': 'vin', 'observaciones': 'observaciones'
        })
        # Proveedores
        _migrate_file(db, data_dir, 'proveedores.json', Proveedor, {
            'id': 'id', 'nombre': 'nombre', 'email': 'email',
            'telefono': 'telefono', 'direccion': 'direccion', 'ciudad': 'ciudad',
            'productos': 'productos', 'tipo': 'tipo'
        })
        # Inventario
        _migrate_file(db, data_dir, 'inventario.json', ItemInventario, {
            'codigo': 'codigo', 'nombre': 'nombre', 'categoria': 'categoria',
            'tipo': 'tipo', 'descripcion': 'descripcion', 'costo': 'costo',
            'rentabilidad': 'rentabilidad', 'precio': 'precio', 'stock': 'stock'
        })
        # Órdenes
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
    """Migra un archivo JSON a la tabla correspondiente"""
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
            # Verificar si ya existe
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


def get_config(clave: str, default: str = '') -> str:
    db = get_db()
    try:
        row = db.query(ConfigSistema).filter_by(clave=clave).first()
        return row.valor if row else default
    finally:
        db.close()


def set_config(clave: str, valor: str):
    db = get_db()
    try:
        row = db.query(ConfigSistema).filter_by(clave=clave).first()
        if row:
            row.valor = valor
        else:
            db.add(ConfigSistema(clave=clave, valor=valor))
        db.commit()
    finally:
        db.close()


def log_actividad(accion: str, modulo: str = '', detalle: str = '', usuario_id: int = None):
    db = get_db()
    try:
        db.add(Actividad(accion=accion, modulo=modulo, detalle=detalle, usuario_id=usuario_id))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
