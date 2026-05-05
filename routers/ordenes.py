"""
routers/ordenes.py — Órdenes de servicio (multi-tenant).

Refactor 2026-04-21: taller_id del JWT via _tenant_id.
Fix: FASES_ORDEN ahora se importa explícitamente (antes dependía de orden
global de importación de dashboard.py, lo que provocaba NameError latente).
"""
import uuid
from utils.upload_validator import validate_upload_bytes
from routers._common import (
    router, ADMIN_HTML,
    _auth, _get_db, _require_admin, _require_staff, _safe_date,
    _img_to_url, _parse_json_field, _make_token, _tenant_id,
    os, json, datetime, timedelta, Path,
    Request, HTTPException, UploadFile, File, List, HTMLResponse, text,
)
from fastapi import Query
from routers.dashboard import FASES_ORDEN


def _coerce_fecha_ingreso(body):
    """Return (fecha_str 'YYYY-MM-DD', fecha_dt for timestamptz).
    Accepts body['fecha'] as 'YYYY-MM-DD' o ISO datetime con hora.
    - Con hora explícita → se respeta tal cual.
    - Solo fecha → 08:00 (inicio de jornada). Antes usaba datetime.now() que
      producía horas "aleatorias" dependientes del momento del POST."""
    raw = (body.get("fecha") or "").strip() if body.get("fecha") else ""
    now = datetime.now()
    if not raw:
        return now.strftime("%Y-%m-%d"), now
    base = raw.replace("T", " ")
    try:
        if len(base) <= 10:
            d = datetime.strptime(base[:10], "%Y-%m-%d").replace(hour=8, minute=0, second=0)
        elif len(base) >= 19:
            d = datetime.strptime(base[:19], "%Y-%m-%d %H:%M:%S")
        else:
            d = datetime.strptime(base[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        return now.strftime("%Y-%m-%d"), now
    return d.strftime("%Y-%m-%d"), d


def _coerce_km(body):
    """Normaliza km a entero. Acepta string vacío, None, int, float, str numérico con coma."""
    v = body.get("km")
    if v is None or v == "":
        return 0
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (ValueError, TypeError):
        return 0


@router.get("/api/ordenes")
async def list_ordenes(
    request: Request,
    estado: str | None = None,
    q: str | None = None,
    tecnico: str | None = None,
    limit: int = Query(200, ge=1, le=500),
):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        sql = """
            SELECT o.consecutivo, o.cliente_id, c.nombre, c.apellidos, o.vehiculo_placa,
                   o.estado, o.monto_cobrado, o.fecha, o.tecnico, o.motivo,
                   COALESCE((SELECT SUM((itm->>'total')::float) FROM jsonb_array_elements(COALESCE(o.items_cotizacion::jsonb,'[]'::jsonb)) itm WHERE itm->>'categoria' NOT IN ('Resumen','Impuesto','Total')), 0) as total,
                   o.km, o.tipo
            FROM ordenes o
            LEFT JOIN clientes c ON c.id = o.cliente_id
            WHERE o.taller_id = :t
        """
        params = {"t": taller_id}
        if estado:
            sql += " AND o.estado = :estado"; params["estado"] = estado
        if tecnico:
            sql += " AND o.tecnico = :tec"; params["tec"] = tecnico
        if q:
            sql += """ AND (o.consecutivo ILIKE :q OR c.nombre ILIKE :q
                        OR o.vehiculo_placa ILIKE :q OR o.motivo ILIKE :q)"""
            params["q"] = f"%{q}%"
        sql += " ORDER BY o.consecutivo DESC LIMIT :lim"
        params["lim"] = limit
        rows = db.execute(text(sql), params).fetchall()
        result = []
        for r in rows:
            total = r[10] or 0; cobrado = r[6] or 0
            if cobrado >= total and total > 0: ps = "PAGADO"
            elif cobrado > 0: ps = "PARCIAL"
            else: ps = "PENDIENTE"
            _e_map = {"CONTROL":"CONTROL CALIDAD","CONTROL_CALIDAD":"CONTROL CALIDAD",
                      "ENTREGA":"LISTO PARA ENTREGA","LISTO":"LISTO PARA ENTREGA",
                      "LISTO_PARA_ENTREGA":"LISTO PARA ENTREGA",
                      "RECEPCION":"RECEPCIÓN","DIAGNOSTICO":"DIAGNÓSTICO",
                      "REPARACION":"REPARACIÓN","APROBACION":"APROBACIÓN","":"RECEPCIÓN"}
            estado_n = _e_map.get((r[5] or "").upper(), r[5] or "RECEPCIÓN")
            result.append({
                "consecutivo": r[0], "cliente_id": r[1],
                "cliente": f"{r[2] or ''} {r[3] or ''}".strip()[:30],
                "placa": r[4], "estado": estado_n, "cobrado": cobrado,
                "total": total, "pago_estado": ps, "fecha": _safe_date(r[7]),
                "tecnico": r[8], "motivo": (r[9] or "")[:50], "km": r[11], "tipo": r[12],
            })
        return result
    finally:
        db.close()


@router.get("/api/ordenes/{consecutivo}")
async def get_orden(consecutivo: str, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        row = db.execute(text("""
            SELECT o.consecutivo, o.cliente_id, c.nombre, c.apellidos, c.telefono,
                   o.vehiculo_placa, v.marca, v.modelo, v.año,
                   o.estado, o.monto_cobrado, o.fecha, o.tecnico, o.motivo,
                   o.diagnostico, o.km, o.tipo, o.observaciones,
                   o.items_cotizacion, o.pagos, o.historial,
                   o.approval_status, o.fotos_evidencia, o.checklist_reparacion,
                   o.approval_token, o.approval_date, o.fecha_dt, o.factura_sunat
            FROM ordenes o
            LEFT JOIN clientes c ON c.id = o.cliente_id
            LEFT JOIN vehiculos v ON v.placa = o.vehiculo_placa AND v.taller_id = o.taller_id
            WHERE o.consecutivo = :id AND o.taller_id = :t
        """), {"id": consecutivo, "t": taller_id}).fetchone()
        if not row:
            raise HTTPException(404, "Orden no encontrada")
        approval_token = row[24]
        if not approval_token or str(approval_token).startswith("USED_"):
            approval_token = uuid.uuid4().hex
            db.execute(text(
                "UPDATE ordenes SET approval_token=:tok WHERE consecutivo=:c AND taller_id=:t"
            ), {"tok": approval_token, "c": row[0], "t": taller_id})
            db.commit()
        items_raw = _parse_json_field(row[18])
        if isinstance(items_raw, dict):
            items = items_raw.get("items", [])
        elif isinstance(items_raw, list):
            items = items_raw
        else:
            items = []
        total = 0
        try:
            if isinstance(items_raw, dict): total = float(items_raw.get("total", 0))
            elif isinstance(items, list):
                total = sum(float(i.get("subtotal", i.get("precio_unitario", 0)) *
                            (i.get("cantidad", 1) if "subtotal" not in i else 1)) for i in items)
        except Exception:
            pass
        cobrado = row[10] or 0
        return {
            "consecutivo": row[0], "cliente_id": row[1],
            "cliente_nombre": f"{row[2] or ''} {row[3] or ''}".strip(),
            "cliente_telefono": row[4],
            "placa": row[5], "vehiculo_placa": row[5],
            "vehiculo": f"{row[6] or ''} {row[7] or ''} {row[8] or ''}".strip(),
            "vehiculo_marca": row[6] or '', "vehiculo_modelo": row[7] or '', "vehiculo_anio": row[8] or '',
            "estado": row[9], "cobrado": cobrado, "total": total,
            "pago_estado": "PAGADO" if cobrado >= total > 0 else ("PARCIAL" if cobrado > 0 else "PENDIENTE"),
            "fecha": _safe_date(row[11]), "fecha_dt": _safe_date(row[26]), "tecnico": row[12], "motivo": row[13],
            "diagnostico": row[14], "km": row[15], "tipo": row[16], "observaciones": row[17],
            "items": items, "pagos": _parse_json_field(row[19]),
            "historial": _parse_json_field(row[20]),
            "approval_status": row[21],
            "fotos": _parse_json_field(row[22]),
            "fotos_evidencia": _parse_json_field(row[22]),
            "checklist_reparacion": _parse_json_field(row[23]),
            "approval_token": approval_token,
            "approval_date": row[25],
            "factura_sunat": row[27] or "",
        }
    finally:
        db.close()


@router.post("/api/ordenes")
async def create_orden(request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    motivo = (body.get("motivo") or "").strip()
    if not motivo:
        raise HTTPException(status_code=400, detail="El motivo de ingreso es obligatorio")
    db = _get_db()
    try:
        fecha_str, fecha_dt = _coerce_fecha_ingreso(body)
        prefix = fecha_dt.strftime("OS-%Y%m%d-")
        token = str(uuid.uuid4()).replace("-", "")
        placa = (body.get("vehiculo_placa") or body.get("placa", "")).upper().strip()
        params_base = {
            "t": taller_id, "f": fecha_str, "fdt": fecha_dt,
            "cli": body.get("cliente_id") or None, "placa": placa or None,
            "motivo": body.get("motivo", ""), "tec": body.get("tecnico", ""),
            "km": _coerce_km(body), "tipo": body.get("tipo", "PREVENTIVO"),
            "obs": body.get("observaciones", ""), "tok": token,
        }
        # Calcula el siguiente consecutivo usando MAX real (no COUNT — los gaps por
        # eliminaciones causaban duplicate-key violations). Loop con retry por race.
        consecutivo = None
        for attempt in range(15):
            row = db.execute(text(
                "SELECT MAX(CAST(SUBSTRING(consecutivo FROM '[0-9]+$') AS INTEGER)) "
                "FROM ordenes WHERE consecutivo LIKE :p AND taller_id=:t"
            ), {"p": f"{prefix}%", "t": taller_id}).fetchone()
            current_max = (row[0] or 0) if row else 0
            next_num = current_max + 1 + attempt
            consecutivo = f"{prefix}{str(next_num).zfill(3)}"
            try:
                db.execute(text("""
                    INSERT INTO ordenes (consecutivo, taller_id, fecha, fecha_dt, cliente_id, vehiculo_placa,
                        motivo, estado, tecnico, km, tipo, observaciones, approval_token, monto_cobrado,
                        approval_status, approval_date)
                    VALUES (:c, :t, :f, :fdt, :cli, :placa, :motivo, 'RECEPCIÓN', :tec, :km, :tipo, :obs, :tok, 0,
                        'pendiente', NULL)
                """), {**params_base, "c": consecutivo})
                db.commit()
                break
            except Exception as e:
                db.rollback()
                msg = str(e).lower()
                if "duplicate key" in msg or "uniqueviolation" in msg:
                    continue
                raise
        try:
            db.execute(text(
                "INSERT INTO actividades (taller_id, usuario_id, modulo, accion, referencia) "
                "VALUES (:t, :u, 'ordenes', :a, :r)"
            ), {"t": taller_id, "u": tok.get("sub"), "a": f"Creó orden {consecutivo}", "r": consecutivo})
            db.commit()
        except Exception:
            pass
        return {"consecutivo": consecutivo, "token": token}
    finally:
        db.close()


@router.put("/api/ordenes/{consecutivo}")
async def update_orden(consecutivo: str, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        allowed = ["motivo", "tecnico", "km", "tipo", "observaciones",
                   "diagnostico", "notas_entrega", "items_cotizacion", "metodo_pago",
                   "vehiculo_placa", "cliente_id"]
        sets, params = [], {"id": consecutivo, "t": taller_id}
        for k in allowed:
            if k in body:
                val = body[k]
                if k == "items_cotizacion" and not isinstance(val, str):
                    val = json.dumps(val)
                elif k == "vehiculo_placa":
                    val = (val or "").upper().strip() or None
                elif k == "cliente_id":
                    val = (val or "").strip() or None
                elif k == "km":
                    val = _coerce_km(body)
                sets.append(f"{k}=:{k}")
                params[k] = val
        if "fecha" in body:
            fecha_str, fecha_dt = _coerce_fecha_ingreso(body)
            sets.append("fecha=:fecha"); params["fecha"] = fecha_str
            sets.append("fecha_dt=:fecha_dt"); params["fecha_dt"] = fecha_dt
        if not sets:
            raise HTTPException(400, "Nada que actualizar")
        db.execute(text(f"UPDATE ordenes SET {', '.join(sets)} WHERE consecutivo=:id AND taller_id=:t"), params)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.post("/api/ordenes/{consecutivo}/fase")
async def avanzar_fase(consecutivo: str, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    nueva_fase = body.get("fase", "").upper()
    _norm = {
        "RECEPCION": "RECEPCIÓN", "DIAGNOSTICO": "DIAGNÓSTICO",
        "APROBACION": "APROBACIÓN", "REPARACION": "REPARACIÓN",
        "CONTROL_CALIDAD": "CONTROL CALIDAD", "CONTROL": "CONTROL CALIDAD",
        "LISTO": "LISTO PARA ENTREGA", "ENTREGA": "LISTO PARA ENTREGA",
        "LISTO_PARA_ENTREGA": "LISTO PARA ENTREGA",
    }
    nueva_fase = _norm.get(nueva_fase, nueva_fase)
    if nueva_fase not in FASES_ORDEN:
        raise HTTPException(400, f"Fase inválida: {nueva_fase}")
    db = _get_db()
    try:
        orden = db.execute(text(
            "SELECT estado FROM ordenes WHERE consecutivo=:id AND taller_id=:t"
        ), {"id": consecutivo, "t": taller_id}).fetchone()
        if not orden:
            raise HTTPException(404, "Orden no encontrada")
        updates = {"id": consecutivo, "t": taller_id, "fase": nueva_fase}
        extra_sql = ""
        if nueva_fase == "ARCHIVADO":
            extra_sql = ", fecha_cobro=TO_CHAR(NOW(), 'YYYY-MM-DD')"
        # Si se retrocede a fase PRE-aprobación, resetear approval_status (era stale)
        _PRE_APROB = {"RECEPCIÓN", "DIAGNÓSTICO", "REPUESTOS", "APROBACIÓN"}
        if nueva_fase in _PRE_APROB:
            extra_sql += ", approval_status='pendiente', approval_date=NULL"
        db.execute(text(
            f"UPDATE ordenes SET estado=:fase {extra_sql} WHERE consecutivo=:id AND taller_id=:t"
        ), updates)
        db.commit()
        try:
            db.execute(text(
                "INSERT INTO actividades (taller_id, usuario_id, modulo, accion, referencia) "
                "VALUES (:t, :u, 'ordenes', :a, :r)"
            ), {"t": taller_id, "u": tok.get("sub"),
                "a": f"Cambió {consecutivo} a {nueva_fase}", "r": consecutivo})
            db.commit()
        except Exception:
            pass
        # 2026-04-30 sync-guardian fix: notificaciones push al cliente al cambiar de fase
        try:
            from utils import notifications as _notifs
            if nueva_fase == "LISTO PARA ENTREGA":
                _notifs.notify_cliente_listo_entrega(db, taller_id, consecutivo)
            else:
                _notifs.notify_cliente_fase_avanzada(db, taller_id, consecutivo, nueva_fase)
        except Exception as _ne:
            import logging
            logging.getLogger("sandoval.notif").warning(
                "Hook notif fase fallido %s: %s", consecutivo, _ne
            )
        return {"ok": True, "fase": nueva_fase}
    finally:
        db.close()


@router.post("/api/admin/cleanup-stale-approvals")
async def cleanup_stale_approvals(request: Request):
    """Limpia órdenes con approval_status='aprobado' que están en fases pre-aprobación.
    Estos son datos inconsistentes (orden retrocedida o datos legacy de seed).
    Solo admin. Devuelve cantidad de órdenes corregidas."""
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        result = db.execute(text("""
            UPDATE ordenes
               SET approval_status='pendiente', approval_date=NULL
             WHERE taller_id=:t
               AND LOWER(COALESCE(approval_status,'')) = 'aprobado'
               AND UPPER(COALESCE(estado,'')) IN
                   ('RECEPCION','RECEPCIÓN','DIAGNOSTICO','DIAGNÓSTICO','REPUESTOS','APROBACION','APROBACIÓN')
        """), {"t": taller_id})
        n = result.rowcount or 0
        db.commit()
        if n > 0:
            try:
                db.execute(text(
                    "INSERT INTO actividades (taller_id, usuario_id, modulo, accion, referencia) "
                    "VALUES (:t, :u, 'ordenes', :a, '')"
                ), {"t": taller_id, "u": tok.get("sub"),
                    "a": f"Limpieza masiva: reseteó approval_status en {n} órdenes pre-aprobación"})
                db.commit()
            except Exception:
                pass
        return {"ok": True, "ordenes_corregidas": n}
    finally:
        db.close()


@router.post("/api/ordenes/{consecutivo}/reset-approval")
async def reset_approval(consecutivo: str, request: Request):
    """Resetea approval_status='pendiente' y approval_date=NULL.
    Usado cuando admin reenvía un presupuesto modificado al cliente."""
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        orden = db.execute(text(
            "SELECT approval_status FROM ordenes WHERE consecutivo=:id AND taller_id=:t"
        ), {"id": consecutivo, "t": taller_id}).fetchone()
        if not orden:
            raise HTTPException(404, "Orden no encontrada")
        db.execute(text(
            "UPDATE ordenes SET approval_status='pendiente', approval_date=NULL "
            "WHERE consecutivo=:id AND taller_id=:t"
        ), {"id": consecutivo, "t": taller_id})
        db.commit()
        try:
            db.execute(text(
                "INSERT INTO actividades (taller_id, usuario_id, modulo, accion, referencia) "
                "VALUES (:t, :u, 'ordenes', :a, :r)"
            ), {"t": taller_id, "u": tok.get("sub"),
                "a": f"Reseteó aprobación de {consecutivo}", "r": consecutivo})
            db.commit()
        except Exception:
            pass
        return {"ok": True, "approval_status": "pendiente"}
    finally:
        db.close()


@router.post("/api/ordenes/{consecutivo}/abono")
async def registrar_abono_orden(consecutivo: str, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    # 2026-05-04 FASE1.2: validacion Pydantic V2 con AbonoPayload
    try:
        from utils.schemas import AbonoPayload
        _p = AbonoPayload.model_validate({
            "monto": body.get("monto", 0),
            "metodo_pago": body.get("metodo_pago", "Efectivo"),
            "observaciones": body.get("observaciones") or body.get("nota") or None,
        })
        monto  = float(_p.monto)
        metodo = _p.metodo_pago
    except Exception as _ve:
        raise HTTPException(422, f"Datos de abono invalidos: {str(_ve)[:200]}")
    if monto <= 0:
        raise HTTPException(400, "Monto debe ser mayor a 0")
    db = _get_db()
    try:
        # Lock de fila durante el cálculo del saldo para evitar sobrepago por concurrencia.
        # PRD §4.2 (integridad financiera): no se puede cobrar mas que el total de la orden.
        orden = db.execute(text(
            "SELECT COALESCE(monto_cobrado, 0), pagos, "
            "       COALESCE(orden_total(items_cotizacion), 0) AS total_orden "
            "  FROM ordenes "
            " WHERE consecutivo=:id AND taller_id=:t FOR UPDATE"
        ), {"id": consecutivo, "t": taller_id}).fetchone()
        if not orden:
            raise HTTPException(404, "Orden no encontrada")
        ya_pagado = float(orden[0] or 0)
        total_orden = float(orden[2] or 0)
        saldo_prev = round(total_orden - ya_pagado, 2)
        if total_orden <= 0:
            raise HTTPException(400, "La orden no tiene items con precio. Agregar items en la cotización antes de cobrar.")
        if saldo_prev <= 0:
            raise HTTPException(400, "La orden ya está pagada por completo")
        if monto > saldo_prev + 0.01:
            raise HTTPException(400, f"El monto excede el saldo pendiente (S/ {saldo_prev:.2f})")
        pagos = _parse_json_field(orden[1])
        if not isinstance(pagos, list): pagos = []
        raw_fecha = (body.get("fecha") or "").strip()
        if raw_fecha:
            base = raw_fecha.replace("T", " ")
            try:
                if len(base) <= 10:
                    now = datetime.now()
                    d = datetime.strptime(base[:10], "%Y-%m-%d").replace(
                        hour=now.hour, minute=now.minute, second=now.second)
                else:
                    d = datetime.strptime(base[:19], "%Y-%m-%d %H:%M:%S") if len(base) >= 19 else datetime.strptime(base[:16], "%Y-%m-%d %H:%M")
                fecha_pago = d.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                fecha_pago = datetime.now().strftime("%Y-%m-%d %H:%M")
        else:
            fecha_pago = datetime.now().strftime("%Y-%m-%d %H:%M")
        pagos.append({
            "monto": round(monto, 2), "metodo": metodo,
            "fecha": fecha_pago,
            "nota": body.get("nota", "") or body.get("observacion", ""),
            "usuario": tok.get("nombre", "")
        })
        # Clamp al total para defensa-en-profundidad (PRD §4.2)
        nuevo_cobrado = round(min(ya_pagado + monto, total_orden), 2)
        db.execute(text("""
            UPDATE ordenes SET monto_cobrado=:mc, pagos=:p, metodo_pago=:mp
            WHERE consecutivo=:id AND taller_id=:t
        """), {
            "mc": nuevo_cobrado, "p": json.dumps(pagos),
            "mp": metodo, "id": consecutivo, "t": taller_id
        })
        db.commit()
        # Hook contabilidad: asiento orden cobro (fail-safe)
        try:
            from utils.contabilidad_engine import generar_asiento_orden_cobro
            generar_asiento_orden_cobro(db, taller_id, consecutivo)
        except Exception as _ce:
            import logging
            logging.getLogger("sandoval.contabilidad").warning(
                "Hook orden asiento fallido %s: %s", consecutivo, _ce
            )
        return {
            "ok": True,
            "nuevo_cobrado": nuevo_cobrado,
            "saldo": round(total_orden - nuevo_cobrado, 2),
            "estado_pago": "PAGADO" if nuevo_cobrado >= total_orden else "PARCIAL",
        }
    finally:
        db.close()


@router.get("/api/ordenes/{consecutivo}/presupuesto.pdf")
async def presupuesto_pdf_admin(consecutivo: str, request: Request):
    """PDF del presupuesto/cotización de una orden — para admin/staff descargar."""
    from fastapi.responses import FileResponse
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        # Buscar orden y cargar dicts cliente/vehículo
        from utils.models import Cliente, Vehiculo, Orden
        # 2026-04-29 audit-fix IDOR: filtro taller_id explicito
        o = db.query(Orden).filter_by(consecutivo=consecutivo, taller_id=taller_id).first()
        if not o:
            raise HTTPException(404, "Orden no encontrada")
        c_obj = db.query(Cliente).filter_by(id=o.cliente_id).first() if o.cliente_id else None
        v_obj = db.query(Vehiculo).filter_by(placa=o.vehiculo_placa).first() if o.vehiculo_placa else None
        o_dict = {col.name: getattr(o, col.name) for col in o.__table__.columns}
        o_dict['fotos_evidencia'] = o.fotos_evidencia
        c_dict = {col.name: getattr(c_obj, col.name) for col in c_obj.__table__.columns} if c_obj else {}
        v_dict = {col.name: getattr(v_obj, col.name) for col in v_obj.__table__.columns} if v_obj else {}
        os.makedirs('pdfs', exist_ok=True)
        safe = consecutivo.replace('/','_').replace(' ','_').replace('#','')
        pdf_path = f'pdfs/Presupuesto_{safe}.pdf'
        from utils.pdf_generator import generate_pdf
        generate_pdf(o_dict, c_dict, v_dict, 'cotizacion', pdf_path)
        if not os.path.isfile(pdf_path):
            raise HTTPException(500, 'PDF no se generó')
        return FileResponse(
            pdf_path, media_type='application/pdf',
            filename=f'Presupuesto_{safe}.pdf',
            headers={'Cache-Control': 'no-store'},
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, f'Error generando presupuesto: {e}')
    finally:
        db.close()


@router.get("/api/ordenes/{consecutivo}/informe-final.pdf")
async def informe_final_orden(consecutivo: str, request: Request):
    from fastapi.responses import FileResponse
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    try:
        from utils.pdf_informe_orden import generar_informe_orden
        pdf_path = generar_informe_orden(consecutivo, taller_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, f'Error generando informe: {e}')
    if not os.path.isfile(pdf_path):
        raise HTTPException(500, 'PDF no se generó')
    safe = consecutivo.replace('/','_').replace(' ','_').replace('#','')
    return FileResponse(
        pdf_path, media_type='application/pdf',
        filename=f'informe_{safe}.pdf',
        headers={'Cache-Control': 'no-store'},
    )


@router.post("/api/ordenes/{consecutivo}/fotos")
async def upload_fotos_orden(consecutivo: str, request: Request, files: List[UploadFile] = File(...), fase: str = ""):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    upload_dir = "/var/www/sandoval/static/evidencia"
    os.makedirs(upload_dir, exist_ok=True)
    db = _get_db()
    try:
        orden = db.execute(text(
            "SELECT fotos_evidencia FROM ordenes WHERE consecutivo=:id AND taller_id=:t"
        ), {"id": consecutivo, "t": taller_id}).fetchone()
        if not orden:
            raise HTTPException(404, "Orden no encontrada")
        fotos = _parse_json_field(orden[0])
        if not isinstance(fotos, list):
            fotos = []
        saved = []
        for file in files:
            ext = (os.path.splitext(file.filename or "")[1] or ".jpg").lower()
            allowed = {".jpg",".jpeg",".png",".gif",".webp",".mp4",".mov",".avi",".pdf"}
            if ext not in allowed:
                continue
            fname = f"{consecutivo}_{uuid.uuid4().hex[:10]}{ext}"
            fpath = os.path.join(upload_dir, fname)
            content = await file.read()
            ok, kind = validate_upload_bytes(content, ext)
            if not ok:
                continue
            with open(fpath, "wb") as fp:
                fp.write(content)
            try: os.chmod(fpath, 0o644)
            except OSError: pass
            url = f"/static/evidencia/{fname}"
            if ext == ".pdf":
                tipo = "pdf"
            elif ext in {".mp4",".mov",".avi"}:
                tipo = "video"
            else:
                tipo = "foto"
            fotos.append({
                "url": url, "nombre": file.filename or fname,
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "tipo": tipo,
                "fase": fase or "general"
            })
            saved.append(url)
        db.execute(text(
            "UPDATE ordenes SET fotos_evidencia=:f WHERE consecutivo=:id AND taller_id=:t"
        ), {"f": json.dumps(fotos), "id": consecutivo, "t": taller_id})
        db.commit()
        return {"ok": True, "urls": saved, "total": len(fotos)}
    finally:
        db.close()


@router.delete("/api/ordenes/{consecutivo}/fotos/{idx}")
async def delete_foto_orden(consecutivo: str, idx: int, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        orden = db.execute(text(
            "SELECT fotos_evidencia FROM ordenes WHERE consecutivo=:id AND taller_id=:t"
        ), {"id": consecutivo, "t": taller_id}).fetchone()
        if not orden:
            raise HTTPException(404, "Orden no encontrada")
        fotos = _parse_json_field(orden[0])
        if not isinstance(fotos, list) or idx < 0 or idx >= len(fotos):
            raise HTTPException(400, "Foto no encontrada")
        removed = fotos.pop(idx)
        try:
            fpath = "/var/www/sandoval" + removed["url"]
            if os.path.exists(fpath):
                os.remove(fpath)
        except Exception:
            pass
        db.execute(text(
            "UPDATE ordenes SET fotos_evidencia=:f WHERE consecutivo=:id AND taller_id=:t"
        ), {"f": json.dumps(fotos), "id": consecutivo, "t": taller_id})
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.delete("/api/ordenes/{consecutivo}")
async def delete_orden(consecutivo: str, request: Request):
    tok = _auth(request)
    _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        db.execute(text(
            "DELETE FROM ordenes WHERE consecutivo=:id AND taller_id=:t"
        ), {"id": consecutivo, "t": taller_id})
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.post("/api/ordenes/{consecutivo}/fase-data")
async def save_fase_data(consecutivo: str, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    fase = body.get("fase", "")
    datos = body.get("datos", {})
    db = _get_db()
    try:
        row = db.execute(text(
            "SELECT checklist_reparacion FROM ordenes WHERE consecutivo=:id AND taller_id=:t"
        ), {"id": consecutivo, "t": taller_id}).fetchone()
        if not row:
            raise HTTPException(404, "Orden no encontrada")
        current = _parse_json_field(row[0]) or {}
        if not isinstance(current, dict):
            current = {}
        current[fase] = datos
        extra_sql = ""
        extra_params = {}
        if fase == "diagnostico" and datos.get("hallazgos"):
            extra_sql = ", diagnostico=:diag"
            extra_params["diag"] = datos["hallazgos"]
        db.execute(text(
            f"UPDATE ordenes SET checklist_reparacion=:chk{extra_sql} WHERE consecutivo=:id AND taller_id=:t"
        ), {"chk": json.dumps(current), "id": consecutivo, "t": taller_id, **extra_params})
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.get("/api/ordenes/{consecutivo}/fase-data")
async def get_fase_data(consecutivo: str, request: Request):
    tok = _auth(request)
    _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        row = db.execute(text(
            "SELECT checklist_reparacion FROM ordenes WHERE consecutivo=:id AND taller_id=:t"
        ), {"id": consecutivo, "t": taller_id}).fetchone()
        if not row:
            raise HTTPException(404, "Orden no encontrada")
        data = _parse_json_field(row[0]) or {}
        return data if isinstance(data, dict) else {}
    finally:
        db.close()
