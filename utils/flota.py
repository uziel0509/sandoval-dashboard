"""
SANDOVAL PRO — Módulo de Flota Empresarial + Web Push.

Contiene:
  - login_dual_detect: detecta si el password recibido es de jefe (DNI/RUC del cliente)
                       o de conductor (RUC inicial / PIN custom).
  - Helpers CRUD de conductores asignados a vehículos.
  - send_push_to_user: envía notificación push a un cliente, conductor o staff.
  - notify_orden_event: punto único de despacho de notificaciones cuando algo
                        cambia en una orden (cambio de fase, presupuesto listo,
                        lista para entrega).

Diseño:
  - 1 conductor asignado por vehículo (campos conductor_* en tabla vehiculos).
  - El RUC del cliente "empresa" funciona como PIN inicial del conductor;
    al primer login el conductor lo cambia (flag conductor_pin_must_change).
  - Las acciones sensibles quedan auditadas en flota_audit_log.
"""

from __future__ import annotations
import json
import secrets
import string
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import text as _t

# ──────────────────────────────────────────────────────────────────────
# CONFIG / VAPID
# ──────────────────────────────────────────────────────────────────────
_VAPID_CACHE: Dict[str, str] = {}


def _load_vapid(db) -> Dict[str, str]:
    """Lee las VAPID keys desde app_config (cache en memoria)."""
    if _VAPID_CACHE:
        return _VAPID_CACHE
    rows = db.execute(_t(
        "SELECT key, value FROM app_config WHERE key IN ('vapid_private','vapid_public','vapid_subject')"
    )).fetchall()
    for k, v in rows:
        _VAPID_CACHE[k] = v
    return _VAPID_CACHE


def get_vapid_public(db) -> str:
    """Devuelve la VAPID public key (la consume el frontend al suscribirse)."""
    return _load_vapid(db).get('vapid_public', '')


# ──────────────────────────────────────────────────────────────────────
# AUDIT
# ──────────────────────────────────────────────────────────────────────
def audit(db, *, taller_id: int, cliente_id: str, placa: Optional[str],
          accion: str, detalle: str = '', actor_tipo: str = 'sistema',
          actor_id: str = '', ip: str = '') -> None:
    """Inserta una entrada en flota_audit_log (no levanta excepciones)."""
    try:
        db.execute(_t("""
            INSERT INTO flota_audit_log
              (taller_id, cliente_id, vehiculo_placa, accion, detalle,
               actor_tipo, actor_id, ip)
            VALUES (:t, :c, :p, :a, :d, :at, :ai, :ip)
        """), {
            't': taller_id, 'c': cliente_id, 'p': placa, 'a': accion,
            'd': detalle[:1000], 'at': actor_tipo, 'ai': actor_id, 'ip': ip,
        })
        db.commit()
    except Exception:
        db.rollback()


# ──────────────────────────────────────────────────────────────────────
# LOGIN DUAL — JEFE vs CONDUCTOR
# ──────────────────────────────────────────────────────────────────────
def detect_login_role(db, *, placa_raw: str, password: str,
                      bcrypt_verify, bcrypt_hash) -> Optional[Dict[str, Any]]:
    """
    Devuelve dict con info del usuario logueado, o None si no matchea.

    Prioridad de detección (importante: conductor PRIMERO si tiene asignación):
      1. Buscar vehículo por placa (bypass RLS).
      2. Si vehículo tiene conductor asignado activo:
         a. Si tiene conductor_pin_hash y password matchea → CONDUCTOR (PIN custom).
         b. Si NO tiene hash y password == documento del cliente (RUC) → CONDUCTOR (PIN inicial).
      3. Si no matchea como conductor, intentar como JEFE/CLIENTE:
         a. password == cliente.pin_acceso (bcrypt) → CLIENTE.
         b. password == cliente.documento (DNI/RUC inicial) → CLIENTE, hashear.
         c. password == cliente_id literal → CLIENTE.
      4. None.
    """
    import re
    placa_norm = (placa_raw or '').strip().upper()
    placa_alnum = re.sub(r'[^A-Z0-9]', '', placa_norm)

    row = db.execute(_t(
        "SELECT cliente_id, taller_id, placa, pin_acceso, documento "
        "FROM lookup_cliente_by_placa(:p)"
    ), {"p": placa_norm}).fetchone()
    if not row and placa_alnum:
        for variante in (placa_alnum, f"{placa_alnum[:3]}-{placa_alnum[3:]}" if len(placa_alnum) >= 4 else placa_alnum):
            row = db.execute(_t(
                "SELECT cliente_id, taller_id, placa, pin_acceso, documento "
                "FROM lookup_cliente_by_placa(:p)"
            ), {"p": variante}).fetchone()
            if row:
                break
    if not row:
        return None

    cliente_id, taller_id, placa_real, pin_acceso, documento = row
    if not cliente_id:
        return None
    taller_id = int(taller_id)
    pin_acceso = pin_acceso or ''
    documento = documento or ''

    # Setear contexto RLS para los queries siguientes
    try:
        db.execute(_t("SELECT set_config('app.taller_id', :t, false)"), {"t": str(taller_id)})
    except Exception:
        pass

    # Tipo del cliente (individual o empresa)
    tipo_row = db.execute(_t(
        "SELECT COALESCE(nombre,''), COALESCE(apellidos,''), telefono, COALESCE(tipo_cliente,'individual') "
        "FROM clientes WHERE id=:c AND taller_id=:t"
    ), {"c": cliente_id, "t": taller_id}).fetchone()
    cli_nombre = ((tipo_row[0] if tipo_row else '') + ' ' + (tipo_row[1] if tipo_row else '')).strip() or cliente_id
    cli_tel = (tipo_row[2] if tipo_row else '') or ''
    tipo_cliente = (tipo_row[3] if tipo_row else 'individual')

    # Info del conductor asignado al vehículo
    veh = db.execute(_t("""
        SELECT conductor_nombre, conductor_telefono, conductor_email,
               conductor_pin_hash, conductor_pin_must_change,
               COALESCE(conductor_activo, TRUE)
          FROM vehiculos
         WHERE placa=:p AND taller_id=:t
    """), {"p": placa_real, "t": taller_id}).fetchone()

    has_conductor = bool(veh and veh[0])
    cond_activo = bool(veh and veh[5])
    c_nombre = veh[0] if veh else None
    c_tel = veh[1] if veh else ''
    c_email = veh[2] if veh else ''
    c_pin_hash = veh[3] if veh else None

    # ═════════ CLIENTE INDIVIDUAL (persona normal) ═════════
    # Mantiene comportamiento legacy: ve todas SUS órdenes con cliente_id.
    if tipo_cliente != 'empresa':
        is_cliente = False
        if pin_acceso:
            try:
                is_cliente = bcrypt_verify(password, pin_acceso)
            except Exception:
                is_cliente = False
        if not is_cliente and documento and password.strip() == str(documento).strip():
            is_cliente = True
        # SECURITY 2026-04-26: removido el match con cliente_id literal.
        # El cliente_id es visible en URLs/UI publicas (formato CLI-...) → no debe servir como auth.
        # Si el cliente nunca cambio el PIN inicial, debe usar el documento (DNI/RUC).
        if is_cliente:
            return {
                'kind': 'cliente',
                'cliente_id': cliente_id,
                'taller_id': taller_id,
                'placa': placa_real,
                'nombre': cli_nombre,
                'telefono': cli_tel,
                'tipo_cliente': 'individual',
            }
        return None

    # ═════════ EMPRESA: jefe vs conductor ═════════
    # Regla simple y sin ambigüedad:
    #   • placa + PIN propio del JEFE (bcrypt match contra cliente.pin_acceso) → JEFE (toda la flota)
    #   • placa + PIN del conductor (bcrypt match contra vehiculos.conductor_pin_hash) → CONDUCTOR (solo placa)
    #   • placa + RUC empresa (string match con clientes.documento)               → CONDUCTOR (solo placa)
    # El RUC SIEMPRE es para conductor, nunca para jefe. El jefe debe usar su PIN propio (generado por el admin).

    # 1) JEFE: pin_acceso bcrypt match
    if pin_acceso:
        try:
            if bcrypt_verify(password, pin_acceso):
                # Doble check: si la pass coincide con el documento crudo y el hash es del documento,
                # significa que el pin_acceso aún es el RUC inicial → tratar como CONDUCTOR, no jefe.
                if not (documento and password.strip() == str(documento).strip()):
                    return {
                        'kind': 'cliente',
                        'cliente_id': cliente_id,
                        'taller_id': taller_id,
                        'placa': placa_real,
                        'nombre': cli_nombre,
                        'telefono': cli_tel,
                        'tipo_cliente': 'empresa',
                    }
        except Exception:
            pass

    # Si la placa tiene conductor asignado y está bloqueado, no permitir login de conductor
    if has_conductor and not cond_activo:
        # El JEFE ya falló arriba si llegó hasta acá. Devolvemos blocked para mostrar el msj correcto.
        return {'kind': 'blocked'}

    # 2) CONDUCTOR con PIN custom (placa + PIN cambiado por el conductor)
    if has_conductor and c_pin_hash:
        try:
            if bcrypt_verify(password, c_pin_hash):
                return {
                    'kind': 'conductor',
                    'cliente_id': cliente_id,
                    'taller_id': taller_id,
                    'placa': placa_real,
                    'nombre': c_nombre,
                    'telefono': c_tel or '',
                    'email': c_email or '',
                    'must_change': bool(veh[4]) if veh else False,
                }
        except Exception:
            pass

    # 3) CONDUCTOR con RUC inicial (placa + RUC empresa, conductor con o sin asignación)
    if documento and password.strip() == str(documento).strip():
        # Conductor de esta placa específica. Si no estaba registrado, lo creamos virtual.
        return {
            'kind': 'conductor',
            'cliente_id': cliente_id,
            'taller_id': taller_id,
            'placa': placa_real,
            'nombre': c_nombre or 'Conductor',
            'telefono': c_tel or '',
            'email': c_email or '',
            'must_change': True,  # forzar cambio de PIN
        }

    return None


# ──────────────────────────────────────────────────────────────────────
# CRUD CONDUCTORES
# ──────────────────────────────────────────────────────────────────────
def listar_flota(db, *, taller_id: int, cliente_id: str) -> List[Dict[str, Any]]:
    """Lista todos los vehículos de un cliente con info de su conductor."""
    rows = db.execute(_t("""
        SELECT placa, marca, modelo, año, color,
               conductor_nombre, conductor_dni, conductor_telefono,
               conductor_email, conductor_pin_must_change,
               COALESCE(conductor_activo, TRUE),
               conductor_assigned_at, conductor_assigned_by
          FROM vehiculos
         WHERE cliente_id=:c AND taller_id=:t
         ORDER BY placa
    """), {"c": cliente_id, "t": taller_id}).fetchall()
    out = []
    for r in rows:
        out.append({
            'placa': r[0], 'marca': r[1] or '', 'modelo': r[2] or '',
            'anio': r[3] or '', 'color': r[4] or '',
            'conductor_nombre': r[5] or '', 'conductor_dni': r[6] or '',
            'conductor_telefono': r[7] or '', 'conductor_email': r[8] or '',
            'conductor_must_change': bool(r[9]) if r[9] is not None else True,
            'conductor_activo': bool(r[10]),
            'conductor_assigned_at': str(r[11] or ''),
            'conductor_assigned_by': r[12] or '',
            'has_conductor': bool(r[5]),
        })
    return out


def asignar_conductor(db, *, taller_id: int, cliente_id: str, placa: str,
                      nombre: str, dni: str = '', telefono: str = '',
                      email: str = '', pin_inicial: Optional[str] = None,
                      bcrypt_hash=None, actor_tipo: str = 'admin_taller',
                      actor_id: str = '', ip: str = '') -> Dict[str, Any]:
    """
    Asigna o actualiza el conductor de un vehículo.
    Si pin_inicial es None → usa el RUC del cliente (al login el conductor lo cambia).
    Si pin_inicial se pasa → se hashea y se guarda.
    Retorna el PIN en texto claro SOLO si fue generado/seteado en este call,
    para que el caller lo muestre/comparta una sola vez.
    """
    veh = db.execute(_t("SELECT placa FROM vehiculos WHERE placa=:p AND taller_id=:t AND cliente_id=:c"),
                     {"p": placa, "t": taller_id, "c": cliente_id}).fetchone()
    if not veh:
        raise ValueError('Vehículo no pertenece a ese cliente')
    if not nombre or not nombre.strip():
        raise ValueError('Nombre del conductor requerido')

    pin_hash = None
    pin_plano_devuelto = None
    if pin_inicial and bcrypt_hash:
        pin_hash = bcrypt_hash(pin_inicial)
        pin_plano_devuelto = pin_inicial

    db.execute(_t("""
        UPDATE vehiculos SET
          conductor_nombre = :n,
          conductor_dni = :d,
          conductor_telefono = :tel,
          conductor_email = :em,
          conductor_pin_hash = :ph,
          conductor_pin_must_change = TRUE,
          conductor_activo = TRUE,
          conductor_assigned_at = NOW(),
          conductor_assigned_by = :ab
        WHERE placa = :p AND taller_id = :t
    """), {
        'n': nombre.strip(), 'd': (dni or '').strip(),
        'tel': (telefono or '').strip(), 'em': (email or '').strip(),
        'ph': pin_hash, 'ab': actor_id[:20], 'p': placa, 't': taller_id,
    })
    db.commit()

    audit(db, taller_id=taller_id, cliente_id=cliente_id, placa=placa,
          accion='conductor_assigned',
          detalle=f"nombre={nombre} dni={dni} tel={telefono}",
          actor_tipo=actor_tipo, actor_id=actor_id, ip=ip)

    return {'placa': placa, 'pin_inicial': pin_plano_devuelto}


def reset_pin_conductor(db, *, taller_id: int, cliente_id: str, placa: str,
                        bcrypt_hash, actor_tipo: str = 'admin_taller',
                        actor_id: str = '', ip: str = '') -> str:
    """Genera un PIN nuevo de 6 dígitos y lo guarda hasheado. Retorna el PIN crudo (UNA VEZ)."""
    pin = ''.join(secrets.choice(string.digits) for _ in range(6))
    pin_hash = bcrypt_hash(pin)
    db.execute(_t("""
        UPDATE vehiculos SET
          conductor_pin_hash = :ph,
          conductor_pin_must_change = TRUE,
          conductor_activo = TRUE
        WHERE placa = :p AND taller_id = :t AND cliente_id = :c
    """), {'ph': pin_hash, 'p': placa, 't': taller_id, 'c': cliente_id})
    db.commit()
    audit(db, taller_id=taller_id, cliente_id=cliente_id, placa=placa,
          accion='pin_reset', actor_tipo=actor_tipo, actor_id=actor_id, ip=ip)
    return pin


def conductor_change_pin(db, *, taller_id: int, placa: str, new_pin: str,
                         bcrypt_hash, ip: str = '') -> None:
    """El propio conductor cambia su PIN (después del primer login)."""
    if not new_pin or len(str(new_pin)) < 4:
        raise ValueError('PIN debe tener al menos 4 caracteres')
    pin_hash = bcrypt_hash(str(new_pin))
    db.execute(_t("""
        UPDATE vehiculos SET
          conductor_pin_hash = :ph,
          conductor_pin_must_change = FALSE
        WHERE placa = :p AND taller_id = :t
    """), {'ph': pin_hash, 'p': placa, 't': taller_id})
    db.commit()
    cli = db.execute(_t("SELECT cliente_id FROM vehiculos WHERE placa=:p AND taller_id=:t"),
                     {'p': placa, 't': taller_id}).fetchone()
    audit(db, taller_id=taller_id, cliente_id=(cli[0] if cli else ''), placa=placa,
          accion='pin_changed', actor_tipo='conductor', actor_id=placa, ip=ip)


def cliente_change_password(db, *, taller_id: int, cliente_id: str,
                            new_password: str, bcrypt_hash, ip: str = '') -> None:
    """El jefe / cliente cambia su propia contraseña (pin_acceso)."""
    if not new_password or len(str(new_password)) < 4:
        raise ValueError('Contraseña debe tener al menos 4 caracteres')
    new_hash = bcrypt_hash(str(new_password))
    db.execute(_t("UPDATE clientes SET pin_acceso=:h WHERE id=:c AND taller_id=:t"),
               {'h': new_hash, 'c': cliente_id, 't': taller_id})
    db.commit()
    audit(db, taller_id=taller_id, cliente_id=cliente_id, placa=None,
          accion='pin_changed', actor_tipo='jefe_empresa', actor_id=cliente_id, ip=ip)


def desactivar_conductor(db, *, taller_id: int, cliente_id: str, placa: str,
                         actor_tipo: str = 'admin_taller', actor_id: str = '',
                         ip: str = '') -> None:
    db.execute(_t("UPDATE vehiculos SET conductor_activo=FALSE WHERE placa=:p AND taller_id=:t AND cliente_id=:c"),
               {'p': placa, 't': taller_id, 'c': cliente_id})
    db.commit()
    audit(db, taller_id=taller_id, cliente_id=cliente_id, placa=placa,
          accion='conductor_deactivated', actor_tipo=actor_tipo, actor_id=actor_id, ip=ip)


def activar_conductor(db, *, taller_id: int, cliente_id: str, placa: str,
                      actor_tipo: str = 'admin_taller', actor_id: str = '',
                      ip: str = '') -> None:
    db.execute(_t("UPDATE vehiculos SET conductor_activo=TRUE WHERE placa=:p AND taller_id=:t AND cliente_id=:c"),
               {'p': placa, 't': taller_id, 'c': cliente_id})
    db.commit()
    audit(db, taller_id=taller_id, cliente_id=cliente_id, placa=placa,
          accion='conductor_activated', actor_tipo=actor_tipo, actor_id=actor_id, ip=ip)


def quitar_conductor(db, *, taller_id: int, cliente_id: str, placa: str,
                     actor_tipo: str = 'admin_taller', actor_id: str = '',
                     ip: str = '') -> None:
    db.execute(_t("""
        UPDATE vehiculos SET
          conductor_nombre=NULL, conductor_dni=NULL, conductor_telefono=NULL,
          conductor_email=NULL, conductor_pin_hash=NULL,
          conductor_pin_must_change=TRUE, conductor_activo=TRUE
        WHERE placa=:p AND taller_id=:t AND cliente_id=:c
    """), {'p': placa, 't': taller_id, 'c': cliente_id})
    db.commit()
    audit(db, taller_id=taller_id, cliente_id=cliente_id, placa=placa,
          accion='conductor_removed', actor_tipo=actor_tipo, actor_id=actor_id, ip=ip)


def get_audit(db, *, taller_id: int, cliente_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Historial de cambios visible para el jefe."""
    rows = db.execute(_t("""
        SELECT fecha, vehiculo_placa, accion, detalle, actor_tipo, actor_id
          FROM flota_audit_log
         WHERE taller_id=:t AND cliente_id=:c
         ORDER BY fecha DESC
         LIMIT :lim
    """), {'t': taller_id, 'c': cliente_id, 'lim': limit}).fetchall()
    return [{
        'fecha': str(r[0]), 'placa': r[1], 'accion': r[2],
        'detalle': r[3] or '', 'actor_tipo': r[4], 'actor_id': r[5],
    } for r in rows]


# ──────────────────────────────────────────────────────────────────────
# WEB PUSH — suscripciones + envío
# ──────────────────────────────────────────────────────────────────────
def save_push_subscription(db, *, taller_id: int, user_kind: str,
                           user_id_str: str, sub: Dict[str, Any],
                           user_agent: str = '') -> int:
    """
    Guarda o actualiza una suscripción push para un usuario.
    sub = { endpoint, keys: { p256dh, auth } }
    """
    endpoint = sub.get('endpoint', '')
    keys = sub.get('keys') or {}
    p256dh = keys.get('p256dh', '')
    auth = keys.get('auth', '')
    if not endpoint or not p256dh or not auth:
        raise ValueError('Suscripción inválida')

    # Reglas RLS de la tabla original requieren taller_id matcheando contexto
    db.execute(_t("SELECT set_config('app.taller_id', :t, false)"), {'t': str(taller_id)})

    # Si ya existe el endpoint, lo actualiza (re-asignar a otro usuario si cambia)
    db.execute(_t("""
        INSERT INTO push_subscriptions
          (taller_id, user_kind, user_id_str, endpoint, p256dh, auth, user_agent, last_used)
        VALUES (:t, :uk, :uid, :ep, :p, :a, :ua, NOW())
        ON CONFLICT (endpoint) DO UPDATE SET
          user_kind = EXCLUDED.user_kind,
          user_id_str = EXCLUDED.user_id_str,
          p256dh = EXCLUDED.p256dh,
          auth = EXCLUDED.auth,
          user_agent = EXCLUDED.user_agent,
          last_used = NOW(),
          enabled = TRUE
    """), {
        't': taller_id, 'uk': user_kind, 'uid': user_id_str,
        'ep': endpoint, 'p': p256dh, 'a': auth, 'ua': user_agent[:500],
    })
    db.commit()
    return 1


def delete_push_subscription(db, *, endpoint: str) -> None:
    db.execute(_t("DELETE FROM push_subscriptions WHERE endpoint=:e"), {'e': endpoint})
    db.commit()


def _send_one(sub_endpoint: str, sub_p256dh: str, sub_auth: str,
              payload: Dict[str, Any], vapid_priv: str, vapid_subject: str) -> bool:
    """Envía 1 push. Retorna True si OK, False si falló (no levanta)."""
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return False
    sub = {'endpoint': sub_endpoint, 'keys': {'p256dh': sub_p256dh, 'auth': sub_auth}}
    try:
        webpush(
            subscription_info=sub,
            data=json.dumps(payload),
            vapid_private_key=vapid_priv,
            vapid_claims={'sub': vapid_subject},
            timeout=8,
        )
        return True
    except Exception as e:
        # Endpoint expirado / desuscrito → debería borrarse
        msg = str(e)
        if '410' in msg or '404' in msg:
            return False  # caller puede borrar el endpoint
        return False


def send_push_to_user(db, *, taller_id: int, user_kind: str,
                      user_id_str: str, title: str, body: str,
                      url: str = '/portal/', icon: str = '/portal/icons/icon-192.png',
                      tag: str = '', data: Optional[Dict[str, Any]] = None) -> int:
    """
    Envía notificación push a TODAS las suscripciones de un usuario.
    Devuelve cuántas se enviaron OK.
    """
    db.execute(_t("SELECT set_config('app.taller_id', :t, false)"), {'t': str(taller_id)})
    vapid = _load_vapid(db)
    priv = vapid.get('vapid_private', '')
    subj = vapid.get('vapid_subject', 'mailto:soporte@sandoval.pe')
    if not priv:
        return 0
    rows = db.execute(_t("""
        SELECT id, endpoint, p256dh, auth FROM push_subscriptions
         WHERE taller_id=:t AND user_kind=:uk AND user_id_str=:uid AND enabled=TRUE
    """), {'t': taller_id, 'uk': user_kind, 'uid': user_id_str}).fetchall()
    payload = {
        'title': title[:80], 'body': body[:200], 'url': url,
        'icon': icon, 'tag': tag or f'{user_kind}-{user_id_str}',
        'data': data or {},
    }
    ok = 0
    for r in rows:
        if _send_one(r[1], r[2], r[3], payload, priv, subj):
            ok += 1
        else:
            # Borrar suscripción rota
            try:
                db.execute(_t("DELETE FROM push_subscriptions WHERE id=:i"), {'i': r[0]})
                db.commit()
            except Exception:
                db.rollback()
    return ok


# ──────────────────────────────────────────────────────────────────────
# DESTINATARIOS DE NOTIFS DE UNA ORDEN
# ──────────────────────────────────────────────────────────────────────
def destinatarios_orden(db, *, taller_id: int, consecutivo: str) -> List[Dict[str, Any]]:
    """
    Para una orden, devuelve lista de destinatarios (jefe + conductor de la placa).
    Cada destinatario: { kind: 'cliente'|'conductor', id, nombre, telefono }.
    """
    db.execute(_t("SELECT set_config('app.taller_id', :t, false)"), {'t': str(taller_id)})
    row = db.execute(_t("""
        SELECT o.cliente_id, o.vehiculo_placa,
               c.nombre, c.apellidos, c.telefono,
               v.conductor_nombre, v.conductor_telefono,
               COALESCE(v.conductor_activo, TRUE)
          FROM ordenes o
          LEFT JOIN clientes c ON c.id = o.cliente_id AND c.taller_id = o.taller_id
          LEFT JOIN vehiculos v ON v.placa = o.vehiculo_placa AND v.taller_id = o.taller_id
         WHERE o.consecutivo=:c AND o.taller_id=:t
    """), {'c': consecutivo, 't': taller_id}).fetchone()
    if not row:
        return []
    cli_id, placa, c_nom, c_ape, c_tel, cond_nom, cond_tel, cond_act = row
    out = []
    # Jefe / cliente individual siempre primero
    nombre_jefe = ((c_nom or '') + ' ' + (c_ape or '')).strip()
    out.append({
        'kind': 'cliente', 'id': cli_id, 'placa_orden': placa,
        'nombre': nombre_jefe or cli_id, 'telefono': c_tel or '',
    })
    # Conductor solo si está asignado y activo
    if cond_nom and cond_act:
        out.append({
            'kind': 'conductor', 'id': placa, 'placa_orden': placa,
            'nombre': cond_nom, 'telefono': cond_tel or '',
        })
    return out


def notify_orden_event(db, *, taller_id: int, consecutivo: str, evento: str,
                       extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Despacha la notificación para un evento de orden:
      evento ∈ {'diagnostico_listo', 'presupuesto_listo', 'aprobado',
                'reparacion_iniciada', 'lista_entrega', 'entregado'}
    Envía web push a todos los destinatarios y retorna info para que el caller
    también pueda armar links wa.me opcionales.
    """
    extra = extra or {}
    dests = destinatarios_orden(db, taller_id=taller_id, consecutivo=consecutivo)
    if not dests:
        return {'ok': False, 'reason': 'orden no encontrada', 'sent_push': 0, 'destinatarios': []}

    placa = (dests[0].get('placa_orden') or '').upper()
    titulos = {
        'diagnostico_listo':   'Diagnóstico listo',
        'presupuesto_listo':   'Presupuesto por aprobar',
        'aprobado':            'Reparación aprobada',
        'reparacion_iniciada': 'Reparación en curso',
        'lista_entrega':       '¡Tu vehículo está listo!',
        'entregado':           'Servicio finalizado',
    }
    bodies_jefe = {
        'diagnostico_listo':   f'Tu {placa} ya tiene diagnóstico técnico.',
        'presupuesto_listo':   f'Hay un presupuesto por aprobar para {placa}.',
        'aprobado':            f'Iniciamos la reparación de {placa}.',
        'reparacion_iniciada': f'La reparación de {placa} está en curso.',
        'lista_entrega':       f'Pasá a recoger {placa} cuando gustes.',
        'entregado':           f'Gracias por confiar en nosotros para {placa}.',
    }
    bodies_cond = {
        'diagnostico_listo':   f'Ya está el diagnóstico de {placa}.',
        'presupuesto_listo':   f'Hay presupuesto, esperando aprobación del jefe.',
        'aprobado':            f'El jefe aprobó. Empezamos la reparación de {placa}.',
        'reparacion_iniciada': f'Reparando {placa} ahora.',
        'lista_entrega':       f'¡{placa} lista! Coordina entrega con el jefe.',
        'entregado':           f'{placa} entregada.',
    }
    title = titulos.get(evento, 'Actualización de orden')
    sent_total = 0
    enriched = []
    for d in dests:
        body = bodies_jefe.get(evento, '') if d['kind'] == 'cliente' else bodies_cond.get(evento, '')
        body = body or 'Hay una novedad en tu orden.'
        url = f"/portal/?orden={consecutivo}"
        sent = send_push_to_user(
            db, taller_id=taller_id,
            user_kind=d['kind'], user_id_str=d['id'],
            title=title, body=body, url=url,
            tag=f"orden-{consecutivo}-{evento}",
            data={'consecutivo': consecutivo, 'evento': evento},
        )
        sent_total += sent
        # Mensaje wa.me listo (por si el staff quiere enviarlo manual)
        wa_msg = f"{title}\n{body}\nVer detalle: https://sandoval.pe/portal/?orden={consecutivo}"
        d2 = dict(d)
        d2['wa_link'] = (f"https://wa.me/{d['telefono'].lstrip('+').replace(' ','').replace('-','')}?text="
                        + _url_encode(wa_msg)) if d.get('telefono') else ''
        d2['mensaje'] = wa_msg
        d2['push_sent'] = sent
        enriched.append(d2)

    return {'ok': True, 'sent_push': sent_total, 'evento': evento,
            'consecutivo': consecutivo, 'destinatarios': enriched}


def _url_encode(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe='')
