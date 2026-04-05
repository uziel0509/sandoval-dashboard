"""
SANDOVAL Dashboard - Apertura y Cierre de Caja
Gestión de turnos con desglose por método de pago
"""

from nicegui import ui
from datetime import datetime, date, timedelta
from utils.models import get_db, CierreCaja, Orden, NotaVenta, log_actividad
from utils.auth import get_current_user
import theme


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _hoy() -> str:
    return date.today().strftime('%Y-%m-%d')


def _ahora() -> str:
    return datetime.now().strftime('%H:%M')


def _caja_hoy(db) -> CierreCaja | None:
    return db.query(CierreCaja).filter_by(fecha=_hoy()).order_by(CierreCaja.id.desc()).first()


def _calcular_resumen(fecha: str) -> dict:
    """Consulta ordenes archivadas + notas de venta del día y calcula totales."""
    db = get_db()
    try:
        # Órdenes archivadas cobradas hoy
        ordenes = db.query(Orden).filter(
            Orden.estado == 'ARCHIVADO',
            Orden.fecha_cobro == fecha
        ).all()

        total_ordenes = 0.0
        total_mo      = 0.0
        total_rep     = 0.0
        ef_ord = ya_ord = tr_ord = tc_ord = 0.0

        for o in ordenes:
            monto = float(o.monto_cobrado or 0)
            total_ordenes += monto
            metodo = (o.metodo_pago or 'Efectivo').strip()
            if metodo == 'Efectivo':       ef_ord += monto
            elif metodo == 'Yape':         ya_ord += monto
            elif metodo == 'Transferencia': tr_ord += monto
            elif metodo == 'Tarjeta':      tc_ord += monto

            # Desglose MO vs repuestos
            for it in (o.items_cotizacion or []):
                cat = str(it.get('categoria') or it.get('tipo') or '').lower()
                sub = float(it.get('subtotal') or 0)
                if 'mano' in cat or 'labor' in cat or 'servicio' in cat:
                    total_mo  += sub
                else:
                    total_rep += sub

        # Notas de venta del día
        fecha_dt_ini = datetime.strptime(fecha, '%Y-%m-%d')
        fecha_dt_fin = fecha_dt_ini + timedelta(days=1)
        notas = db.query(NotaVenta).filter(
            NotaVenta.estado == 'pagada',
            NotaVenta.fecha >= fecha_dt_ini,
            NotaVenta.fecha < fecha_dt_fin,
        ).all()

        total_notas = 0.0
        ef_nv = ya_nv = tr_nv = tc_nv = 0.0

        for nv in notas:
            monto = float(nv.total or 0)
            total_notas += monto
            metodo = (nv.metodo_pago or 'Efectivo').strip()
            if metodo == 'Efectivo':       ef_nv += monto
            elif metodo == 'Yape':         ya_nv += monto
            elif metodo == 'Transferencia': tr_nv += monto
            elif metodo == 'Tarjeta':      tc_nv += monto
            # notas = repuestos
            total_rep += monto

        return {
            'total_efectivo':     round(ef_ord + ef_nv, 2),
            'total_yape':         round(ya_ord + ya_nv, 2),
            'total_transferencia': round(tr_ord + tr_nv, 2),
            'total_tarjeta':      round(tc_ord + tc_nv, 2),
            'total_ordenes':      round(total_ordenes, 2),
            'total_notas':        round(total_notas, 2),
            'total_mo':           round(total_mo, 2),
            'total_repuestos':    round(total_rep, 2),
            'ganancia_neta':      round(total_ordenes + total_notas, 2),
            'num_ordenes':        len(ordenes),
            'num_notas':          len(notas),
        }
    finally:
        db.close()


# ─── Apertura dialog ─────────────────────────────────────────────────────────

def _open_apertura_dialog(on_done):
    user = get_current_user()
    with ui.dialog() as dlg, ui.card().style('width:420px;border-radius:20px;padding:0;overflow:hidden;box-shadow:0 20px 40px rgba(0,0,0,.1)'):
        with ui.element('div').style('background:linear-gradient(135deg,#f0fdf4,#dcfce7);padding:24px 30px;border-bottom:1px solid #bbf7d0'):
            with ui.row().classes('items-center gap-3'):
                ui.icon('lock_open', size='md', color='green-7')
                ui.label('Apertura de Caja').style('font-size:22px;font-weight:800;color:#14532d;font-family:Inter,sans-serif')

        with ui.column().classes('w-full p-8 gap-5'):
            ui.label(f'Fecha: {date.today().strftime("%d/%m/%Y")} — Hora: {_ahora()}').style('font-size:13px;color:#64748b')

            saldo_in = ui.number('Saldo inicial en efectivo (S/)', value=0, min=0, format='%.2f').props('outlined dense').classes('w-full')
            notas_in = ui.textarea('Notas de apertura (opcional)', placeholder='Ej: Inicio de turno mañana').props('outlined dense rows=2').classes('w-full')

            with ui.row().classes('w-full gap-3 justify-end'):
                ui.button('Cancelar', on_click=dlg.close).props('flat color=grey-7')

                def _abrir():
                    db = get_db()
                    try:
                        # Verificar si ya hay caja abierta hoy
                        existente = _caja_hoy(db)
                        if existente:
                            theme.notify_warning('Ya existe una caja para hoy.')
                            dlg.close()
                            return
                        caja = CierreCaja(
                            fecha=_hoy(),
                            apertura_hora=_ahora(),
                            saldo_apertura=float(saldo_in.value or 0),
                            notas_operador=(notas_in.value or '').strip(),
                            estado='abierta',
                            usuario_apertura=user['nombre'] if user else '',
                        )
                        db.add(caja)
                        db.commit()
                        log_actividad('Apertura de caja', 'cierre_caja', f'Saldo: S/ {saldo_in.value:.2f}')
                        theme.notify_success('✅ Caja abierta correctamente')
                    except Exception as e:
                        db.rollback()
                        theme.notify_error(f'Error: {e}')
                    finally:
                        db.close()
                    dlg.close()
                    on_done()

                ui.button('Abrir Caja', icon='lock_open', on_click=_abrir).props('unelevated color=green-7').classes('font-bold')

    dlg.open()


# ─── Cierre dialog ────────────────────────────────────────────────────────────

def _open_cierre_dialog(caja: CierreCaja, resumen: dict, on_done):
    user = get_current_user()
    with ui.dialog() as dlg, ui.card().style('width:480px;border-radius:20px;padding:0;overflow:hidden;box-shadow:0 20px 40px rgba(0,0,0,.1)'):
        with ui.element('div').style('background:linear-gradient(135deg,#fef2f2,#fee2e2);padding:24px 30px;border-bottom:1px solid #fca5a5'):
            with ui.row().classes('items-center gap-3'):
                ui.icon('lock', size='md', color='red-7')
                ui.label('Cierre de Caja').style('font-size:22px;font-weight:800;color:#7f1d1d;font-family:Inter,sans-serif')

        with ui.column().classes('w-full p-8 gap-4'):
            ui.label(f'Turno abierto a las {caja.apertura_hora} por {caja.usuario_apertura}').style('font-size:12px;color:#64748b')

            # Resumen del día
            with ui.element('div').style('width:100%;background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:16px'):
                ui.label('Resumen del día').style('font-size:13px;font-weight:700;color:#334155;margin-bottom:12px;display:block')

                def _row(label, value, color='#334155'):
                    with ui.row().classes('w-full justify-between'):
                        ui.label(label).style(f'font-size:13px;color:#64748b')
                        ui.label(f'S/ {value:,.2f}').style(f'font-size:13px;font-weight:700;color:{color}')

                _row('Órdenes de servicio cobradas', resumen['total_ordenes'], '#059669')
                _row('Notas de venta', resumen['total_notas'], '#059669')
                ui.separator().style('margin:6px 0')
                _row('💵 Efectivo', resumen['total_efectivo'])
                _row('📱 Yape', resumen['total_yape'])
                _row('🏦 Transferencia', resumen['total_transferencia'])
                _row('💳 Tarjeta', resumen['total_tarjeta'])
                ui.separator().style('margin:6px 0')
                _row('🔧 Mano de obra', resumen['total_mo'])
                _row('🔩 Repuestos / productos', resumen['total_repuestos'])
                ui.separator().style('margin:6px 0')
                _row('💰 TOTAL INGRESADO', resumen['ganancia_neta'], '#0369a1')
                with ui.row().classes('w-full justify-between mt-1'):
                    ui.label(f"Órdenes: {resumen['num_ordenes']} | Notas: {resumen['num_notas']}").style('font-size:11px;color:#94a3b8')

            saldo_cierre_in = ui.number('Efectivo en caja al cerrar (S/)', value=round(float(caja.saldo_apertura) + resumen['total_efectivo'], 2), format='%.2f').props('outlined dense').classes('w-full')
            notas_cierre_in = ui.textarea('Notas de cierre (opcional)').props('outlined dense rows=2').classes('w-full')

            with ui.row().classes('w-full gap-3 justify-end'):
                ui.button('Cancelar', on_click=dlg.close).props('flat color=grey-7')

                def _cerrar():
                    db = get_db()
                    try:
                        c = db.query(CierreCaja).filter_by(id=caja.id).first()
                        if not c:
                            theme.notify_error('Caja no encontrada')
                            return
                        c.cierre_hora       = _ahora()
                        c.saldo_cierre      = float(saldo_cierre_in.value or 0)
                        c.total_efectivo    = resumen['total_efectivo']
                        c.total_yape        = resumen['total_yape']
                        c.total_transferencia = resumen['total_transferencia']
                        c.total_tarjeta     = resumen['total_tarjeta']
                        c.total_ordenes     = resumen['total_ordenes']
                        c.total_notas       = resumen['total_notas']
                        c.total_mo          = resumen['total_mo']
                        c.total_repuestos   = resumen['total_repuestos']
                        c.ganancia_neta     = resumen['ganancia_neta']
                        c.num_ordenes       = resumen['num_ordenes']
                        c.num_notas         = resumen['num_notas']
                        c.notas_operador    = (notas_cierre_in.value or '').strip()
                        c.estado            = 'cerrada'
                        c.usuario_cierre    = user['nombre'] if user else ''
                        db.commit()
                        log_actividad('Cierre de caja', 'cierre_caja', f'Total: S/ {resumen["ganancia_neta"]:.2f}')
                        theme.notify_success('✅ Caja cerrada correctamente')
                    except Exception as e:
                        db.rollback()
                        theme.notify_error(f'Error: {e}')
                    finally:
                        db.close()
                    dlg.close()
                    on_done()

                ui.button('Cerrar Caja', icon='lock', on_click=_cerrar).props('unelevated color=red-7').classes('font-bold')

    dlg.open()


# ─── Historial card ──────────────────────────────────────────────────────────

def _render_historial_card(caja: CierreCaja):
    estado_color = '#059669' if caja.estado == 'cerrada' else '#d97706'
    estado_icon  = 'check_circle' if caja.estado == 'cerrada' else 'pending'
    with ui.card().classes('w-full').style('border-radius:16px;border:1px solid #e2e8f0;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,.05)'):
        with ui.row().classes('w-full justify-between items-center mb-3'):
            with ui.row().classes('items-center gap-2'):
                ui.icon(estado_icon, color=f'{"green" if caja.estado == "cerrada" else "orange"}-7').style('font-size:20px')
                fecha_fmt = datetime.strptime(caja.fecha, '%Y-%m-%d').strftime('%d/%m/%Y')
                ui.label(fecha_fmt).style('font-size:16px;font-weight:800;color:#1e293b')
            ui.badge(caja.estado.upper(), color='green' if caja.estado == 'cerrada' else 'orange').style('font-size:10px;font-weight:700')

        with ui.row().classes('w-full gap-6 flex-wrap'):
            def _stat(label, value, color='#334155'):
                with ui.column().classes('gap-0'):
                    ui.label(label).style('font-size:10px;color:#94a3b8;font-weight:600;text-transform:uppercase')
                    ui.label(f'S/ {value:,.2f}').style(f'font-size:15px;font-weight:800;color:{color}')

            _stat('Total ingresado', caja.ganancia_neta, '#0369a1')
            _stat('Efectivo', caja.total_efectivo)
            _stat('Yape', caja.total_yape)
            _stat('Transferencia', caja.total_transferencia)
            _stat('Tarjeta', caja.total_tarjeta)

        ui.separator().style('margin:12px 0')
        with ui.row().classes('w-full gap-6 flex-wrap'):
            def _mini(label, value):
                ui.label(f'{label}: {value}').style('font-size:11px;color:#64748b')

            _mini('Apertura', f'{caja.apertura_hora} — {caja.usuario_apertura}')
            if caja.cierre_hora:
                _mini('Cierre', f'{caja.cierre_hora} — {caja.usuario_cierre}')
            _mini('Órdenes', caja.num_ordenes)
            _mini('Notas venta', caja.num_notas)
            _mini('MO', f'S/ {caja.total_mo:,.2f}')
            _mini('Repuestos', f'S/ {caja.total_repuestos:,.2f}')


# ─── Página principal ────────────────────────────────────────────────────────

def show_cierre_caja(container):
    with container:
        container.clear()

    with container:
        with ui.column().classes('w-full max-w-4xl mx-auto p-6 gap-6'):
            # ── Header ────────────────────────────────────────────────────────
            with ui.row().classes('w-full justify-between items-center'):
                with ui.column().classes('gap-0'):
                    ui.label('Apertura / Cierre de Caja').style('font-size:28px;font-weight:900;color:#1e293b;font-family:Inter,sans-serif')
                    ui.label('Control de turnos y métodos de pago').style('font-size:13px;color:#94a3b8;font-weight:500')
                refresh_btn = ui.button(icon='refresh', on_click=lambda: show_cierre_caja(container)).props('flat round color=grey-6')

            # ── Estado de caja hoy ────────────────────────────────────────────
            status_area = ui.column().classes('w-full')

            def _render_status():
                status_area.clear()
                with status_area:
                    db = get_db()
                    try:
                        caja = _caja_hoy(db)
                    finally:
                        db.close()

                    resumen = _calcular_resumen(_hoy())
                    fecha_fmt = date.today().strftime('%d/%m/%Y')

                    if not caja:
                        # Sin apertura
                        with ui.card().classes('w-full').style('border-radius:20px;border:2px dashed #d1d5db;padding:32px;text-align:center;background:#fafafa'):
                            ui.icon('point_of_sale', size='xl', color='grey-4')
                            ui.label(f'No hay caja abierta para hoy ({fecha_fmt})').style('font-size:16px;font-weight:700;color:#94a3b8;margin:12px 0 8px')
                            ui.label('Inicia el turno haciendo la apertura de caja').style('font-size:13px;color:#cbd5e1')
                            ui.button('Abrir Caja', icon='lock_open', on_click=lambda: _open_apertura_dialog(_render_status)).props('unelevated color=green-7').classes('mt-4 font-bold')

                    elif caja.estado == 'abierta':
                        # Caja abierta — mostrar resumen en vivo
                        with ui.card().classes('w-full').style('border-radius:20px;border:2px solid #bbf7d0;padding:28px;background:#f0fdf4'):
                            with ui.row().classes('w-full justify-between items-center mb-4'):
                                with ui.row().classes('items-center gap-3'):
                                    ui.icon('lock_open', color='green-7', size='md')
                                    ui.label(f'Caja abierta — {fecha_fmt}').style('font-size:18px;font-weight:800;color:#14532d')
                                ui.badge('ABIERTA', color='green').style('font-size:11px;font-weight:700')

                            ui.label(f'Apertura: {caja.apertura_hora} por {caja.usuario_apertura} | Saldo inicial: S/ {caja.saldo_apertura:,.2f}').style('font-size:12px;color:#4ade80;margin-bottom:16px')

                            # Tarjetas de métricas
                            with ui.row().classes('w-full gap-4 flex-wrap'):
                                def _card_metrica(icon, label, value, bg, border, text_color):
                                    with ui.element('div').style(f'flex:1;min-width:140px;background:{bg};border:1px solid {border};border-radius:14px;padding:16px'):
                                        with ui.row().classes('items-center gap-2 mb-1'):
                                            ui.icon(icon, size='sm').style(f'color:{text_color}')
                                            ui.label(label).style(f'font-size:11px;font-weight:700;color:{text_color};text-transform:uppercase')
                                        ui.label(f'S/ {value:,.2f}').style(f'font-size:22px;font-weight:900;color:{text_color}')

                                _card_metrica('payments', 'Total día', resumen['ganancia_neta'], '#f0fdf4', '#86efac', '#166534')
                                _card_metrica('build', 'Órdenes', resumen['total_ordenes'], '#eff6ff', '#bfdbfe', '#1d4ed8')
                                _card_metrica('receipt_long', 'Notas venta', resumen['total_notas'], '#faf5ff', '#e9d5ff', '#7e22ce')

                            ui.separator().style('margin:16px 0')

                            with ui.row().classes('w-full gap-4 flex-wrap'):
                                def _pago_chip(label, value, icon):
                                    with ui.element('div').style('background:white;border:1px solid #e2e8f0;border-radius:10px;padding:10px 14px;display:flex;align-items:center;gap:8px'):
                                        ui.icon(icon, size='xs', color='grey-6')
                                        ui.label(label).style('font-size:11px;color:#64748b')
                                        ui.label(f'S/ {value:,.2f}').style('font-size:14px;font-weight:800;color:#334155')

                                _pago_chip('Efectivo', resumen['total_efectivo'], 'payments')
                                _pago_chip('Yape', resumen['total_yape'], 'smartphone')
                                _pago_chip('Transferencia', resumen['total_transferencia'], 'account_balance')
                                _pago_chip('Tarjeta', resumen['total_tarjeta'], 'credit_card')

                            ui.separator().style('margin:16px 0')

                            with ui.row().classes('w-full gap-3 justify-end'):
                                ui.button('Actualizar', icon='refresh', on_click=_render_status).props('outline color=green-7').classes('font-bold')
                                ui.button('Cerrar Caja', icon='lock', on_click=lambda: _open_cierre_dialog(caja, resumen, _render_status)).props('unelevated color=red-7').classes('font-bold')

                    else:
                        # Caja cerrada hoy
                        with ui.card().classes('w-full').style('border-radius:20px;border:2px solid #fca5a5;padding:28px;background:#fff5f5'):
                            with ui.row().classes('items-center gap-3 mb-2'):
                                ui.icon('lock', color='red-7', size='md')
                                ui.label(f'Caja cerrada — {fecha_fmt}').style('font-size:18px;font-weight:800;color:#7f1d1d')
                            ui.label(f'Turno finalizado a las {caja.cierre_hora} por {caja.usuario_cierre} | Total: S/ {caja.ganancia_neta:,.2f}').style('font-size:12px;color:#f87171')

            _render_status()

            # ── Historial últimos 7 días ──────────────────────────────────────
            ui.separator().style('margin:8px 0')
            ui.label('Historial reciente').style('font-size:18px;font-weight:800;color:#1e293b')

            db = get_db()
            try:
                desde = (date.today() - timedelta(days=6)).strftime('%Y-%m-%d')
                historial = db.query(CierreCaja).filter(
                    CierreCaja.fecha >= desde,
                    CierreCaja.fecha < _hoy()
                ).order_by(CierreCaja.fecha.desc()).all()
            finally:
                db.close()

            if not historial:
                ui.label('Sin registros anteriores').style('font-size:13px;color:#94a3b8;text-align:center;padding:24px')
            else:
                with ui.column().classes('w-full gap-3'):
                    for c in historial:
                        _render_historial_card(c)
