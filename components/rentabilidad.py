"""
SANDOVAL Dashboard - Dashboard de Rentabilidad v1.0
Análisis completo de ingresos, costos, márgenes y rendimiento
"""

from nicegui import ui
from utils.models import get_db, Orden, Cliente, Vehiculo, ItemInventario
from datetime import datetime, timedelta
import json


# ── Helpers de cálculo ────────────────────────────────────────────────────────

def _parse_items(items_raw) -> list:
    """Parsea items_cotizacion (JSON string o list)"""
    if not items_raw:
        return []
    try:
        if isinstance(items_raw, str):
            return json.loads(items_raw)
        if isinstance(items_raw, list):
            return items_raw
    except Exception:
        pass
    return []


def _build_costo_map(db) -> dict:
    """
    Construye mapa {codigo: costo} Y {nombre_lower: costo} desde ItemInventario.
    Prioriza búsqueda por código (campo referencia/ref de los items).
    """
    costo_map = {}
    try:
        items_inv = db.query(ItemInventario).all()
        for inv in items_inv:
            costo_val = float(inv.costo or 0)
            if inv.codigo:
                costo_map[inv.codigo.strip()] = costo_val
            nombre_key = (inv.nombre or '').strip().lower()
            if nombre_key and nombre_key not in costo_map:
                costo_map[nombre_key] = costo_val
    except Exception:
        pass
    return costo_map


def _calcular_orden(o, costo_map: dict) -> dict:
    """
    Retorna dict con: cobrado, costo_rep, ganancia, margen.
    Busca el costo real de cada ítem en el mapa de inventario.
    Si no encuentra, usa el 60% del precio como estimado.
    """
    items = _parse_items(o.items_cotizacion)
    cobrado = 0.0
    costo_rep = 0.0
    for it in items:
        try:
            qty = float(it.get('cantidad', 1) or 1)
            cat = (it.get('categoria') or '').strip().lower()
            ref = (it.get('referencia') or it.get('ref') or '').strip()
            nombre_key = (it.get('nombre') or '').strip().lower()

            # Monto cobrado: preferir 'total', sino precio_unitario * qty
            if it.get('total') not in (None, '', 0):
                cobrado += float(it['total'])
            elif it.get('precio_unitario') not in (None, ''):
                cobrado += float(it.get('precio_unitario', 0)) * qty

            # Mano de obra: costo = 0 (100% ganancia)
            es_mo = (cat in ('servicio', 'mano de obra')
                     or ref == 'MANO-DE-OBRA'
                     or nombre_key.startswith('mano de obra'))
            if es_mo:
                continue  # costo 0, no suma a costo_rep

            # Costo repuesto: 1) campo costo en ítem, 2) por código ref, 3) por nombre
            costo_unit = float(it.get('costo', 0) or 0)
            if costo_unit == 0 and ref:
                costo_unit = costo_map.get(ref, 0)
            if costo_unit == 0 and nombre_key:
                costo_unit = costo_map.get(nombre_key, 0)
            # Sin fallback estimado: si no hay costo en inventario, queda 0
            costo_rep += costo_unit * qty
        except Exception:
            pass
    ganancia = cobrado - costo_rep
    margen = (ganancia / cobrado * 100) if cobrado > 0 else 0
    return {
        'cobrado': cobrado,
        'costo_rep': costo_rep,
        'ganancia': ganancia,
        'margen': margen,
    }


def _get_data():
    """Obtiene y agrupa todos los datos de rentabilidad desde la BD"""
    db = get_db()
    try:
        ordenes = db.query(Orden).all()
        # Excluir solo órdenes sin items (vacías)
        ordenes = [o for o in ordenes if o.items_cotizacion and o.items_cotizacion != '[]']

        # Mapa de costos desde inventario {nombre_lower: costo}
        costo_map = _build_costo_map(db)

        # --- KPIs globales ---
        ingresos_total = 0.0
        costos_total = 0.0
        ordenes_calc = []

        for o in ordenes:
            calc = _calcular_orden(o, costo_map)
            ordenes_calc.append((o, calc))
            ingresos_total += calc['cobrado']
            costos_total += calc['costo_rep']

        ganancia_total = ingresos_total - costos_total
        margen_prom = (ganancia_total / ingresos_total * 100) if ingresos_total > 0 else 0
        ticket_prom = (ingresos_total / len(ordenes_calc)) if ordenes_calc else 0

        # --- Últimas 8 semanas (ingresos vs costos) ---
        hoy = datetime.now()
        semanas = []
        for i in range(7, -1, -1):
            inicio = hoy - timedelta(weeks=i + 1)
            fin = hoy - timedelta(weeks=i)
            label = fin.strftime('%d/%m')
            ing_s = 0.0
            cos_s = 0.0
            for o, calc in ordenes_calc:
                try:
                    f = str(o.fecha or '')[:10]
                    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
                        try:
                            fecha_o = datetime.strptime(f, fmt)
                            break
                        except Exception:
                            fecha_o = None
                    if fecha_o and inicio <= fecha_o < fin:
                        ing_s += calc['cobrado']
                        cos_s += calc['costo_rep']
                except Exception:
                    pass
            semanas.append({'label': label, 'ingresos': ing_s, 'costos': cos_s})

        # --- Composición: mano de obra vs repuestos (ingresos reales por categoría) ---
        ing_mo = 0.0
        ing_rep_real = 0.0
        for o, _ in ordenes_calc:
            for it in _parse_items(o.items_cotizacion):
                try:
                    total_it = float(it.get('total') or float(it.get('precio_unitario', 0)) * float(it.get('cantidad', 1)))
                    cat = (it.get('categoria') or '').strip().lower()
                    ref = (it.get('referencia') or it.get('ref') or '').strip()
                    nombre_it = (it.get('nombre') or '').strip().lower()
                    es_mo = (cat in ('servicio', 'mano de obra')
                             or ref == 'MANO-DE-OBRA'
                             or nombre_it.startswith('mano de obra'))
                    if es_mo:
                        ing_mo += total_it
                    else:
                        ing_rep_real += total_it
                except Exception:
                    pass
        total_rep = ing_rep_real
        total_mo = ing_mo

        # --- Ranking de servicios (por motivo) ---
        servicios: dict = {}
        for o, calc in ordenes_calc:
            motivo = (o.motivo or 'Sin especificar').strip()[:40]
            if motivo not in servicios:
                servicios[motivo] = {'cobrado': 0, 'costo': 0, 'count': 0}
            servicios[motivo]['cobrado'] += calc['cobrado']
            servicios[motivo]['costo'] += calc['costo_rep']
            servicios[motivo]['count'] += 1

        ranking = []
        for svc, vals in servicios.items():
            gan = vals['cobrado'] - vals['costo']
            mrg = (gan / vals['cobrado'] * 100) if vals['cobrado'] > 0 else 0
            ranking.append({'servicio': svc, 'cobrado': vals['cobrado'], 'ganancia': gan, 'margen': mrg, 'count': vals['count']})
        ranking.sort(key=lambda x: x['ganancia'], reverse=True)
        ranking = ranking[:8]

        # --- Rendimiento por técnico ---
        tecnicos: dict = {}
        for o, calc in ordenes_calc:
            tec = (o.tecnico or 'Sin asignar').strip()
            if tec not in tecnicos:
                tecnicos[tec] = {'cobrado': 0, 'costo': 0, 'count': 0}
            tecnicos[tec]['cobrado'] += calc['cobrado']
            tecnicos[tec]['costo'] += calc['costo_rep']
            tecnicos[tec]['count'] += 1

        tec_list = []
        max_cobrado = 1.0
        for tec, vals in tecnicos.items():
            gan = vals['cobrado'] - vals['costo']
            mrg = (gan / vals['cobrado'] * 100) if vals['cobrado'] > 0 else 0
            tec_list.append({'nombre': tec, 'cobrado': vals['cobrado'], 'ganancia': gan, 'margen': mrg, 'count': vals['count']})
            if vals['cobrado'] > max_cobrado:
                max_cobrado = vals['cobrado']
        tec_list.sort(key=lambda x: x['cobrado'], reverse=True)
        tec_list = tec_list[:6]
        for t in tec_list:
            t['pct'] = min(100, int(t['cobrado'] / max_cobrado * 100))

        # --- Alertas de rentabilidad ---
        alertas = []
        for o, calc in ordenes_calc:
            if calc['cobrado'] > 0 and calc['margen'] < 20:
                alertas.append({
                    'tipo': 'danger' if calc['margen'] < 10 else 'warning',
                    'orden': o.consecutivo or str(o.id),
                    'cliente': o.cliente_id or '—',
                    'margen': calc['margen'],
                    'cobrado': calc['cobrado'],
                })
        alertas.sort(key=lambda x: x['margen'])
        alertas = alertas[:5]

        # --- Tabla detalle órdenes (top 30 por ganancia) ---
        tabla = []
        for o, calc in ordenes_calc:
            nombre_cliente = o.cliente_id or '—'
            try:
                cl = db.query(Cliente).filter_by(id=o.cliente_id).first()
                if cl:
                    nombre_cliente = f"{cl.nombre} {cl.apellidos}".strip()
            except Exception:
                pass
            tabla.append({
                'orden': o.consecutivo or f'#{o.id}',
                'cliente': nombre_cliente,
                'vehiculo': o.vehiculo_placa or '—',
                'servicio': (o.motivo or '—')[:35],
                'cobrado': calc['cobrado'],
                'costo_rep': calc['costo_rep'],
                'ganancia': calc['ganancia'],
                'margen': calc['margen'],
                'estado': o.estado or '—',
                'fecha': str(o.fecha)[:10] if o.fecha else '—',
            })
        tabla.sort(key=lambda x: x['ganancia'], reverse=True)
        tabla = tabla[:30]

        return {
            'ingresos': ingresos_total,
            'costos': costos_total,
            'ganancia': ganancia_total,
            'margen_prom': margen_prom,
            'ticket_prom': ticket_prom,
            'total_ordenes': len(ordenes_calc),
            'semanas': semanas,
            'total_rep': total_rep,
            'total_mo': total_mo,
            'ranking': ranking,
            'tecnicos': tec_list,
            'alertas': alertas,
            'tabla': tabla,
        }
    finally:
        db.close()


# ── Sección: Header ───────────────────────────────────────────────────────────

def _header(container):
    with container:
        with ui.row().classes('w-full items-center justify-between mb-2'):
            with ui.column().classes('gap-1'):
                ui.label('Dashboard de Rentabilidad').classes('text-3xl font-black text-gray-900 tracking-tight')
                ui.label('Análisis de ingresos, costos y márgenes en tiempo real').classes('text-sm text-gray-400 font-medium')
            with ui.row().classes('items-center gap-3'):
                ui.chip(
                    datetime.now().strftime('%B %Y').title(),
                    icon='calendar_today',
                ).props('outline color=blue-8').classes('text-xs font-bold')
                ui.chip('En vivo', icon='circle').props('color=green-6').classes('text-xs font-bold text-white')


# ── Sección: KPIs ─────────────────────────────────────────────────────────────

def _kpis(container, d):
    kpis = [
        {
            'label': 'Ingresos Netos',
            'value': f"S/ {d['ingresos']:,.0f}",
            'icon': 'trending_up',
            'color': '#274495',
            'bg': '#eff6ff',
            'sub': f"{d['total_ordenes']} órdenes cobradas",
        },
        {
            'label': 'Costo Repuestos',
            'value': f"S/ {d['costos']:,.0f}",
            'icon': 'build_circle',
            'color': '#f59e0b',
            'bg': '#fffbeb',
            'sub': f"{(d['costos']/d['ingresos']*100 if d['ingresos'] else 0):.1f}% de ingresos",
        },
        {
            'label': 'Ganancia Bruta',
            'value': f"S/ {d['ganancia']:,.0f}",
            'icon': 'payments',
            'color': '#059669',
            'bg': '#f0fdf4',
            'sub': 'Ingresos − Costos',
        },
        {
            'label': 'Margen Promedio',
            'value': f"{d['margen_prom']:.1f}%",
            'icon': 'percent',
            'color': '#7c3aed',
            'bg': '#f5f3ff',
            'sub': 'Rentabilidad por orden',
        },
        {
            'label': 'Ticket Promedio',
            'value': f"S/ {d['ticket_prom']:,.0f}",
            'icon': 'receipt_long',
            'color': '#0891b2',
            'bg': '#ecfeff',
            'sub': 'Por orden de servicio',
        },
    ]

    with container:
        with ui.row().classes('w-full gap-4'):
            for k in kpis:
                with ui.card().classes('flex-1 bg-white border border-gray-100 p-5 card-sandoval'):
                    with ui.row().classes('w-full items-center justify-between mb-3'):
                        ui.label(k['label']).classes('text-xs text-gray-500 font-bold uppercase tracking-wider')
                        with ui.element('div').style(f'background:{k["bg"]};border-radius:10px;padding:8px;'):
                            ui.icon(k['icon'], size='22px').style(f'color:{k["color"]}')
                    ui.label(k['value']).classes('text-2xl font-black text-gray-900 tracking-tight mb-1')
                    ui.label(k['sub']).classes('text-xs text-gray-400 font-medium')


# ── Sección: Gráfico semanal ──────────────────────────────────────────────────

def _chart_semanal(container, d):
    semanas = d['semanas']
    labels = [s['label'] for s in semanas]
    ingresos_data = [round(s['ingresos'], 2) for s in semanas]
    costos_data = [round(s['costos'], 2) for s in semanas]
    ganancias_data = [round(s['ingresos'] - s['costos'], 2) for s in semanas]

    fig = {
        'data': [
            {
                'type': 'bar',
                'name': 'Ingresos',
                'x': labels,
                'y': ingresos_data,
                'marker': {'color': '#274495'},
                'opacity': 0.9,
            },
            {
                'type': 'bar',
                'name': 'Costos',
                'x': labels,
                'y': costos_data,
                'marker': {'color': '#f59e0b'},
                'opacity': 0.85,
            },
            {
                'type': 'scatter',
                'mode': 'lines+markers',
                'name': 'Ganancia',
                'x': labels,
                'y': ganancias_data,
                'line': {'color': '#059669', 'width': 2},
                'marker': {'color': '#059669', 'size': 6},
                'yaxis': 'y2',
            },
        ],
        'layout': {
            'barmode': 'group',
            'paper_bgcolor': 'white',
            'plot_bgcolor': 'white',
            'font': {'family': 'Outfit, sans-serif', 'color': '#475569', 'size': 12},
            'margin': {'l': 50, 'r': 50, 't': 20, 'b': 40},
            'legend': {'orientation': 'h', 'y': -0.2, 'x': 0.5, 'xanchor': 'center', 'font': {'size': 11}},
            'xaxis': {'showgrid': False, 'tickfont': {'size': 10}},
            'yaxis': {'showgrid': True, 'gridcolor': '#f1f5f9', 'tickprefix': 'S/ ', 'tickfont': {'size': 10}},
            'yaxis2': {
                'overlaying': 'y',
                'side': 'right',
                'showgrid': False,
                'tickprefix': 'S/ ',
                'tickfont': {'size': 10},
            },
            'bargap': 0.25,
            'bargroupgap': 0.1,
        }
    }

    with container:
        with ui.card().classes('flex-1 bg-white border border-gray-100 p-6 card-sandoval'):
            with ui.row().classes('items-center gap-3 mb-4'):
                with ui.element('div').style('background:#eff6ff;border-radius:10px;padding:8px'):
                    ui.icon('bar_chart', size='22px').style('color:#274495')
                with ui.column().classes('gap-0'):
                    ui.label('Ingresos vs Costos').classes('text-base font-bold text-gray-800')
                    ui.label('Últimas 8 semanas').classes('text-xs text-gray-400')
            ui.plotly(fig).classes('w-full').style('height:280px')


# ── Sección: Donut composición ────────────────────────────────────────────────

def _chart_donut(container, d):
    total = d['total_mo'] + d['total_rep']
    pct_mo = (d['total_mo'] / total * 100) if total > 0 else 0
    pct_rep = (d['total_rep'] / total * 100) if total > 0 else 0

    fig = {
        'data': [{
            'type': 'pie',
            'hole': 0.65,
            'labels': ['Mano de Obra', 'Repuestos'],
            'values': [max(d['total_mo'], 0.01), max(d['total_rep'], 0.01)],
            'marker': {'colors': ['#274495', '#f59e0b']},
            'textinfo': 'none',
            'hovertemplate': '%{label}: S/ %{value:,.0f}<extra></extra>',
        }],
        'layout': {
            'paper_bgcolor': 'white',
            'plot_bgcolor': 'white',
            'font': {'family': 'Outfit, sans-serif'},
            'margin': {'l': 10, 'r': 10, 't': 10, 'b': 10},
            'showlegend': True,
            'legend': {
                'orientation': 'v',
                'x': 1.05,
                'y': 0.5,
                'font': {'size': 11, 'color': '#475569'},
            },
            'annotations': [{
                'text': f'{pct_mo:.0f}%<br>M.O.',
                'x': 0.5, 'y': 0.5,
                'font': {'size': 16, 'color': '#274495', 'family': 'Outfit'},
                'showarrow': False,
                'align': 'center',
            }],
        }
    }

    with container:
        with ui.card().classes('bg-white border border-gray-100 p-6 card-sandoval').style('width:320px;flex-shrink:0'):
            with ui.row().classes('items-center gap-3 mb-4'):
                with ui.element('div').style('background:#eff6ff;border-radius:10px;padding:8px'):
                    ui.icon('donut_large', size='22px').style('color:#274495')
                with ui.column().classes('gap-0'):
                    ui.label('Composición').classes('text-base font-bold text-gray-800')
                    ui.label('M.O. vs Repuestos').classes('text-xs text-gray-400')
            ui.plotly(fig).classes('w-full').style('height:200px')
            ui.separator().classes('my-3')
            with ui.row().classes('w-full justify-around'):
                with ui.column().classes('items-center gap-0'):
                    ui.label(f"S/ {d['total_mo']:,.0f}").classes('text-sm font-black text-[#274495]')
                    ui.label('Mano de Obra').classes('text-[10px] text-gray-400 font-medium')
                with ui.column().classes('items-center gap-0'):
                    ui.label(f"S/ {d['total_rep']:,.0f}").classes('text-sm font-black text-amber-500')
                    ui.label('Repuestos').classes('text-[10px] text-gray-400 font-medium')


# ── Sección: Ranking servicios ────────────────────────────────────────────────

def _ranking_servicios(container, ranking):
    with container:
        with ui.card().classes('bg-white border border-gray-100 p-6 card-sandoval').style('min-width:340px;flex:1'):
            with ui.row().classes('items-center gap-3 mb-4'):
                with ui.element('div').style('background:#f0fdf4;border-radius:10px;padding:8px'):
                    ui.icon('emoji_events', size='22px').style('color:#059669')
                with ui.column().classes('gap-0'):
                    ui.label('Servicios más Rentables').classes('text-base font-bold text-gray-800')
                    ui.label('Ranking por ganancia bruta').classes('text-xs text-gray-400')

            if not ranking:
                ui.label('Sin datos aún').classes('text-gray-400 text-sm text-center w-full py-4')
                return

            max_gan = max((r['ganancia'] for r in ranking), default=1)
            for i, svc in enumerate(ranking):
                mrg = svc['margen']
                if mrg >= 50:
                    badge_color, badge_bg = '#059669', '#f0fdf4'
                    badge_txt = 'Alto'
                elif mrg >= 25:
                    badge_color, badge_bg = '#f59e0b', '#fffbeb'
                    badge_txt = 'Medio'
                else:
                    badge_color, badge_bg = '#ef4444', '#fef2f2'
                    badge_txt = 'Bajo'

                pct_bar = int(svc['ganancia'] / max_gan * 100) if max_gan > 0 else 0

                with ui.row().classes('w-full items-center gap-3 mb-3'):
                    with ui.element('div').style(
                        'width:24px;height:24px;border-radius:6px;background:#f1f5f9;'
                        'display:flex;align-items:center;justify-content:center;'
                        f'font-size:10px;font-weight:800;color:#94a3b8;flex-shrink:0'
                    ):
                        ui.label(str(i + 1))
                    with ui.column().classes('flex-1 gap-1'):
                        with ui.row().classes('w-full items-center justify-between'):
                            ui.label(svc['servicio']).classes('text-xs font-bold text-gray-700').style('max-width:160px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis')
                            with ui.row().classes('items-center gap-2'):
                                ui.label(f"S/ {svc['ganancia']:,.0f}").classes('text-xs font-black text-gray-800')
                                with ui.element('span').style(
                                    f'background:{badge_bg};color:{badge_color};'
                                    'font-size:9px;font-weight:800;padding:2px 6px;'
                                    'border-radius:999px;'
                                ):
                                    ui.label(f"{mrg:.0f}% {badge_txt}")
                        with ui.element('div').style('width:100%;background:#f1f5f9;border-radius:999px;height:4px;overflow:hidden'):
                            ui.element('div').style(f'width:{pct_bar}%;background:#274495;height:4px;border-radius:999px;transition:width 0.5s')


# ── Sección: Rendimiento técnicos ─────────────────────────────────────────────

def _rendimiento_tecnicos(container, tec_list):
    with container:
        with ui.card().classes('bg-white border border-gray-100 p-6 card-sandoval').style('min-width:320px;flex:1'):
            with ui.row().classes('items-center gap-3 mb-4'):
                with ui.element('div').style('background:#f5f3ff;border-radius:10px;padding:8px'):
                    ui.icon('engineering', size='22px').style('color:#7c3aed')
                with ui.column().classes('gap-0'):
                    ui.label('Técnicos por Ingresos').classes('text-base font-bold text-gray-800')
                    ui.label('Facturación generada por técnico').classes('text-xs text-gray-400')

            if not tec_list:
                ui.label('Sin datos aún').classes('text-gray-400 text-sm text-center w-full py-4')
                return

            for tec in tec_list:
                initials = ''.join(w[0].upper() for w in tec['nombre'].split()[:2]) or '?'
                with ui.row().classes('w-full items-center gap-3 mb-4'):
                    ui.avatar(initials, color='blue-9', text_color='white').props('size=sm').classes('font-bold flex-shrink-0')
                    with ui.column().classes('flex-1 gap-1'):
                        with ui.row().classes('w-full items-center justify-between'):
                            ui.label(tec['nombre']).classes('text-xs font-bold text-gray-700')
                            ui.label(f"S/ {tec['cobrado']:,.0f}").classes('text-xs font-black text-[#274495]')
                        with ui.element('div').style('width:100%;background:#f1f5f9;border-radius:999px;height:6px;overflow:hidden'):
                            color = '#274495' if tec['pct'] >= 60 else ('#7c3aed' if tec['pct'] >= 30 else '#94a3b8')
                            ui.element('div').style(f'width:{tec["pct"]}%;background:{color};height:6px;border-radius:999px;transition:width 0.5s')
                        with ui.row().classes('w-full items-center justify-between'):
                            ui.label(f"{tec['count']} órdenes").classes('text-[10px] text-gray-400')
                            ui.label(f"Margen {tec['margen']:.0f}%").classes('text-[10px] text-gray-400')


# ── Sección: Alertas rentabilidad ─────────────────────────────────────────────

def _alertas(container, alertas):
    with container:
        with ui.card().classes('bg-white border border-gray-100 p-6 card-sandoval'):
            with ui.row().classes('items-center gap-3 mb-4'):
                with ui.element('div').style('background:#fef2f2;border-radius:10px;padding:8px'):
                    ui.icon('warning_amber', size='22px').style('color:#ef4444')
                with ui.column().classes('gap-0'):
                    ui.label('Alertas de Rentabilidad').classes('text-base font-bold text-gray-800')
                    ui.label('Órdenes con margen bajo').classes('text-xs text-gray-400')

            if not alertas:
                with ui.column().classes('w-full items-center py-6'):
                    ui.icon('check_circle', size='40px').classes('text-green-400 mb-2')
                    ui.label('¡Todas las órdenes tienen margen saludable!').classes('text-sm text-gray-400 text-center')
                return

            for a in alertas:
                border_color = '#fca5a5' if a['tipo'] == 'danger' else '#fcd34d'
                bg_color = '#fef2f2' if a['tipo'] == 'danger' else '#fffbeb'
                icon_name = 'error_outline' if a['tipo'] == 'danger' else 'warning_amber'
                icon_color = '#ef4444' if a['tipo'] == 'danger' else '#f59e0b'
                with ui.element('div').style(
                    f'width:100%;background:{bg_color};border:1px solid {border_color};'
                    'border-radius:10px;padding:10px 14px;margin-bottom:8px;'
                    'display:flex;align-items:center;gap:12px'
                ):
                    ui.icon(icon_name, size='18px').style(f'color:{icon_color};flex-shrink:0')
                    with ui.column().classes('flex-1 gap-0'):
                        ui.label(f"Orden {a['orden']} — {a['cliente']}").classes('text-xs font-bold text-gray-700')
                        ui.label(f"Margen {a['margen']:.1f}% · Cobrado S/ {a['cobrado']:,.0f}").classes('text-[10px] text-gray-500')


# ── Sección: Tabla detalle ────────────────────────────────────────────────────

def _tabla_detalle(container, tabla):
    HEADER_STYLE = 'text-[10px] font-black text-gray-400 uppercase tracking-wider text-right'
    CELL_STYLE = 'text-xs font-semibold text-gray-700 text-right'

    with container:
        with ui.card().classes('w-full bg-white border border-gray-100 p-6 card-sandoval'):
            with ui.row().classes('w-full items-center justify-between mb-4'):
                with ui.row().classes('items-center gap-3'):
                    with ui.element('div').style('background:#ecfeff;border-radius:10px;padding:8px'):
                        ui.icon('table_chart', size='22px').style('color:#0891b2')
                    with ui.column().classes('gap-0'):
                        ui.label('Detalle por Orden de Servicio').classes('text-base font-bold text-gray-800')
                        ui.label(f'Top {len(tabla)} órdenes ordenadas por ganancia').classes('text-xs text-gray-400')
                ui.badge(f"{len(tabla)} registros", color='blue-8').classes('text-[10px] font-bold')

            if not tabla:
                ui.label('Sin datos de órdenes aún').classes('text-gray-400 text-sm text-center w-full py-8')
                return

            with ui.element('div').style('width:100%;overflow-x:auto'):
                # Cabecera
                with ui.row().classes('w-full items-center gap-2 px-3 pb-2 border-b border-gray-100'):
                    ui.label('Orden').classes('text-[10px] font-black text-gray-400 uppercase tracking-wider').style('min-width:80px')
                    ui.label('Cliente').classes('text-[10px] font-black text-gray-400 uppercase tracking-wider flex-1')
                    ui.label('Vehículo').classes('text-[10px] font-black text-gray-400 uppercase tracking-wider').style('min-width:80px')
                    ui.label('Servicio').classes('text-[10px] font-black text-gray-400 uppercase tracking-wider flex-1')
                    ui.label('Cobrado').classes(HEADER_STYLE).style('min-width:90px')
                    ui.label('Costo Rep.').classes(HEADER_STYLE).style('min-width:90px')
                    ui.label('Ganancia').classes(HEADER_STYLE).style('min-width:90px')
                    ui.label('Margen').classes(HEADER_STYLE).style('min-width:70px')

                with ui.scroll_area().style('max-height:360px'):
                    total_cobrado = 0
                    total_costo = 0
                    total_ganancia = 0

                    for row in tabla:
                        mrg = row['margen']
                        if mrg >= 50:
                            mrg_color, mrg_bg = '#059669', '#f0fdf4'
                        elif mrg >= 20:
                            mrg_color, mrg_bg = '#f59e0b', '#fffbeb'
                        else:
                            mrg_color, mrg_bg = '#ef4444', '#fef2f2'

                        total_cobrado += row['cobrado']
                        total_costo += row['costo_rep']
                        total_ganancia += row['ganancia']

                        with ui.row().classes('w-full items-center gap-2 px-3 py-2 hover:bg-gray-50 rounded-lg transition-colors'):
                            ui.label(row['orden']).classes('text-xs font-bold text-[#274495]').style('min-width:80px')
                            ui.label(row['cliente']).classes('text-xs text-gray-600 flex-1').style('overflow:hidden;white-space:nowrap;text-overflow:ellipsis;max-width:140px')
                            ui.label(row['vehiculo']).classes('text-xs text-gray-500 font-mono').style('min-width:80px')
                            ui.label(row['servicio']).classes('text-xs text-gray-600 flex-1').style('overflow:hidden;white-space:nowrap;text-overflow:ellipsis;max-width:140px')
                            ui.label(f"S/ {row['cobrado']:,.0f}").classes(CELL_STYLE).style('min-width:90px')
                            ui.label(f"S/ {row['costo_rep']:,.0f}").classes(CELL_STYLE).style('min-width:90px')
                            ui.label(f"S/ {row['ganancia']:,.0f}").classes(
                                'text-xs font-black text-right text-green-600' if row['ganancia'] >= 0
                                else 'text-xs font-black text-right text-red-500'
                            ).style('min-width:90px')
                            with ui.element('div').style(
                                f'min-width:70px;text-align:right;'
                            ):
                                with ui.element('span').style(
                                    f'background:{mrg_bg};color:{mrg_color};font-size:10px;'
                                    'font-weight:800;padding:2px 8px;border-radius:999px;'
                                ):
                                    ui.label(f"{mrg:.1f}%")

                    # Fila de totales
                    total_mrg = (total_ganancia / total_cobrado * 100) if total_cobrado > 0 else 0
                    with ui.row().classes('w-full items-center gap-2 px-3 py-3 bg-[#274495] rounded-lg mt-2'):
                        ui.label('TOTALES').classes('text-xs font-black text-white').style('min-width:80px')
                        ui.label('').classes('flex-1')
                        ui.label('').style('min-width:80px')
                        ui.label(f"{len(tabla)} órdenes").classes('text-xs text-blue-200 flex-1')
                        ui.label(f"S/ {total_cobrado:,.0f}").classes('text-xs font-black text-white text-right').style('min-width:90px')
                        ui.label(f"S/ {total_costo:,.0f}").classes('text-xs font-black text-white text-right').style('min-width:90px')
                        ui.label(f"S/ {total_ganancia:,.0f}").classes('text-xs font-black text-white text-right').style('min-width:90px')
                        with ui.element('div').style('min-width:70px;text-align:right'):
                            ui.label(f"{total_mrg:.1f}%").classes('text-xs font-black text-white')


# ── Entry point ───────────────────────────────────────────────────────────────

def show_rentabilidad(container):
    """Renderiza el Dashboard de Rentabilidad completo"""
    # Agregar estilos 3D para gráficos
    try:
        from components.graficos_3d import GRAFICOS_3D_CSS
        ui.add_head_html(GRAFICOS_3D_CSS)
    except ImportError:
        pass

    with container:
        try:
            data = _get_data()
        except Exception as e:
            ui.label(f'Error cargando datos: {e}').classes('text-red-500 text-sm')
            return

        # Header
        header_row = ui.row().classes('w-full')
        _header(header_row)

        # KPIs
        kpi_row = ui.row().classes('w-full')
        _kpis(kpi_row, data)

        # Gráfico semanal + Donut (fila)
        charts_row = ui.row().classes('w-full items-stretch gap-4')
        _chart_semanal(charts_row, data)
        _chart_donut(charts_row, data)

        # Ranking + Técnicos (fila)
        mid_row = ui.row().classes('w-full items-stretch gap-4 flex-wrap')
        _ranking_servicios(mid_row, data['ranking'])
        _rendimiento_tecnicos(mid_row, data['tecnicos'])

        # Alertas (ancho completo)
        alertas_row = ui.row().classes('w-full')
        _alertas(alertas_row, data['alertas'])

        # Tabla detalle
        tabla_row = ui.row().classes('w-full')
        _tabla_detalle(tabla_row, data['tabla'])
