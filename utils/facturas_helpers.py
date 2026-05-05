"""
SANDOVAL — Helpers puros de facturas (sin NiceGUI).

Extraídos de components/facturas.py para que utils/telegram_bot.py pueda
usarlos sin necesidad del runtime NiceGUI.

Funciones expuestas:
  - _check_duplicate_factura(proveedor, numero_factura, total=None, fecha=None) -> bool
  - _save_factura(data: dict) -> int
  - _agregar_items_a_inventario(items: list)
  - _save_proveedor(nombre, tipo, ruc='') -> None  (interna, llamada por _save_factura)
"""
from __future__ import annotations

import hashlib
import json
import traceback
from datetime import datetime

from sqlalchemy import text

from utils.models import get_db, ItemInventario

# Multi-tenant: el portal admin del taller propietario opera siempre con
# TALLER_ID=1 hasta que se complete el refactor a tok["taller_id"] (Fase 2 BRD).
TALLER_ID = 1


def _ensure_rls_context():
    """En contextos sin HTTP middleware (telegram bot, scripts), el
    ContextVar de RLS no está seteado. Las INSERT/SELECT con `TALLER_ID=1`
    fallarían con RLS STRICT. Forzamos el setting para este request.
    """
    try:
        from utils.rls_session import set_current_taller_id
        set_current_taller_id(TALLER_ID)
    except Exception:
        pass


def _save_proveedor(nombre, tipo: str, ruc: str = '') -> None:
    """Inserta o actualiza el proveedor en la tabla `proveedores`.

    Llamada internamente desde `_save_factura`. Silenciosa ante errores
    (no debe romper el guardado de la factura).
    """
    nombre_str = str(nombre).strip() if nombre else ''
    if not nombre_str or nombre_str.lower() in (
        'desconocido', 's/n', 'none', 'null', ''
    ):
        return

    from utils.models import Proveedor as _Proveedor

    db = get_db()
    try:
        nombre_clean = nombre_str.upper()
        ruc_clean = str(ruc).strip() if ruc else ''
        tipo_label = (
            "📦 MERCADERÍA / REPUESTOS" if (tipo or '').lower() == 'mercaderia'
            else "💸 GASTOS OPERACIONALES"
        )

        p = None
        if ruc_clean and len(ruc_clean) >= 8:
            p = db.query(_Proveedor).filter_by(id=ruc_clean).first()
        if not p:
            p = db.query(_Proveedor).filter(_Proveedor.nombre == nombre_clean).first()

        if not p:
            fake_ruc = ruc_clean if (ruc_clean and len(ruc_clean) >= 8) else (
                "PROV-" + hashlib.md5(nombre_clean.encode()).hexdigest()[:6].upper()
            )
            p = _Proveedor(
                id=fake_ruc, nombre=nombre_clean,
                productos=tipo_label, tipo='Empresa',
            )
            db.add(p)
        else:
            prods = p.productos or ''
            if 'GASTOS' not in prods and 'MERCADERÍA' not in prods:
                p.productos = tipo_label
            elif tipo_label not in prods:
                p.productos = f"{prods} - {tipo_label}"

        db.commit()
    except Exception as e:
        print(f"ERROR _save_proveedor: {e}")
        traceback.print_exc()
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        try:
            db.close()
        except Exception:
            pass


def _check_duplicate_factura(
    proveedor: str,
    numero_factura: str,
    total: float = None,
    fecha: str = None,
) -> bool:
    """Detecta duplicados:
    - Si hay número de factura: busca por número exacto (más confiable).
    - Si NO hay número: busca por proveedor + total + fecha (fallback).
    """
    _ensure_rls_context()
    num = str(numero_factura or '').strip()
    num_valido = bool(num) and num.upper() not in (
        'S/N', 'SIN NUMERO', 'NONE', 'NULL', '',
    )

    db = get_db()
    try:
        if num_valido:
            row = db.execute(text("""
                SELECT id FROM facturas
                WHERE taller_id=:t
                  AND LOWER(REPLACE(numero_factura, ' ', '')) = LOWER(REPLACE(:num, ' ', ''))
                LIMIT 1
            """), {'t': TALLER_ID, 'num': num}).fetchone()
        else:
            if not proveedor or total is None:
                return False
            row = db.execute(text("""
                SELECT id FROM facturas
                WHERE taller_id=:t
                  AND LOWER(proveedor) LIKE :prov
                  AND ABS(total - :total) < 0.01
                  AND fecha = :fecha
                LIMIT 1
            """), {
                't':     TALLER_ID,
                'prov':  f"%{str(proveedor).strip().lower()[:20]}%",
                'total': float(total),
                'fecha': str(fecha or '').strip(),
            }).fetchone()
        return bool(row)
    except Exception:
        return False
    finally:
        db.close()


def _save_factura(data: dict) -> int:
    """Inserta una factura nueva en la tabla `facturas` y devuelve su id.
    También intenta guardar el proveedor en su propia tabla.
    """
    _ensure_rls_context()
    db = get_db()
    try:
        result = db.execute(text("""
            INSERT INTO facturas (taller_id, tipo, subtipo_gasto, proveedor,
                ruc_proveedor, numero_factura, fecha,
                subtotal, igv, total, imagen_path, items_json, estado, notas,
                fecha_registro, agregado_inventario)
            VALUES (:taller_id, :tipo, :subtipo_gasto, :proveedor,
                :ruc_proveedor, :numero_factura, :fecha,
                :subtotal, :igv, :total, :imagen_path, :items_json, :estado, :notas,
                :fecha_registro, :agregado_inventario)
            RETURNING id
        """), {
            'taller_id':           TALLER_ID,
            'tipo':                data.get('tipo', 'mercaderia'),
            'subtipo_gasto':       data.get('subtipo_gasto', ''),
            'proveedor':           data.get('proveedor', ''),
            'ruc_proveedor':       data.get('ruc_proveedor', ''),
            'numero_factura':      data.get('numero_factura', ''),
            'fecha':               data.get('fecha', datetime.now().strftime('%Y-%m-%d')),
            'subtotal':            float(data.get('subtotal', 0) or 0),
            'igv':                 float(data.get('igv', 0) or 0),
            'total':               float(data.get('total', 0) or 0),
            'imagen_path':         data.get('imagen_path', ''),
            'items_json':          json.dumps(data.get('items', []), ensure_ascii=False),
            'estado':              data.get('estado', 'procesada'),
            'notas':               data.get('notas', ''),
            'fecha_registro':      datetime.now().isoformat(),
            'agregado_inventario': 0,
        })
        row = result.fetchone()
        factura_id = row[0] if row else 0
        db.commit()

        try:
            _save_proveedor(
                data.get('proveedor', ''),
                data.get('tipo', 'mercaderia'),
                data.get('ruc_proveedor', ''),
            )
        except Exception:
            pass

        return factura_id
    finally:
        db.close()


def _agregar_items_a_inventario(items: list) -> None:
    """Suma stock o crea ítems nuevos en `inventario` desde una lista de
    items de factura. Las claves esperadas por ítem: nombre, cantidad,
    precio_unitario.
    """
    _ensure_rls_context()
    import random
    import string

    db = get_db()
    try:
        for item in items:
            nombre = (item.get('nombre') or '').strip()
            if not nombre:
                continue
            cantidad = int(item.get('cantidad', 1) or 1)
            costo = float(item.get('precio_unitario', 0) or 0)
            existente = db.query(ItemInventario).filter(
                ItemInventario.taller_id == TALLER_ID,
                ItemInventario.nombre.ilike(f"%{nombre[:20]}%"),
            ).first()
            if existente:
                existente.stock += cantidad
                if costo > 0:
                    existente.costo = costo
            else:
                codigo = 'AUTO-' + ''.join(
                    random.choices(string.ascii_uppercase + string.digits, k=6)
                )
                db.add(ItemInventario(
                    codigo=codigo, nombre=nombre,
                    categoria='Repuesto', tipo='Repuesto',
                    costo=costo, precio=round(costo * 1.3, 2),
                    stock=cantidad, stock_minimo=2,
                    taller_id=TALLER_ID,
                ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
