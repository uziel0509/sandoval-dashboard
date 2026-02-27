"""
SANDOVAL Dashboard - Portal del Cliente v5.0
Diseño premium basado en el HTML corporativo solicitado.
Vinculado 100% a la base de datos SQLite real.
"""

import os
import json
from datetime import datetime, timedelta
from nicegui import ui
from utils.models import get_db, Cliente, Vehiculo, Orden, Cita, Actividad, verify_password, hash_password
from utils.auth import get_current_user
from utils.notifications import get_client_notifications, marcar_notifs_leidas_cliente


# ─── CSS GLOBAL DEL PORTAL ───────────────────────────────────────────────────

PORTAL_CSS = '''
<style>
:root {
    --azul: #1a3a6b;
    --azul-med: #2356a8;
    --azul-claro: #3a7bd5;
    --azul-super-claro: #e8f0fb;
    --azul-borde: #c5d8f5;
    --blanco: #ffffff;
    --gris-bg: #f4f7fc;
    --gris-texto: #6b7a99;
    --gris-borde: #dde4f0;
    --verde: #1db97a;
    --naranja: #f59e0b;
    --rojo: #ef4444;
    --texto: #1a2340;
    --sombra: 0 2px 16px rgba(26,58,107,.10);
    --sombra-hover: 0 6px 28px rgba(26,58,107,.18);
}

/* Reset NiceGUI para el portal */
.portal-wrap * { box-sizing: border-box; }
.portal-wrap { font-family: 'Inter', 'Outfit', sans-serif !important; }

/* Cards */
.p-card {
    background: var(--blanco);
    border-radius: 16px;
    border: 1.5px solid var(--gris-borde);
    box-shadow: var(--sombra);
    padding: 28px;
    width: 100%;
}

/* Stats */
.p-stat {
    background: var(--blanco);
    border-radius: 14px;
    border: 1.5px solid var(--gris-borde);
    box-shadow: var(--sombra);
    padding: 20px 22px;
    display: flex;
    align-items: center;
    gap: 14px;
    flex: 1;
    min-width: 180px;
}
.p-stat-icon {
    width: 46px; height: 46px;
    border-radius: 12px;
    background: var(--azul-super-claro);
    display: flex; align-items: center; justify-content: center;
    font-size: 22px;
    flex-shrink: 0;
}
.p-stat-num {
    font-size: 28px; font-weight: 800;
    color: var(--azul); line-height: 1;
    margin-bottom: 3px;
}
.p-stat-label {
    font-size: 12px; color: var(--gris-texto); font-weight: 500;
}

/* Tracker */
.p-tracker {
    background: var(--blanco);
    border-radius: 16px;
    border: 1.5px solid var(--gris-borde);
    box-shadow: var(--sombra);
    padding: 28px 32px;
}
.phases-wrapper {
    position: relative;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin: 12px 0;
}
.phases-line {
    position: absolute;
    top: 26px; left: 4%; right: 4%;
    height: 3px;
    background: var(--gris-borde);
    border-radius: 4px;
    z-index: 0;
}
.phases-progress {
    position: absolute;
    top: 26px; left: 4%;
    height: 3px;
    background: linear-gradient(90deg, var(--azul), var(--azul-claro));
    border-radius: 4px;
    z-index: 1;
    transition: width .8s ease;
}
.phase-item {
    display: flex; flex-direction: column;
    align-items: center; gap: 8px;
    position: relative; z-index: 2;
    flex: 1;
}
.phase-circle {
    width: 52px; height: 52px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
    transition: all .25s;
    position: relative;
}
.phase-item.done .phase-circle {
    background: var(--azul); color: var(--blanco);
    box-shadow: 0 4px 14px rgba(26,58,107,.3);
}
.phase-item.active .phase-circle {
    background: var(--azul-med); color: var(--blanco);
    box-shadow: 0 4px 20px rgba(35,86,168,.45);
    animation: pulseRing 2s infinite;
}
@keyframes pulseRing {
    0%, 100% { box-shadow: 0 4px 20px rgba(35,86,168,.45); }
    50% { box-shadow: 0 4px 28px rgba(35,86,168,.8), 0 0 0 6px rgba(35,86,168,.1); }
}
.phase-item.pending .phase-circle {
    background: var(--blanco);
    border: 2.5px solid var(--gris-borde);
    color: var(--gris-texto);
}
.phase-name {
    font-size: 11px; font-weight: 600;
    text-align: center; line-height: 1.3;
    color: var(--gris-texto);
}
.phase-item.done .phase-name { color: var(--azul); }
.phase-item.active .phase-name { color: var(--azul-med); font-weight: 700; }
.phase-sub {
    font-size: 10px; text-align: center;
    color: var(--gris-texto);
}
.phase-item.done .phase-sub { color: var(--verde); font-weight: 500; }
.phase-item.active .phase-sub { color: var(--naranja); font-weight: 500; }

.tracker-status {
    margin-top: 20px;
    text-align: center;
    font-size: 13px;
    color: var(--gris-texto);
    background: var(--gris-bg);
    padding: 10px 20px;
    border-radius: 8px;
    border: 1px solid var(--gris-borde);
}

/* Section title */
.p-section-title {
    font-size: 18px; font-weight: 700;
    color: var(--azul);
    display: flex; align-items: center; gap: 8px;
    margin-bottom: 18px;
}
.p-icon-circle {
    width: 32px; height: 32px;
    border-radius: 8px;
    background: var(--azul-super-claro);
    display: flex; align-items: center; justify-content: center;
    font-size: 15px;
}

/* Vehicle data rows */
.p-data-row {
    display: flex; justify-content: space-between;
    align-items: center; font-size: 13.5px;
    padding: 5px 0;
}
.p-data-label { color: var(--gris-texto); font-weight: 500; }
.p-data-val { font-weight: 700; color: var(--texto); text-align: right; }
.p-divider { height: 1px; background: var(--gris-borde); margin: 12px 0; }
.p-obs {
    font-size: 13px; color: var(--gris-texto);
    line-height: 1.6;
    background: var(--gris-bg); border-radius: 8px;
    padding: 10px 14px;
    border-left: 3px solid var(--azul-claro);
}
.p-mecanico {
    display: inline-flex; align-items: center; gap: 8px;
    background: var(--azul-super-claro);
    border: 1px solid var(--azul-borde);
    border-radius: 100px;
    padding: 5px 12px;
    font-size: 12px; color: var(--azul); font-weight: 500;
    margin-top: 10px;
}
.p-vehicle-placeholder {
    width: 100%; height: 160px;
    border-radius: 10px;
    background: linear-gradient(135deg, var(--azul-super-claro), #dae8f9);
    display: flex; align-items: center; justify-content: center;
    font-size: 52px; margin-bottom: 18px;
    border: 2px dashed var(--azul-borde);
}

/* Services list */
.p-service-row {
    display: flex; align-items: center; gap: 12px;
    padding: 11px 14px;
    background: var(--gris-bg);
    border-radius: 10px;
    border: 1px solid var(--gris-borde);
    transition: all .18s;
    margin-bottom: 10px;
}
.p-service-row:hover {
    border-color: var(--azul-borde);
    background: var(--azul-super-claro);
}
.p-sr-icon {
    width: 36px; height: 36px;
    border-radius: 8px;
    background: var(--blanco);
    border: 1px solid var(--azul-borde);
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; flex-shrink: 0;
}
.p-sr-name { font-size: 13px; font-weight: 600; color: var(--texto); }
.p-sr-qty { font-size: 11px; color: var(--gris-texto); }
.p-sr-price { font-size: 14px; font-weight: 700; color: var(--azul); margin-left: auto; }

/* Totals */
.p-totals {
    background: var(--gris-bg);
    border-radius: 10px; padding: 14px 16px;
    border: 1px solid var(--gris-borde); margin-top: 8px;
}
.p-total-row {
    display: flex; justify-content: space-between;
    font-size: 13px; color: var(--gris-texto); margin-bottom: 6px;
}
.p-total-final {
    display: flex; justify-content: space-between;
    font-size: 16px; font-weight: 800; color: var(--azul);
    padding-top: 8px;
    border-top: 2px solid var(--azul-borde); margin-top: 6px;
}
.p-btn-factura {
    display: block; width: 100%; margin-top: 12px;
    padding: 10px; border-radius: 10px;
    border: 1.5px solid var(--azul-claro);
    background: var(--blanco); color: var(--azul-med);
    font-size: 13px; font-weight: 600;
    cursor: pointer; text-align: center; transition: all .18s;
    font-family: inherit;
}
.p-btn-factura:hover { background: var(--azul-super-claro); border-color: var(--azul); }

/* Calendar strip */
.p-cal-strip {
    display: flex; gap: 8px;
    overflow-x: auto; scrollbar-width: none;
    padding-bottom: 4px; margin-bottom: 18px;
}
.p-cal-strip::-webkit-scrollbar { display: none; }
.p-cal-day {
    flex-shrink: 0; width: 58px; padding: 10px 6px;
    border-radius: 12px; text-align: center;
    border: 1.5px solid var(--gris-borde);
    background: var(--blanco); cursor: pointer;
    transition: all .18s;
}
.p-cal-day:hover { border-color: var(--azul-claro); background: var(--azul-super-claro); }
.p-cal-day.selected { background: var(--azul); border-color: var(--azul); }
.p-cal-day.selected .p-cal-dow,
.p-cal-day.selected .p-cal-num { color: #fff !important; }
.p-cal-dow {
    font-size: 10px; text-transform: uppercase;
    letter-spacing: 1px; color: var(--gris-texto);
    margin-bottom: 4px; font-weight: 500;
}
.p-cal-num { font-size: 20px; font-weight: 800; color: var(--texto); line-height: 1; }

/* Form labels */
.p-form-label {
    font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 1px;
    color: var(--gris-texto); display: block; margin-bottom: 6px;
}
.p-btn-agendar {
    display: flex; align-items: center; justify-content: center; gap: 10px;
    width: 100%; padding: 15px;
    background: var(--azul); border: none; border-radius: 12px;
    color: var(--blanco); font-family: 'Inter', sans-serif;
    font-size: 15px; font-weight: 700; cursor: pointer;
    transition: all .2s; letter-spacing: .3px; margin-top: 16px;
}
.p-btn-agendar:hover {
    background: var(--azul-med);
    transform: translateY(-1px);
    box-shadow: 0 6px 22px rgba(26,58,107,.3);
}

/* Notifications */
.p-notif-item {
    display: flex; gap: 12px; align-items: flex-start;
    padding: 12px 14px; border-radius: 10px;
    border: 1.5px solid var(--gris-borde);
    background: var(--gris-bg); transition: all .18s;
    margin-bottom: 10px;
}
.p-notif-item.nueva {
    border-color: var(--azul-borde);
    background: var(--azul-super-claro);
}
.p-notif-item:hover { border-color: var(--azul-borde); background: var(--azul-super-claro); }
.p-ni-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--azul-claro); margin-top: 5px; flex-shrink: 0;
}
.p-ni-dot.read { background: var(--gris-borde); }
.p-ni-icon {
    width: 36px; height: 36px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; flex-shrink: 0;
}
.p-ni-icon.azul { background: var(--azul-super-claro); }
.p-ni-icon.verde { background: rgba(29,185,122,.1); }
.p-ni-icon.naranja { background: rgba(245,158,11,.1); }
.p-ni-title { font-size: 13px; font-weight: 600; color: var(--texto); margin-bottom: 2px; }
.p-ni-desc { font-size: 12px; color: var(--gris-texto); line-height: 1.4; }
.p-ni-time { font-size: 11px; color: var(--gris-texto); margin-top: 3px; }

/* Historial table */
.p-hist-table { width: 100%; border-collapse: collapse; }
.p-hist-table thead th {
    font-size: 11px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 1px;
    color: var(--gris-texto); padding: 8px 14px;
    text-align: left; border-bottom: 2px solid var(--gris-borde);
    background: var(--gris-bg);
}
.p-hist-table tbody tr {
    border-bottom: 1px solid var(--gris-borde);
    transition: background .15s; cursor: pointer;
}
.p-hist-table tbody tr:hover { background: var(--azul-super-claro); }
.p-hist-table tbody td { padding: 12px 14px; font-size: 13.5px; }
.td-fecha { color: var(--gris-texto); font-size: 12px; }
.td-servicio { font-weight: 600; color: var(--texto); }
.td-costo { font-weight: 700; color: var(--azul); }
.p-folio {
    font-size: 11px; color: var(--azul);
    background: var(--azul-super-claro);
    padding: 2px 7px; border-radius: 5px;
    font-family: monospace;
}
.p-badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 4px 10px; border-radius: 100px;
    font-size: 11px; font-weight: 600;
}
.p-badge.completado {
    background: rgba(29,185,122,.1); color: var(--verde);
    border: 1px solid rgba(29,185,122,.25);
}
.p-badge.proceso {
    background: rgba(245,158,11,.1); color: var(--naranja);
    border: 1px solid rgba(245,158,11,.25);
}
.p-badge.pendiente {
    background: var(--gris-bg); color: var(--gris-texto);
    border: 1px solid var(--gris-borde);
}
.p-ver-mas {
    display: block; text-align: center;
    padding: 10px; margin-top: 8px;
    font-size: 13px; font-weight: 600;
    color: var(--azul-med); cursor: pointer;
    border-radius: 8px; transition: background .15s;
}
.p-ver-mas:hover { background: var(--azul-super-claro); }

/* Tabs */
.p-tabs {
    display: flex; gap: 4px;
    background: var(--gris-bg);
    border-radius: 10px; padding: 4px;
    border: 1px solid var(--gris-borde);
}
.p-tab {
    padding: 8px 16px; border-radius: 8px;
    font-size: 13px; font-weight: 500;
    color: var(--gris-texto); cursor: pointer; transition: all .18s;
}
.p-tab.active {
    background: var(--blanco); color: var(--azul);
    font-weight: 700; box-shadow: 0 1px 6px rgba(26,58,107,.1);
}

/* Grid 2 col */
.p-grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
}
@media (max-width: 900px) {
    .p-grid-2 { grid-template-columns: 1fr; }
    .p-stat { min-width: 140px; }
}

/* Toast animado */
.p-toast {
    background: var(--blanco);
    border: 1.5px solid var(--azul-borde);
    border-left: 4px solid var(--azul);
    border-radius: 12px; padding: 14px 18px;
    min-width: 280px;
    display: flex; align-items: flex-start; gap: 12px;
    box-shadow: 0 8px 32px rgba(26,58,107,.18);
    animation: toastIn .35s ease forwards;
    margin-bottom: 8px;
}
@keyframes toastIn {
    from { opacity: 0; transform: translateX(40px); }
    to { opacity: 1; transform: translateX(0); }
}
</style>
<script>
// Filtro de historial — disponible desde que carga el portal
window._histFiltroActivo = 'todos';
window.filterHist = function(tipo, el) {
    window._histFiltroActivo = tipo;
    document.querySelectorAll(".p-tab").forEach(function(t) { t.classList.remove("active"); });
    if (el) el.classList.add("active");
    var rows = document.querySelectorAll("#histTable tbody tr");
    rows.forEach(function(r) {
        if (tipo === "todos") { r.style.display = ""; }
        else { r.style.display = (r.dataset.estado === tipo) ? "" : "none"; }
    });
};
// Re-aplica el filtro activo cuando la tabla cambia (ver más / ver menos)
window.reaplicarFiltroHist = function() {
    var tipo = window._histFiltroActivo || 'todos';
    var rows = document.querySelectorAll("#histTable tbody tr");
    rows.forEach(function(r) {
        if (tipo === "todos") { r.style.display = ""; }
        else { r.style.display = (r.dataset.estado === tipo) ? "" : "none"; }
    });
};
</script>
'''


# ─── FUNCIÓN PRINCIPAL ────────────────────────────────────────────────────────

def show_portal(container):
    user = get_current_user()
    if not user or user.get('rol') != 'cliente':
        with container:
            ui.label('Acceso no autorizado').classes('text-red-500 p-8')
        return

    ui.add_head_html(PORTAL_CSS)
    
    # Agregar estilos 3D mejorados
    try:
        from components.portal_cliente_3d import PORTAL_3D_ENHANCEMENTS
        ui.add_head_html(PORTAL_3D_ENHANCEMENTS)
    except ImportError:
        pass
    
    # Agregar estilos premium v3.0
    try:
        from components.portal_cliente_premium import PORTAL_CLIENTE_PREMIUM_CSS
        ui.add_head_html(PORTAL_CLIENTE_PREMIUM_CSS)
    except ImportError:
        pass


    db = get_db()
    try:
        user_id   = user.get('id')
        user_plate = user.get('placa')

        cliente   = db.query(Cliente).filter_by(id=user_id).first()
        vehiculo  = db.query(Vehiculo).filter_by(placa=user_plate).first()
        todos_vehiculos = db.query(Vehiculo).filter_by(cliente_id=user_id).all()
        ordenes_all = (
            db.query(Orden)
            .filter(Orden.vehiculo_placa.in_([v.placa for v in todos_vehiculos]))
            .order_by(Orden.fecha.desc())
            .all()
        )
        citas_all = db.query(Cita).filter_by(cliente_id=user_id).all()

        if not cliente:
            with container:
                ui.label('Error: Cliente no encontrado').classes('text-red-500 p-10')
            return

        # ── Cargar datos en memoria antes de cerrar sesión BD ─────
        # Evita DetachedInstanceError si NiceGUI accede a atributos ORM
        # después de que db.close() se ejecute en el finally
        def _o2d(o):
            """Convierte Orden ORM a dict plano seguro"""
            return {c.name: getattr(o, c.name) for c in o.__table__.columns}

        ordenes_dicts = [_o2d(o) for o in ordenes_all]
        active_dict   = next(
            (d for d in ordenes_dicts if d.get('estado') not in ('ARCHIVADO', 'ENTREGA')), None
        )
        # Mantener objetos ORM solo durante la sesión
        active_order = next(
            (o for o in ordenes_all if o.estado not in ('ARCHIVADO', 'ENTREGA')), None
        )
        servicios_activos = 1 if active_order else 0
        visitas_totales   = len(ordenes_all)
        vehiculos_total   = len(todos_vehiculos)

        proxima_cita_label = '—'
        hoy_str = datetime.now().strftime('%Y-%m-%d')
        futuras = sorted(
            [c for c in citas_all if c.fecha_cita >= hoy_str and c.estado != 'cancelada'],
            key=lambda x: x.fecha_cita
        )
        if futuras:
            fc = futuras[0]
            try:
                d = datetime.strptime(fc.fecha_cita, '%Y-%m-%d')
                proxima_cita_label = f'{d.day} {_mes(d.month)}'
            except Exception:
                proxima_cita_label = fc.fecha_cita

        # ── Notificaciones del cliente ────────────────────────────
        notifs_cliente = get_client_notifications(user_id, user_plate)

        # ── Historial de actividad del historial de la orden ──────
        actividades_orden = []
        if active_order and active_order.historial:
            hist = active_order.historial
            if isinstance(hist, str):
                try: hist = json.loads(hist)
                except: hist = []
            actividades_orden = hist if isinstance(hist, list) else []

        # ─────────────────────────────────────────────────────────
        # RENDER DEL PORTAL
        # ─────────────────────────────────────────────────────────
        with container:
            with ui.element('div').classes('portal-wrap w-full flex flex-col gap-6'):

                # ════════════════════════════════════════════════
                # 1. STATS ROW - Cards Clickeables
                # ════════════════════════════════════════════════
                
                # Crear funciones de callback con variables capturadas
                def click_vehiculos():
                    _mostrar_vehiculos_dialog(get_db(), cliente_id)
                
                def click_servicio():
                    if active_order:
                        _mostrar_servicio_dialog(active_order, vehiculo)
                
                def click_historial():
                    _mostrar_historial_dialog(get_db(), cliente_id)
                
                def click_cita():
                    _mostrar_cita_dialog(get_db(), cliente_id)
                
                with ui.element('div').style('display:flex;gap:16px;flex-wrap:wrap;'):
                    # Card: Mis vehículos
                    with ui.element('div').classes('portal-stat-card cursor-pointer').style(
                        '--color-start: #3b82f6; --color-end: #60a5fa; flex: 1; min-width: 200px;'
                    ).on('click', click_vehiculos):
                        ui.html(f'''
                        <div class="portal-stat-icon" style="background: rgba(59, 130, 246, 0.15); color: #3b82f6;">
                            🚗
                        </div>
                        <div class="p-stat-num" style="font-size: 2rem; font-weight: 900; color: #1e293b; margin-bottom: 0.25rem;">
                            {vehiculos_total}
                        </div>
                        <div class="p-stat-label" style="font-size: 0.875rem; color: #64748b; font-weight: 600;">
                            Mis vehículos
                        </div>
                        ''')
                    
                    # Card: Servicio activo
                    with ui.element('div').classes('portal-stat-card cursor-pointer').style(
                        '--color-start: #10b981; --color-end: #34d399; flex: 1; min-width: 200px;'
                    ).on('click', click_servicio):
                        ui.html(f'''
                        <div class="portal-stat-icon" style="background: rgba(16, 185, 129, 0.15); color: #10b981;">
                            🔧
                        </div>
                        <div class="p-stat-num" style="font-size: 2rem; font-weight: 900; color: #1e293b; margin-bottom: 0.25rem;">
                            {servicios_activos}
                        </div>
                        <div class="p-stat-label" style="font-size: 0.875rem; color: #64748b; font-weight: 600;">
                            Servicio activo
                        </div>
                        ''')
                    
                    # Card: Visitas totales
                    with ui.element('div').classes('portal-stat-card cursor-pointer').style(
                        '--color-start: #8b5cf6; --color-end: #a78bfa; flex: 1; min-width: 200px;'
                    ).on('click', click_historial):
                        ui.html(f'''
                        <div class="portal-stat-icon" style="background: rgba(139, 92, 246, 0.15); color: #8b5cf6;">
                            📋
                        </div>
                        <div class="p-stat-num" style="font-size: 2rem; font-weight: 900; color: #1e293b; margin-bottom: 0.25rem;">
                            {visitas_totales}
                        </div>
                        <div class="p-stat-label" style="font-size: 0.875rem; color: #64748b; font-weight: 600;">
                            Visitas totales
                        </div>
                        ''')
                    
                    # Card: Próxima cita
                    with ui.element('div').classes('portal-stat-card cursor-pointer').style(
                        '--color-start: #f59e0b; --color-end: #fbbf24; flex: 1; min-width: 200px;'
                    ).on('click', click_cita):
                        ui.html(f'''
                        <div class="portal-stat-icon" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b;">
                            📅
                        </div>
                        <div class="p-stat-num" style="font-size: 2rem; font-weight: 900; color: #1e293b; margin-bottom: 0.25rem;">
                            {proxima_cita_label}
                        </div>
                        <div class="p-stat-label" style="font-size: 0.875rem; color: #64748b; font-weight: 600;">
                            Próx. cita
                        </div>
                        ''')

                # ════════════════════════════════════════════════
                # 2. TRACKER DE SEGUIMIENTO
                # ════════════════════════════════════════════════
                if active_order:
                    _render_tracker_card(active_order, vehiculo)
                else:
                    with ui.element('div').classes('p-card'):
                        ui.html('''
                        <div style="text-align:center;padding:40px 0;color:var(--gris-texto);">
                            <div style="font-size:48px;margin-bottom:12px;">✅</div>
                            <div style="font-size:16px;font-weight:700;color:var(--azul);margin-bottom:6px;">
                                No hay servicios activos
                            </div>
                            <div style="font-size:13px;">Su vehículo no está en taller en este momento.</div>
                        </div>
                        ''')

                # ════════════════════════════════════════════════
                # 3. GRID: Estado vehículo + Repuestos/Cotización
                # ════════════════════════════════════════════════
                with ui.element('div').classes('p-grid-2'):
                    # — Estado del Vehículo —
                    with ui.element('div').classes('p-card'):
                        _section_title('🚙', 'Estado de su Vehículo')
                        # Mostrar foto de ingreso si existe, sino placeholder
                        foto_ingreso = None
                        if active_order:
                            fotos = _safe_json(active_order.fotos_evidencia) if hasattr(active_order, 'fotos_evidencia') else []
                            foto_ingreso = fotos[0] if fotos else None
                        if foto_ingreso:
                            _foto_html = (
                                '<div style="width:100%;height:160px;border-radius:10px;overflow:hidden;'
                                'margin-bottom:18px;border:2px solid var(--azul-borde);">'
                                '<img src="' + foto_ingreso + '" style="width:100%;height:100%;object-fit:cover;" '
                                'onerror="this.style.display=&apos;none&apos;"/>'
                                '</div>'
                            )
                            ui.html(_foto_html)
                        else:
                            ui.html('<div class="p-vehicle-placeholder">&#128663;</div>')

                        if vehiculo:
                            veh_nombre = f'{vehiculo.marca} {vehiculo.modelo} {vehiculo.año}'.strip()
                            km_val     = active_order.km if active_order else '—'
                            tecnico_val= active_order.tecnico if active_order else '—'
                            _data_row('Vehículo', veh_nombre or '—')
                            _data_row('Placa', vehiculo.placa)
                            if active_order:
                                _data_row('Orden de Trabajo', f'#{active_order.consecutivo}')
                                _data_row('Kilometraje', f'{km_val} km' if km_val and km_val != '—' else '—')
                            ui.html('<div class="p-divider"></div>')
                            obs = (active_order.diagnostico or active_order.motivo or '—') if active_order else '—'
                            ui.html(f'<div class="p-obs">{obs}</div>')
                            if tecnico_val and tecnico_val != '—':
                                ui.html(f'<div class="p-mecanico">🧑‍🔧 Mecánico asignado: {tecnico_val}</div>')
                        else:
                            ui.label('Sin datos de vehículo').classes('text-gray-400 text-sm')

                    # — Repuestos y Servicios —
                    with ui.element('div').classes('p-card'):
                        _section_title('🔩', 'Repuestos y Servicios Aprobados')
                        if active_order:
                            items = _safe_json(active_order.items_cotizacion)
                            if items:
                                subtotal = 0.0
                                for it in items:
                                    val = float(it.get('total', 0) or 0)
                                    subtotal += val
                                    nombre = it.get('item', it.get('nombre', 'Ítem'))
                                    cant   = it.get('cantidad', 1)
                                    icon   = _item_icon(nombre)
                                    ui.html(f'''
                                    <div class="p-service-row">
                                        <div class="p-sr-icon">{icon}</div>
                                        <div style="flex:1;">
                                            <div class="p-sr-name">{nombre}</div>
                                            <div class="p-sr-qty">Cant: {cant}</div>
                                        </div>
                                        <div class="p-sr-price">S/ {val:,.2f}</div>
                                    </div>
                                    ''')
                                # Los precios ya incluyen IGV — desglose informativo
                                base_sin_igv = subtotal / 1.18
                                igv_incluido = subtotal - base_sin_igv
                                pdf_path_active = getattr(active_order, 'pdf_cotizacion', '') or ''
                                pdf_exists = bool(pdf_path_active and os.path.exists(pdf_path_active))
                                ui.html(f'''
                                <div class="p-totals">
                                    <div class="p-total-row" style="font-size:11px;color:var(--gris-texto);">
                                        <span>Base imponible (incluida)</span><span>S/ {base_sin_igv:,.2f}</span>
                                    </div>
                                    <div class="p-total-row" style="font-size:11px;color:var(--gris-texto);">
                                        <span>IGV 18% (incluido)</span><span>S/ {igv_incluido:,.2f}</span>
                                    </div>
                                    <div class="p-total-final">
                                        <span>Total (Inc. IGV)</span><span>S/ {subtotal:,.2f}</span>
                                    </div>
                                </div>
                                ''')
                                # Botón Ver PDF (funcional si existe el archivo)
                                if pdf_exists:
                                    ui.html(f'<a href="/{pdf_path_active}" target="_blank" class="p-btn-factura" style="display:block;text-decoration:none;text-align:center;">🧾 Ver Presupuesto PDF</a>')
                                else:
                                    ui.html('<div class="p-btn-factura" style="opacity:.45;cursor:default;">🧾 PDF disponible al aprobar presupuesto</div>')
                            else:
                                ui.html('''
                                <div style="text-align:center;padding:40px 0;color:var(--gris-texto);font-size:13px;">
                                    <div style="font-size:36px;margin-bottom:10px;">🔩</div>
                                    Aún no hay ítems en la cotización.
                                </div>
                                ''')
                        else:
                            ui.html('''
                            <div style="text-align:center;padding:40px 0;color:var(--gris-texto);font-size:13px;">
                                <div style="font-size:36px;margin-bottom:10px;">📋</div>
                                Sin servicio activo en este momento.
                            </div>
                            ''')

                # ════════════════════════════════════════════════
                # 4. GRID: Agendar Cita + Notificaciones
                # ════════════════════════════════════════════════
                with ui.element('div').classes('p-grid-2'):

                    # — Agendar Cita —
                    with ui.element('div').classes('p-card'):
                        _section_title('📅', 'Agendar Nueva Cita')

                        # Calendar strip dinámico
                        selected = {'fecha': None, 'btn_ref': None}
                        ui.label('SELECCIONAR FECHA').classes('p-form-label')

                        with ui.element('div').classes('p-cal-strip') as strip_el:
                            btn_refs = []
                            current = datetime.now()
                            day_count = 0
                            i = 0
                            while day_count < 10:
                                day = current + timedelta(days=i)
                                i += 1
                                if day.weekday() == 6:  # omitir domingo
                                    continue
                                dow = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB'][day.weekday()]
                                day_str = day.strftime('%Y-%m-%d')

                                btn = ui.element('div').classes('p-cal-day')
                                with btn:
                                    ui.html(f'<div class="p-cal-dow">{dow}</div>'
                                            f'<div class="p-cal-num">{day.day}</div>')
                                btn_refs.append((btn, day_str))

                                def _on_click(b=btn, ds=day_str):
                                    for rb, _ in btn_refs:
                                        rb.classes(remove='selected')
                                    b.classes(add='selected')
                                    selected['fecha'] = ds

                                btn.on('click', _on_click)
                                day_count += 1

                        # Seleccionar opciones de vehículos del cliente
                        veh_opts = {v.placa: f'{v.marca} {v.modelo} — {v.placa}'.strip()
                                    for v in todos_vehiculos}
                        if not veh_opts:
                            veh_opts = {user_plate: user_plate}

                        with ui.element('div').style('display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px;'):
                            with ui.column().classes('gap-1'):
                                ui.html('<span class="p-form-label">Vehículo</span>')
                                veh_sel = ui.select(veh_opts, value=list(veh_opts.keys())[0] if veh_opts else None).props('outlined dense').classes('w-full')
                            with ui.column().classes('gap-1'):
                                ui.html('<span class="p-form-label">Hora disponible</span>')
                                hora_sel = ui.select(
                                    ['08:00', '09:00', '10:00', '11:00',
                                     '12:00', '14:00', '15:00', '16:00', '17:00'],
                                    value='09:00'
                                ).props('outlined dense').classes('w-full')
                            with ui.column().classes('gap-1'):
                                ui.html('<span class="p-form-label">Tipo de Servicio</span>')
                                serv_sel = ui.select(
                                    ['Mantenimiento General', 'Cambio de Aceite y Filtros',
                                     'Revisión de Frenos', 'Diagnóstico Eléctrico',
                                     'Aire Acondicionado', 'Otro / Consulta'],
                                    value='Mantenimiento General'
                                ).props('outlined dense').classes('w-full')
                            with ui.column().classes('gap-1'):
                                ui.html('<span class="p-form-label">Prioridad</span>')
                                prio_sel = ui.select(
                                    ['Normal', 'Urgente'], value='Normal'
                                ).props('outlined dense').classes('w-full')

                        with ui.column().classes('gap-1 w-full'):
                            ui.html('<span class="p-form-label">Descripción del Problema (opcional)</span>')
                            desc_inp = ui.textarea(
                                placeholder='Ej: El carro hace un ruido al frenar en la parte delantera derecha...'
                            ).props('outlined dense rows=3').classes('w-full')

                        # Label de mensaje de horario ocupado (oculto por defecto)
                        msg_hora = ui.html('').style('display:none;')

                        async def _guardar_cita():
                            if not selected['fecha']:
                                ui.notify('Por favor seleccione una fecha', type='warning', position='top')
                                return
                            db2 = get_db()
                            try:
                                # ── Validar que el horario no esté ocupado ──
                                hora_elegida = hora_sel.value
                                fecha_elegida = selected['fecha']
                                cita_existente = db2.query(Cita).filter(
                                    Cita.fecha_cita == fecha_elegida,
                                    Cita.hora == hora_elegida,
                                    Cita.estado.in_(['programada', 'confirmada'])
                                ).first()
                                if cita_existente:
                                    msg_hora.content = f'''
                                    <div style="background:#fff3cd;border:1.5px solid #f59e0b;border-radius:10px;
                                                padding:12px 16px;margin-bottom:12px;font-size:13px;color:#92400e;">
                                        <strong>⚠️ Hora ocupada:</strong> El horario de las <strong>{hora_elegida}</strong>
                                        del <strong>{fecha_elegida}</strong> ya está reservado.<br>
                                        Por favor elige otra hora o
                                        <a onclick="fetch('/open-whatsapp?phone=51999999999&msg=Hola%2C%20quiero%20agendar%20una%20cita%20para%20el%20{fecha_elegida}')"
                                           style="color:#1a3a6b;font-weight:700;cursor:pointer;text-decoration:underline;">
                                           contacta al taller por WhatsApp
                                        </a> para coordinar.
                                    </div>'''
                                    msg_hora.style('display:block;')
                                    return
                                msg_hora.style('display:none;')

                                motivo = f'[{serv_sel.value}] {desc_inp.value}'.strip()
                                db2.add(Cita(
                                    cliente_id=user_id,
                                    vehiculo_placa=veh_sel.value or user_plate,
                                    fecha_cita=fecha_elegida,
                                    hora=hora_elegida,
                                    motivo=motivo,
                                    estado='programada',
                                ))
                                db2.commit()
                                msg_hora.style('display:none;')
                                ui.notify('¡Cita solicitada con éxito! El taller la confirmará pronto.',
                                          type='positive', position='top', icon='event_available')
                                desc_inp.value = ''
                                for rb, _ in btn_refs:
                                    rb.classes(remove='selected')
                                selected['fecha'] = None
                            except Exception as exc:
                                ui.notify(f'Error al guardar: {exc}', type='negative')
                            finally:
                                db2.close()

                        ui.button('📅  Confirmar Cita', on_click=_guardar_cita).props(
                            'unelevated'
                        ).classes('w-full h-14 text-base font-bold rounded-xl shadow-md').style(
                            'background:var(--azul);color:white;margin-top:16px;'
                            'letter-spacing:.3px;transition:all .2s;'
                        )

                    # — Notificaciones —
                    notif_container_ref = {'el': None}
                    with ui.element('div').classes('p-card'):
                        with ui.element('div').style('display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;'):
                            ui.html('<div class="p-section-title"><div class="p-icon-circle">🔔</div> Notificaciones</div>')
                            def _marcar_leidas():
                                # Guardar IDs leídas en DB para persistencia entre sesiones
                                ids_leidas = [n['id'] for n in notifs_cliente if 'id' in n]
                                marcar_notifs_leidas_cliente(user_id, ids_leidas)
                                # Marcar también en la lista local (para que no reaparezcan al navegar en esta sesión)
                                for n in notifs_cliente:
                                    n['nueva'] = False
                                # Actualizar visualmente
                                ui.run_javascript("""
                                    document.querySelectorAll('.p-ni-dot').forEach(d => {
                                        d.style.background = 'var(--gris-borde)';
                                    });
                                    document.querySelectorAll('.p-notif-item.nueva').forEach(n => {
                                        n.classList.remove('nueva');
                                    });
                                """)
                                ui.notify('Notificaciones marcadas como leídas', type='positive', position='top')
                            ui.button('✓ Marcar leídas', on_click=_marcar_leidas).props(
                                'flat dense'
                            ).style('font-size:12px;color:var(--azul-med);font-weight:600;')

                        notifs_cliente_ref = notifs_cliente  # captura local
                        if notifs_cliente_ref:
                            for n in notifs_cliente_ref:
                                _notif_item_html(n['nueva'], n['icon_cls'], n['icon'], n['titulo'], n['desc'], n['tiempo'])
                        else:
                            ui.html('''
                            <div style="text-align:center;padding:32px 0;color:var(--gris-texto);">
                                <div style="font-size:36px;margin-bottom:8px;">🔔</div>
                                <div style="font-size:13px;">Sin notificaciones nuevas</div>
                            </div>
                            ''')
                        # Botón WhatsApp — usa endpoint /open-whatsapp del servidor Python (único que funciona en pywebview)
                        with ui.element('div').style('margin-top:16px;border-top:1px solid var(--gris-borde);padding-top:14px;'):
                            ui.button(
                                'Contactar al Taller por WhatsApp',
                                icon='chat',
                                on_click=lambda: ui.run_javascript("fetch('/open-whatsapp?phone=51999999999&msg=Hola%2C%20necesito%20informaci%C3%B3n%20sobre%20mi%20veh%C3%ADculo')")
                            ).style(
                                'width:100%;background:#25d366;color:white;'
                                'font-weight:700;font-size:13px;border-radius:10px;padding:12px 0;'
                            ).props('no-caps')

                # ════════════════════════════════════════════════
                # 5. HISTORIAL DE SERVICIOS
                # ════════════════════════════════════════════════
                with ui.element('div').classes('p-card'):
                    with ui.element('div').style('display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;flex-wrap:wrap;gap:12px;'):
                        _section_title('📂', 'Historial de Servicios')
                        # Filtro activo guardado en dict mutable para closures
                        filtro_estado = {'valor': 'todos'}
                        tab_refs = {}
                        with ui.element('div').style('display:flex;gap:6px;'):
                            tab_refs['todos']      = ui.button('Todos',      on_click=lambda: _aplicar_filtro('todos')).style('font-size:12px;font-weight:700;padding:5px 14px;border-radius:20px;background:#1a3a6b;color:white;border:none;cursor:pointer;')
                            tab_refs['completado'] = ui.button('Completados', on_click=lambda: _aplicar_filtro('completado')).style('font-size:12px;font-weight:600;padding:5px 14px;border-radius:20px;background:#e8f0fb;color:#1a3a6b;border:none;cursor:pointer;')
                            tab_refs['proceso']    = ui.button('En Proceso',  on_click=lambda: _aplicar_filtro('proceso')).style('font-size:12px;font-weight:600;padding:5px 14px;border-radius:20px;background:#e8f0fb;color:#1a3a6b;border:none;cursor:pointer;')

                    if ordenes_all:
                        filas_html = ''
                        for o in ordenes_all:
                            total_o = sum(float(it.get('total', 0) or 0)
                                          for it in _safe_json(o.items_cotizacion))
                            estado_cls = ('completado' if o.estado in ('ARCHIVADO', 'ENTREGA')
                                          else 'proceso' if o.estado not in ('ARCHIVADO',)
                                          else 'pendiente')
                            badge_lbl  = ('✔ Completado' if estado_cls == 'completado'
                                          else '⏳ En Proceso')
                            try:
                                fd = datetime.strptime(o.fecha[:10], '%Y-%m-%d')
                                fecha_fmt = f'{fd.day} {_mes(fd.month)} {fd.year}'
                            except Exception:
                                fecha_fmt = o.fecha[:10] if o.fecha else '—'

                            motivo_corto = (o.motivo or 'Revisión general')
                            if len(motivo_corto) > 45:
                                motivo_corto = motivo_corto[:45] + '…'

                            # Botones de documentos: Presupuesto PDF + Factura SUNAT
                            pdf_path = getattr(o, 'pdf_cotizacion', '') or ''
                            factura_path = getattr(o, 'factura_sunat', '') or ''

                            docs_btns = ''
                            if pdf_path and os.path.exists(pdf_path):
                                docs_btns += f'<a href="/{pdf_path}" target="_blank" style="display:inline-flex;align-items:center;gap:3px;background:#274495;color:#fff;font-size:10px;font-weight:700;padding:3px 8px;border-radius:6px;text-decoration:none;margin-right:4px;">📄 Presupuesto</a>'
                            if factura_path and os.path.exists(factura_path):
                                docs_btns += f'<a href="/{factura_path}" target="_blank" style="display:inline-flex;align-items:center;gap:3px;background:#059669;color:#fff;font-size:10px;font-weight:700;padding:3px 8px;border-radius:6px;text-decoration:none;">🧾 Factura</a>'
                            if not docs_btns:
                                docs_btns = '<span style="color:var(--gris-texto);font-size:11px;">—</span>'

                            filas_html += f'''
                            <tr data-estado="{estado_cls}">
                                <td class="td-fecha">{fecha_fmt}</td>
                                <td class="td-servicio">{motivo_corto}</td>
                                <td style="color:var(--gris-texto);font-size:12px;">{o.vehiculo_placa or chr(8212)}</td>
                                <td><span class="p-folio">#{o.consecutivo}</span></td>
                                <td class="td-costo">S/ {total_o:,.2f}</td>
                                <td><span class="p-badge {estado_cls}">{badge_lbl}</span></td>
                                <td style="white-space:nowrap;">{docs_btns}</td>
                            </tr>
                            '''


                        # ── Separar filas por estado para filtrado Python-side ──
                        filas_por_estado = {
                            'todos': filas_html,
                            'completado': '',
                            'proceso': '',
                        }
                        for o2 in ordenes_all:
                            total_o2 = sum(float(it.get('total', 0) or 0) for it in _safe_json(o2.items_cotizacion))
                            e2 = ('completado' if o2.estado in ('ARCHIVADO', 'ENTREGA') else 'proceso')
                            badge2 = ('✔ Completado' if e2 == 'completado' else '⏳ En Proceso')
                            try:
                                fd2 = datetime.strptime(o2.fecha[:10], '%Y-%m-%d')
                                fecha2 = f'{fd2.day} {_mes(fd2.month)} {fd2.year}'
                            except Exception:
                                fecha2 = o2.fecha[:10] if o2.fecha else '—'
                            mot2 = (o2.motivo or 'Revisión general')[:45]
                            pdf2  = getattr(o2, 'pdf_cotizacion', '') or ''
                            fac2  = getattr(o2, 'factura_sunat', '') or ''
                            docs2 = ''
                            if pdf2 and os.path.exists(pdf2):
                                docs2 += f'<a href="/{pdf2}" target="_blank" style="display:inline-flex;align-items:center;gap:3px;background:#274495;color:#fff;font-size:10px;font-weight:700;padding:3px 8px;border-radius:6px;text-decoration:none;margin-right:4px;">📄 Presupuesto</a>'
                            if fac2 and os.path.exists(fac2):
                                docs2 += f'<a href="/{fac2}" target="_blank" style="display:inline-flex;align-items:center;gap:3px;background:#059669;color:#fff;font-size:10px;font-weight:700;padding:3px 8px;border-radius:6px;text-decoration:none;">🧾 Factura</a>'
                            if not docs2:
                                docs2 = '<span style="color:var(--gris-texto);font-size:11px;">—</span>'
                            fila2 = f'<tr><td class="td-fecha">{fecha2}</td><td class="td-servicio">{mot2}</td><td style="color:var(--gris-texto);font-size:12px;">{o2.vehiculo_placa or "—"}</td><td><span class="p-folio">#{o2.consecutivo}</span></td><td class="td-costo">S/ {total_o2:,.2f}</td><td><span class="p-badge {e2}">{badge2}</span></td><td style="white-space:nowrap;">{docs2}</td></tr>'
                            filas_por_estado[e2] += fila2

                        THEAD = '<table class="p-hist-table" id="histTable"><thead><tr><th>Fecha</th><th>Servicio</th><th>Vehículo</th><th>Orden</th><th>Costo</th><th>Estado</th><th>Presupuesto</th></tr></thead><tbody>'
                        TFOOTER = '</tbody></table>'
                        FILAS_PREVIEW = 5

                        # Tabla inicial — todos, primeras 5 filas
                        filas_lista_todos = [f for f in filas_por_estado['todos'].split('</tr>') if f.strip()]
                        mostrar_todo = {'activo': False}

                        tabla_el = ui.html(THEAD + ''.join(filas_lista_todos[:FILAS_PREVIEW]) + TFOOTER)

                        ver_mas_btn_ref = {'btn': None}

                        def _aplicar_filtro(nuevo_filtro: str):
                            filtro_estado['valor'] = nuevo_filtro
                            # Actualizar estilos de botones
                            activo_style  = 'font-size:12px;font-weight:700;padding:5px 14px;border-radius:20px;background:#1a3a6b;color:white;border:none;cursor:pointer;'
                            inactivo_style = 'font-size:12px;font-weight:600;padding:5px 14px;border-radius:20px;background:#e8f0fb;color:#1a3a6b;border:none;cursor:pointer;'
                            for k, btn in tab_refs.items():
                                btn.style(activo_style if k == nuevo_filtro else inactivo_style)
                            # Regenerar tabla con filas del filtro (todas visibles)
                            filas_filtradas = filas_por_estado.get(nuevo_filtro, filas_por_estado['todos'])
                            filas_lista_f = [f for f in filas_filtradas.split('</tr>') if f.strip()]
                            mostrar_todo['activo'] = True  # mostrar todas al filtrar
                            tabla_el.content = THEAD + ''.join(filas_lista_f) + TFOOTER
                            # Actualizar o esconder el botón "ver más"
                            if ver_mas_btn_ref['btn']:
                                ver_mas_btn_ref['btn'].visible = False

                        def _toggle_historial():
                            filas_lista_act = [f for f in filas_por_estado.get(filtro_estado['valor'], filas_por_estado['todos']).split('</tr>') if f.strip()]
                            mostrar_todo['activo'] = not mostrar_todo['activo']
                            if mostrar_todo['activo']:
                                tabla_el.content = THEAD + ''.join(filas_lista_act) + TFOOTER
                                ver_mas_btn_ref['btn'].set_text('← Mostrar menos')
                            else:
                                tabla_el.content = THEAD + ''.join(filas_lista_act[:FILAS_PREVIEW]) + TFOOTER
                                ver_mas_btn_ref['btn'].set_text(f'Ver historial completo ({len(filas_lista_todos)} registros) →')

                        if len(filas_lista_todos) > FILAS_PREVIEW:
                            btn_ver = ui.button(
                                f'Ver historial completo ({len(filas_lista_todos)} registros) →',
                                on_click=_toggle_historial
                            ).props('flat').style(
                                'width:100%;margin-top:8px;font-size:13px;font-weight:600;'
                                'color:var(--azul-med);border-radius:8px;'
                            )
                            ver_mas_btn_ref['btn'] = btn_ver
                    else:
                        ui.html('''
                        <div style="text-align:center;padding:40px 0;color:var(--gris-texto);">
                            <div style="font-size:36px;margin-bottom:8px;">📂</div>
                            <div style="font-size:13px;">Sin historial de servicios aún.</div>
                        </div>
                        ''')

                # ════════════════════════════════════════════════
                # 6. MIS EVIDENCIAS Y VIDEOS DE DIAGNÓSTICO
                # ════════════════════════════════════════════════
                _VIDEO_EXTS_P = {'.mp4', '.mov', '.avi', '.webm', '.mkv', '.m4v', '.3gp', '.ogg'}
                def _p_is_video(p):
                    import os
                    return os.path.splitext((p or '').lower())[1] in _VIDEO_EXTS_P

                # Recopilar todas las órdenes que tengan evidencias
                ordenes_con_ev = [(o, list(o.fotos_evidencia or [])) for o in ordenes_all if o.fotos_evidencia]
                if ordenes_con_ev:
                    with ui.element('div').classes('p-card'):
                        _section_title('\ud83d\udcc2', 'Mis Evidencias y Videos de Diagnóstico')
                        ui.html('<div style="font-size:12px;color:var(--gris-texto);margin-bottom:16px;">Aquí puedes ver todas las fotos y videos adjuntados por el técnico en tus visitas al taller.</div>')

                        for ord_ev, medios_ev in ordenes_con_ev:
                            fotos_p = [m for m in medios_ev if not _p_is_video(m)]
                            videos_p = [m for m in medios_ev if _p_is_video(m)]
                            if not (fotos_p or videos_p):
                                continue

                            try:
                                fd_ev = datetime.strptime(ord_ev.fecha[:10], '%Y-%m-%d')
                                fecha_ev = f'{fd_ev.day} {_mes(fd_ev.month)} {fd_ev.year}'
                            except Exception:
                                fecha_ev = ord_ev.fecha[:10] if ord_ev.fecha else ''

                            with ui.element('div').style('margin-bottom:24px;'):
                                ui.html(f'''
                                    <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
                                        <span style="font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:1px;color:#1a3a6b;">
                                            Orden #{ord_ev.consecutivo}
                                        </span>
                                        <span style="font-size:11px;color:var(--gris-texto);">— {fecha_ev}</span>
                                        <span style="font-size:10px;color:var(--gris-texto);">{ord_ev.motivo or ''}</span>
                                    </div>
                                ''')

                                if fotos_p:
                                    with ui.row().classes('gap-2 flex-wrap mb-3'):
                                        for fp in fotos_p:
                                            ui.html(f'''
                                                <a href="{fp}" target="_blank" style="display:block;width:90px;height:90px;
                                                    border-radius:10px;overflow:hidden;border:2px solid var(--gris-borde);
                                                    background:#f3f4f6;flex-shrink:0;">
                                                    <img src="{fp}" style="width:100%;height:100%;object-fit:cover;"
                                                        onerror="this.style.display='none'"/>
                                                </a>
                                            ''')

                                if videos_p:
                                    with ui.column().classes('gap-3 w-full'):
                                        for vp in videos_p:
                                            fn_v = vp.split('/')[-1]
                                            ui.html(f'''
                                                <div style="background:#0f172a;border-radius:12px;overflow:hidden;
                                                    border:1.5px solid #3b82f6;">
                                                    <video src="{vp}" controls preload="metadata" playsinline
                                                        style="width:100%;max-height:280px;display:block;">
                                                        Tu navegador no soporta video.
                                                    </video>
                                                    <div style="padding:8px 12px;display:flex;align-items:center;gap:8px;">
                                                        <span style="font-size:18px;">\ud83c\udfa5</span>
                                                        <span style="font-size:12px;color:#94a3b8;flex:1;">{fn_v}</span>
                                                        <a href="{vp}" target="_blank" style="font-size:11px;color:#60a5fa;font-weight:700;text-decoration:none;">Abrir →</a>
                                                    </div>
                                                </div>
                                            ''')

                # ════════════════════════════════════════════════
                # 7. MI CUENTA — Cambiar Contraseña
                # ════════════════════════════════════════════════
                with ui.element('div').classes('p-card'):
                    _section_title('🔐', 'Mi Cuenta')
                    ui.html('''
                    <p style="font-size:13px;color:var(--gris-texto);margin:0 0 18px 0;">
                        Aquí puede cambiar su contraseña de acceso al portal.
                        Use letras, números o un PIN. Su contraseña inicial es su DNI o RUC.
                    </p>
                    ''')

                    msg_cuenta = ui.label('').style(
                        'font-size:13px;font-weight:600;margin-bottom:8px;display:block;'
                    )
                    msg_cuenta.visible = False

                    with ui.element('div').style('display:grid;grid-template-columns:1fr 1fr;gap:14px;max-width:480px;'):
                        nueva_pass = ui.input(
                            'Nueva contraseña / PIN',
                            password=True,
                            password_toggle_button=True
                        ).props('outlined dense').style('width:100%;')
                        confirmar_pass = ui.input(
                            'Confirmar nueva contraseña',
                            password=True,
                            password_toggle_button=True
                        ).props('outlined dense').style('width:100%;')

                    ui.html('''
                    <p style="font-size:11px;color:var(--gris-texto);margin:8px 0 16px 0;">
                        Mínimo 4 caracteres. Puede usar letras, números o combinaciones.
                    </p>
                    ''')

                    def _cambiar_contrasena():
                        nueva = (nueva_pass.value or '').strip()
                        confirmar = (confirmar_pass.value or '').strip()
                        msg_cuenta.visible = True

                        if len(nueva) < 4:
                            msg_cuenta.text = '⚠ La contraseña debe tener al menos 4 caracteres.'
                            msg_cuenta.style(
                                'font-size:13px;font-weight:600;margin-bottom:8px;display:block;'
                                'color:#ef4444;'
                            )
                            return
                        if nueva != confirmar:
                            msg_cuenta.text = '⚠ Las contraseñas no coinciden. Intente nuevamente.'
                            msg_cuenta.style(
                                'font-size:13px;font-weight:600;margin-bottom:8px;display:block;'
                                'color:#ef4444;'
                            )
                            return

                        try:
                            db2 = get_db()
                            cli = db2.query(Cliente).filter_by(id=user_id).first()
                            if cli:
                                cli.pin_acceso = hash_password(nueva)
                                db2.commit()
                                msg_cuenta.text = '✅ Contraseña actualizada correctamente.'
                                msg_cuenta.style(
                                    'font-size:13px;font-weight:600;margin-bottom:8px;display:block;'
                                    'color:#1db97a;'
                                )
                                nueva_pass.value = ''
                                confirmar_pass.value = ''
                            else:
                                msg_cuenta.text = '⚠ Error: cliente no encontrado.'
                                msg_cuenta.style(
                                    'font-size:13px;font-weight:600;margin-bottom:8px;display:block;'
                                    'color:#ef4444;'
                                )
                            db2.close()
                        except Exception as ex:
                            msg_cuenta.text = f'⚠ Error al guardar: {ex}'
                            msg_cuenta.style(
                                'font-size:13px;font-weight:600;margin-bottom:8px;display:block;'
                                'color:#ef4444;'
                            )

                    ui.button(
                        'Actualizar Contraseña',
                        icon='lock_reset',
                        on_click=_cambiar_contrasena
                    ).style(
                        'background:#1a3a6b;color:white;font-weight:700;'
                        'border-radius:10px;padding:10px 22px;font-size:13px;'
                    )

    except Exception as exc:
        import traceback
        with container:
            ui.label(f'Error al cargar portal: {exc}').classes('text-red-500 p-8')
            ui.label(traceback.format_exc()).classes('text-xs font-mono text-gray-400 p-4')
    finally:
        db.close()


# ─── HELPERS DE RENDER ────────────────────────────────────────────────────────

def _render_tracker_card(order: 'Orden', vehiculo):
    PHASES = [
        ('RECEPCIÓN',  '📥'),
        ('DIAGNÓSTICO','🔍'),
        ('REPUESTOS',  '📦'),
        ('APROBACIÓN', '✅'),
        ('REPARACIÓN', '🔧'),
        ('CONTROL',    '🛡️'),
        ('ENTREGA',    '🚘'),
    ]
    # Mapa de normalización: variantes sin tilde → con tilde oficial
    _NORM = {
        'RECEPCION':  'RECEPCIÓN',
        'DIAGNOSTICO':'DIAGNÓSTICO',
        'APROBACION': 'APROBACIÓN',
        'REPARACION': 'REPARACIÓN',
    }
    estado_raw = (order.estado or '').upper().strip()
    estado = _NORM.get(estado_raw, estado_raw)
    current_idx = next(
        (i for i, (n, _) in enumerate(PHASES) if n == estado), 0
    )
    total_phases = len(PHASES)
    pct = int((current_idx / (total_phases - 1)) * 92) if total_phases > 1 else 0

    veh_label = ''
    if vehiculo:
        veh_label = f'{vehiculo.marca} {vehiculo.modelo} {vehiculo.año} — {vehiculo.placa}'.strip()

    # Generar HTML de fases
    phases_html = ''
    for i, (name, emoji) in enumerate(PHASES):
        if i < current_idx:
            cls   = 'done'
            inner = '✓'
            sub   = '✔ Listo'
        elif i == current_idx:
            cls   = 'active'
            inner = emoji
            sub   = '⏳ En curso'
        else:
            cls   = 'pending'
            inner = str(i + 1)
            sub   = '— Pendiente'

        phases_html += f'''
        <div class="phase-item {cls}">
            <div class="phase-circle">{inner}</div>
            <div class="phase-name">{name}</div>
            <div class="phase-sub">{sub}</div>
        </div>
        '''

    tecnico = order.tecnico or ''
    motivo  = order.motivo or 'Procesando...'

    ui.html(f'''
    <div class="p-tracker">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:28px;flex-wrap:wrap;gap:12px;">
            <div>
                <div style="font-size:17px;font-weight:800;color:var(--azul);margin-bottom:4px;">
                    Seguimiento en Vivo
                </div>
                <div style="font-size:13px;color:var(--gris-texto);">
                    Orden de Trabajo: <strong style="color:var(--azul);">#{order.consecutivo}</strong>
                    {f" · {veh_label}" if veh_label else ""}
                </div>
            </div>
            <div style="background:var(--azul-super-claro);color:var(--azul-med);
                        padding:6px 14px;border-radius:100px;font-size:12px;
                        font-weight:600;border:1px solid var(--azul-borde);">
                📋 Estado: {estado}
            </div>
        </div>

        <div class="phases-wrapper">
            <div class="phases-line"></div>
            <div class="phases-progress" style="width:{pct}%;"></div>
            {phases_html}
        </div>

        <div class="tracker-status">
            Estado actual: <strong>{estado}</strong>
            {f" — {motivo}" if motivo else ""}
            {f" · Mecánico: {tecnico}" if tecnico else ""}
        </div>
    </div>
    ''')


def _stat_card(icon, value, label):
    """Stat card mejorada con colores y animaciones"""
    # Definir colores según el icono
    colors = {
        '🚗': ('rgba(59, 130, 246, 0.15)', 'rgba(96, 165, 250, 0.05)', '#3b82f6', '#60a5fa'),
        '🔧': ('rgba(16, 185, 129, 0.15)', 'rgba(16, 185, 129, 0.05)', '#10b981', '#34d399'),
        '📋': ('rgba(139, 92, 246, 0.15)', 'rgba(139, 92, 246, 0.05)', '#8b5cf6', '#a78bfa'),
        '📅': ('rgba(245, 158, 11, 0.15)', 'rgba(245, 158, 11, 0.05)', '#f59e0b', '#fbbf24'),
    }
    bg, bg_icon, color_start, color_end = colors.get(icon, ('rgba(148, 163, 184, 0.1)', 'rgba(148, 163, 184, 0.05)', '#94a3b8', '#cbd5e1'))
    
    ui.html(f'''
    <div class="portal-stat-card" style="--color-start: {color_start}; --color-end: {color_end};">
        <div class="portal-stat-icon" style="background: {bg}; color: {color_start};">
            {icon}
        </div>
        <div class="p-stat-num" style="font-size: 2rem; font-weight: 900; color: #1e293b; margin-bottom: 0.25rem;">
            {value}
        </div>
        <div class="p-stat-label" style="font-size: 0.875rem; color: #64748b; font-weight: 600;">
            {label}
        </div>
    </div>
    ''')


def _section_title(icon, text):
    """Título de sección mejorado con estilo premium"""
    ui.html(f'''
    <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; padding-bottom: 0.75rem; border-bottom: 2px solid #f1f5f9;">
        <div style="width: 40px; height: 40px; border-radius: 12px; background: linear-gradient(135deg, rgba(39, 68, 149, 0.1), rgba(96, 165, 250, 0.05)); display: flex; align-items: center; justify-content: center; font-size: 20px;">
            {icon}
        </div>
        <span style="font-size: 1.125rem; font-weight: 800; color: #1e293b; letter-spacing: -0.5px;">
            {text}
        </span>
    </div>
    ''')


def _data_row(label, val):
    ui.html(f'''
    <div class="p-data-row">
        <span class="p-data-label">{label}</span>
        <span class="p-data-val">{val}</span>
    </div>
    ''')


def _notif_item_html(nueva: bool, icon_cls: str, icon: str, titulo: str, desc: str, tiempo: str):
    nueva_cls = 'nueva' if nueva else ''
    dot_cls   = '' if nueva else 'read'
    ui.html(f'''
    <div class="p-notif-item {nueva_cls}">
        <div class="p-ni-dot {dot_cls}"></div>
        <div class="p-ni-icon {icon_cls}">{icon}</div>
        <div style="flex:1;">
            <div class="p-ni-title">{titulo}</div>
            <div class="p-ni-desc">{desc}</div>
            <div class="p-ni-time">{tiempo}</div>
        </div>
    </div>
    ''')


# _build_client_notifications eliminada — se usa get_client_notifications() de utils/notifications.py


def _item_icon(nombre: str) -> str:
    n = nombre.lower()
    if any(x in n for x in ['aceite', 'lubric']): return '🛢️'
    if any(x in n for x in ['freno', 'pastill', 'disco']): return '🛞'
    if any(x in n for x in ['agua', 'refriger', 'anticongelante']): return '💧'
    if any(x in n for x in ['filtro']): return '🔄'
    if any(x in n for x in ['mano de obra', 'servicio', 'diagnóstico', 'diagnostico']): return '🔧'
    if any(x in n for x in ['batería', 'bateria', 'eléctric', 'electric']): return '⚡'
    if any(x in n for x in ['llanta', 'neumático', 'goma']): return '🚗'
    return '🔩'


def _mes(m: int) -> str:
    return ['', 'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
            'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'][m]


def _safe_json(data) -> list:
    if not data: return []
    if isinstance(data, list): return data
    try: return json.loads(data)
    except: return []


# ═══════════════════════════════════════════════════════════════
# DIÁLOGOS INTERACTIVOS PARA STATS CARDS
# ═══════════════════════════════════════════════════════════════

def _mostrar_vehiculos_dialog(db, cliente_id):
    """Muestra diálogo con lista de vehículos del cliente"""
    from utils.models import Vehiculo
    
    vehiculos = db.query(Vehiculo).filter_by(cliente_id=cliente_id).all()
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
        with ui.row().classes('w-full items-center justify-between mb-4 pb-4 border-b-2 border-gray-100'):
            ui.label('🚗 Mis Vehículos').classes('text-2xl font-black text-gray-900')
            ui.button(icon='close', on_click=dialog.close).props('flat round').classes('text-gray-400')
        
        if vehiculos:
            with ui.column().classes('w-full gap-4'):
                for v in vehiculos:
                    with ui.card().classes('w-full bg-gradient-to-r from-blue-50 to-white border-l-4 border-blue-500 hover:shadow-lg transition-all'):
                        with ui.row().classes('w-full items-center gap-4'):
                            with ui.element('div').classes('p-4 bg-blue-100 rounded-xl'):
                                ui.icon('directions_car', size='xl').classes('text-blue-600')
                            
                            with ui.column().classes('flex-1 gap-1'):
                                ui.label(f'{v.marca} {v.modelo} {v.año}'.strip()).classes('text-lg font-bold text-gray-900')
                                ui.label(f'Placa: {v.placa}').classes('text-sm text-gray-600 font-semibold')
                                if v.color:
                                    ui.label(f'Color: {v.color}').classes('text-sm text-gray-500')
                            
                            with ui.badge().props('color=blue'):
                                ui.label(v.tipo_vehiculo or 'Auto')
        else:
            ui.label('No hay vehículos registrados').classes('text-center text-gray-400 py-8')
    
    dialog.open()


def _mostrar_servicio_dialog(orden, vehiculo):
    """Muestra detalles del servicio activo"""
    if not orden:
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-md'):
            ui.label('No hay servicio activo').classes('text-center text-gray-400 py-8')
            ui.button('Cerrar', on_click=dialog.close).classes('w-full btn-sandoval')
        dialog.open()
        return
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
        with ui.row().classes('w-full items-center justify-between mb-4 pb-4 border-b-2 border-gray-100'):
            ui.label('🔧 Servicio Activo').classes('text-2xl font-black text-gray-900')
            ui.button(icon='close', on_click=dialog.close).props('flat round').classes('text-gray-400')
        
        # Info del vehículo
        if vehiculo:
            with ui.card().classes('w-full bg-gradient-to-r from-green-50 to-white border-l-4 border-green-500 mb-4'):
                ui.label(f'🚗 {vehiculo.marca} {vehiculo.modelo} - {vehiculo.placa}').classes('text-lg font-bold text-gray-900 mb-2')
                with ui.grid(columns=2).classes('w-full gap-2 text-sm'):
                    ui.label(f'📍 Estado: ').classes('text-gray-600 font-semibold')
                    with ui.badge().props(f'color={_get_estado_color(orden.estado)}'):
                        ui.label(orden.estado)
                    
                    ui.label(f'👨‍🔧 Técnico: ').classes('text-gray-600 font-semibold')
                    ui.label(orden.tecnico or 'No asignado').classes('text-gray-900')
                    
                    ui.label(f'📅 Ingreso: ').classes('text-gray-600 font-semibold')
                    ui.label(orden.fecha or '—').classes('text-gray-900')
        
        # Servicios
        if orden.items_cotizacion:
            ui.label('Servicios solicitados:').classes('text-lg font-bold text-gray-900 mt-4 mb-2')
            with ui.column().classes('w-full gap-2'):
                for item in orden.items_cotizacion:
                    desc = item.get('descripcion', 'Servicio')
                    cant = item.get('cantidad', 1)
                    ui.label(f'• {desc} (x{cant})').classes('text-sm text-gray-700')
        
        ui.button('Cerrar', on_click=dialog.close).classes('w-full btn-sandoval mt-4')
    
    dialog.open()


def _mostrar_historial_dialog(db, cliente_id):
    """Muestra historial de visitas del cliente"""
    from utils.models import Orden, Vehiculo
    
    ordenes = db.query(Orden).join(Vehiculo).filter(Vehiculo.cliente_id == cliente_id).order_by(Orden.fecha.desc()).limit(20).all()
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-3xl').style('max-height: 80vh; overflow-y: auto;'):
        with ui.row().classes('w-full items-center justify-between mb-4 pb-4 border-b-2 border-gray-100'):
            ui.label('📋 Historial de Visitas').classes('text-2xl font-black text-gray-900')
            ui.button(icon='close', on_click=dialog.close).props('flat round').classes('text-gray-400')
        
        if ordenes:
            with ui.column().classes('w-full gap-3'):
                for o in ordenes:
                    vehiculo = db.query(Vehiculo).filter_by(id=o.vehiculo_id).first()
                    with ui.card().classes('w-full hover:shadow-lg transition-all border-l-4').style(f'border-color: {_get_estado_color(o.estado)};'):
                        with ui.row().classes('w-full items-start justify-between'):
                            with ui.column().classes('flex-1 gap-1'):
                                ui.label(f'Orden #{o.consecutivo}').classes('text-lg font-bold text-gray-900')
                                if vehiculo:
                                    ui.label(f'🚗 {vehiculo.marca} {vehiculo.modelo} - {vehiculo.placa}').classes('text-sm text-gray-600')
                                ui.label(f'📅 {o.fecha}').classes('text-xs text-gray-500')
                            
                            with ui.badge().props(f'color={_get_estado_color(o.estado)}'):
                                ui.label(o.estado)
        else:
            ui.label('No hay historial de visitas').classes('text-center text-gray-400 py-8')
    
    dialog.open()


def _mostrar_cita_dialog(db, cliente_id):
    """Muestra próxima cita o permite agendar"""
    from utils.models import Cita, Vehiculo
    from datetime import datetime
    
    # Buscar próxima cita
    citas = db.query(Cita).join(Vehiculo).filter(
        Vehiculo.cliente_id == cliente_id,
        Cita.estado == 'pendiente'
    ).order_by(Cita.fecha_hora).all()
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
        with ui.row().classes('w-full items-center justify-between mb-4 pb-4 border-b-2 border-gray-100'):
            ui.label('📅 Mis Citas').classes('text-2xl font-black text-gray-900')
            ui.button(icon='close', on_click=dialog.close).props('flat round').classes('text-gray-400')
        
        if citas:
            ui.label(f'Tienes {len(citas)} cita(s) programada(s):').classes('text-lg font-semibold text-gray-700 mb-3')
            with ui.column().classes('w-full gap-3'):
                for cita in citas[:5]:
                    vehiculo = db.query(Vehiculo).filter_by(id=cita.vehiculo_id).first()
                    with ui.card().classes('w-full bg-gradient-to-r from-orange-50 to-white border-l-4 border-orange-500'):
                        with ui.row().classes('w-full items-center gap-4'):
                            with ui.element('div').classes('p-4 bg-orange-100 rounded-xl'):
                                ui.icon('event', size='xl').classes('text-orange-600')
                            
                            with ui.column().classes('flex-1 gap-1'):
                                ui.label(f'📅 {cita.fecha_hora}').classes('text-lg font-bold text-gray-900')
                                if vehiculo:
                                    ui.label(f'🚗 {vehiculo.marca} {vehiculo.modelo} - {vehiculo.placa}').classes('text-sm text-gray-600')
                                if cita.motivo:
                                    ui.label(f'Motivo: {cita.motivo}').classes('text-sm text-gray-500')
        else:
            with ui.column().classes('w-full items-center gap-4 py-8'):
                ui.icon('event_busy', size='64px').classes('text-gray-300')
                ui.label('No tienes citas programadas').classes('text-lg text-gray-400 font-semibold')
                ui.label('Comunícate con el taller para agendar una cita').classes('text-sm text-gray-500')
                with ui.row().classes('gap-2 mt-4'):
                    ui.button('📞 Llamar', icon='phone').classes('bg-green-600 text-white')
                    ui.button('💬 WhatsApp', icon='chat').classes('bg-green-500 text-white')
    
    dialog.open()


def _get_estado_color(estado):
    """Retorna color Quasar según el estado"""
    colores = {
        'RECEPCION': 'blue',
        'DIAGNOSTICO': 'purple',
        'COTIZACION': 'orange',
        'EN_TRABAJO': 'indigo',
        'CONTROL_CALIDAD': 'teal',
        'ENTREGA': 'green',
        'RECHAZADO': 'red',
        'ARCHIVADO': 'grey'
    }
    return colores.get(estado, 'grey')

