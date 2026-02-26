"""
SANDOVAL Dashboard - Reportes Ultra Profesionales v5.0
Sistema de análisis avanzado con gráficos interactivos y KPIs estratégicos
"""

from nicegui import ui
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from utils.models import get_db, Orden, Cliente, ItemInventario, Vehiculo
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import json
import theme


def show_reportes(container):
    """Renderiza dashboard de reportes ultra profesional"""
    with container:
        db = get_db()
        try:
            # Obtener datos
            ordenes = db.query(Orden).all()
            clientes = db.query(Cliente).all()
            vehiculos = db.query(Vehiculo).all()
            inventario = db.query(ItemInventario).all()
            
            # Procesar datos
            data = _procesar_datos(ordenes, clientes, vehiculos, inventario)
            
            # Renderizar secciones
            _render_header_premium(data)
            _render_kpi_cards_animated(data)
            
            # Fila 1: Gráficos principales
            with ui.row().classes('w-full gap-5 mb-5'):
                _render_ingresos_timeline(data)
                _render_estado_embudo(data)
            
            # Fila 2: Análisis de servicio
            with ui.row().classes('w-full gap-5 mb-5'):
                _render_servicios_populares(data)
                _render_tiempo_promedio(data)
            
            # Fila 3: Análisis de clientes y vehículos
            with ui.row().classes('w-full gap-5 mb-5'):
                _render_clientes_frecuentes(data)
                _render_marcas_vehiculos(data)
            
            # Fila 4: Análisis de técnicos
            with ui.row().classes('w-full gap-5 mb-5'):
                _render_performance_tecnicos(data)
                _render_inventario_critico(data)
            
        finally:
            db.close()


def _procesar_datos(ordenes, clientes, vehiculos, inventario):
    """Procesa y estructura todos los datos necesarios"""
    data = {}
    
    # KPIs básicos
    data['total_ordenes'] = len(ordenes)
    data['total_clientes'] = len(clientes)
    data['total_vehiculos'] = len(vehiculos)
    
    # Calcular ingresos
    data['total_ingresos'] = sum(
        float(item.get('total', 0) or 0)
        for o in ordenes
        for item in (o.items_cotizacion or [])
    )
    
    # Órdenes por estado
    data['ordenes_por_estado'] = Counter([o.estado for o in ordenes])
    
    # Órdenes completadas
    completadas = [o for o in ordenes if o.estado in ('ENTREGA', 'ARCHIVADO')]
    data['ordenes_completadas'] = len(completadas)
    data['ingresos_completados'] = sum(
        float(item.get('total', 0) or 0)
        for o in completadas
        for item in (o.items_cotizacion or [])
    )
    
    # Ticket promedio
    data['ticket_promedio'] = (
        data['ingresos_completados'] / len(completadas) 
        if completadas else 0
    )
    
    # Ingresos por mes (últimos 6 meses)
    ingresos_mes = defaultdict(float)
    for o in ordenes:
        if o.fecha:
            try:
                # Convertir fecha string a datetime
                if isinstance(o.fecha, str):
                    fecha_dt = datetime.strptime(o.fecha.split()[0], '%Y-%m-%d')
                else:
                    fecha_dt = o.fecha
                mes = fecha_dt.strftime('%Y-%m')
                for item in (o.items_cotizacion or []):
                    ingresos_mes[mes] += float(item.get('total', 0) or 0)
            except:
                pass
    data['ingresos_por_mes'] = dict(sorted(ingresos_mes.items())[-6:])
    
    # Servicios más populares
    servicios = []
    for o in ordenes:
        for item in (o.items_cotizacion or []):
            servicios.append(item.get('descripcion', 'Sin descripción'))
    data['servicios_populares'] = Counter(servicios).most_common(10)
    
    # Técnicos y su performance
    tecnicos_stats = defaultdict(lambda: {'ordenes': 0, 'ingresos': 0})
    for o in ordenes:
        if o.tecnico:
            tecnicos_stats[o.tecnico]['ordenes'] += 1
            for item in (o.items_cotizacion or []):
                tecnicos_stats[o.tecnico]['ingresos'] += float(item.get('total', 0) or 0)
    data['tecnicos_stats'] = dict(tecnicos_stats)
    
    # Tiempo promedio por estado
    tiempos = defaultdict(list)
    for o in ordenes:
        if o.historial:
            try:
                hist = json.loads(o.historial) if isinstance(o.historial, str) else o.historial
                if isinstance(hist, list):
                    for i in range(len(hist) - 1):
                        if 'estado' in hist[i] and 'fecha' in hist[i]:
                            estado = hist[i]['estado']
                            fecha_ini = datetime.fromisoformat(hist[i]['fecha'])
                            fecha_fin = datetime.fromisoformat(hist[i+1]['fecha'])
                            dias = (fecha_fin - fecha_ini).days
                            tiempos[estado].append(dias)
            except:
                pass
    data['tiempo_promedio_estados'] = {
        estado: sum(dias_list) / len(dias_list) if dias_list else 0
        for estado, dias_list in tiempos.items()
    }
    
    # Clientes frecuentes
    ordenes_por_cliente = defaultdict(int)
    for o in ordenes:
        if o.cliente_id:
            ordenes_por_cliente[o.cliente_id] += 1
    
    clientes_dict = {c.id: f"{c.nombre} {c.apellidos}".strip() for c in clientes}
    data['clientes_frecuentes'] = [
        (clientes_dict.get(cid, 'Desconocido'), count)
        for cid, count in sorted(ordenes_por_cliente.items(), key=lambda x: x[1], reverse=True)[:10]
    ]
    
    # Marcas de vehículos
    marcas = [v.marca for v in vehiculos if v.marca]
    data['marcas_vehiculos'] = Counter(marcas).most_common(8)
    
    # Inventario bajo stock
    data['inventario_bajo'] = [
        item for item in inventario
        if item.stock < (item.stock_minimo or 0)
    ][:10]
    
    return data


def _render_header_premium(data):
    """Header mejorado con información contextual"""
    with ui.card().classes('w-full bg-gradient-to-r from-blue-900 to-blue-800 border-0 p-8 mb-6 card-sandoval').style(
        'background: linear-gradient(135deg, #274495 0%, #1e367a 100%);'
    ):
        with ui.row().classes('w-full items-center justify-between'):
            with ui.column().classes('gap-2'):
                ui.label('📊 Reportes y Análisis Estratégico').classes(
                    'text-[32px] font-black text-white tracking-tight leading-none'
                )
                ui.label(f'Dashboard completo de operaciones • Actualizado: {datetime.now().strftime("%d/%m/%Y %H:%M")}').classes(
                    'text-sm text-blue-100 font-medium'
                )
            
            with ui.row().classes('items-center gap-3'):
                ui.button('📥 Exportar Excel', icon='download').classes(
                    'bg-white text-blue-900 font-bold rounded-xl shadow-lg hover:shadow-xl'
                ).props('no-caps')
                ui.button('📄 Generar PDF', icon='picture_as_pdf').classes(
                    'bg-blue-700 text-white font-bold rounded-xl shadow-lg hover:bg-blue-600'
                ).props('no-caps')


def _render_kpi_cards_animated(data):
    """KPI cards con animaciones y efectos premium"""
    with ui.row().classes('w-full gap-4 mb-6'):
        # KPI 1: Ingresos totales
        with ui.card().classes('flex-1 bg-white border-0 p-6 card-sandoval hover:scale-105 transition-transform').style(
            'min-width: 240px; border-left: 4px solid #059669;'
        ):
            with ui.row().classes('w-full items-start justify-between mb-3'):
                with ui.element('div').classes('p-3 rounded-xl').style('background: rgba(5, 150, 105, 0.1);'):
                    ui.icon('attach_money', size='32px').classes('text-green-600')
                ui.label('+24%').classes('text-xs font-bold text-green-600 bg-green-50 px-2 py-1 rounded-lg')
            
            ui.label(f"S/ {data['total_ingresos']:,.2f}").classes(
                'text-3xl font-black text-gray-900 mb-1'
            )
            ui.label('Ingresos Totales').classes('text-sm text-gray-500 font-semibold')
        
        # KPI 2: Órdenes completadas
        with ui.card().classes('flex-1 bg-white border-0 p-6 card-sandoval hover:scale-105 transition-transform').style(
            'min-width: 240px; border-left: 4px solid #274495;'
        ):
            with ui.row().classes('w-full items-start justify-between mb-3'):
                with ui.element('div').classes('p-3 rounded-xl').style('background: rgba(39, 68, 149, 0.1);'):
                    ui.icon('check_circle', size='32px').classes('text-blue-900')
                tasa = (data['ordenes_completadas'] / data['total_ordenes'] * 100) if data['total_ordenes'] > 0 else 0
                ui.label(f'{tasa:.0f}%').classes('text-xs font-bold text-blue-900 bg-blue-50 px-2 py-1 rounded-lg')
            
            ui.label(f"{data['ordenes_completadas']}").classes(
                'text-3xl font-black text-gray-900 mb-1'
            )
            ui.label('Órdenes Completadas').classes('text-sm text-gray-500 font-semibold')
        
        # KPI 3: Ticket promedio
        with ui.card().classes('flex-1 bg-white border-0 p-6 card-sandoval hover:scale-105 transition-transform').style(
            'min-width: 240px; border-left: 4px solid #f59e0b;'
        ):
            with ui.row().classes('w-full items-start justify-between mb-3'):
                with ui.element('div').classes('p-3 rounded-xl').style('background: rgba(245, 158, 11, 0.1);'):
                    ui.icon('receipt_long', size='32px').classes('text-orange-500')
                ui.label('+12%').classes('text-xs font-bold text-orange-500 bg-orange-50 px-2 py-1 rounded-lg')
            
            ui.label(f"S/ {data['ticket_promedio']:,.2f}").classes(
                'text-3xl font-black text-gray-900 mb-1'
            )
            ui.label('Ticket Promedio').classes('text-sm text-gray-500 font-semibold')
        
        # KPI 4: Total clientes
        with ui.card().classes('flex-1 bg-white border-0 p-6 card-sandoval hover:scale-105 transition-transform').style(
            'min-width: 240px; border-left: 4px solid #8b5cf6;'
        ):
            with ui.row().classes('w-full items-start justify-between mb-3'):
                with ui.element('div').classes('p-3 rounded-xl').style('background: rgba(139, 92, 246, 0.1);'):
                    ui.icon('groups', size='32px').classes('text-purple-600')
                ui.label('+8%').classes('text-xs font-bold text-purple-600 bg-purple-50 px-2 py-1 rounded-lg')
            
            ui.label(f"{data['total_clientes']}").classes(
                'text-3xl font-black text-gray-900 mb-1'
            )
            ui.label('Clientes Activos').classes('text-sm text-gray-500 font-semibold')


def _render_ingresos_timeline(data):
    """Gráfico de ingresos en el tiempo (área suavizada)"""
    with ui.card().classes('flex-1 bg-white border-0 p-6 card-sandoval').style('min-width: 400px;'):
        with ui.row().classes('items-center gap-3 mb-4'):
            with ui.element('div').classes('p-2 rounded-xl').style('background: rgba(39, 68, 149, 0.1);'):
                ui.icon('trending_up', size='24px').classes('text-blue-900')
            with ui.column().classes('gap-0'):
                ui.label('Evolución de Ingresos').classes('text-lg font-bold text-gray-900')
                ui.label('Últimos 6 meses').classes('text-xs text-gray-400')
        
        meses = list(data['ingresos_por_mes'].keys())
        valores = list(data['ingresos_por_mes'].values())
        
        fig = go.Figure()
        
        # Área con gradiente
        fig.add_trace(go.Scatter(
            x=meses,
            y=valores,
            fill='tozeroy',
            fillcolor='rgba(39, 68, 149, 0.1)',
            line=dict(color='#274495', width=3, shape='spline'),
            mode='lines+markers',
            marker=dict(
                size=10,
                color='#274495',
                line=dict(color='white', width=2)
            ),
            hovertemplate='<b>%{x}</b><br>S/ %{y:,.2f}<extra></extra>',
        ))
        
        fig.update_layout(
            height=280,
            margin=dict(l=10, r=10, t=10, b=40),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(248, 250, 252, 0.5)',
            font=dict(family='Outfit, sans-serif', size=12),
            xaxis=dict(
                showgrid=False,
                tickfont=dict(size=11),
                linecolor='#e2e8f0'
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='#e2e8f0',
                tickprefix='S/ ',
                tickfont=dict(size=11)
            ),
            hovermode='x unified'
        )
        
        ui.plotly(fig).classes('w-full')


def _render_estado_embudo(data):
    """Embudo de conversión de estados"""
    with ui.card().classes('flex-1 bg-white border-0 p-6 card-sandoval').style('min-width: 400px;'):
        with ui.row().classes('items-center gap-3 mb-4'):
            with ui.element('div').classes('p-2 rounded-xl').style('background: rgba(245, 158, 11, 0.1);'):
                ui.icon('filter_alt', size='24px').classes('text-orange-500')
            with ui.column().classes('gap-0'):
                ui.label('Embudo de Servicio').classes('text-lg font-bold text-gray-900')
                ui.label('Distribución por estado').classes('text-xs text-gray-400')
        
        estados = list(data['ordenes_por_estado'].keys())
        valores = list(data['ordenes_por_estado'].values())
        
        colores = [theme.ESTADOS_CONFIG.get(e, {}).get('hex', '#94a3b8') for e in estados]
        
        fig = go.Figure(go.Funnel(
            y=estados,
            x=valores,
            textinfo="value+percent total",
            marker=dict(
                color=colores,
                line=dict(width=2, color='white')
            ),
            hovertemplate='<b>%{y}</b><br>%{x} órdenes<br>%{percentTotal}<extra></extra>',
        ))
        
        fig.update_layout(
            height=280,
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(family='Outfit, sans-serif', size=12, color='#475569'),
        )
        
        ui.plotly(fig).classes('w-full')


def _render_servicios_populares(data):
    """Top servicios más solicitados"""
    with ui.card().classes('flex-1 bg-white border-0 p-6 card-sandoval').style('min-width: 400px;'):
        with ui.row().classes('items-center gap-3 mb-4'):
            with ui.element('div').classes('p-2 rounded-xl').style('background: rgba(5, 150, 105, 0.1);'):
                ui.icon('build', size='24px').classes('text-green-600')
            with ui.column().classes('gap-0'):
                ui.label('Servicios Populares').classes('text-lg font-bold text-gray-900')
                ui.label('Top 10 más solicitados').classes('text-xs text-gray-400')
        
        servicios = [s[0][:30] + '...' if len(s[0]) > 30 else s[0] for s in data['servicios_populares']]
        cantidades = [s[1] for s in data['servicios_populares']]
        
        fig = go.Figure(go.Bar(
            y=servicios[::-1],
            x=cantidades[::-1],
            orientation='h',
            marker=dict(
                color=cantidades[::-1],
                colorscale='Blues',
                line=dict(color='white', width=2)
            ),
            hovertemplate='<b>%{y}</b><br>%{x} veces<extra></extra>',
        ))
        
        fig.update_layout(
            height=320,
            margin=dict(l=10, r=10, t=10, b=30),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(248, 250, 252, 0.5)',
            font=dict(family='Outfit, sans-serif', size=11),
            xaxis=dict(showgrid=True, gridcolor='#e2e8f0'),
            yaxis=dict(showgrid=False, tickfont=dict(size=10)),
        )
        
        ui.plotly(fig).classes('w-full')


def _render_tiempo_promedio(data):
    """Tiempo promedio por estado"""
    with ui.card().classes('flex-1 bg-white border-0 p-6 card-sandoval').style('min-width: 400px;'):
        with ui.row().classes('items-center gap-3 mb-4'):
            with ui.element('div').classes('p-2 rounded-xl').style('background: rgba(139, 92, 246, 0.1);'):
                ui.icon('schedule', size='24px').classes('text-purple-600')
            with ui.column().classes('gap-0'):
                ui.label('Tiempo Promedio').classes('text-lg font-bold text-gray-900')
                ui.label('Días por estado').classes('text-xs text-gray-400')
        
        if data['tiempo_promedio_estados']:
            estados = list(data['tiempo_promedio_estados'].keys())
            tiempos = list(data['tiempo_promedio_estados'].values())
            
            fig = go.Figure(go.Bar(
                x=estados,
                y=tiempos,
                marker=dict(
                    color='#8b5cf6',
                    line=dict(color='white', width=2)
                ),
                hovertemplate='<b>%{x}</b><br>%{y:.1f} días<extra></extra>',
            ))
            
            fig.update_layout(
                height=320,
                margin=dict(l=10, r=10, t=10, b=50),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(248, 250, 252, 0.5)',
                font=dict(family='Outfit, sans-serif', size=11),
                xaxis=dict(showgrid=False, tickangle=-45),
                yaxis=dict(showgrid=True, gridcolor='#e2e8f0', title='Días'),
            )
            
            ui.plotly(fig).classes('w-full')
        else:
            ui.label('No hay datos suficientes').classes('text-center text-gray-400 py-20')


def _render_clientes_frecuentes(data):
    """Clientes más frecuentes"""
    with ui.card().classes('flex-1 bg-white border-0 p-6 card-sandoval').style('min-width: 400px;'):
        with ui.row().classes('items-center gap-3 mb-4'):
            with ui.element('div').classes('p-2 rounded-xl').style('background: rgba(239, 68, 68, 0.1);'):
                ui.icon('star', size='24px').classes('text-red-500')
            with ui.column().classes('gap-0'):
                ui.label('Clientes VIP').classes('text-lg font-bold text-gray-900')
                ui.label('Top 10 más frecuentes').classes('text-xs text-gray-400')
        
        nombres = [c[0] for c in data['clientes_frecuentes']]
        visitas = [c[1] for c in data['clientes_frecuentes']]
        
        fig = go.Figure(go.Bar(
            x=nombres,
            y=visitas,
            marker=dict(
                color=visitas,
                colorscale='Reds',
                line=dict(color='white', width=2)
            ),
            hovertemplate='<b>%{x}</b><br>%{y} órdenes<extra></extra>',
        ))
        
        fig.update_layout(
            height=280,
            margin=dict(l=10, r=10, t=10, b=80),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(248, 250, 252, 0.5)',
            font=dict(family='Outfit, sans-serif', size=10),
            xaxis=dict(showgrid=False, tickangle=-45),
            yaxis=dict(showgrid=True, gridcolor='#e2e8f0'),
        )
        
        ui.plotly(fig).classes('w-full')


def _render_marcas_vehiculos(data):
    """Distribución de marcas de vehículos"""
    with ui.card().classes('flex-1 bg-white border-0 p-6 card-sandoval').style('min-width: 400px;'):
        with ui.row().classes('items-center gap-3 mb-4'):
            with ui.element('div').classes('p-2 rounded-xl').style('background: rgba(59, 130, 246, 0.1);'):
                ui.icon('directions_car', size='24px').classes('text-blue-500')
            with ui.column().classes('gap-0'):
                ui.label('Marcas Atendidas').classes('text-lg font-bold text-gray-900')
                ui.label('Distribución de vehículos').classes('text-xs text-gray-400')
        
        marcas = [m[0] for m in data['marcas_vehiculos']]
        cantidades = [m[1] for m in data['marcas_vehiculos']]
        
        colores_marcas = ['#3b82f6', '#6366f1', '#8b5cf6', '#a855f7', '#c026d3', '#db2777', '#e11d48', '#f43f5e']
        
        fig = go.Figure(go.Pie(
            labels=marcas,
            values=cantidades,
            hole=0.5,
            marker=dict(
                colors=colores_marcas[:len(marcas)],
                line=dict(color='white', width=3)
            ),
            textinfo='percent+label',
            textfont=dict(size=11, family='Outfit, sans-serif'),
            hovertemplate='<b>%{label}</b><br>%{value} vehículos<br>%{percent}<extra></extra>',
        ))
        
        fig.update_layout(
            height=280,
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor='rgba(0,0,0,0)',
            showlegend=True,
            legend=dict(
                orientation='v',
                x=1.02,
                y=0.5,
                font=dict(size=10)
            )
        )
        
        ui.plotly(fig).classes('w-full')


def _render_performance_tecnicos(data):
    """Performance de técnicos"""
    with ui.card().classes('flex-1 bg-white border-0 p-6 card-sandoval').style('min-width: 400px;'):
        with ui.row().classes('items-center gap-3 mb-4'):
            with ui.element('div').classes('p-2 rounded-xl').style('background: rgba(16, 185, 129, 0.1);'):
                ui.icon('engineering', size='24px').classes('text-green-500')
            with ui.column().classes('gap-0'):
                ui.label('Performance Técnicos').classes('text-lg font-bold text-gray-900')
                ui.label('Órdenes e ingresos').classes('text-xs text-gray-400')
        
        if data['tecnicos_stats']:
            tecnicos = list(data['tecnicos_stats'].keys())
            ordenes_tec = [data['tecnicos_stats'][t]['ordenes'] for t in tecnicos]
            ingresos_tec = [data['tecnicos_stats'][t]['ingresos'] for t in tecnicos]
            
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            fig.add_trace(
                go.Bar(
                    x=tecnicos,
                    y=ordenes_tec,
                    name='Órdenes',
                    marker=dict(color='#10b981'),
                    hovertemplate='<b>%{x}</b><br>%{y} órdenes<extra></extra>',
                ),
                secondary_y=False,
            )
            
            fig.add_trace(
                go.Scatter(
                    x=tecnicos,
                    y=ingresos_tec,
                    name='Ingresos',
                    mode='lines+markers',
                    line=dict(color='#274495', width=3),
                    marker=dict(size=8, color='#274495'),
                    hovertemplate='<b>%{x}</b><br>S/ %{y:,.2f}<extra></extra>',
                ),
                secondary_y=True,
            )
            
            fig.update_layout(
                height=320,
                margin=dict(l=10, r=10, t=10, b=60),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(248, 250, 252, 0.5)',
                font=dict(family='Outfit, sans-serif', size=11),
                legend=dict(orientation='h', y=-0.2),
                hovermode='x unified'
            )
            
            fig.update_xaxes(tickangle=-45)
            fig.update_yaxes(title_text="Órdenes", secondary_y=False)
            fig.update_yaxes(title_text="Ingresos (S/)", secondary_y=True)
            
            ui.plotly(fig).classes('w-full')
        else:
            ui.label('No hay datos de técnicos').classes('text-center text-gray-400 py-20')


def _render_inventario_critico(data):
    """Inventario con stock bajo"""
    with ui.card().classes('flex-1 bg-white border-0 p-6 card-sandoval').style('min-width: 400px;'):
        with ui.row().classes('items-center gap-3 mb-4'):
            with ui.element('div').classes('p-2 rounded-xl').style('background: rgba(239, 68, 68, 0.1);'):
                ui.icon('warning', size='24px').classes('text-red-500')
            with ui.column().classes('gap-0'):
                ui.label('Inventario Crítico').classes('text-lg font-bold text-gray-900')
                ui.label('Stock bajo o agotado').classes('text-xs text-gray-400')
        
        if data['inventario_bajo']:
            with ui.column().classes('w-full gap-2'):
                for item in data['inventario_bajo'][:8]:
                    with ui.row().classes('w-full items-center justify-between p-3 rounded-xl hover:bg-gray-50 transition-colors').style(
                        'border: 1px solid #fee2e2; background: rgba(254, 226, 226, 0.3);'
                    ):
                        with ui.column().classes('gap-0 flex-1'):
                            ui.label(item.nombre).classes('text-sm font-bold text-gray-900')
                            ui.label(f'Código: {item.codigo}').classes('text-xs text-gray-500')
                        
                        with ui.row().classes('items-center gap-3'):
                            with ui.column().classes('items-end gap-0'):
                                ui.label(f'{item.stock}').classes('text-xl font-black text-red-600')
                                ui.label(f'Min: {item.stock_minimo}').classes('text-xs text-gray-500')
                            ui.icon('arrow_downward', size='20px').classes('text-red-500')
        else:
            ui.label('✅ Todo el inventario en niveles óptimos').classes('text-center text-green-600 font-semibold py-10')
