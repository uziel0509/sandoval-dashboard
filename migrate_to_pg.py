#!/usr/bin/env python3
"""
SANDOVAL SaaS — Script de Migración SQLite → PostgreSQL
Ejecutar UNA sola vez en el VPS después de configurar PostgreSQL.

Uso:
    python3 /var/www/sandoval/migrate_to_pg.py

El script:
 1. Lee todos los datos de sandoval.db (SQLite)
 2. Crea las tablas en PostgreSQL (via models.py)
 3. Inserta todos los registros con taller_id=1
 4. Verifica que los conteos coincidan
 5. NO modifica ni elimina la base SQLite (queda como backup)
"""

import os
import sys
import sqlite3
import json
import traceback
from datetime import datetime

# ─── Configuración ────────────────────────────────────────────────────────────
SQLITE_PATH = '/var/www/sandoval/data/sandoval.db'
PG_URL      = 'postgresql://sandoval_user:SandovalSaaS2026!@localhost:5432/sandoval_saas'

os.environ['DATABASE_URL'] = PG_URL
sys.path.insert(0, '/var/www/sandoval')

print("=" * 60)
print("  SANDOVAL SaaS — Migración SQLite → PostgreSQL")
print("=" * 60)

# ── 1. Conectar a SQLite ──────────────────────────────────────────────────────
print("\n[1/5] Conectando a SQLite...")
try:
    sq = sqlite3.connect(SQLITE_PATH)
    sq.row_factory = sqlite3.Row
    print(f"      OK → {SQLITE_PATH}")
except Exception as e:
    print(f"      ERROR: {e}")
    sys.exit(1)

# ── 2. Crear tablas en PostgreSQL ─────────────────────────────────────────────
print("\n[2/5] Creando tablas en PostgreSQL...")
try:
    from utils.models import (
        Base, engine, get_db, init_db,
        Taller, Usuario, Cliente, Vehiculo, ItemInventario, Proveedor,
        Orden, OrdenComputadora, Actividad, ConfigSistema, Cita,
        NotaVenta, Cotizacion, CotizacionItem, CierreCaja,
        AgentMemoria, AgentCorreccion, hash_password
    )
    Base.metadata.create_all(engine)
    print("      OK → Tablas creadas")
except Exception as e:
    print(f"      ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)

# ── 3. Crear taller Sandoval (id=1) ───────────────────────────────────────────
print("\n[3/5] Creando taller Sandoval (id=1)...")
db = get_db()
try:
    # Leer config desde SQLite para poblar el taller
    cfg_rows = sq.execute("SELECT clave, valor FROM config_sistema").fetchall()
    cfg = {r['clave']: r['valor'] for r in cfg_rows}

    taller = db.query(Taller).filter_by(id=1).first()
    if not taller:
        db.add(Taller(
            id=1,
            nombre=cfg.get('empresa_nombre', 'Mecánica y Repuestos Sandoval'),
            subdominio='sandoval',
            ruc=cfg.get('empresa_ruc', ''),
            plan='premium',
            activo=True,
            empresa_nombre=cfg.get('empresa_nombre', 'MECÁNICA Y REPUESTOS SANDOVAL EIRL'),
            empresa_ruc=cfg.get('empresa_ruc', ''),
            empresa_direccion=cfg.get('empresa_direccion', ''),
            empresa_telefono=cfg.get('empresa_telefono', ''),
            empresa_email=cfg.get('empresa_email', ''),
            igv_porcentaje=float(cfg.get('igv_porcentaje', 18)),
            moneda=cfg.get('moneda', 'PEN'),
        ))
        db.commit()
        print("      OK → Taller Sandoval creado")
    else:
        print("      OK → Taller Sandoval ya existe")
finally:
    db.close()


def parse_json(val):
    """Convierte texto JSON de SQLite a objeto Python."""
    if val is None:
        return None
    if isinstance(val, (list, dict)):
        return val
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return None
        try:
            return json.loads(val)
        except Exception:
            return val
    return val


def safe_bool(val):
    if val is None:
        return True
    if isinstance(val, bool):
        return val
    return bool(val)


def safe_float(val, default=0.0):
    if val is None:
        return default
    try:
        return float(val)
    except Exception:
        return default


def safe_int(val, default=0):
    if val is None:
        return default
    try:
        return int(val)
    except Exception:
        return default


def safe_dt(val):
    """Convierte string de fecha a datetime o None."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(val), fmt)
        except Exception:
            pass
    return None


# ── 4. Migrar datos ───────────────────────────────────────────────────────────
print("\n[4/5] Migrando datos...")

errors   = []
counters = {}

def migrate_table(name, rows_fn, insert_fn):
    """Migra una tabla leyendo de SQLite e insertando en PostgreSQL."""
    db2 = get_db()
    count = 0
    skipped = 0
    try:
        rows = rows_fn()
        for row in rows:
            try:
                result = insert_fn(db2, row)
                if result == 'skip':
                    skipped += 1
                else:
                    count += 1
                    if count % 50 == 0:
                        db2.flush()
            except Exception as e:
                errors.append(f"{name}: {e}")
                db2.rollback()
                db2 = get_db()
        db2.commit()
    except Exception as e:
        errors.append(f"{name} global: {e}")
        db2.rollback()
    finally:
        db2.close()
    counters[name] = (count, skipped)
    print(f"      {name:25s} → {count:4d} migrados, {skipped:3d} omitidos")


# ─── Usuarios ───
def ins_usuario(db2, r):
    if db2.query(Usuario).filter_by(username=r['username'], taller_id=1).first():
        return 'skip'
    db2.add(Usuario(
        taller_id=1,
        username=r['username'],
        password_hash=r['password_hash'] or '',
        nombre=r['nombre'] or '',
        rol=r['rol'] or 'tecnico',
        email=r['email'] or '',
        activo=safe_bool(r['activo']),
        fecha_creacion=safe_dt(r['fecha_creacion']),
        ultimo_login=safe_dt(r['ultimo_login']),
    ))

migrate_table('usuarios',
    lambda: sq.execute("SELECT * FROM usuarios").fetchall(),
    ins_usuario)

# ─── Clientes ───
def ins_cliente(db2, r):
    if db2.query(Cliente).filter_by(id=r['id']).first():
        return 'skip'
    db2.add(Cliente(
        id=r['id'], taller_id=1,
        nombre=r['nombre'] or '',
        apellidos=r['apellidos'] or '',
        email=r['email'] or '',
        telefono=r['telefono'] or '',
        direccion=r['direccion'] or '',
        ciudad=r['ciudad'] or '',
        pais=r['pais'] or 'PERÚ',
        tipo=r['tipo'] or 'Persona',
        observaciones=r['observaciones'] or '',
        fecha_registro=safe_dt(r['fecha_registro']),
        pin_acceso=r['pin_acceso'] or '',
        notifs_leidas=r['notifs_leidas'] or '[]',
    ))

migrate_table('clientes',
    lambda: sq.execute("SELECT * FROM clientes").fetchall(),
    ins_cliente)

# ─── Vehículos ───
def ins_vehiculo(db2, r):
    if db2.query(Vehiculo).filter_by(placa=r['placa']).first():
        return 'skip'
    db2.add(Vehiculo(
        placa=r['placa'], taller_id=1,
        cliente_id=r['cliente_id'],
        marca=r['marca'] or '',
        modelo=r['modelo'] or '',
        año=r['año'] or '',
        color=r['color'] or '',
        tipo=r['tipo'] or 'Sedán',
        responsable=r['responsable'] or '' if 'responsable' in r.keys() else '',
        tel_responsable=r['tel_responsable'] or '' if 'tel_responsable' in r.keys() else '',
        vin=r['vin'] or '',
        observaciones=r['observaciones'] or '',
    ))

migrate_table('vehiculos',
    lambda: sq.execute("SELECT * FROM vehiculos").fetchall(),
    ins_vehiculo)

# ─── Inventario ───
def ins_inventario(db2, r):
    if db2.query(ItemInventario).filter_by(codigo=r['codigo']).first():
        return 'skip'
    db2.add(ItemInventario(
        codigo=r['codigo'], taller_id=1,
        nombre=r['nombre'] or '',
        categoria=r['categoria'] or 'Otros',
        tipo=r['tipo'] or 'Repuesto',
        descripcion=r['descripcion'] or '',
        costo=safe_float(r['costo']),
        rentabilidad=safe_float(r['rentabilidad']),
        precio=safe_float(r['precio']),
        stock=safe_int(r['stock']),
        stock_minimo=safe_int(r['stock_minimo'], 5),
    ))

migrate_table('inventario',
    lambda: sq.execute("SELECT * FROM inventario").fetchall(),
    ins_inventario)

# ─── Proveedores ───
def ins_proveedor(db2, r):
    if db2.query(Proveedor).filter_by(id=r['id']).first():
        return 'skip'
    db2.add(Proveedor(
        id=r['id'], taller_id=1,
        nombre=r['nombre'] or '',
        email=r['email'] or '',
        telefono=r['telefono'] or '',
        direccion=r['direccion'] or '',
        ciudad=r['ciudad'] or '',
        productos=r['productos'] or '',
        tipo=r['tipo'] or 'Empresa',
    ))

migrate_table('proveedores',
    lambda: sq.execute("SELECT * FROM proveedores").fetchall(),
    ins_proveedor)

# ─── Órdenes ───
def ins_orden(db2, r):
    if db2.query(Orden).filter_by(consecutivo=r['consecutivo']).first():
        return 'skip'
    db2.add(Orden(
        consecutivo=r['consecutivo'], taller_id=1,
        fecha=r['fecha'] or '',
        cliente_id=r['cliente_id'],
        vehiculo_placa=r['vehiculo_placa'],
        motivo=r['motivo'] or '',
        diagnostico=r['diagnostico'] or '',
        estado=r['estado'] or 'RECEPCIÓN',
        tecnico=r['tecnico'] or '',
        km=r['km'] or '',
        tipo=r['tipo'] or 'Express',
        observaciones=r['observaciones'] or '',
        diagnostico_requerido=safe_bool(r['diagnostico_requerido']),
        items_cotizacion=parse_json(r['items_cotizacion']) or [],
        historial=parse_json(r['historial']) or [],
        approval_token=r['approval_token'] or '' if 'approval_token' in r.keys() else '',
        approval_status=r['approval_status'] or 'pendiente' if 'approval_status' in r.keys() else 'pendiente',
        approval_date=r['approval_date'] or '' if 'approval_date' in r.keys() else '',
        report_token=r['report_token'] or '' if 'report_token' in r.keys() else '',
        checklist_reparacion=parse_json(r['checklist_reparacion']) or [] if 'checklist_reparacion' in r.keys() else [],
        fotos_evidencia=parse_json(r['fotos_evidencia']) or [] if 'fotos_evidencia' in r.keys() else [],
        firma_cliente=r['firma_cliente'] or '' if 'firma_cliente' in r.keys() else '',
        proximo_mantenimiento=r['proximo_mantenimiento'] or '' if 'proximo_mantenimiento' in r.keys() else '',
        notas_entrega=r['notas_entrega'] or '' if 'notas_entrega' in r.keys() else '',
        encuesta=parse_json(r['encuesta']) or {} if 'encuesta' in r.keys() else {},
        pdf_cotizacion=r['pdf_cotizacion'] or '' if 'pdf_cotizacion' in r.keys() else '',
        factura_sunat=r['factura_sunat'] or '' if 'factura_sunat' in r.keys() else '',
        metodo_pago=r['metodo_pago'] or '' if 'metodo_pago' in r.keys() else '',
        fecha_cobro=r['fecha_cobro'] or '' if 'fecha_cobro' in r.keys() else '',
        monto_cobrado=safe_float(r['monto_cobrado']) if 'monto_cobrado' in r.keys() else 0.0,
        pagos=parse_json(r['pagos']) or [] if 'pagos' in r.keys() else [],
    ))

migrate_table('ordenes',
    lambda: sq.execute("SELECT * FROM ordenes").fetchall(),
    ins_orden)

# ─── Órdenes Computadoras ───
try:
    rows_oc = sq.execute("SELECT * FROM ordenes_computadoras").fetchall()
    if rows_oc:
        def ins_oc(db2, r):
            if db2.query(OrdenComputadora).filter_by(consecutivo=r['consecutivo']).first():
                return 'skip'
            db2.add(OrdenComputadora(
                consecutivo=r['consecutivo'], taller_id=1,
                orden_servicio_id=r['orden_servicio_id'],
                modulo_nombre=r['modulo_nombre'] or '',
                marca=r['marca'] or '',
                modelo=r['modelo'] or '',
                serie=r['serie'] or '',
                diagnostico_lab=r['diagnostico_lab'] or '',
                trabajo_realizado=r['trabajo_realizado'] or '',
                estado=r['estado'] or 'RECIBIDO',
                costo_reparacion=safe_float(r['costo_reparacion']),
                fecha_ingreso=safe_dt(r['fecha_ingreso']),
                fecha_entrega=safe_dt(r['fecha_entrega']),
            ))
        migrate_table('ordenes_computadoras',
            lambda: sq.execute("SELECT * FROM ordenes_computadoras").fetchall(),
            ins_oc)
except Exception as e:
    print(f"      ordenes_computadoras (skip: tabla puede no existir): {e}")

# ─── Config Sistema ───
def ins_config(db2, r):
    if db2.query(ConfigSistema).filter_by(clave=r['clave'], taller_id=1).first():
        return 'skip'
    db2.add(ConfigSistema(taller_id=1, clave=r['clave'], valor=r['valor'] or ''))

migrate_table('config_sistema',
    lambda: sq.execute("SELECT * FROM config_sistema").fetchall(),
    ins_config)

# ─── Citas ───
def ins_cita(db2, r):
    existing = db2.query(Cita).filter_by(taller_id=1, fecha_cita=r['fecha_cita'], hora=r['hora'] or '', cliente_id=r['cliente_id']).first()
    if existing:
        return 'skip'
    db2.add(Cita(
        taller_id=1,
        cliente_id=r['cliente_id'],
        vehiculo_placa=r['vehiculo_placa'],
        fecha_cita=r['fecha_cita'] or '',
        hora=r['hora'] or '',
        motivo=r['motivo'] or '',
        estado=r['estado'] or 'programada',
        notas=r['notas'] or '',
        vista_admin=safe_int(r['vista_admin']) if 'vista_admin' in r.keys() else 0,
    ))

try:
    migrate_table('citas',
        lambda: sq.execute("SELECT * FROM citas").fetchall(),
        ins_cita)
except Exception as e:
    print(f"      citas (error): {e}")

# ─── Notas de Venta ───
def ins_nota(db2, r):
    if db2.query(NotaVenta).filter_by(numero=r['numero'], taller_id=1).first():
        return 'skip'
    db2.add(NotaVenta(
        taller_id=1,
        numero=r['numero'],
        fecha=safe_dt(r['fecha']),
        cliente_id=r['cliente_id'],
        cliente_nombre=r['cliente_nombre'] or '',
        subtotal=safe_float(r['subtotal']),
        igv=safe_float(r['igv']),
        total=safe_float(r['total']),
        estado=r['estado'] or 'pagada',
        notas=r['notas'] or '',
        metodo_pago=r['metodo_pago'] or '' if 'metodo_pago' in r.keys() else '',
        items=parse_json(r['items']) or [],
    ))

try:
    migrate_table('notas_venta',
        lambda: sq.execute("SELECT * FROM notas_venta").fetchall(),
        ins_nota)
except Exception as e:
    print(f"      notas_venta (error): {e}")

# ─── Cotizaciones ───
cot_id_map = {}  # old_id → new_id

def ins_cotizacion(db2, r):
    if db2.query(Cotizacion).filter_by(numero=r['numero'], taller_id=1).first():
        return 'skip'
    obj = Cotizacion(
        taller_id=1,
        numero=r['numero'],
        cliente_id=r['cliente_id'],
        nombre_cliente=r['nombre_cliente'] or '',
        estado=r['estado'] or 'PENDIENTE',
        total=safe_float(r['total']),
        nota=r['nota'] or '',
        creado_por=r['creado_por'] or '',
        fecha_creacion=safe_dt(r['fecha_creacion']),
    )
    db2.add(obj)
    db2.flush()
    cot_id_map[r['id']] = obj.id

try:
    migrate_table('cotizaciones',
        lambda: sq.execute("SELECT * FROM cotizaciones").fetchall(),
        ins_cotizacion)
except Exception as e:
    print(f"      cotizaciones (error): {e}")

# ─── Cotización Items ───
def ins_cot_item(db2, r):
    new_cot_id = cot_id_map.get(r['cotizacion_id'], r['cotizacion_id'])
    db2.add(CotizacionItem(
        cotizacion_id=new_cot_id,
        descripcion=r['descripcion'] or '',
        tipo=r['tipo'] or 'repuesto',
        cantidad=safe_int(r['cantidad'], 1),
        precio_unitario=safe_float(r['precio_unitario']),
        subtotal=safe_float(r['subtotal']),
    ))

try:
    migrate_table('cotizacion_items',
        lambda: sq.execute("SELECT * FROM cotizacion_items").fetchall(),
        ins_cot_item)
except Exception as e:
    print(f"      cotizacion_items (error): {e}")

# ─── Cierres de Caja ───
def ins_cierre(db2, r):
    if db2.query(CierreCaja).filter_by(taller_id=1, fecha=r['fecha']).first():
        return 'skip'
    db2.add(CierreCaja(
        taller_id=1,
        fecha=r['fecha'] or '',
        apertura_hora=r['apertura_hora'] or '',
        cierre_hora=r['cierre_hora'] or '',
        saldo_apertura=safe_float(r['saldo_apertura']),
        saldo_cierre=safe_float(r['saldo_cierre']),
        total_efectivo=safe_float(r['total_efectivo']),
        total_yape=safe_float(r['total_yape']),
        total_transferencia=safe_float(r['total_transferencia']),
        total_tarjeta=safe_float(r['total_tarjeta']),
        total_ordenes=safe_float(r['total_ordenes']),
        total_notas=safe_float(r['total_notas']),
        total_creditos=safe_float(r['total_creditos']) if 'total_creditos' in r.keys() else 0.0,
        total_mo=safe_float(r['total_mo']),
        total_repuestos=safe_float(r['total_repuestos']),
        ganancia_neta=safe_float(r['ganancia_neta']),
        num_ordenes=safe_int(r['num_ordenes']),
        num_notas=safe_int(r['num_notas']),
        notas_operador=r['notas_operador'] or '',
        estado=r['estado'] or 'abierta',
        usuario_apertura=r['usuario_apertura'] or '',
        usuario_cierre=r['usuario_cierre'] or '',
    ))

try:
    migrate_table('cierres_caja',
        lambda: sq.execute("SELECT * FROM cierres_caja").fetchall(),
        ins_cierre)
except Exception as e:
    print(f"      cierres_caja (error): {e}")

# ─── Actividades ───
def ins_actividad(db2, r):
    db2.add(Actividad(
        taller_id=1,
        fecha=safe_dt(r['fecha']),
        usuario_id=r['usuario_id'],
        accion=r['accion'] or '',
        modulo=r['modulo'] or '',
        detalle=r['detalle'] or '',
    ))

try:
    rows_act = sq.execute("SELECT * FROM actividades ORDER BY id LIMIT 500").fetchall()
    migrate_table('actividades',
        lambda: rows_act,
        ins_actividad)
except Exception as e:
    print(f"      actividades (error): {e}")

# ─── Agent Memoria ───
def ins_mem(db2, r):
    if db2.query(AgentMemoria).filter_by(telegram_user_id=r['telegram_user_id']).first():
        return 'skip'
    db2.add(AgentMemoria(
        telegram_user_id=r['telegram_user_id'],
        historial_json=r['historial_json'] or '[]',
        updated_at=safe_dt(r['updated_at']),
    ))

try:
    migrate_table('agent_memoria',
        lambda: sq.execute("SELECT * FROM agent_memoria").fetchall(),
        ins_mem)
except Exception as e:
    print(f"      agent_memoria (skip o vacío): {e}")

# ─── Agent Correcciones ───
def ins_corr(db2, r):
    db2.add(AgentCorreccion(
        mensaje_original=r['mensaje_original'] or '',
        respuesta_jarvis=r['respuesta_jarvis'] or '',
        correccion_usuario=r['correccion_usuario'] or '',
        keywords=r['keywords'] or '',
        fecha=safe_dt(r['fecha']),
    ))

try:
    migrate_table('agent_correcciones',
        lambda: sq.execute("SELECT * FROM agent_correcciones").fetchall(),
        ins_corr)
except Exception as e:
    print(f"      agent_correcciones (skip o vacío): {e}")


# ── 5. Verificación de conteos ────────────────────────────────────────────────
print("\n[5/5] Verificando integridad de datos...")

tablas_verificar = [
    ('clientes',   'clientes',   Cliente),
    ('vehiculos',  'vehiculos',  Vehiculo),
    ('inventario', 'inventario', ItemInventario),
    ('proveedores','proveedores',Proveedor),
    ('ordenes',    'ordenes',    Orden),
]

db_v = get_db()
all_ok = True
try:
    for sq_table, label, ModelClass in tablas_verificar:
        try:
            sq_count = sq.execute(f"SELECT COUNT(*) FROM {sq_table}").fetchone()[0]
            pg_count = db_v.query(ModelClass).count()
            status = "✓" if pg_count >= sq_count else "✗ DIFERENCIA"
            print(f"      {label:20s}: SQLite={sq_count:4d}  PG={pg_count:4d}  {status}")
            if pg_count < sq_count:
                all_ok = False
        except Exception as e:
            print(f"      {label}: ERROR verificando — {e}")
finally:
    db_v.close()

sq.close()

print("\n" + "=" * 60)
if errors:
    print(f"  ADVERTENCIAS ({len(errors)} errores parciales):")
    for err in errors[:10]:
        print(f"    - {err}")
    if len(errors) > 10:
        print(f"    ... y {len(errors)-10} más")

if all_ok:
    print("\n  ✓ MIGRACIÓN EXITOSA")
    print(f"  Base de datos PostgreSQL lista en: sandoval_saas")
    print(f"  SQLite backup en: {SQLITE_PATH} (NO eliminar aún)")
    print(f"\n  SIGUIENTE PASO:")
    print(f"  1. Editar /var/www/sandoval/.env y agregar:")
    print(f"     DATABASE_URL=postgresql://sandoval_user:SandovalSaaS2026!@localhost:5432/sandoval_saas")
    print(f"  2. Reiniciar: systemctl restart sandoval")
else:
    print("\n  ✗ MIGRACIÓN CON DIFERENCIAS — revisar errores antes de continuar")
print("=" * 60)
