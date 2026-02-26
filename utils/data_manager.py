"""
SANDOVAL Dashboard - Data Manager v2
Capa de datos con SQLite (SQLAlchemy) - reemplaza al JSON puro
Mantiene compatibilidad con la API anterior para que los componentes existentes funcionen
"""

import json
import os
from datetime import datetime
from utils.models import (
    get_db, Cliente, Vehiculo, Proveedor, ItemInventario, Orden,
    Actividad, ConfigSistema, Cita, log_actividad
)

# Mapeo colección → modelo
_MODEL_MAP = {
    'clientes': (Cliente, 'id'),
    'vehiculos': (Vehiculo, 'placa'),
    'proveedores': (Proveedor, 'id'),
    'inventario': (ItemInventario, 'codigo'),
    'ordenes': (Orden, 'consecutivo'),
}


def _to_dict(obj):
    """Convierte un objeto SQLAlchemy a dict"""
    if obj is None:
        return None
    d = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name, None)
        if isinstance(val, datetime):
            val = val.strftime('%Y-%m-%d %H:%M')
        d[col.name] = val
    return d


def load(collection: str) -> list:
    """Carga todos los registros de una colección"""
    if collection not in _MODEL_MAP:
        return []
    model, _ = _MODEL_MAP[collection]
    db = get_db()
    try:
        items = db.query(model).all()
        return [_to_dict(item) for item in items]
    finally:
        db.close()


def save(collection: str, data: list):
    """Reemplaza todos los registros (para compatibilidad, preferir add/update/delete)"""
    if collection not in _MODEL_MAP:
        return
    model, pk = _MODEL_MAP[collection]
    db = get_db()
    try:
        db.query(model).delete()
        for item in data:
            kwargs = {col.name: item.get(col.name) for col in model.__table__.columns if col.name in item}
            db.add(model(**kwargs))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def find_by_id(collection: str, record_id: str, id_field: str = None) -> dict | None:
    """Busca un registro por ID"""
    if collection not in _MODEL_MAP:
        return None
    model, default_pk = _MODEL_MAP[collection]
    field = id_field or default_pk
    db = get_db()
    try:
        item = db.query(model).filter(getattr(model, field) == str(record_id)).first()
        return _to_dict(item)
    finally:
        db.close()


def add(collection: str, record: dict) -> dict:
    """Agrega un registro"""
    if collection not in _MODEL_MAP:
        return record
    model, _ = _MODEL_MAP[collection]
    db = get_db()
    try:
        kwargs = {}
        for col in model.__table__.columns:
            if col.name in record:
                kwargs[col.name] = record[col.name]
        obj = model(**kwargs)
        db.add(obj)
        db.commit()
        log_actividad(f'Creado en {collection}', collection)
        return record
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def update(collection: str, record_id: str, updates: dict, id_field: str = None) -> bool:
    """Actualiza un registro"""
    if collection not in _MODEL_MAP:
        return False
    model, default_pk = _MODEL_MAP[collection]
    field = id_field or default_pk
    db = get_db()
    try:
        obj = db.query(model).filter(getattr(model, field) == str(record_id)).first()
        if not obj:
            return False
        for key, val in updates.items():
            if hasattr(obj, key):
                setattr(obj, key, val)
        db.commit()
        log_actividad(f'Actualizado en {collection}: {record_id}', collection)
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def delete(collection: str, record_id: str, id_field: str = None) -> bool:
    """Elimina un registro"""
    if collection not in _MODEL_MAP:
        return False
    model, default_pk = _MODEL_MAP[collection]
    field = id_field or default_pk
    db = get_db()
    try:
        obj = db.query(model).filter(getattr(model, field) == str(record_id)).first()
        if not obj:
            return False
        db.delete(obj)
        db.commit()
        log_actividad(f'Eliminado de {collection}: {record_id}', collection)
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def next_id(collection: str, prefix: str = '', id_field: str = None) -> str:
    """Genera el siguiente ID secuencial"""
    items = load(collection)
    if not items:
        return f'{prefix}0001'
    
    _, default_pk = _MODEL_MAP.get(collection, (None, 'id'))
    field = id_field or default_pk
    
    max_num = 0
    for item in items:
        item_id = str(item.get(field, ''))
        num_part = item_id.replace(prefix, '').replace('-', '').replace('#', '')
        try:
            num = int(num_part)
            max_num = max(max_num, num)
        except ValueError:
            continue
    return f'{prefix}{str(max_num + 1).zfill(4)}'


def search(collection: str, query: str, fields: list = None) -> list:
    """Búsqueda por texto"""
    if not query:
        return load(collection)
    query = query.lower().strip()
    return [item for item in load(collection)
            if any(query in str(item.get(f, '')).lower() for f in (fields or item.keys()))]
