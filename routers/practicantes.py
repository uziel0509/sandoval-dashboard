"""
routers/practicantes.py — Modulo Practicantes SENATI v5.3 (2026-05-02).

Spec del usuario titular:
- Practicantes son estudiantes SENATI que cumplen horas de practica (NO se les paga)
- Cada practicante tiene horario semanal propio (puede variar)
- Se registra entrada/salida diaria → calcula horas trabajadas
- Reportes: horas/semana, horas/mes, % cumplimiento
- Tolerancia configurable de faltas → si excede → INHABILITADO automatico
- Cron diario detecta faltas (no marco entrada en dia con horario)

Endpoints (16 totales, prefijo /api/practicantes):

CRUD practicantes:
  GET    /api/practicantes                  → lista paginada con KPIs por practicante
  GET    /api/practicantes/{id}             → detalle (incluye horarios + reporte)
  POST   /api/practicantes                  → crear
  PUT    /api/practicantes/{id}             → actualizar
  DELETE /api/practicantes/{id}             → soft-delete (suspendido)

Horarios semanales:
  GET    /api/practicantes/{id}/horarios    → lista horarios
  POST   /api/practicantes/{id}/horarios    → crear horario (dia + hora_entrada + hora_salida)
  DELETE /api/practicantes/horarios/{hid}   → eliminar horario

Asistencia:
  GET    /api/practicantes/{id}/asistencia?desde=&hasta=  → registros
  POST   /api/practicantes/{id}/marcar-entrada            → ahora (boton rapido)
  POST   /api/practicantes/{id}/marcar-salida             → ahora (calcula horas)
  POST   /api/practicantes/{id}/asistencia                → registro manual con fecha
  PUT    /api/practicantes/asistencia/{aid}               → corregir registro
  DELETE /api/practicantes/asistencia/{aid}               → eliminar (admin)

Reportes:
  GET    /api/practicantes/{id}/reporte?periodo=mes|semana|total  → estadisticas
  GET    /api/practicantes/resumen          → KPIs globales del modulo

Cron asistido:
  POST   /api/practicantes/_cron/registrar-faltas         → marca faltas + inhabilita
"""
from routers._common import (
    router,
    _auth, _get_db, _require_admin, _require_staff, _tenant_id,
    datetime, Request, HTTPException, text,
)
from fastapi import Query
from datetime import date as _date, time as _time
import os as _os
import hmac as _hmac  # FIX 2026-05-04: timing-safe comparison para cron token


# ════════════════════════════════════════════════════════════
# CRUD PRACTICANTES
# ════════════════════════════════════════════════════════════

@router.get("/api/practicantes")
async def list_practicantes(
    request: Request,
    estado: str | None = None,
    area: str | None = None,
    busq: str | None = None,
    limit: int = Query(200, ge=1, le=500),
):
    """Lista practicantes con KPIs computados (horas hechas, faltas, %cumplimiento)."""
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        where = ["p.taller_id=:t"]
        params: dict = {"t": taller_id, "lim": limit}
        if estado:
            where.append("p.estado=:e"); params["e"] = estado
        if area:
            where.append("p.area_asignada=:a"); params["a"] = area
        if busq:
            where.append("(p.nombres ILIKE :b OR p.apellidos ILIKE :b OR p.dni LIKE :b)")
            params["b"] = f"%{busq}%"
        # FIX 2026-05-04: incluir TODOS los campos del form (incluyendo fecha_nacimiento)
        # + estado de asistencia HOY para UI de marcar entrada/salida
        sql = (
            "SELECT p.id, p.dni, p.apellidos, p.nombres, "
            "       p.fecha_nacimiento, p.sexo, p.direccion, "
            "       p.telefono, p.email, p.institucion, "
            "       p.carrera, p.ciclo_actual, p.area_asignada, p.supervisor_id, "
            "       p.fecha_inicio, p.fecha_fin, "
            "       p.horas_requeridas, p.tolerancia_faltas, p.estado, "
            "       p.foto_path, p.observaciones, p.motivo_inhabilitacion, "
            "       COALESCE((SELECT SUM(horas_trabajadas) FROM practicantes_asistencia "
            "                  WHERE practicante_id=p.id AND taller_id=p.taller_id "
            "                    AND tipo IN ('presente','tardanza','salida_anticipada')), 0)::float AS horas_hechas, "
            "       COALESCE((SELECT COUNT(*) FROM practicantes_asistencia "
            "                  WHERE practicante_id=p.id AND taller_id=p.taller_id "
            "                    AND tipo='falta'), 0) AS faltas_total, "
            "       (SELECT nombre FROM trabajadores WHERE id=p.supervisor_id) AS supervisor_nombre, "
            "       (SELECT hora_entrada::text FROM practicantes_asistencia "
            "          WHERE practicante_id=p.id AND taller_id=p.taller_id AND fecha=CURRENT_DATE) AS entrada_hoy, "
            "       (SELECT hora_salida::text FROM practicantes_asistencia "
            "          WHERE practicante_id=p.id AND taller_id=p.taller_id AND fecha=CURRENT_DATE) AS salida_hoy, "
            "       (SELECT horas_trabajadas::float FROM practicantes_asistencia "
            "          WHERE practicante_id=p.id AND taller_id=p.taller_id AND fecha=CURRENT_DATE) AS horas_hoy, "
            "       (SELECT tipo FROM practicantes_asistencia "
            "          WHERE practicante_id=p.id AND taller_id=p.taller_id AND fecha=CURRENT_DATE) AS tipo_hoy, "
            "       EXISTS(SELECT 1 FROM practicantes_horarios "
            "              WHERE practicante_id=p.id AND taller_id=p.taller_id "
            "                AND activo AND dia_semana=EXTRACT(DOW FROM CURRENT_DATE)::int - 1 + "
            "                CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)=0 THEN 7 ELSE 0 END) AS tiene_horario_hoy "
            "FROM practicantes p "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY p.estado='activo' DESC, p.apellidos, p.nombres "
            "LIMIT :lim"
        )
        rows = db.execute(text(sql), params).fetchall()
        result = []
        for r in rows:
            horas_hechas = float(r[22] or 0)
            horas_req = int(r[16] or 1)
            pct = round(horas_hechas * 100 / horas_req, 1) if horas_req > 0 else 0
            result.append({
                "id": r[0], "dni": r[1], "apellidos": r[2], "nombres": r[3],
                "nombre_completo": f"{r[2]}, {r[3]}",
                "fecha_nacimiento": str(r[4]) if r[4] else None,
                "sexo": r[5], "direccion": r[6],
                "telefono": r[7], "email": r[8], "institucion": r[9],
                "carrera": r[10], "ciclo_actual": r[11], "area_asignada": r[12],
                "supervisor_id": r[13],
                "fecha_inicio": str(r[14]) if r[14] else None,
                "fecha_fin": str(r[15]) if r[15] else None,
                "horas_requeridas": horas_req, "tolerancia_faltas": r[17],
                "estado": r[18], "foto_path": r[19], "observaciones": r[20],
                "motivo_inhabilitacion": r[21],
                "horas_hechas": horas_hechas,
                "faltas_total": int(r[23] or 0),
                "pct_cumplimiento": min(pct, 100),
                "supervisor_nombre": r[24] or "",
                # Estado de HOY (para UI marcar entrada/salida)
                "entrada_hoy": r[25],
                "salida_hoy": r[26],
                "horas_hoy": float(r[27] or 0),
                "tipo_hoy": r[28],
                "tiene_horario_hoy": bool(r[29]),
            })
        return {"practicantes": result, "total": len(result)}
    finally:
        db.close()


@router.get("/api/practicantes/resumen")
async def resumen_practicantes(request: Request):
    """KPIs globales del modulo: activos, completados, inhabilitados, horas mes, faltas mes."""
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        kpis = db.execute(text(
            "SELECT "
            "  COUNT(*) FILTER (WHERE estado='activo') AS activos, "
            "  COUNT(*) FILTER (WHERE estado='completado') AS completados, "
            "  COUNT(*) FILTER (WHERE estado='inhabilitado') AS inhabilitados, "
            "  COUNT(*) FILTER (WHERE estado='suspendido') AS suspendidos, "
            "  COUNT(*) FILTER (WHERE estado='activo' AND fecha_fin IS NOT NULL "
            "                   AND fecha_fin <= CURRENT_DATE + INTERVAL '30 days') AS proximos_vencer "
            "FROM practicantes WHERE taller_id=:t"
        ), {"t": taller_id}).fetchone()
        horas_mes = db.execute(text(
            "SELECT COALESCE(SUM(horas_trabajadas), 0)::float "
            "FROM practicantes_asistencia "
            "WHERE taller_id=:t AND fecha >= date_trunc('month', NOW())::date "
            "  AND tipo IN ('presente','tardanza','salida_anticipada')"
        ), {"t": taller_id}).scalar() or 0
        faltas_mes = db.execute(text(
            "SELECT COUNT(*) FROM practicantes_asistencia "
            "WHERE taller_id=:t AND fecha >= date_trunc('month', NOW())::date AND tipo='falta'"
        ), {"t": taller_id}).scalar() or 0
        return {
            "activos": kpis[0] or 0, "completados": kpis[1] or 0,
            "inhabilitados": kpis[2] or 0, "suspendidos": kpis[3] or 0,
            "proximos_vencer": kpis[4] or 0,
            "horas_mes": float(horas_mes), "faltas_mes": int(faltas_mes),
        }
    finally:
        db.close()


@router.get("/api/practicantes/{pid}")
async def get_practicante(pid: int, request: Request):
    """Detalle individual + horarios + ultimos 30 dias asistencia."""
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        r = db.execute(text(
            "SELECT id, dni, apellidos, nombres, fecha_nacimiento, sexo, "
            "       telefono, email, direccion, institucion, carrera, ciclo_actual, "
            "       area_asignada, supervisor_id, fecha_inicio, fecha_fin, "
            "       horas_requeridas, tolerancia_faltas, estado, motivo_inhabilitacion, "
            "       foto_path, convenio_pdf_path, observaciones, fecha_creacion "
            "FROM practicantes WHERE id=:i AND taller_id=:t"
        ), {"i": pid, "t": taller_id}).fetchone()
        if not r:
            raise HTTPException(404, "Practicante no encontrado")
        horarios = db.execute(text(
            "SELECT id, dia_semana, hora_entrada::text, hora_salida::text, activo "
            "FROM practicantes_horarios WHERE practicante_id=:i AND taller_id=:t "
            "ORDER BY dia_semana, hora_entrada"
        ), {"i": pid, "t": taller_id}).fetchall()
        asistencia = db.execute(text(
            "SELECT id, fecha, hora_entrada::text, hora_salida::text, "
            "       horas_trabajadas, tipo, observacion "
            "FROM practicantes_asistencia "
            "WHERE practicante_id=:i AND taller_id=:t AND fecha >= CURRENT_DATE - INTERVAL '30 days' "
            "ORDER BY fecha DESC"
        ), {"i": pid, "t": taller_id}).fetchall()
        horas_hechas = db.execute(text(
            "SELECT COALESCE(SUM(horas_trabajadas), 0)::float "
            "FROM practicantes_asistencia WHERE practicante_id=:i AND taller_id=:t "
            "AND tipo IN ('presente','tardanza','salida_anticipada')"
        ), {"i": pid, "t": taller_id}).scalar() or 0
        faltas_total = db.execute(text(
            "SELECT COUNT(*) FROM practicantes_asistencia "
            "WHERE practicante_id=:i AND taller_id=:t AND tipo='falta'"
        ), {"i": pid, "t": taller_id}).scalar() or 0
        return {
            "id": r[0], "dni": r[1], "apellidos": r[2], "nombres": r[3],
            "fecha_nacimiento": str(r[4]) if r[4] else None, "sexo": r[5],
            "telefono": r[6], "email": r[7], "direccion": r[8],
            "institucion": r[9], "carrera": r[10], "ciclo_actual": r[11],
            "area_asignada": r[12], "supervisor_id": r[13],
            "fecha_inicio": str(r[14]) if r[14] else None,
            "fecha_fin": str(r[15]) if r[15] else None,
            "horas_requeridas": r[16], "tolerancia_faltas": r[17],
            "estado": r[18], "motivo_inhabilitacion": r[19],
            "foto_path": r[20], "convenio_pdf_path": r[21],
            "observaciones": r[22], "fecha_creacion": str(r[23]) if r[23] else None,
            "horas_hechas": float(horas_hechas),
            "faltas_total": int(faltas_total),
            "pct_cumplimiento": round(horas_hechas * 100 / max(r[16] or 1, 1), 1),
            "horarios": [{"id": h[0], "dia_semana": h[1], "hora_entrada": h[2],
                          "hora_salida": h[3], "activo": bool(h[4])} for h in horarios],
            "asistencia_reciente": [{"id": a[0], "fecha": str(a[1]),
                                     "hora_entrada": a[2], "hora_salida": a[3],
                                     "horas_trabajadas": float(a[4] or 0),
                                     "tipo": a[5], "observacion": a[6]} for a in asistencia],
        }
    finally:
        db.close()


@router.post("/api/practicantes")
async def create_practicante(request: Request):
    """Crear practicante. Requiere admin."""
    tok = _auth(request); _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    dni = (body.get("dni") or "").strip()
    if not (len(dni) == 8 and dni.isdigit()):
        raise HTTPException(400, "DNI debe ser 8 digitos")
    apellidos = (body.get("apellidos") or "").strip()
    nombres = (body.get("nombres") or "").strip()
    if not apellidos or not nombres:
        raise HTTPException(400, "Apellidos y nombres son obligatorios")
    db = _get_db()
    try:
        # Verificar DNI duplicado
        dup = db.execute(text(
            "SELECT id FROM practicantes WHERE taller_id=:t AND dni=:d"
        ), {"t": taller_id, "d": dni}).fetchone()
        if dup:
            raise HTTPException(409, f"Ya existe un practicante con DNI {dni}")
        # FIX 2026-05-04: CAST explicito a DATE para fecha_nacimiento, inicio, fin
        # (PG no castea automaticamente string→date en algunos drivers/contextos)
        # 2026-05-04 FASE2.1: agregar 7 campos SUNAFIL al INSERT
        new_id = db.execute(text("""
            INSERT INTO practicantes (
                taller_id, dni, apellidos, nombres, fecha_nacimiento, sexo,
                telefono, email, direccion, institucion, carrera, ciclo_actual,
                area_asignada, supervisor_id, fecha_inicio, fecha_fin,
                horas_requeridas, tolerancia_faltas, estado, observaciones, creado_por,
                numero_convenio_mtpe, modalidad, subvencion_economica,
                seguro_essalud, poliza_seguro, tutor_institucion, plan_aprendizaje_path
            ) VALUES (
                :t, :dni, :apellidos, :nombres,
                CASE WHEN :fnac IS NULL OR :fnac = '' THEN NULL ELSE CAST(:fnac AS date) END,
                :sexo,
                :tel, :email, :dir, :inst, :car, :ciclo,
                :area, :sup,
                CAST(:fini AS date),
                CASE WHEN :ffin IS NULL OR :ffin = '' THEN NULL ELSE CAST(:ffin AS date) END,
                :horas, :tol, COALESCE(NULLIF(:est, ''), 'activo'), :obs, :cp,
                :ncm, :mod, CAST(:sub AS numeric), :ess, :pol, :tut, :pap
            ) RETURNING id
        """), {
            "t": taller_id, "dni": dni,
            "apellidos": apellidos, "nombres": nombres,
            "fnac": body.get("fecha_nacimiento") or None,
            "sexo": (body.get("sexo") or "").strip()[:1] or None,
            "tel": body.get("telefono") or None, "email": body.get("email") or None,
            "dir": body.get("direccion") or None,
            "inst": body.get("institucion") or "SENATI",
            "car": body.get("carrera") or "Mecánica Automotriz",
            "ciclo": body.get("ciclo_actual") or None,
            "area": body.get("area_asignada") or "mecanica",
            "sup": body.get("supervisor_id") or None,
            "fini": body.get("fecha_inicio") or _date.today().isoformat(),
            "ffin": body.get("fecha_fin") or None,
            "horas": int(body.get("horas_requeridas") or 480),
            "tol": int(body.get("tolerancia_faltas") or 4),
            "est": (body.get("estado") or "activo").strip(),
            "obs": body.get("observaciones") or None,
            "cp": tok.get("sub"),
            # SUNAFIL
            "ncm": body.get("numero_convenio_mtpe") or None,
            "mod": body.get("modalidad") or "Aprendizaje SENATI",
            "sub": float(body.get("subvencion_economica") or 0),
            "ess": bool(body.get("seguro_essalud") or False),
            "pol": body.get("poliza_seguro") or None,
            "tut": body.get("tutor_institucion") or None,
            "pap": body.get("plan_aprendizaje_path") or None,
        }).scalar()
        # FIX 2026-05-04: insertar horarios en MISMA transaccion (cron faltas requiere horarios)
        # Si falla cualquier horario, ROLLBACK del practicante completo (atomicidad)
        horarios_payload = body.get("horarios") or []
        horarios_creados = 0
        for h in horarios_payload:
            try:
                dia = int(h.get("dia_semana"))
                if not (0 <= dia <= 6):
                    continue
                _time.fromisoformat(h.get("hora_entrada", ""))  # validar formato
                _time.fromisoformat(h.get("hora_salida", ""))
            except (ValueError, TypeError):
                continue
            db.execute(text("""
                INSERT INTO practicantes_horarios
                    (taller_id, practicante_id, dia_semana, hora_entrada, hora_salida)
                VALUES (:t, :p, :d, CAST(:hi AS time), CAST(:ho AS time))
            """), {"t": taller_id, "p": int(new_id), "d": dia,
                   "hi": h["hora_entrada"], "ho": h["hora_salida"]})
            horarios_creados += 1
        db.commit()
        return {"ok": True, "id": int(new_id), "horarios_creados": horarios_creados}
    finally:
        db.close()


@router.put("/api/practicantes/{pid}")
async def update_practicante(pid: int, request: Request):
    tok = _auth(request); _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        # 2026-05-04 FASE2.2: whitelist explicita por TIPO. Antes el f-string SQL
        # interpolaba nombre de columna desde el body permitiendo cualquier campo
        # en `editable` sin distincion de tipo. Ahora cada campo tiene CAST explicito.
        # AGREGADOS FASE2.1: 7 campos SUNAFIL (numero_convenio_mtpe, modalidad,
        # subvencion_economica, seguro_essalud, poliza_seguro, tutor_institucion,
        # plan_aprendizaje_path).
        FIELD_TYPE = {
            "apellidos":             "text",
            "nombres":                "text",
            "fecha_nacimiento":       "date",
            "sexo":                   "text",
            "telefono":               "text",
            "email":                  "text",
            "direccion":              "text",
            "institucion":            "text",
            "carrera":                "text",
            "ciclo_actual":           "int",
            "area_asignada":          "text",
            "supervisor_id":          "int",
            "fecha_inicio":           "date",
            "fecha_fin":              "date",
            "horas_requeridas":       "int",
            "tolerancia_faltas":      "int",
            "estado":                 "text",
            "motivo_inhabilitacion":  "text",
            "observaciones":          "text",
            # SUNAFIL Ley 28518 / D.L. 1401
            "numero_convenio_mtpe":   "text",
            "modalidad":              "text",
            "subvencion_economica":   "numeric",
            "seguro_essalud":         "bool",
            "poliza_seguro":          "text",
            "tutor_institucion":      "text",
            "plan_aprendizaje_path":  "text",
        }
        sets = []; params: dict = {"i": pid, "t": taller_id}
        for k, v in body.items():
            tipo = FIELD_TYPE.get(k)
            if not tipo:
                continue
            if v in (None, ""):
                sets.append(f"{k} = NULL")
                continue
            if tipo == "date":
                sets.append(f"{k} = CAST(:{k} AS date)")
                params[k] = v
            elif tipo == "int":
                try: params[k] = int(v)
                except (ValueError, TypeError): continue
                sets.append(f"{k} = :{k}")
            elif tipo == "numeric":
                try: params[k] = float(v)
                except (ValueError, TypeError): continue
                sets.append(f"{k} = CAST(:{k} AS numeric)")
            elif tipo == "bool":
                params[k] = bool(v) if not isinstance(v, str) else v.lower() in ("true","1","si","sí","yes")
                sets.append(f"{k} = :{k}")
            else:  # text
                sets.append(f"{k} = :{k}")
                params[k] = str(v)
        # FIX 2026-05-04: si hay horarios en el body, reemplazar (DELETE+INSERT)
        # en MISMA transaccion. Si solo se editan otros campos, los horarios no se tocan.
        horarios_payload = body.get("horarios")
        if sets:
            db.execute(text(
                f"UPDATE practicantes SET {', '.join(sets)} WHERE id=:i AND taller_id=:t"
            ), params)
        if horarios_payload is not None and isinstance(horarios_payload, list):
            # Reemplazo total (UI envia siempre la lista completa)
            db.execute(text(
                "DELETE FROM practicantes_horarios WHERE practicante_id=:p AND taller_id=:t"
            ), {"p": pid, "t": taller_id})
            for h in horarios_payload:
                try:
                    dia = int(h.get("dia_semana"))
                    if not (0 <= dia <= 6):
                        continue
                    _time.fromisoformat(h.get("hora_entrada", ""))
                    _time.fromisoformat(h.get("hora_salida", ""))
                except (ValueError, TypeError):
                    continue
                db.execute(text("""
                    INSERT INTO practicantes_horarios
                        (taller_id, practicante_id, dia_semana, hora_entrada, hora_salida)
                    VALUES (:t, :p, :d, CAST(:hi AS time), CAST(:ho AS time))
                """), {"t": taller_id, "p": pid, "d": dia,
                       "hi": h["hora_entrada"], "ho": h["hora_salida"]})
        if not sets and horarios_payload is None:
            raise HTTPException(400, "No hay campos a actualizar")
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.delete("/api/practicantes/{pid}")
async def delete_practicante(
    pid: int,
    request: Request,
    permanente: bool = Query(False, description="Si true, elimina fisicamente (incluye horarios+asistencia via CASCADE)"),
):
    """Por defecto soft-delete (estado='suspendido', preserva historico).
    Con ?permanente=true → DELETE fisico que tambien elimina horarios y asistencia (CASCADE).
    Esta operacion es IRREVERSIBLE — el frontend debe pedir confirmacion fuerte."""
    tok = _auth(request); _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        # Verificar existe antes (para devolver 404 explicito)
        row = db.execute(text(
            "SELECT apellidos, nombres FROM practicantes WHERE id=:i AND taller_id=:t"
        ), {"i": pid, "t": taller_id}).fetchone()
        if not row:
            raise HTTPException(404, "Practicante no encontrado")
        nombre_completo = f"{row[0]}, {row[1]}"
        if permanente:
            # Audit antes de borrar (registrar en eventos_seguridad para Ley 29733)
            try:
                db.execute(text("""
                    INSERT INTO eventos_seguridad
                        (taller_id, tipo, severidad, user_id, endpoint, descripcion)
                    VALUES (:t, 'practicante_eliminado_permanente', 'WARN', :u,
                            '/api/practicantes/' || :pid, :d)
                """), {
                    "t": taller_id, "u": str(tok.get("sub") or ""),
                    "pid": str(pid),
                    "d": f"Eliminacion permanente de practicante {nombre_completo} (id={pid})",
                })
            except Exception:
                pass  # tabla puede no existir en algunos talleres antiguos; no bloquear
            # CASCADE: practicantes_horarios y practicantes_asistencia tienen ON DELETE CASCADE
            db.execute(text(
                "DELETE FROM practicantes WHERE id=:i AND taller_id=:t"
            ), {"i": pid, "t": taller_id})
            db.commit()
            return {"ok": True, "permanente": True, "eliminado": nombre_completo}
        else:
            # Soft-delete
            db.execute(text(
                "UPDATE practicantes SET estado='suspendido' WHERE id=:i AND taller_id=:t"
            ), {"i": pid, "t": taller_id})
            db.commit()
            return {"ok": True, "soft_deleted": True, "suspendido": nombre_completo}
    finally:
        db.close()


# ════════════════════════════════════════════════════════════
# HORARIOS SEMANALES
# ════════════════════════════════════════════════════════════

@router.get("/api/practicantes/{pid}/horarios")
async def list_horarios(pid: int, request: Request):
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        rows = db.execute(text(
            "SELECT id, dia_semana, hora_entrada::text, hora_salida::text, activo "
            "FROM practicantes_horarios WHERE practicante_id=:i AND taller_id=:t "
            "ORDER BY dia_semana, hora_entrada"
        ), {"i": pid, "t": taller_id}).fetchall()
        return [{"id": r[0], "dia_semana": r[1], "hora_entrada": r[2],
                 "hora_salida": r[3], "activo": bool(r[4])} for r in rows]
    finally:
        db.close()


@router.post("/api/practicantes/{pid}/horarios")
async def create_horario(pid: int, request: Request):
    tok = _auth(request); _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    try:
        dia = int(body.get("dia_semana"))
        hora_in = body.get("hora_entrada", "").strip()
        hora_out = body.get("hora_salida", "").strip()
        if not (0 <= dia <= 6):
            raise ValueError("dia_semana fuera de rango")
        # Validar formato HH:MM
        _time.fromisoformat(hora_in)
        _time.fromisoformat(hora_out)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"Datos invalidos: {e}")
    db = _get_db()
    try:
        # Verificar practicante existe
        if not db.execute(text(
            "SELECT 1 FROM practicantes WHERE id=:i AND taller_id=:t"
        ), {"i": pid, "t": taller_id}).fetchone():
            raise HTTPException(404, "Practicante no encontrado")
        new_id = db.execute(text("""
            INSERT INTO practicantes_horarios
                (taller_id, practicante_id, dia_semana, hora_entrada, hora_salida)
            VALUES (:t, :p, :d, CAST(:hi AS time), CAST(:ho AS time))
            RETURNING id
        """), {"t": taller_id, "p": pid, "d": dia, "hi": hora_in, "ho": hora_out}).scalar()
        db.commit()
        return {"ok": True, "id": int(new_id)}
    finally:
        db.close()


@router.delete("/api/practicantes/horarios/{hid}")
async def delete_horario(hid: int, request: Request):
    tok = _auth(request); _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        # FIX 2026-05-04 (backend-engineer #1): verificar rowcount → 404 explicito
        res = db.execute(text(
            "DELETE FROM practicantes_horarios WHERE id=:i AND taller_id=:t"
        ), {"i": hid, "t": taller_id})
        if res.rowcount == 0:
            raise HTTPException(404, "Horario no encontrado")
        db.commit()
        return {"ok": True}
    finally:
        db.close()


# ════════════════════════════════════════════════════════════
# ASISTENCIA (entrada / salida / registro)
# ════════════════════════════════════════════════════════════

@router.post("/api/practicantes/{pid}/marcar-entrada")
async def marcar_entrada(pid: int, request: Request):
    """Boton rapido: marca entrada AHORA. Permite re-marcar (sobrescribe hora_entrada).
    Si ya hay salida marcada, la borra (re-inicia el dia)."""
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        # FIX 2026-05-04 (backend-engineer #2): verificar existencia antes (404 vs 500 silencioso)
        if not db.execute(text(
            "SELECT 1 FROM practicantes WHERE id=:p AND taller_id=:t"
        ), {"p": pid, "t": taller_id}).fetchone():
            raise HTTPException(404, "Practicante no encontrado")
        now_t = datetime.now().time().replace(microsecond=0).isoformat()
        hoy = _date.today().isoformat()
        # FIX 2026-05-04: re-marcar entrada borra salida e horas (re-inicia el dia)
        db.execute(text("""
            INSERT INTO practicantes_asistencia
                (taller_id, practicante_id, fecha, hora_entrada, tipo, registrado_por)
            VALUES (:t, :p, CAST(:f AS date), CAST(:h AS time), 'presente', :u)
            ON CONFLICT (taller_id, practicante_id, fecha) DO UPDATE SET
                hora_entrada     = EXCLUDED.hora_entrada,
                hora_salida      = NULL,
                horas_trabajadas = 0,
                tipo             = 'presente',
                registrado_por   = EXCLUDED.registrado_por
        """), {"t": taller_id, "p": pid, "f": hoy, "h": now_t, "u": tok.get("sub")})
        db.commit()
        return {"ok": True, "fecha": hoy, "hora_entrada": now_t,
                "mensaje": f"Entrada marcada a las {now_t[:5]}"}
    finally:
        db.close()


@router.post("/api/practicantes/{pid}/marcar-salida")
async def marcar_salida(pid: int, request: Request):
    """Boton rapido: marca salida AHORA. Calcula horas_trabajadas = salida - entrada.
    FIX 2026-05-04 v2: NO crear silenciosamente — si no hay entrada, devolver 400 claro.
    Esto evita registros confusos."""
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        hoy = _date.today().isoformat()
        now_dt = datetime.now()
        now_t = now_dt.time().replace(microsecond=0).isoformat()
        # Buscar registro de hoy
        row = db.execute(text(
            "SELECT id, hora_entrada::text, hora_salida::text "
            "FROM practicantes_asistencia "
            "WHERE taller_id=:t AND practicante_id=:p AND fecha=CAST(:f AS date) FOR UPDATE"
        ), {"t": taller_id, "p": pid, "f": hoy}).fetchone()
        if not row or not row[1]:
            raise HTTPException(
                400,
                "Este practicante no ha registrado hora de entrada hoy. "
                "Marca entrada primero antes de marcar salida."
            )
        aid, hora_in, hora_salida_existente = row
        # FIX 2026-05-04 v2: si ya tiene salida marcada, mensaje claro
        if hora_salida_existente:
            raise HTTPException(
                400,
                f"Este practicante ya marcó salida hoy a las {hora_salida_existente[:5]}. "
                "Si necesitas corregirlo, edita el registro manualmente o re-marca entrada."
            )
        # Calcular horas = salida - entrada (con minutos)
        h_in = _time.fromisoformat(hora_in)
        h_out = _time.fromisoformat(now_t)
        delta_min = (h_out.hour * 60 + h_out.minute) - (h_in.hour * 60 + h_in.minute)
        horas = max(0, round(delta_min / 60.0, 2))
        db.execute(text(
            "UPDATE practicantes_asistencia "
            "SET hora_salida=CAST(:h AS time), horas_trabajadas=:hor "
            "WHERE id=:i AND taller_id=:t"
        ), {"h": now_t, "hor": horas, "i": aid, "t": taller_id})
        db.commit()
        # Format human readable: "4h 45min"
        h_int = int(horas)
        m_int = int(round((horas - h_int) * 60))
        horas_fmt = f"{h_int}h {m_int}min" if m_int else f"{h_int}h"
        return {"ok": True, "fecha": hoy, "hora_salida": now_t,
                "horas_trabajadas": horas, "horas_fmt": horas_fmt,
                "mensaje": f"Salida {now_t[:5]} — Trabajadas: {horas_fmt}"}
    finally:
        db.close()


@router.get("/api/practicantes/{pid}/asistencia")
async def list_asistencia(
    pid: int, request: Request,
    desde: str | None = None, hasta: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
):
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        where = ["taller_id=:t", "practicante_id=:p"]
        params: dict = {"t": taller_id, "p": pid, "lim": limit}
        if desde:
            where.append("fecha >= CAST(:d AS date)"); params["d"] = desde
        if hasta:
            where.append("fecha <= CAST(:h AS date)"); params["h"] = hasta
        rows = db.execute(text(
            "SELECT id, fecha, hora_entrada::text, hora_salida::text, "
            "       horas_trabajadas, tipo, observacion "
            f"FROM practicantes_asistencia WHERE {' AND '.join(where)} "
            "ORDER BY fecha DESC LIMIT :lim"
        ), params).fetchall()
        return [{"id": r[0], "fecha": str(r[1]),
                 "hora_entrada": r[2], "hora_salida": r[3],
                 "horas_trabajadas": float(r[4] or 0),
                 "tipo": r[5], "observacion": r[6]} for r in rows]
    finally:
        db.close()


@router.post("/api/practicantes/{pid}/asistencia")
async def create_asistencia_manual(pid: int, request: Request):
    """Registro manual con fecha (para corregir asistencia atrasada)."""
    tok = _auth(request); _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    fecha = body.get("fecha") or _date.today().isoformat()
    tipo = (body.get("tipo") or "presente").strip()
    if tipo not in ("presente", "falta", "tardanza", "justificado", "salida_anticipada"):
        raise HTTPException(400, f"Tipo invalido: {tipo}")
    h_in = body.get("hora_entrada") or None
    h_out = body.get("hora_salida") or None
    horas = float(body.get("horas_trabajadas") or 0)
    if h_in and h_out and horas == 0:
        try:
            d_min = (_time.fromisoformat(h_out).hour * 60 + _time.fromisoformat(h_out).minute) \
                  - (_time.fromisoformat(h_in).hour * 60 + _time.fromisoformat(h_in).minute)
            horas = max(0, round(d_min / 60.0, 2))
        except Exception:
            pass
    db = _get_db()
    try:
        new_id = db.execute(text("""
            INSERT INTO practicantes_asistencia
                (taller_id, practicante_id, fecha, hora_entrada, hora_salida,
                 horas_trabajadas, tipo, observacion, registrado_por)
            VALUES (:t, :p, CAST(:f AS date),
                    CASE WHEN :hi IS NULL OR :hi = '' THEN NULL ELSE CAST(:hi AS time) END,
                    CASE WHEN :ho IS NULL OR :ho = '' THEN NULL ELSE CAST(:ho AS time) END,
                    :hor, :tip, :obs, :u)
            ON CONFLICT (taller_id, practicante_id, fecha) DO UPDATE SET
                hora_entrada     = EXCLUDED.hora_entrada,
                hora_salida      = EXCLUDED.hora_salida,
                horas_trabajadas = EXCLUDED.horas_trabajadas,
                tipo             = EXCLUDED.tipo,
                observacion      = EXCLUDED.observacion
            RETURNING id
        """), {"t": taller_id, "p": pid, "f": fecha,
               "hi": h_in, "ho": h_out, "hor": horas, "tip": tipo,
               "obs": body.get("observacion") or "", "u": tok.get("sub")}).scalar()
        db.commit()
        return {"ok": True, "id": int(new_id)}
    finally:
        db.close()


@router.put("/api/practicantes/asistencia/{aid}")
async def update_asistencia(aid: int, request: Request):
    tok = _auth(request); _require_admin(tok)
    taller_id = _tenant_id(tok)
    body = await request.json()
    db = _get_db()
    try:
        editable = {"hora_entrada", "hora_salida", "horas_trabajadas", "tipo", "observacion"}
        sets = []; params: dict = {"i": aid, "t": taller_id}
        for k, v in body.items():
            if k in editable:
                if k in ("hora_entrada", "hora_salida"):
                    if v in (None, ""):
                        sets.append(f"{k} = NULL")
                    else:
                        sets.append(f"{k} = CAST(:{k} AS time)")
                        params[k] = v
                else:
                    sets.append(f"{k} = :{k}")
                    params[k] = v
        if not sets:
            raise HTTPException(400, "No hay campos a actualizar")
        db.execute(text(
            f"UPDATE practicantes_asistencia SET {', '.join(sets)} WHERE id=:i AND taller_id=:t"
        ), params)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.delete("/api/practicantes/asistencia/{aid}")
async def delete_asistencia(aid: int, request: Request):
    tok = _auth(request); _require_admin(tok)
    taller_id = _tenant_id(tok)
    db = _get_db()
    try:
        # FIX 2026-05-04 (security-reviewer #4): audit + 404 explicito
        # Eliminar asistencia afecta calculo horas SENATI → exige trazabilidad Ley 29733
        row = db.execute(text(
            "SELECT practicante_id, fecha, tipo, horas_trabajadas FROM practicantes_asistencia "
            "WHERE id=:i AND taller_id=:t"
        ), {"i": aid, "t": taller_id}).fetchone()
        if not row:
            raise HTTPException(404, "Registro de asistencia no encontrado")
        # Audit en MISMA transaccion (no silenciar)
        try:
            db.execute(text("""
                INSERT INTO eventos_seguridad
                    (taller_id, tipo, severidad, user_id, endpoint, descripcion)
                VALUES (:t, 'asistencia_eliminada', 'WARN', :u,
                        '/api/practicantes/asistencia/' || :aid,
                        :d)
            """), {
                "t": taller_id, "u": str(tok.get("sub") or ""), "aid": str(aid),
                "d": (f"Eliminacion asistencia id={aid}, practicante_id={row[0]}, "
                      f"fecha={row[1]}, tipo={row[2]}, horas={row[3]}"),
            })
        except Exception:
            pass  # tabla puede no existir en talleres antiguos
        db.execute(text(
            "DELETE FROM practicantes_asistencia WHERE id=:i AND taller_id=:t"
        ), {"i": aid, "t": taller_id})
        db.commit()
        return {"ok": True, "fecha_eliminada": str(row[1]), "tipo": row[2]}
    finally:
        db.close()


# ════════════════════════════════════════════════════════════
# REPORTES
# ════════════════════════════════════════════════════════════

@router.get("/api/practicantes/{pid}/reporte")
async def reporte_practicante(
    pid: int, request: Request,
    periodo: str = Query("total", pattern="^(semana|mes|total)$"),
):
    """Reporte de cumplimiento del practicante (semana / mes / total)."""
    tok = _auth(request); _require_staff(tok)
    taller_id = _tenant_id(tok)
    if periodo == "semana":
        where_fecha = "AND fecha >= date_trunc('week', NOW())::date"
    elif periodo == "mes":
        where_fecha = "AND fecha >= date_trunc('month', NOW())::date"
    else:
        where_fecha = ""
    db = _get_db()
    try:
        # Datos del practicante
        p = db.execute(text(
            "SELECT apellidos, nombres, horas_requeridas, tolerancia_faltas, estado "
            "FROM practicantes WHERE id=:i AND taller_id=:t"
        ), {"i": pid, "t": taller_id}).fetchone()
        if not p:
            raise HTTPException(404, "Practicante no encontrado")
        # Estadisticas asistencia
        stats = db.execute(text(
            "SELECT "
            "  COALESCE(SUM(horas_trabajadas) FILTER "
            "    (WHERE tipo IN ('presente','tardanza','salida_anticipada')), 0)::float AS horas, "
            "  COUNT(*) FILTER (WHERE tipo='presente') AS dias_presente, "
            "  COUNT(*) FILTER (WHERE tipo='falta') AS faltas, "
            "  COUNT(*) FILTER (WHERE tipo='tardanza') AS tardanzas, "
            "  COUNT(*) FILTER (WHERE tipo='justificado') AS justificadas "
            f"FROM practicantes_asistencia WHERE taller_id=:t AND practicante_id=:p {where_fecha}"
        ), {"t": taller_id, "p": pid}).fetchone()
        horas = float(stats[0] or 0)
        horas_req = int(p[2] or 1)
        return {
            "practicante": {
                "nombre_completo": f"{p[0]}, {p[1]}",
                "horas_requeridas": horas_req,
                "tolerancia_faltas": p[3],
                "estado": p[4],
            },
            "periodo": periodo,
            "horas_hechas": horas,
            "horas_pendientes": max(0, horas_req - horas),
            "pct_cumplimiento": min(round(horas * 100 / horas_req, 1), 100) if horas_req else 0,
            "dias_presente": int(stats[1] or 0),
            "faltas": int(stats[2] or 0),
            "tardanzas": int(stats[3] or 0),
            "justificadas": int(stats[4] or 0),
        }
    finally:
        db.close()


# ════════════════════════════════════════════════════════════
# CRON: detectar faltas + inhabilitar
# ════════════════════════════════════════════════════════════

@router.post("/api/practicantes/_cron/registrar-faltas")
async def cron_registrar_faltas(request: Request):
    """
    Cron diario (22:00): para cada practicante activo, si HOY es dia de su horario
    y NO tiene registro de asistencia → marca FALTA.
    Si total faltas > tolerancia_faltas → estado='inhabilitado' automatico.

    Endpoint protegido: requiere admin O header X-Cron-Token (configurable).
    """
    # FIX 2026-05-04 (security-reviewer #1): hmac.compare_digest contra timing attack
    # _os y _hmac importados al top del modulo (antes 'import os' inline en cada llamada)
    cron_token = (_os.environ.get('CRON_TOKEN') or '').strip()
    header_tok = request.headers.get('X-Cron-Token', '').strip()
    if cron_token and header_tok and _hmac.compare_digest(header_tok, cron_token):
        pass  # autenticado por cron (timing-safe)
    else:
        tok = _auth(request); _require_admin(tok)
    db = _get_db()
    try:
        # Iterar TODOS los talleres (cron es global). Para cada (taller, practicante)
        # activo y dia de horario hoy → falta si no hay registro
        hoy = _date.today()
        # weekday: 0=lunes, 6=domingo (Python ya está en formato ISO)
        dia_sem = hoy.weekday()
        # Buscar practicantes activos con horario para hoy y sin registro
        rows = db.execute(text(
            "SELECT DISTINCT p.taller_id, p.id "
            "FROM practicantes p "
            "JOIN practicantes_horarios h ON h.practicante_id=p.id "
            "                              AND h.taller_id=p.taller_id "
            "                              AND h.activo "
            "                              AND h.dia_semana=:d "
            "WHERE p.estado='activo' "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM practicantes_asistencia a "
            "    WHERE a.practicante_id=p.id "
            "      AND a.taller_id=p.taller_id "
            "      AND a.fecha=CAST(:f AS date)"
            "  )"
        ), {"d": dia_sem, "f": hoy.isoformat()}).fetchall()
        registrados = 0; inhabilitados = 0
        for taller_id, pid in rows:
            # Setear contexto RLS antes de operar
            db.execute(text("SET LOCAL app.taller_id = :t"), {"t": taller_id})
            # Insertar falta
            db.execute(text("""
                INSERT INTO practicantes_asistencia
                    (taller_id, practicante_id, fecha, tipo, observacion)
                VALUES (:t, :p, CAST(:f AS date), 'falta',
                        'Marcado automaticamente por cron (sin registro de entrada)')
                ON CONFLICT (taller_id, practicante_id, fecha) DO NOTHING
            """), {"t": taller_id, "p": pid, "f": hoy.isoformat()})
            registrados += 1
            # FIX 2026-05-04 (contador-experto): COUNT solo faltas NO justificadas
            # (las justificadas no deben contar para inhabilitacion → falso positivo legal)
            res = db.execute(text(
                "SELECT p.tolerancia_faltas, "
                "       (SELECT COUNT(*) FROM practicantes_asistencia "
                "          WHERE practicante_id=p.id AND taller_id=p.taller_id "
                "            AND tipo='falta') AS faltas "
                "FROM practicantes p WHERE p.id=:i AND p.taller_id=:t"
            ), {"i": pid, "t": taller_id}).fetchone()
            if res and int(res[1] or 0) > int(res[0] or 0):
                # INHABILITAR
                db.execute(text("""
                    UPDATE practicantes
                    SET estado='inhabilitado',
                        motivo_inhabilitacion=:m,
                        fecha_inhabilitacion=NOW()
                    WHERE id=:i AND taller_id=:t
                """), {
                    "i": pid, "t": taller_id,
                    "m": f"Excedio tolerancia de {res[0]} faltas (total: {res[1]})"
                })
                inhabilitados += 1
        db.commit()
        return {
            "ok": True, "fecha": hoy.isoformat(),
            "faltas_registradas": registrados,
            "inhabilitados": inhabilitados,
        }
    finally:
        db.close()
