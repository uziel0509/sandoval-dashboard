"""
utils/api_mobile_admin.py — Endpoints admin para la PWA móvil (/api/*).

Replica la lógica de los routers admin (`routers/caja.py`, `facturas.py`,
`proveedores.py`, `cotizaciones.py`, `creditos.py`, `finanzas.py`, `equipo.py`)
exponiéndola bajo el prefijo `/api/` con el mecanismo de autenticación de la
PWA (SQLite session tokens en `utils.api_service`).

Por qué un módulo separado:
  - El portal PC consume los routers admin bajo `/admin/api/*` con JWT.
  - La PWA móvil consume `/api/*` con token de sesión SQLite (contrato fijo
    por retrocompatibilidad con la app instalada).
  - Este módulo traduce "sesión móvil" → taller_id y delega a SQL directo
    para no modificar los routers admin (intencionalmente intactos).

Multi-tenant: cada query filtra por taller_id sacado del usuario autenticado
(fallback a `SELECT taller_id FROM usuarios WHERE id=:uid` si el user_dict
legado no lo trae).
"""

import json
import re
from datetime import date as _date, datetime, timedelta
from typing import Optional

from sqlalchemy import text
from starlette.requests import Request
from starlette.responses import JSONResponse

from utils.api_service import (
    _require_auth,
    _require_admin,
    json_ok,
    json_err,
)
from utils.models import get_db


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _tenant_id(user: dict, db) -> Optional[int]:
    """Taller del usuario. Fallback a DB si el user_dict no lo trae."""
    tid = user.get('taller_id')
    if tid:
        try:
            return int(tid)
        except (TypeError, ValueError):
            pass
    uid = user.get('id')
    if not uid:
        return None
    row = db.execute(
        text("SELECT taller_id FROM usuarios WHERE id=:i"), {"i": uid}
    ).fetchone()
    return int(row[0]) if row and row[0] else None


def _safe_date(raw):
    if not raw:
        return None
    s = str(raw).strip()[:10]
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        return None


def _parse_json(raw):
    if raw is None:
        return []
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw) or []
    except Exception:
        return []


def _img_to_url(p):
    if not p:
        return None
    if str(p).startswith(('http://', 'https://', '/')):
        return p
    return f"/{p}"


def _auth_tenant(request: Request, admin: bool = False):
    """Retorna (user, tenant_id, db) o JSONResponse si auth falla."""
    result = _require_admin(request) if admin else _require_auth(request)
    if isinstance(result, JSONResponse):
        return result
    db = get_db()
    tid = _tenant_id(result, db)
    if not tid:
        db.close()
        return json_err("Sesión sin taller asociado", 403)
    return result, tid, db


# ═════════════════════════════════════════════════════════════════════════════
# CAJA
# ═════════════════════════════════════════════════════════════════════════════

async def api_caja_get(request: Request) -> JSONResponse:
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse):
        return auth
    _user, taller_id, db = auth
    try:
        hoy = _date.today().strftime("%Y-%m-%d")
        caja = db.execute(text(
            "SELECT id, fecha, apertura_hora, saldo_apertura, estado, "
            "usuario_apertura, notas_operador "
            "FROM cierres_caja WHERE taller_id=:t AND fecha=:f "
            "ORDER BY id DESC LIMIT 1"
        ), {"t": taller_id, "f": hoy}).fetchone()
        if not caja:
            return json_ok({"estado": "sin_apertura", "fecha": hoy})
        # 2026-05-05 P0 SYNC FIX (sync-guardian audit): usar pagos[] JSON
        # con fecha real del abono (igual que routers/caja.py admin SPA).
        # Antes: filtraba `estado='ARCHIVADO' AND fecha_dt::date=CURRENT_DATE`
        # → órdenes creadas ayer y cobradas hoy NO se contaban + perdía abonos
        # parciales de órdenes en otras fases. Resultado: caja PC ≠ caja PWA.
        # Ahora: lee `pagos[].fecha` (fecha del abono) + fallback legacy.
        tot = db.execute(text("""
            WITH pagos_jsonb AS (
              SELECT
                (p->>'fecha')::date AS dia,
                (p->>'monto')::numeric AS monto,
                COALESCE(NULLIF(p->>'metodo',''), 'Efectivo') AS metodo
              FROM ordenes o
              CROSS JOIN LATERAL json_array_elements(COALESCE(o.pagos, '[]'::json)) AS p
              WHERE o.taller_id = :t
                AND COALESCE(json_array_length(o.pagos), 0) > 0
            ),
            pagos_legacy AS (
              SELECT o.fecha_dt::date AS dia,
                     COALESCE(o.monto_cobrado, 0)::numeric AS monto,
                     COALESCE(o.metodo_pago, 'Efectivo') AS metodo
              FROM ordenes o
              WHERE o.taller_id = :t
                AND COALESCE(o.monto_cobrado, 0) > 0
                AND (o.pagos IS NULL OR COALESCE(json_array_length(o.pagos), 0) = 0)
            ),
            pagos_unif AS (SELECT * FROM pagos_jsonb UNION ALL SELECT * FROM pagos_legacy)
            SELECT
              COALESCE(SUM(monto) FILTER (WHERE metodo='Efectivo'), 0),
              COALESCE(SUM(monto) FILTER (WHERE metodo IN ('Yape','Plin')), 0),
              COALESCE(SUM(monto) FILTER (WHERE metodo='Transferencia'), 0),
              COALESCE(SUM(monto) FILTER (WHERE metodo='Tarjeta'), 0),
              COUNT(DISTINCT monto)
            FROM pagos_unif
            WHERE dia = CURRENT_DATE
        """), {"t": taller_id}).fetchone()
        nv_m = db.execute(text("""
            SELECT
              COALESCE(SUM(COALESCE(NULLIF(monto_pagado, 0), total)) FILTER (WHERE metodo_pago='Efectivo'), 0),
              COALESCE(SUM(COALESCE(NULLIF(monto_pagado, 0), total)) FILTER (WHERE metodo_pago IN ('Yape','Plin')), 0),
              COALESCE(SUM(COALESCE(NULLIF(monto_pagado, 0), total)) FILTER (WHERE metodo_pago='Transferencia'), 0),
              COALESCE(SUM(COALESCE(NULLIF(monto_pagado, 0), total)) FILTER (WHERE metodo_pago='Tarjeta'), 0),
              COALESCE(SUM(total), 0)
            FROM notas_venta WHERE taller_id=:t AND fecha::date=CURRENT_DATE
        """), {"t": taller_id}).fetchone()
        ab_m = db.execute(text("""
            SELECT
              COALESCE(SUM(monto) FILTER (WHERE metodo_pago='Efectivo'), 0),
              COALESCE(SUM(monto) FILTER (WHERE metodo_pago IN ('Yape','Plin')), 0),
              COALESCE(SUM(monto) FILTER (WHERE metodo_pago='Transferencia'), 0),
              COALESCE(SUM(monto) FILTER (WHERE metodo_pago='Tarjeta'), 0)
            FROM abonos_credito WHERE taller_id=:t AND fecha_dt::date=CURRENT_DATE
        """), {"t": taller_id}).fetchone()
        ef = round(float(tot[0]) + float(nv_m[0]) + float(ab_m[0]), 2)
        yp = round(float(tot[1]) + float(nv_m[1]) + float(ab_m[1]), 2)
        tr = round(float(tot[2]) + float(nv_m[2]) + float(ab_m[2]), 2)
        ta = round(float(tot[3]) + float(nv_m[3]) + float(ab_m[3]), 2)
        nv = round(float(nv_m[4]), 2)
        total_dia = ef + yp + tr + ta
        return json_ok({
            "id": caja[0], "fecha": str(caja[1]) if caja[1] else None,
            "apertura_hora": caja[2], "saldo_apertura": float(caja[3] or 0),
            "estado": caja[4], "usuario_apertura": caja[5], "notas": caja[6],
            "totales": {
                "efectivo": ef, "yape": yp, "transferencia": tr, "tarjeta": ta,
                "notas_venta": nv, "total": round(total_dia, 2),
                "n_ordenes": int(tot[4] or 0),
            }
        })
    finally:
        db.close()


async def api_caja_abrir(request: Request) -> JSONResponse:
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse):
        return auth
    user, taller_id, db = auth
    try:
        body = await request.json()
        hoy = _date.today().strftime("%Y-%m-%d")
        exists = db.execute(text(
            "SELECT id FROM cierres_caja WHERE taller_id=:t AND fecha=:f"
        ), {"t": taller_id, "f": hoy}).fetchone()
        if exists:
            return json_err("Ya existe una caja abierta para hoy", 409)
        db.execute(text("""
            INSERT INTO cierres_caja (taller_id, fecha, apertura_hora, saldo_apertura,
                estado, usuario_apertura, notas_operador)
            VALUES (:t, :f, :h, :sa, 'abierto', :u, :n)
        """), {
            "t": taller_id, "f": hoy,
            "h": datetime.now().strftime("%H:%M"),
            "sa": float(body.get("saldo_apertura", 0) or 0),
            "u": user.get("nombre", ""),
            "n": body.get("notas", ""),
        })
        db.commit()
        return json_ok({"ok": True})
    finally:
        db.close()


async def api_caja_cerrar(request: Request) -> JSONResponse:
    auth = _auth_tenant(request, admin=True)
    if isinstance(auth, JSONResponse):
        return auth
    user, taller_id, db = auth
    try:
        body = await request.json()
        cid = request.path_params.get("cid")
        hoy = _date.today().strftime("%Y-%m-%d")
        if cid:
            caja = db.execute(text(
                "SELECT id FROM cierres_caja WHERE id=:id AND taller_id=:t"
            ), {"id": int(cid), "t": taller_id}).fetchone()
        else:
            caja = db.execute(text(
                "SELECT id FROM cierres_caja "
                "WHERE taller_id=:t AND fecha=:f AND estado='abierto'"
            ), {"t": taller_id, "f": hoy}).fetchone()
        if not caja:
            return json_err("No hay caja abierta para cerrar", 404)
        db.execute(text("""
            UPDATE cierres_caja SET estado='CERRADA', cierre_hora=:h,
                saldo_cierre=:sc, notas_operador=:n, usuario_cierre=:u
            WHERE id=:id AND taller_id=:t
        """), {
            "h": datetime.now().strftime("%H:%M"),
            "sc": float(body.get("saldo_cierre", 0) or 0),
            "n": body.get("notas", ""),
            "u": user.get("nombre", ""),
            "id": caja[0], "t": taller_id,
        })
        db.commit()
        return json_ok({"ok": True})
    finally:
        db.close()


# ═════════════════════════════════════════════════════════════════════════════
# PROVEEDORES
# ═════════════════════════════════════════════════════════════════════════════

_RUC_VALID = re.compile(r"^[A-Z0-9\-]{3,20}$")


def _pick_ruc(body: dict) -> str:
    raw = (body.get("ruc") or "").strip().upper()
    if not raw:
        return ""
    raw = re.sub(r"\s+", "", raw)
    if raw.startswith("CLI-") or raw in ("N/A", "NA", "---", "SIN RUC", "SINRUC"):
        return ""
    if not _RUC_VALID.match(raw):
        return ""
    return raw[:20]


def _canon_nombre(existing: str, incoming: str) -> str:
    e = (existing or "").strip()
    i = (incoming or "").strip()
    if not e:
        return i
    if not i:
        return e
    return i if len(i) > len(e) else e


def _merge_alias(current, *cands):
    seen, out = set(), []
    for v in list(current or []) + list(cands):
        v = (v or "").strip()
        if not v:
            continue
        k = v.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(v)
        if len(out) >= 10:
            break
    return out


async def api_proveedores_list(request: Request) -> JSONResponse:
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse):
        return auth
    _user, taller_id, db = auth
    try:
        rows = db.execute(text(
            "SELECT id, nombre, email, telefono, direccion, ciudad, tipo, ruc, alias "
            "FROM proveedores WHERE taller_id=:t ORDER BY nombre"
        ), {"t": taller_id}).fetchall()
        return json_ok([{
            "id": r[0], "nombre": r[1], "email": r[2] or "", "telefono": r[3] or "",
            "direccion": r[4] or "", "ciudad": r[5] or "", "tipo": r[6] or "",
            "ruc": r[7] or "", "alias": list(r[8] or []),
        } for r in rows])
    finally:
        db.close()


async def api_proveedor_create(request: Request) -> JSONResponse:
    """POST /api/proveedores — upsert por (taller_id, ruc) o nombre exacto."""
    auth = _auth_tenant(request, admin=True)
    if isinstance(auth, JSONResponse):
        return auth
    _user, taller_id, db = auth
    try:
        body = await request.json()
        nombre_in = (body.get("nombre") or "").strip()
        if not nombre_in:
            return json_err("Nombre requerido", 400)
        ruc = _pick_ruc(body)
        extra_alias = body.get("alias") or []
        if isinstance(extra_alias, str):
            extra_alias = [extra_alias]

        existing = None
        if ruc:
            existing = db.execute(text(
                "SELECT id, nombre, email, telefono, direccion, ciudad, tipo, ruc, alias "
                "FROM proveedores WHERE taller_id=:t AND ruc=:ruc"
            ), {"t": taller_id, "ruc": ruc}).fetchone()
        if existing is None:
            existing = db.execute(text(
                "SELECT id, nombre, email, telefono, direccion, ciudad, tipo, ruc, alias "
                "FROM proveedores WHERE taller_id=:t AND LOWER(TRIM(nombre))=LOWER(TRIM(:n)) "
                "LIMIT 1"
            ), {"t": taller_id, "n": nombre_in}).fetchone()

        if existing is not None:
            pid = existing[0]
            cur_nombre = existing[1]
            cur_ruc = existing[7] or ""
            cur_alias = list(existing[8] or [])
            new_nombre = _canon_nombre(cur_nombre, nombre_in)
            new_alias = _merge_alias(cur_alias, cur_nombre, nombre_in, *extra_alias)
            new_ruc = ruc or cur_ruc
            sets = ["nombre=:n", "alias=:al", "ruc=:ruc"]
            params = {"id": pid, "t": taller_id,
                      "n": new_nombre, "al": new_alias, "ruc": new_ruc}
            for key in ("email", "telefono", "direccion", "ciudad", "tipo", "productos"):
                v = body.get(key)
                if v:
                    sets.append(f"{key}=:{key}")
                    params[key] = v
            db.execute(
                text(f"UPDATE proveedores SET {', '.join(sets)} "
                     f"WHERE id=:id AND taller_id=:t"),
                params,
            )
            db.commit()
            return json_ok({"ok": True, "merged": True, "id": pid,
                            "nombre": new_nombre, "ruc": new_ruc, "alias": new_alias})

        initial_alias = _merge_alias([], *extra_alias)
        row = db.execute(text("""
            INSERT INTO proveedores (taller_id, nombre, email, telefono, direccion,
                                     ciudad, tipo, productos, ruc, alias)
            VALUES (:t, :n, :e, :tel, :dir, :ciu, :tipo, :prod, :ruc, :al)
            RETURNING id
        """), {
            "t": taller_id, "n": nombre_in,
            "e": body.get("email", ""), "tel": body.get("telefono", ""),
            "dir": body.get("direccion", ""), "ciu": body.get("ciudad", ""),
            "tipo": body.get("tipo", ""), "prod": body.get("productos", ""),
            "ruc": ruc, "al": initial_alias,
        }).fetchone()
        db.commit()
        return json_ok({"ok": True, "merged": False, "id": row[0],
                        "nombre": nombre_in, "ruc": ruc, "alias": initial_alias})
    finally:
        db.close()


# ═════════════════════════════════════════════════════════════════════════════
# FACTURAS
# ═════════════════════════════════════════════════════════════════════════════

async def api_facturas_list(request: Request) -> JSONResponse:
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse):
        return auth
    _user, taller_id, db = auth
    try:
        tipo = request.query_params.get("tipo")
        try:
            limit = max(1, min(500, int(request.query_params.get("limit", 100))))
        except (TypeError, ValueError):
            limit = 100
        sql = ("SELECT id, tipo, proveedor, ruc_proveedor, numero_factura, fecha, "
               "subtotal, igv, total, estado, notas, items_json, imagen_path, "
               "subtipo_gasto, agregado_inventario, COALESCE(moneda,'PEN') "
               "FROM facturas WHERE taller_id=:t")
        params = {"t": taller_id, "lim": limit}
        if tipo:
            sql += " AND tipo=:tipo"
            params["tipo"] = tipo
        sql += " ORDER BY id DESC LIMIT :lim"
        rows = db.execute(text(sql), params).fetchall()
        return json_ok([{
            "id": r[0], "tipo": r[1], "proveedor": r[2], "ruc_proveedor": r[3],
            "numero_factura": r[4], "fecha": r[5],
            "subtotal": float(r[6] or 0), "igv": float(r[7] or 0),
            "total": float(r[8] or 0), "estado": r[9], "notas": r[10],
            "items_json": r[11], "imagen_path": _img_to_url(r[12]),
            "subtipo_gasto": r[13], "agregado_inventario": r[14],
            "moneda": r[15],
        } for r in rows])
    finally:
        db.close()


async def api_factura_create(request: Request) -> JSONResponse:
    auth = _auth_tenant(request, admin=True)
    if isinstance(auth, JSONResponse):
        return auth
    _user, taller_id, db = auth
    try:
        body = await request.json()
        new_id = db.execute(text("""
            INSERT INTO facturas (taller_id, tipo, subtipo_gasto, proveedor, ruc_proveedor,
                numero_factura, fecha, subtotal, igv, total, estado, notas,
                items_json, moneda, fecha_registro)
            VALUES (:t, :tipo, :st, :prov, :ruc, :num, :fecha, :sub, :igv, :tot, 'PENDIENTE',
                    :notas, :items, :moneda, NOW())
            RETURNING id
        """), {
            "t": taller_id,
            "tipo": body.get("tipo", "gasto"),
            "st": body.get("subtipo_gasto", ""),
            "prov": body.get("proveedor", ""),
            "ruc": body.get("ruc_proveedor", ""),
            "num": body.get("numero_factura", ""),
            "fecha": body.get("fecha", datetime.now().strftime("%Y-%m-%d")),
            "sub": float(body.get("subtotal", 0) or 0),
            "igv": float(body.get("igv", 0) or 0),
            "tot": float(body.get("total", 0) or 0),
            "notas": body.get("notas", ""),
            "items": json.dumps(body.get("items", [])),
            "moneda": body.get("moneda", "PEN"),
        }).scalar()
        db.commit()
        return json_ok({"ok": True, "id": int(new_id)})
    finally:
        db.close()


# ═════════════════════════════════════════════════════════════════════════════
# COTIZACIONES
# ═════════════════════════════════════════════════════════════════════════════

async def api_cotizaciones_list(request: Request) -> JSONResponse:
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse):
        return auth
    _user, taller_id, db = auth
    try:
        try:
            limit = max(1, min(500, int(request.query_params.get("limit", 200))))
        except (TypeError, ValueError):
            limit = 200
        q = request.query_params.get("q")
        estado = request.query_params.get("estado")
        sql = ("SELECT c.id, c.numero, c.fecha_creacion AS fecha, c.cliente_id, "
               "c.nombre_cliente, c.estado, c.total, cl.nombre, cl.apellidos "
               "FROM cotizaciones c "
               "LEFT JOIN clientes cl ON cl.id=c.cliente_id "
               "WHERE c.taller_id=:t")
        params = {"t": taller_id}
        if estado:
            sql += " AND c.estado=:est"
            params["est"] = estado
        if q:
            sql += " AND (c.numero ILIKE :q OR c.nombre_cliente ILIKE :q OR cl.nombre ILIKE :q)"
            params["q"] = f"%{q}%"
        sql += " ORDER BY c.id DESC LIMIT :lim"
        params["lim"] = limit
        rows = db.execute(text(sql), params).fetchall()
        return json_ok([{
            "id": r[0], "numero": r[1],
            "fecha": str(r[2])[:19] if r[2] else None,
            "cliente_id": r[3],
            "nombre_cliente": r[4] or f"{r[7] or ''} {r[8] or ''}".strip(),
            "estado": r[5], "total": float(r[6] or 0),
        } for r in rows])
    finally:
        db.close()


# ═════════════════════════════════════════════════════════════════════════════
# CRÉDITOS
# ═════════════════════════════════════════════════════════════════════════════

async def api_creditos_list(request: Request) -> JSONResponse:
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse):
        return auth
    _user, taller_id, db = auth
    try:
        try:
            limit = max(1, min(500, int(request.query_params.get("limit", 200))))
        except (TypeError, ValueError):
            limit = 200
        rows = db.execute(text("""
            SELECT id, cliente_nombre, telefono, descripcion, total, pendiente, estado,
                   nota, fecha_venta, fecha_amortizacion, items_json
            FROM creditos WHERE taller_id=:tid
            ORDER BY id DESC LIMIT :lim
        """), {"tid": taller_id, "lim": limit}).fetchall()
        return json_ok([{
            "id": r[0], "cliente": r[1], "telefono": r[2] or "",
            "descripcion": r[3] or "", "total": float(r[4] or 0),
            "pendiente": float(r[5] or 0), "estado": r[6] or "",
            "nota": r[7] or "",
            "fecha_venta": str(r[8]) if r[8] else None,
            "fecha_amortizacion": str(r[9]) if r[9] else None,
            "items": _parse_json(r[10]),
        } for r in rows])
    finally:
        db.close()


async def api_credito_abono(request: Request) -> JSONResponse:
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse):
        return auth
    _user, taller_id, db = auth
    try:
        cid = int(request.path_params.get("cid", 0))
        body = await request.json()
        try:
            monto = float(body.get("monto", 0) or 0)
        except (TypeError, ValueError):
            return json_err("Monto inválido", 400)
        if monto <= 0:
            return json_err("Monto inválido", 400)
        fecha = _safe_date(body.get("fecha")) or datetime.now().strftime("%Y-%m-%d")
        credito = db.execute(text(
            "SELECT pendiente FROM creditos WHERE id=:id AND taller_id=:tid FOR UPDATE"
        ), {"id": cid, "tid": taller_id}).fetchone()
        if not credito:
            return json_err("Crédito no encontrado", 404)
        nuevo_pend = max(0.0, float(credito[0] or 0) - monto)
        nuevo_estado = "PAGADO" if nuevo_pend == 0 else "PARCIAL"
        db.execute(text(
            "UPDATE creditos SET pendiente=:p, estado=:e "
            "WHERE id=:id AND taller_id=:tid"
        ), {"p": nuevo_pend, "e": nuevo_estado, "id": cid, "tid": taller_id})
        db.execute(text("""
            INSERT INTO abonos_credito (taller_id, credito_id, monto, nota, metodo_pago, fecha, fecha_dt)
            VALUES (:tid, :c, :m, :n, :mp, :f, CAST(:f AS date))
        """), {
            "tid": taller_id, "c": cid, "m": monto,
            "n": body.get("nota", ""),
            "mp": body.get("metodo_pago", "Efectivo"),
            "f": fecha,
        })
        db.commit()
        return json_ok({"ok": True, "pendiente": round(nuevo_pend, 2),
                        "estado": nuevo_estado, "fecha": fecha})
    finally:
        db.close()


# ═════════════════════════════════════════════════════════════════════════════
# FINANZAS
# ═════════════════════════════════════════════════════════════════════════════

def _items_from_raw(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw) or []
        except Exception:
            return []
    return []


_REP_CATS = ("repuesto", "general")
_MO_CATS = ("servicio", "mano de obra", "mano_obra")


def _ganancia_items(db, items, taller_id):
    mo = rep_venta = rep_costo = total = 0.0
    for item in items:
        cat = str(item.get("categoria", "")).lower().strip()
        qty = float(item.get("cantidad", 1) or 1)
        pu = float(item.get("precio_unitario", 0) or 0)
        tot = float(item.get("total", item.get("subtotal", qty * pu)) or 0)
        if any(k in cat for k in _MO_CATS):
            mo += tot
        elif any(k in cat for k in _REP_CATS) or cat == "":
            rep_venta += tot
            codigo = item.get("referencia") or item.get("codigo") or ""
            if codigo:
                row = db.execute(text(
                    "SELECT costo FROM inventario "
                    "WHERE codigo=:c AND taller_id=:t LIMIT 1"
                ), {"c": codigo, "t": taller_id}).fetchone()
                costo_unit = float(row[0]) if row and row[0] else pu * 0.6
            else:
                costo_unit = pu * 0.6
            rep_costo += costo_unit * qty
        total += tot
    return round(mo, 2), round(rep_venta, 2), round(rep_costo, 2), round(total, 2)


async def api_finanzas_get(request: Request) -> JSONResponse:
    auth = _auth_tenant(request, admin=True)
    if isinstance(auth, JSONResponse):
        return auth
    _user, taller_id, db = auth
    try:
        ing = db.execute(text("""
            SELECT metodo_pago, COALESCE(SUM(monto_cobrado), 0)
            FROM ordenes
            WHERE taller_id=:t AND COALESCE(monto_cobrado,0) > 0
              AND fecha_dt::date >= date_trunc('month', NOW())::date
            GROUP BY metodo_pago
        """), {"t": taller_id}).fetchall()
        ingresos_metodo = {}
        for metodo, monto in ing:
            key = (metodo or "").strip() or "Efectivo"
            ingresos_metodo[key] = round(
                ingresos_metodo.get(key, 0.0) + float(monto or 0), 2
            )
        total_ordenes = round(sum(ingresos_metodo.values()), 2)

        nv_mes = db.execute(text(
            "SELECT COALESCE(SUM(COALESCE(monto_pagado, total)), 0) "
            "FROM notas_venta WHERE taller_id=:t "
            "AND fecha >= date_trunc('month', NOW())"
        ), {"t": taller_id}).fetchone()[0] or 0

        ac_mes = db.execute(text(
            "SELECT COALESCE(SUM(monto), 0) FROM abonos_credito "
            "WHERE taller_id=:t AND fecha_dt >= date_trunc('month', NOW())::date"
        ), {"t": taller_id}).fetchone()[0] or 0

        inicio_mes = datetime.now().strftime("%Y-%m-01")
        gastos_fact = db.execute(text("""
            SELECT COALESCE(SUM(total), 0) FROM facturas
            WHERE taller_id=:t AND tipo='gasto'
              AND CASE
                    WHEN fecha ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$' THEN TO_DATE(fecha, 'DD/MM/YYYY')
                    WHEN fecha ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN TO_DATE(substring(fecha,1,10), 'YYYY-MM-DD')
                    ELSE NULL::date
                  END >= CAST(:inicio AS date)
        """), {"t": taller_id, "inicio": inicio_mes}).fetchone()[0] or 0

        gastos_nomina = db.execute(text(
            "SELECT COALESCE(SUM(monto), 0) FROM pagos_trabajadores "
            "WHERE taller_id=:t AND fecha >= date_trunc('month', NOW())::date"
        ), {"t": taller_id}).fetchone()[0] or 0
        gastos = float(gastos_fact) + float(gastos_nomina)

        mo_o = rep_v_o = rep_c_o = 0.0
        for items_raw, cobrado_o, total_jsonb in db.execute(text(
            "SELECT items_cotizacion, COALESCE(monto_cobrado,0), "
            "       COALESCE(orden_total(items_cotizacion), 0)::float "
            "FROM ordenes "
            "WHERE taller_id=:t AND COALESCE(monto_cobrado,0) > 0 "
            "AND fecha_dt::date >= date_trunc('month', NOW())::date"
        ), {"t": taller_id}).fetchall():
            m, rv, rc, tot = _ganancia_items(db, _items_from_raw(items_raw), taller_id)
            base = float(total_jsonb) or tot
            pct = min(float(cobrado_o) / base, 1.0) if base > 0 else 1.0
            mo_o += m * pct
            rep_v_o += rv * pct
            rep_c_o += rc * pct

        mo_n = rep_v_n = rep_c_n = 0.0
        for items_raw, pagado_n, total_n in db.execute(text(
            "SELECT items, COALESCE(monto_pagado, total, 0), COALESCE(total, 0) "
            "FROM notas_venta "
            "WHERE taller_id=:t AND fecha >= date_trunc('month', NOW())"
        ), {"t": taller_id}).fetchall():
            m, rv, rc, _ = _ganancia_items(db, _items_from_raw(items_raw), taller_id)
            pct = min(float(pagado_n) / float(total_n), 1.0) if total_n and total_n > 0 else 1.0
            mo_n += m * pct
            rep_v_n += rv * pct
            rep_c_n += rc * pct

        mo_c = rep_v_c = rep_c_c = 0.0
        cr_rows = db.execute(text("""
            SELECT c.items_json, c.total,
                   COALESCE(SUM(a.monto) FILTER (
                       WHERE a.fecha_dt >= date_trunc('month', NOW())::date), 0) AS cobrado_mes
            FROM creditos c
            LEFT JOIN abonos_credito a ON a.credito_id = c.id AND a.taller_id = c.taller_id
            WHERE c.taller_id = :t
            GROUP BY c.id, c.items_json, c.total
            HAVING COALESCE(SUM(a.monto) FILTER (
                WHERE a.fecha_dt >= date_trunc('month', NOW())::date), 0) > 0
        """), {"t": taller_id}).fetchall()
        for items_raw, total_c, cobrado in cr_rows:
            m, rv, rc, _ = _ganancia_items(db, _items_from_raw(items_raw), taller_id)
            pct = float(cobrado or 0) / float(total_c) if total_c else 0
            mo_c += m * pct
            rep_v_c += rv * pct
            rep_c_c += rc * pct

        mo_total = round(mo_o + mo_n + mo_c, 2)
        rep_venta = round(rep_v_o + rep_v_n + rep_v_c, 2)
        rep_costo = round(rep_c_o + rep_c_n + rep_c_c, 2)
        rep_ganancia = round(rep_venta - rep_costo, 2)
        ganancia_bruta = round(mo_total + rep_ganancia, 2)
        ganancia_neta = round(ganancia_bruta - float(gastos), 2)

        return json_ok({
            "ingresos_mes": round(total_ordenes, 2),
            "notas_venta_mes": round(float(nv_mes), 2),
            "creditos_cobrados_mes": round(float(ac_mes), 2),
            "gastos_mes": round(float(gastos), 2),
            "utilidad_mes": round(
                total_ordenes + float(nv_mes) + float(ac_mes) - float(gastos), 2
            ),
            "por_metodo": ingresos_metodo,
            "ganancias": {
                "mano_obra_100pct": mo_total,
                "repuesto_venta": rep_venta,
                "repuesto_costo": rep_costo,
                "repuesto_ganancia": rep_ganancia,
                "ganancia_bruta": ganancia_bruta,
                "ganancia_neta": ganancia_neta,
            },
        })
    except Exception:
        import traceback
        traceback.print_exc()
        return json_err("Error en finanzas", 500)
    finally:
        db.close()


# ═════════════════════════════════════════════════════════════════════════════
# EQUIPO
# ═════════════════════════════════════════════════════════════════════════════

_ROLES = {"tecnico", "recepcionista", "administrativo", "mecanico", "ayudante", "otro"}
_PERIODS = {"diario", "semanal", "quincenal", "mensual"}
_TIPOS_PAGO = {"sueldo", "adelanto", "bono", "comision"}


def _saldo_pendiente(db, trabajador_id, taller_id, salario, periodicidad):
    now = datetime.now()
    if periodicidad == "diario":
        desde = hasta = now.strftime("%Y-%m-%d")
        etiqueta = desde
    elif periodicidad == "semanal":
        lunes = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        domingo = (now - timedelta(days=now.weekday()) + timedelta(days=6)).strftime("%Y-%m-%d")
        desde, hasta = lunes, domingo
        etiqueta = f"Sem {now.isocalendar()[1]}"
    elif periodicidad == "quincenal":
        if now.day <= 15:
            desde = now.strftime("%Y-%m-01")
            hasta = now.strftime("%Y-%m-15")
            etiqueta = f"{now.strftime('%Y-%m')} Q1"
        else:
            desde = now.strftime("%Y-%m-16")
            if now.month == 12:
                nxt = datetime(now.year + 1, 1, 1)
            else:
                nxt = datetime(now.year, now.month + 1, 1)
            hasta = (nxt - timedelta(days=1)).strftime("%Y-%m-%d")
            etiqueta = f"{now.strftime('%Y-%m')} Q2"
    else:
        desde = now.strftime("%Y-%m-01")
        if now.month == 12:
            nxt = datetime(now.year + 1, 1, 1)
        else:
            nxt = datetime(now.year, now.month + 1, 1)
        hasta = (nxt - timedelta(days=1)).strftime("%Y-%m-%d")
        etiqueta = now.strftime("%Y-%m")
    row = db.execute(text(
        "SELECT COALESCE(SUM(monto), 0) FROM pagos_trabajadores "
        "WHERE taller_id=:t AND trabajador_id=:tr "
        "AND fecha >= :d AND fecha <= :h"
    ), {"t": taller_id, "tr": trabajador_id, "d": desde, "h": hasta}).fetchone()
    pagado = float(row[0] or 0)
    pendiente = round(max(float(salario) - pagado, 0.0), 2)
    return {"periodo": etiqueta,
            "pagado_periodo": round(pagado, 2),
            "pendiente_periodo": pendiente}


async def api_equipo_list(request: Request) -> JSONResponse:
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse):
        return auth
    _user, taller_id, db = auth
    try:
        rows = db.execute(text(
            "SELECT id, nombre, dni, rol, salario, periodicidad, telefono, "
            "fecha_ingreso, activo, notas "
            "FROM trabajadores WHERE taller_id=:t "
            "ORDER BY activo DESC, nombre"
        ), {"t": taller_id}).fetchall()
        out = []
        for r in rows:
            saldo = _saldo_pendiente(
                db, r[0], taller_id, float(r[4] or 0), r[5] or "mensual"
            )
            out.append({
                "id": r[0], "nombre": r[1], "dni": r[2] or "",
                "rol": r[3] or "tecnico", "salario": float(r[4] or 0),
                "periodicidad": r[5] or "mensual", "telefono": r[6] or "",
                "fecha_ingreso": r[7].isoformat() if r[7] else None,
                "activo": bool(r[8]), "notas": r[9] or "",
                **saldo,
            })
        return json_ok(out)
    finally:
        db.close()


async def api_equipo_create(request: Request) -> JSONResponse:
    auth = _auth_tenant(request, admin=True)
    if isinstance(auth, JSONResponse):
        return auth
    _user, taller_id, db = auth
    try:
        body = await request.json()
        nombre = (body.get("nombre") or "").strip()
        if not nombre:
            return json_err("Nombre requerido", 400)
        rol = (body.get("rol") or "tecnico").lower().strip()
        if rol not in _ROLES:
            rol = "otro"
        periodicidad = (body.get("periodicidad") or "mensual").lower().strip()
        if periodicidad not in _PERIODS:
            periodicidad = "mensual"
        try:
            salario = float(body.get("salario") or 0)
        except (TypeError, ValueError):
            return json_err("Salario inválido", 400)
        if salario < 0:
            return json_err("Salario negativo", 400)
        res = db.execute(text("""
            INSERT INTO trabajadores
              (taller_id, nombre, dni, rol, salario, periodicidad, telefono,
               fecha_ingreso, activo, notas)
            VALUES (:t, :n, :dni, :rol, :sal, :per, :tel, :fi, :act, :notas)
            RETURNING id
        """), {
            "t": taller_id, "n": nombre,
            "dni": (body.get("dni") or "").strip() or None,
            "rol": rol, "sal": salario, "per": periodicidad,
            "tel": (body.get("telefono") or "").strip() or None,
            "fi": _safe_date(body.get("fecha_ingreso")) or datetime.now().date().isoformat(),
            "act": bool(body.get("activo", True)),
            "notas": (body.get("notas") or "").strip() or None,
        })
        new_id = res.fetchone()[0]
        db.commit()
        return json_ok({"ok": True, "id": new_id})
    finally:
        db.close()


async def api_equipo_pago(request: Request) -> JSONResponse:
    auth = _auth_tenant(request, admin=True)
    if isinstance(auth, JSONResponse):
        return auth
    user, taller_id, db = auth
    try:
        tid = int(request.path_params.get("tid", 0))
        body = await request.json()
        try:
            monto = float(body.get("monto") or 0)
        except (TypeError, ValueError):
            return json_err("Monto inválido", 400)
        if monto <= 0:
            return json_err("Monto debe ser > 0", 400)
        tipo = (body.get("tipo") or "sueldo").lower().strip()
        if tipo not in _TIPOS_PAGO:
            tipo = "sueldo"
        exists = db.execute(text(
            "SELECT 1 FROM trabajadores WHERE id=:id AND taller_id=:t"
        ), {"id": tid, "t": taller_id}).fetchone()
        if not exists:
            return json_err("Trabajador no encontrado", 404)
        res = db.execute(text("""
            INSERT INTO pagos_trabajadores
              (taller_id, trabajador_id, monto, fecha, metodo_pago, tipo,
               periodo_cubierto, observacion, registrado_por)
            VALUES (:t, :tr, :m, :f, :mp, :tipo, :per, :obs, :who)
            RETURNING id
        """), {
            "t": taller_id, "tr": tid, "m": monto,
            "f": _safe_date(body.get("fecha")) or datetime.now().date().isoformat(),
            "mp": (body.get("metodo_pago") or "Efectivo").strip(),
            "tipo": tipo,
            "per": (body.get("periodo_cubierto") or "").strip() or None,
            "obs": (body.get("observacion") or "").strip() or None,
            "who": user.get("nombre") or "admin",
        })
        new_id = res.fetchone()[0]
        db.commit()
        return json_ok({"ok": True, "id": new_id})
    finally:
        db.close()


# ═════════════════════════════════════════════════════════════════════════════
# CITAS — update móvil (PUT /api/citas/{cid})
# ═════════════════════════════════════════════════════════════════════════════

async def api_cita_update(request: Request) -> JSONResponse:
    auth = _auth_tenant(request)
    if isinstance(auth, JSONResponse):
        return auth
    _user, taller_id, db = auth
    try:
        cid = int(request.path_params.get("cid", 0))
        body = await request.json()
        sets, params = [], {"id": cid, "t": taller_id}
        for f in ("cliente_nombre", "telefono", "servicio", "estado", "observaciones"):
            if f in body:
                sets.append(f"{f}=:{f}")
                params[f] = body[f]
        if "fecha_hora" in body:
            sets.append("fecha_hora=:fh")
            params["fh"] = body["fecha_hora"]
        if not sets:
            return json_ok({"ok": True, "noop": True})
        db.execute(
            text(f"UPDATE citas SET {', '.join(sets)} WHERE id=:id AND taller_id=:t"),
            params,
        )
        db.commit()
        return json_ok({"ok": True})
    finally:
        db.close()


# ═════════════════════════════════════════════════════════════════════════════
# REGISTRO
# ═════════════════════════════════════════════════════════════════════════════

def register_mobile_admin_routes(app):
    """Registra endpoints admin bajo /api/* con auth de sesión móvil."""
    # Caja
    # 2026-05-05 RE-HABILITADO: routers/caja.py monta sus rutas bajo /admin/* (JWT
    # admin), pero la PWA staff (sandoval-app) usa sesión SQLite via
    # /api/auth/login. Sin estas rutas /api/caja → 404 → frontend muestra
    # "Not found" rojo y dispara logout. Las funciones api_caja_* aquí usan
    # _auth_tenant() compatible con session SQLite.
    app.add_api_route('/api/caja',               api_caja_get,     methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/caja/abrir',         api_caja_abrir,   methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/caja/cerrar',        api_caja_cerrar,  methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/caja/{cid}/cerrar',  api_caja_cerrar,  methods=['POST', 'OPTIONS'])

    # Proveedores
    app.add_api_route('/api/proveedores', api_proveedores_list, methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/proveedores', api_proveedor_create, methods=['POST', 'OPTIONS'])

    # Facturas
    app.add_api_route('/api/facturas', api_facturas_list,  methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/facturas', api_factura_create, methods=['POST', 'OPTIONS'])

    # Cotizaciones
    app.add_api_route('/api/cotizaciones', api_cotizaciones_list, methods=['GET', 'OPTIONS'])

    # Créditos
    app.add_api_route('/api/creditos',             api_creditos_list, methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/creditos/{cid}/abono', api_credito_abono, methods=['POST', 'OPTIONS'])

    # Finanzas
    app.add_api_route('/api/finanzas', api_finanzas_get, methods=['GET', 'OPTIONS'])

    # Equipo
    app.add_api_route('/api/equipo',             api_equipo_list,   methods=['GET', 'OPTIONS'])
    app.add_api_route('/api/equipo',             api_equipo_create, methods=['POST', 'OPTIONS'])
    app.add_api_route('/api/equipo/{tid}/pagos', api_equipo_pago,   methods=['POST', 'OPTIONS'])

    # Citas (update)
    app.add_api_route('/api/citas/{cid}', api_cita_update, methods=['PUT', 'OPTIONS'])
