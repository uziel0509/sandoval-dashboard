"""
SANDOVAL Dashboard - Reportes y Estadísticas v4.0
Arquitectura premium: fondo blanco, azul corporativo, limpio y profesional
"""

from nicegui import ui
import plotly.graph_objects as go
from utils.models import get_db, Orden, Cliente, ItemInventario
import theme


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRADA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def show_reportes(container):
    with container:
        db = get_db()
        try:
            ordenes      = db.query(Orden).all()
            n_clientes   = db.query(Cliente).count()
            inventario   = db.query(ItemInventario).all()
            completadas  = [o for o in ordenes if o.estado in ('ENTREGA', 'ARCHIVADO')]

            total_ingresos = sum(
                float(it.get('total', 0) or 0)
                for o in ordenes
                for it in (o.items_cotizacion or [])
            )
            ingresos_completadas = sum(
                float(it.get('total', 0) or 0)
                for o in completadas
                for it in (o.items_cotizacion or [])
            )

            # Técnicos únicos
            tecnicos_set = {o.tecnico for o in ordenes if o.tecnico and o.tecnico.strip()}

            # ── LAYOUT ────────────────────────────────────────────────────────
            _render_header()
            _render_kpis(ordenes, n_clientes, inventario, completadas,
                         total_ingresos, len(tecnicos_set))

            with ui.row().classes('w-full gap-5 mb-5'):
                _render_estados_pie(ordenes)
                _render_top_items(ordenes)

            with ui.row().classes('w-full gap-5 mb-5'):
                _render_tecnicos(ordenes, completadas)
                _render_tiempo_etapas(ordenes)

            _render_inventario(inventario)

        finally:
            db.close()


# ─────────────────────────────────────────────────────────────────────────────
#  HEADER
# ─────────────────────────────────────────────────────────────────────────────

def _render_header():
    with ui.row().classes('w-full items-center justify-between mb-6 fade-in'):
        with ui.column().classes('gap-0'):
            ui.label('Reportes y Estadísticas').classes(
                'text-[28px] font-black text-gray-900 tracking-tight leading-none')
            ui.label('Análisis completo de operaciones y rentabilidad').classes(
                'text-sm text-gray-400 font-medium mt-1')
        with ui.row().classes('items-center gap-3'):
            ui.button('Excel Órdenes', icon='download',
                      on_click=lambda: _export('ordenes')
            ).classes(
                'bg-white border border-gray-200 text-gray-700 font-bold '
                'rounded-xl shadow-sm hover:border-[#274495] hover:text-[#274495] '
                'transition-colors text-xs px-4 py-2'
            ).props('flat no-caps')
            ui.button('Excel Clientes', icon='download',
                      on_click=lambda: _export('clientes')
            ).classes(
                'bg-white border border-gray-200 text-gray-700 font-bold '
                'rounded-xl shadow-sm hover:border-[#274495] hover:text-[#274495] '
                'transition-colors text-xs px-4 py-2'
            ).props('flat no-caps')
            ui.button('Excel Inventario', icon='download',
                      on_click=lambda: _export('inventario')
            ).classes(
                'text-white font-bold rounded-xl text-xs px-4 py-2'
            ).style('background:#274495').props('no-caps')


# ─────────────────────────────────────────────────────────────────────────────
#  KPIs — FILA DE 6 TARJETAS
# ─────────────────────────────────────────────────────────────────────────────

def _render_kpis(ordenes, n_clientes, inventario, completadas,
                 total_ingresos, n_tecnicos):
    tasa = (len(completadas) / len(ordenes) * 100) if ordenes else 0
    kpis = [
        ('Total Órdenes',       str(len(ordenes)),          'Historial completo',      'build',        '#274495', '#eff6ff'),
        ('Servicios Compl.',    str(len(completadas)),       'Trabajos entregados',     'task_alt',     '#10b981', '#f0fdf4'),
        ('Ingresos Totales',    f'S/ {total_ingresos:,.0f}','Proyectado acumulado',    'payments',     '#0ea5e9', '#f0f9ff'),
        ('Tasa de Cierre',      f'{tasa:.0f}%',             'Órdenes completadas',     'trending_up',  '#6366f1', '#eef2ff'),
        ('Clientes',            str(n_clientes),             'Registrados en sistema',  'groups',       '#f59e0b', '#fffbeb'),
        ('Ítems Inventario',    str(len(inventario)),        'Referencias activas',     'inventory_2',  '#64748b', '#f8fafc'),
    ]
    with ui.row().classes('w-full gap-4 mb-5'):
        for titulo, valor, sub, icon, color, bg in kpis:
            with ui.card().classes(
                    'flex-1 bg-white border border-gray-100 p-5 rounded-2xl shadow-sm '
                    'hover:shadow-md hover:-translate-y-1 transition-all cursor-default'):
                with ui.row().classes('w-full items-start justify-between'):
                    with ui.column().classes('gap-1 flex-1 min-w-0'):
                        ui.label(titulo).classes(
                            'text-[10px] font-black text-gray-400 tracking-widest uppercase leading-none')
                        ui.label(valor).classes(
                            'text-2xl font-black text-gray-900 leading-none mt-2')
                        ui.label(sub).classes(
                            'text-[10px] text-gray-400 font-medium mt-1')
                    ui.element('div').classes(
                        'p-3 rounded-xl flex items-center justify-center flex-shrink-0'
                    ).style(f'background:{bg}').add_slot(
                        'default',
                        f'<q-icon name="{icon}" size="20px" style="color:{color};"></q-icon>')


# ─────────────────────────────────────────────────────────────────────────────
#  GRÁFICO DONUT — ESTADOS
# ─────────────────────────────────────────────────────────────────────────────

def _render_estados_pie(ordenes):
    with ui.card().classes(
            'bg-white border border-gray-100 p-6 rounded-2xl shadow-sm flex-1'):
        with ui.column().classes('gap-0 mb-4'):
            ui.label('Distribución por Estado').classes('text-base font-black text-gray-800')
            ui.label('Órdenes agrupadas por etapa del flujo').classes(
                'text-xs text-gray-400 font-medium')

        counts = {}
        for o in ordenes:
            e = o.estado or 'RECEPCIÓN'
            counts[e] = counts.get(e, 0) + 1

        if not counts:
            _empty_state('pie_chart', 'Sin datos de órdenes')
            return

        colores = [theme.ESTADOS_CONFIG.get(e, {}).get('hex', '#94a3b8') for e in counts]
        fig = go.Figure(data=[go.Pie(
            labels=list(counts.keys()),
            values=list(counts.values()),
            marker=dict(colors=colores, line=dict(color='white', width=4)),
            hole=0.48,
            textinfo='label+value',
            textposition='outside',
            textfont=dict(size=10, color='#374151'),
            hovertemplate='<b>%{label}</b><br>%{value} órdenes (%{percent})<extra></extra>',
        )])
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            showlegend=False,
            font=dict(color='#374151', size=10),
            margin=dict(l=40, r=40, t=20, b=20),
            height=280,
        )
        ui.plotly(fig).classes('w-full')


# ─────────────────────────────────────────────────────────────────────────────
#  GRÁFICO BARRAS — TOP ÍTEMS COTIZADOS
# ─────────────────────────────────────────────────────────────────────────────

def _render_top_items(ordenes):
    with ui.card().classes(
            'bg-white border border-gray-100 p-6 rounded-2xl shadow-sm flex-1'):
        with ui.column().classes('gap-0 mb-4'):
            ui.label('Servicios y Repuestos Más Solicitados').classes(
                'text-base font-black text-gray-800')
            ui.label('Top 8 ítems por cantidad cotizada').classes(
                'text-xs text-gray-400 font-medium')

        counts: dict = {}
        for o in ordenes:
            for item in (o.items_cotizacion or []):
                name = (item.get('nombre') or 'Sin nombre').strip()
                counts[name] = counts.get(name, 0) + int(item.get('cantidad', 1) or 1)

        if not counts:
            _empty_state('bar_chart', 'Sin ítems cotizados aún')
            return

        top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:8]
        labels = [t[0][:28] + '…' if len(t[0]) > 28 else t[0] for t in top]
        values = [t[1] for t in top]

        # Gradiente manual de azul claro a azul corporativo según posición
        n = len(values)
        bar_colors = []
        for idx in range(n):
            ratio = idx / max(n - 1, 1)
            # Interpola entre #c7d9f7 (claro) y #274495 (oscuro) — más arriba = más oscuro
            r = int(199 - ratio * (199 - 39))
            g = int(217 - ratio * (217 - 68))
            b = int(247 - ratio * (247 - 149))
            bar_colors.append(f'rgb({r},{g},{b})')

        fig = go.Figure(data=[go.Bar(
            x=values,
            y=labels,
            orientation='h',
            marker=dict(
                color=bar_colors,
                line=dict(color='white', width=1),
            ),
            text=[f'  {v}' for v in values],
            textposition='outside',
            textfont=dict(size=11, color='#374151'),
            hovertemplate='<b>%{y}</b><br>%{x} unidades<extra></extra>',
        )])
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#374151', size=10),
            margin=dict(l=10, r=60, t=10, b=10),
            height=280,
            xaxis=dict(
                showgrid=False,
                showticklabels=False,
                zeroline=False,
                range=[0, max(values) * 1.25],
            ),
            yaxis=dict(
                autorange='reversed',
                tickfont=dict(size=11, color='#374151'),
                gridcolor='rgba(0,0,0,0)',
            ),
            bargap=0.3,
        )
        ui.plotly(fig).classes('w-full')


# ─────────────────────────────────────────────────────────────────────────────
#  TABLA RENDIMIENTO POR TÉCNICO
# ─────────────────────────────────────────────────────────────────────────────

def _render_tecnicos(ordenes, completadas):
    with ui.card().classes(
            'bg-white border border-gray-100 p-6 rounded-2xl shadow-sm flex-1'):
        with ui.column().classes('gap-0 mb-5'):
            ui.label('Rendimiento por Técnico').classes('text-base font-black text-gray-800')
            ui.label('Órdenes asignadas y completadas').classes(
                'text-xs text-gray-400 font-medium')

        tecnicos: dict = {}
        for o in ordenes:
            tec = (o.tecnico or '').strip()
            if not tec:
                continue
            if tec not in tecnicos:
                tecnicos[tec] = {'total': 0, 'completadas': 0}
            tecnicos[tec]['total'] += 1
            if o.estado in ('ENTREGA', 'ARCHIVADO'):
                tecnicos[tec]['completadas'] += 1

        if not tecnicos:
            _empty_state('engineering', 'Sin técnicos asignados aún')
            return

        # Cabecera
        with ui.element('div').classes('grid px-3 mb-2').style(
                'grid-template-columns: 1fr 70px 80px 80px'):
            for h in ['TÉCNICO', 'TOTAL', 'COMPL.', 'TASA']:
                ui.label(h).classes('text-[9px] font-black text-gray-300 tracking-widest')

        for tec, data in sorted(tecnicos.items(), key=lambda x: x[1]['total'], reverse=True):
            tasa = (data['completadas'] / data['total'] * 100) if data['total'] else 0

            with ui.element('div').classes(
                    'grid px-3 py-3 rounded-xl items-center '
                    'hover:bg-slate-50 transition-colors border-b border-gray-50'
            ).style('grid-template-columns: 1fr 70px 80px 80px'):
                # Nombre con avatar inicial
                with ui.row().classes('items-center gap-2'):
                    with ui.element('div').classes(
                            'w-7 h-7 rounded-full flex items-center justify-center '
                            'text-[10px] font-black text-white flex-shrink-0'
                    ).style('background:#274495'):
                        ui.label(tec[0].upper())
                    ui.label(tec).classes('text-xs font-semibold text-gray-700 truncate')

                ui.label(str(data['total'])).classes(
                    'text-xs font-bold text-gray-500 text-center')
                ui.label(str(data['completadas'])).classes(
                    'text-xs font-bold text-green-600 text-center')

                # Barra de tasa
                with ui.element('div').classes('flex items-center gap-1'):
                    with ui.element('div').classes(
                            'flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden'):
                        ui.element('div').style(
                            f'width:{tasa:.0f}%;'
                            'background:linear-gradient(90deg,#274495,#4f78e0);'
                        ).classes('h-full rounded-full')
                    ui.label(f'{tasa:.0f}%').classes(
                        'text-[9px] font-black text-[#274495] w-8 text-right')


# ─────────────────────────────────────────────────────────────────────────────
#  TIEMPO PROMEDIO POR ETAPA
# ─────────────────────────────────────────────────────────────────────────────

def _render_tiempo_etapas(ordenes):
    with ui.card().classes(
            'bg-white border border-gray-100 p-6 rounded-2xl shadow-sm flex-1'):
        with ui.column().classes('gap-0 mb-5'):
            ui.label('Flujo de Trabajo').classes('text-base font-black text-gray-800')
            ui.label('Órdenes por etapa del proceso').classes(
                'text-xs text-gray-400 font-medium')

        etapas_orden = [
            'RECEPCIÓN', 'DIAGNÓSTICO', 'REPUESTOS', 'APROBACIÓN',
            'REPARACIÓN', 'CONTROL', 'ENTREGA', 'ARCHIVADO',
        ]
        conteos = {}
        for est in etapas_orden:
            conteos[est] = len([o for o in ordenes if o.estado == est])

        total_ord = len(ordenes) or 1
        max_val   = max(conteos.values()) or 1

        for est in etapas_orden:
            cnt = conteos[est]
            pct = (cnt / max_val) * 100
            cfg = theme.ESTADOS_CONFIG.get(est, {})
            hex_c = cfg.get('hex', '#94a3b8')
            icon  = cfg.get('icon', 'circle')

            with ui.element('div').classes('w-full mb-3'):
                with ui.row().classes('w-full items-center justify-between mb-1'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon(icon, size='14px').style(f'color:{hex_c}')
                        ui.label(est.capitalize()).classes(
                            'text-xs font-bold text-gray-600')
                    with ui.row().classes('items-center gap-2'):
                        ui.label(str(cnt)).classes('text-xs font-black text-gray-800')
                        ui.label(f'{cnt/total_ord*100:.0f}%').classes(
                            'text-[9px] text-gray-400 font-medium w-8 text-right')
                with ui.element('div').classes(
                        'w-full h-2 bg-gray-100 rounded-full overflow-hidden'):
                    ui.element('div').style(
                        f'width:{pct:.0f}%;background:{hex_c};'
                    ).classes('h-full rounded-full transition-all duration-700')


# ─────────────────────────────────────────────────────────────────────────────
#  TABLA DE VALORIZACIÓN DEL INVENTARIO
# ─────────────────────────────────────────────────────────────────────────────

def _render_inventario(inventario):
    with ui.card().classes('w-full bg-white border border-gray-100 p-6 rounded-2xl shadow-sm'):
        with ui.row().classes('w-full items-center justify-between mb-5'):
            with ui.column().classes('gap-0'):
                ui.label('Valorización del Inventario').classes(
                    'text-base font-black text-gray-800')
                ui.label('Stock y valor por categoría').classes(
                    'text-xs text-gray-400 font-medium')
            ui.button('Excel Inventario', icon='download',
                      on_click=lambda: _export('inventario')
            ).classes('text-xs font-bold').style('color:#274495').props('flat no-caps')

        # Agrupar por categoría
        cat_data: dict = {}
        for item in inventario:
            cat = item.categoria or 'Otros'
            if cat not in cat_data:
                cat_data[cat] = {'items': 0, 'stock': 0, 'costo': 0.0, 'venta': 0.0}
            cat_data[cat]['items'] += 1
            cat_data[cat]['stock'] += item.stock or 0
            cat_data[cat]['costo'] += (item.costo or 0) * (item.stock or 0)
            cat_data[cat]['venta'] += (item.precio or 0) * (item.stock or 0)

        if not cat_data:
            _empty_state('inventory_2', 'Sin inventario registrado')
            return

        total_items  = sum(v['items']  for v in cat_data.values())
        total_stock  = sum(v['stock']  for v in cat_data.values())
        total_costo  = sum(v['costo']  for v in cat_data.values())
        total_venta  = sum(v['venta']  for v in cat_data.values())
        total_margen = total_venta - total_costo

        # Cabecera tabla
        with ui.element('div').classes(
                'grid px-4 py-2 mb-1 rounded-xl bg-gray-50').style(
                'grid-template-columns: 1fr 80px 100px 140px 140px 120px'):
            for h in ['CATEGORÍA', 'ÍTEMS', 'STOCK', 'VALOR COSTO', 'VALOR VENTA', 'MARGEN']:
                ui.label(h).classes('text-[9px] font-black text-gray-400 tracking-widest')

        # Filas
        colors_row = ['#ffffff', '#f8fafc']
        for i, (cat, data) in enumerate(
                sorted(cat_data.items(), key=lambda x: x[1]['venta'], reverse=True)):
            margen = data['venta'] - data['costo']
            pct_m  = (margen / data['venta'] * 100) if data['venta'] else 0

            with ui.element('div').classes(
                    'grid px-4 py-3 rounded-xl items-center border-b border-gray-50 '
                    'hover:bg-blue-50/30 transition-colors').style(
                    f'grid-template-columns: 1fr 80px 100px 140px 140px 120px;'
                    f'background:{colors_row[i % 2]}'):
                ui.label(cat).classes('text-xs font-semibold text-gray-700')
                ui.label(str(data['items'])).classes(
                    'text-xs font-bold text-gray-500 text-center')
                ui.label(f"{data['stock']:,}").classes(
                    'text-xs font-bold text-gray-500 text-center')
                ui.label(f"S/ {data['costo']:,.2f}").classes(
                    'text-xs font-bold text-gray-700')
                ui.label(f"S/ {data['venta']:,.2f}").classes(
                    'text-xs font-bold text-[#274495]')
                # Margen con color
                m_color = '#10b981' if pct_m >= 20 else ('#f59e0b' if pct_m >= 10 else '#ef4444')
                with ui.element('div').classes('flex items-center gap-1'):
                    ui.label(f"S/ {margen:,.0f}").classes(
                        'text-xs font-black').style(f'color:{m_color}')
                    ui.label(f"({pct_m:.0f}%)").classes(
                        'text-[9px] font-medium text-gray-400')

        # Totales
        with ui.element('div').classes(
                'grid px-4 py-3 rounded-xl mt-1').style(
                'grid-template-columns: 1fr 80px 100px 140px 140px 120px;'
                'background:#274495'):
            ui.label('TOTAL').classes('text-xs font-black text-white')
            ui.label(str(total_items)).classes('text-xs font-black text-white/80 text-center')
            ui.label(f'{total_stock:,}').classes('text-xs font-black text-white/80 text-center')
            ui.label(f'S/ {total_costo:,.2f}').classes('text-xs font-black text-white/80')
            ui.label(f'S/ {total_venta:,.2f}').classes('text-xs font-black text-white')
            ui.label(f'S/ {total_margen:,.0f}').classes('text-xs font-black text-green-300')


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _empty_state(icon, msg):
    with ui.column().classes('w-full items-center justify-center py-12'):
        ui.icon(icon, size='40px').classes('text-gray-100')
        ui.label(msg).classes('text-gray-300 text-sm mt-2')


def _export(tipo):
    try:
        from utils.excel_tools import export_ordenes_excel, export_clientes_excel, export_inventario_excel
        import os
        os.makedirs('exports', exist_ok=True)
        if tipo == 'ordenes':
            filepath = export_ordenes_excel()
        elif tipo == 'clientes':
            filepath = export_clientes_excel()
        else:
            filepath = export_inventario_excel()
        ui.download(filepath)
        theme.notify_success(f'Excel exportado correctamente')
    except Exception as e:
        theme.notify_error(f'Error exportando: {str(e)}')
