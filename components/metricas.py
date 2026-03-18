"""
SANDOVAL Dashboard - Dashboard Principal v4.0
Arquitectura premium: fondo blanco, azul corporativo, limpio y profesional
"""

import json
from datetime import datetime
from nicegui import ui
import plotly.graph_objects as go
from utils.models import get_db, Orden, Cliente, Vehiculo, ItemInventario, NotaVenta
import theme


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRADA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def show_dashboard(container):
    # Agregar estilos 3D para gráficos
    try:
        from components.graficos_3d import GRAFICOS_3D_CSS
        ui.add_head_html(GRAFICOS_3D_CSS)
    except ImportError:
        pass
    
    with container:
        db = get_db()
        try:
            ordenes    = db.query(Orden).all()
            n_clientes = db.query(Cliente).count()

            # ── Cálculos ──────────────────────────────────────────────────────
            encuestas = []
            for o in ordenes:
                if o.encuesta:
                    try:
                        dt = o.encuesta if isinstance(o.encuesta, dict) else json.loads(o.encuesta)
                        if dt and dt.get('completada'):
                            encuestas.append(dt)
                    except Exception:
                        pass

            recom_vals     = [e.get('recomendacion', 10) for e in encuestas]
            avg_nps        = (sum(recom_vals) / len(recom_vals)) if recom_vals else 0
            total_ingresos = sum(
                float(it.get('total', 0) or 0)
                for o in ordenes
                for it in (
                    __import__('json').loads(o.items_cotizacion)
                    if isinstance(o.items_cotizacion, str) else (o.items_cotizacion or [])
                )
            )
            activas      = [o for o in ordenes if o.estado not in ('ARCHIVADO', 'ENTREGA')]
            completadas  = [o for o in ordenes if o.estado in ('ARCHIVADO', 'ENTREGA')]

            from utils.models import Cliente as ClienteModel
            client_ids  = list({o.cliente_id for o in ordenes if o.cliente_id})
            clients_map = {
                c.id: f"{c.nombre} {c.apellidos}".strip()
                for c in db.query(ClienteModel).filter(ClienteModel.id.in_(client_ids)).all()
            }

            items_todos  = db.query(ItemInventario).all()
            stock_alerts = [i for i in items_todos if i.stock <= i.stock_minimo]

            # ── Ventas directas (Notas de Venta) ──────────────────────────────
            notas_mes = [
                n for n in db.query(NotaVenta).filter_by(estado='pagada').all()
                if n.fecha and n.fecha.month == datetime.now().month
                   and n.fecha.year == datetime.now().year
            ]
            ventas_mes = sum(n.total for n in notas_mes)

            # ── LAYOUT ────────────────────────────────────────────────────────
            _render_header()
            _render_kpis(avg_nps, total_ingresos, len(activas), n_clientes,
                         len(completadas), len(encuestas), ventas_mes)

            with ui.column().classes('w-full gap-5 mb-5 md:flex-row md:flex-wrap lg:flex-nowrap'):
                _render_estados_chart(ordenes)
                _render_active_orders(activas, clients_map)

            with ui.column().classes('w-full gap-5 md:flex-row md:flex-wrap lg:flex-nowrap'):
                _render_satisfaction(encuestas)
                _render_alerts(stock_alerts, activas)
                _render_voice(encuestas)

        finally:
            db.close()


# ─────────────────────────────────────────────────────────────────────────────
#  HEADER
# ─────────────────────────────────────────────────────────────────────────────

def _render_header():
    now    = datetime.now()
    dias   = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    meses  = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    fecha  = f"{dias[now.weekday()]} {now.day} {meses[now.month - 1]} {now.year}"

    with ui.row().classes('w-full items-center justify-between mb-6 fade-in'):
        with ui.column().classes('gap-0'):
            ui.label('Panel de Control').classes(
                'text-[28px] font-black text-gray-900 tracking-tight leading-none')
            ui.label('Resumen operativo en tiempo real').classes(
                'text-sm text-gray-400 font-medium mt-1')
        with ui.row().classes('items-center gap-3'):
            with ui.element('div').classes(
                    'flex items-center gap-2 px-4 py-2 bg-white border border-gray-100 rounded-xl shadow-sm'):
                ui.icon('calendar_today', size='16px').classes('text-[#274495]')
                ui.label(fecha).classes('text-sm font-bold text-gray-700')
            with ui.element('div').classes(
                    'flex items-center gap-2 px-4 py-2 rounded-xl cursor-pointer hover:bg-blue-800 transition-colors').style('background:#274495').on('click', _show_qr_dialog):
                ui.icon('qr_code', size='16px').classes('text-white')
                ui.label('Portal Cliente').classes('text-xs font-bold text-white')

def _show_qr_dialog():
    from utils.models import get_config
    import socket
    try: host = socket.gethostbyname(socket.gethostname())
    except: host = 'localhost'
    
    base_url = get_config('dominio_taller', f'http://{host}:3000').rstrip('/')
    final_url = f"{base_url}/app/"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={final_url}"
    
    with ui.dialog() as dlg, ui.card().classes('w-full max-w-sm bg-white p-0 rounded-[40px] overflow-hidden shadow-2xl'):
        # Header Blue
        with ui.column().classes('w-full bg-[#274495] p-8 items-center text-center gap-2'):
            ui.icon('qr_code_2', size='56px', color='white')
            ui.label('Acceso Portal Móvil').classes('text-2xl font-black text-white tracking-tighter')
            ui.label('Mecánica Sandoval').classes('text-white/60 text-[10px] font-bold uppercase tracking-[0.2em]')
        
        # QR Area
        with ui.column().classes('w-full items-center p-10 gap-6'):
            with ui.element('div').classes('p-6 bg-slate-50 rounded-[32px] border-2 border-dashed border-gray-200'):
                ui.image(qr_url).classes('w-44 h-44 shadow-xl border-8 border-white rounded-2xl')
            
            ui.label(final_url).classes('text-[9px] font-black text-blue-500 tracking-widest uppercase text-center')
            
            with ui.row().classes('w-full gap-2'):
                ui.button('Imprimir', icon='print', on_click=lambda: ui.run_javascript('window.print()')).props('unelevated rounded color=gray-2 text-color=gray-8').classes('flex-1')
                
                async def download_flyer():
                    from utils.pdf_generator import generate_pdf
                    pdf_path = f"pdfs/flyer_qr_dashboard.pdf"
                    generate_pdf({'qr_url': qr_url}, {}, {}, 'qr_flyer', pdf_path)
                    ui.download(pdf_path)
                
                ui.button('Flyer PDF', icon='picture_as_pdf', on_click=download_flyer).props('unelevated rounded color=red-7').classes('flex-1')
        
        ui.button('Cerrar', on_click=dlg.close).props('flat color=grey-6').classes('w-full py-4 text-[10px] font-black uppercase tracking-widest')
    
    dlg.open()


# ─────────────────────────────────────────────────────────────────────────────
#  KPIs — FILA DE 5 TARJETAS
# ─────────────────────────────────────────────────────────────────────────────

def _render_kpis(avg_nps, total_ingresos, n_activas, n_clientes, n_completadas, n_encuestas, ventas_mes=0):
    kpis = [
        ('Ingresos Taller',        f'S/ {total_ingresos:,.0f}', 'Servicios acumulados',          'payments',     '#10b981', '#f0fdf4'),
        ('Ventas Repuestos',       f'S/ {ventas_mes:,.0f}',     'Notas de venta este mes',       'receipt_long', '#274495', '#eff6ff'),
        ('Órdenes en Taller',      str(n_activas),              'Trabajos activos ahora',        'engineering',  '#6366f1', '#eef2ff'),
        ('Clientes Registrados',   str(n_clientes),             'Base de fidelización',          'groups',       '#0ea5e9', '#f0f9ff'),
        ('Satisfacción Global',    f'{avg_nps:.1f}/10',         f'{n_encuestas} encuestas',      'star_rate',    '#f59e0b', '#fffbeb'),
    ]
    with ui.row().classes('w-full gap-4 mb-5 justify-center md:flex-nowrap flex-wrap'):
        for titulo, valor, sub, icon, color, bg in kpis:
            with ui.card().classes(
                    'w-full md:flex-1 bg-white border border-gray-100 p-5 rounded-2xl shadow-sm '
                    'hover:shadow-md hover:-translate-y-1 transition-all cursor-default min-w-[160px]'):
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
                        f'<q-icon name="{icon}" size="22px" style="color:{color};"></q-icon>')


# ─────────────────────────────────────────────────────────────────────────────
#  GRÁFICO DONUT DE ESTADOS
# ─────────────────────────────────────────────────────────────────────────────

def _render_estados_chart(ordenes):
    with ui.card().classes(
            'bg-white border border-gray-100 p-6 rounded-2xl shadow-sm w-full lg:flex-[1.2]'):
        with ui.row().classes('w-full items-center justify-between mb-4'):
            with ui.column().classes('gap-0'):
                ui.label('Estado del Taller').classes('text-base font-black text-gray-800')
                ui.label('Distribución de órdenes por etapa').classes(
                    'text-xs text-gray-400 font-medium')
            with ui.element('div').classes(
                    'px-3 py-1 rounded-full text-[10px] font-black bg-blue-50').style('color:#274495'):
                ui.label('EN VIVO')

        counts = {
            est: len([o for o in ordenes if o.estado == est])
            for est in theme.ESTADOS_CONFIG
            if len([o for o in ordenes if o.estado == est]) > 0
        }

        if not counts:
            with ui.column().classes('w-full items-center justify-center py-16'):
                ui.icon('bar_chart', size='48px').classes('text-gray-100')
                ui.label('Sin datos para mostrar').classes('text-gray-300 text-sm mt-2')
            return

        total = sum(counts.values())
        colores = [theme.ESTADOS_CONFIG[e]['hex'] for e in counts]
        fig = go.Figure(data=[go.Pie(
            labels=list(counts.keys()),
            values=list(counts.values()),
            hole=0.62,
            marker=dict(
                colors=colores, 
                line=dict(color='white', width=4),
            ),
            textinfo='percent',
            textposition='inside',
            textfont=dict(size=12, color='white', family='Outfit, sans-serif'),
            hovertemplate='<b>%{label}</b><br>%{value} órdenes<br>%{percent}<extra></extra>',
            pull=[0.05 if i == 0 else 0.02 for i in range(len(counts))],
            rotation=45,
        )])
        fig.add_annotation(
            text=f'<b>{total}</b>',
            x=0.5, y=0.55, showarrow=False,
            font=dict(size=32, color='#111827', family='Outfit, sans-serif'),
        )
        fig.add_annotation(
            text='órdenes',
            x=0.5, y=0.42, showarrow=False,
            font=dict(size=12, color='#9ca3af', family='Outfit, sans-serif'),
        )
        fig.update_layout(
            showlegend=True,
            legend=dict(
                orientation='v',
                x=1.02, y=0.9,
                xanchor='left',
                font=dict(size=11, color='#374151', family='Outfit, sans-serif'),
                bgcolor='rgba(255,255,255,0.95)',
                borderwidth=1,
                bordercolor='rgba(226, 232, 240, 0.8)',
            ),
            margin=dict(t=10, b=10, l=10, r=130),
            height=280,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            # Animaciones y transiciones
            transition={
                'duration': 500,
                'easing': 'cubic-in-out'
            },
        )
        # Agregar sombra 3D al gráfico
        ui.add_head_html('''
        <style>
        .plotly-graph-div {
            filter: drop-shadow(0 10px 25px rgba(39, 68, 149, 0.08));
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .plotly-graph-div:hover {
            filter: drop-shadow(0 15px 35px rgba(39, 68, 149, 0.12));
            transform: translateY(-2px);
        }
        </style>
        ''')
        ui.plotly(fig).classes('w-full')


# ─────────────────────────────────────────────────────────────────────────────
#  TABLA DE ÓRDENES ACTIVAS
# ─────────────────────────────────────────────────────────────────────────────

def _render_active_orders(activas, clients_map):
    with ui.card().classes(
            'bg-white border border-gray-100 p-6 rounded-2xl shadow-sm w-full lg:flex-[1.8]'):
        with ui.row().classes('w-full items-center justify-between mb-4'):
            with ui.column().classes('gap-0'):
                ui.label('Órdenes Activas').classes('text-base font-black text-gray-800')
                ui.label(f'{len(activas)} trabajos en curso').classes(
                    'text-xs text-gray-400 font-medium')

        if not activas:
            with ui.column().classes('w-full items-center justify-center py-12'):
                ui.icon('check_circle', size='48px').classes('text-green-100')
                ui.label('Todo al día — sin pendientes').classes('text-gray-300 text-sm mt-2')
            return

        recientes = sorted(activas, key=lambda o: o.fecha or '', reverse=True)[:6]

        # Cabeceras (Sólo desktop)
        with ui.element('div').classes('hide-on-mobile grid px-3 mb-1').style(
                'grid-template-columns: 85px 1fr 90px 120px'):
            for h in ['FOLIO', 'CLIENTE', 'PLACA', 'ESTADO']:
                ui.label(h).classes('text-[9px] font-black text-gray-300 tracking-widest')

        # Filas
        with ui.column().classes('w-full gap-2'):
            for o in recientes:
                cfg   = theme.ESTADOS_CONFIG.get(o.estado, {})
                hex_c = cfg.get('hex', '#94a3b8')
                nombre = clients_map.get(o.cliente_id, '—')
                
                # Vista móvil: tarjeta compacta
                with ui.element('div').classes('md:hidden block bg-slate-50 p-3 rounded-xl border border-gray-100'):
                    with ui.row().classes('w-full justify-between items-center mb-1'):
                        ui.label(o.consecutivo).classes('text-[10px] font-black text-[#274495]')
                        ui.label(o.vehiculo_placa or '—').classes('text-[10px] font-bold text-gray-400')
                    ui.label(nombre).classes('text-xs font-bold text-gray-800 block mb-2')
                    with ui.element('div').classes('px-2 py-0.5 rounded text-[8px] font-black text-white text-center inline-block').style(f'background:{hex_c}'):
                        ui.label(o.estado or '—')

                # Vista desktop: grid
                with ui.element('div').classes(
                        'hide-on-mobile grid px-3 py-3 rounded-xl items-center '
                        'hover:bg-slate-50 transition-colors border-b border-gray-50'
                ).style('grid-template-columns: 85px 1fr 90px 120px'):
                    ui.label(o.consecutivo).classes('text-xs font-black text-[#274495] tracking-tight')
                    ui.label(nombre).classes('text-xs font-semibold text-gray-700 truncate')
                    ui.label(o.vehiculo_placa or '—').classes('text-xs font-bold text-gray-400')
                    with ui.element('div').classes('px-2 py-1 rounded-lg text-[9px] font-black tracking-widest text-white text-center inline-block').style(f'background:{hex_c}'):
                        ui.label(o.estado or '—')


# ─────────────────────────────────────────────────────────────────────────────
#  SATISFACCIÓN POR ÁREA
# ─────────────────────────────────────────────────────────────────────────────

def _render_satisfaction(encuestas):
    with ui.card().classes(
            'bg-white border border-gray-100 p-6 rounded-2xl shadow-sm flex-1'):
        with ui.column().classes('gap-0 mb-5'):
            ui.label('Satisfacción').classes('text-base font-black text-gray-800')
            ui.label('Calificación por área').classes('text-xs text-gray-400 font-medium')

        if not encuestas:
            with ui.column().classes('w-full items-center py-8'):
                ui.icon('poll', size='40px').classes('text-gray-100')
                ui.label('Sin encuestas aún').classes('text-gray-300 text-sm mt-2')
            return

        areas = [
            ('calidad_trabajo',  'Calidad Técnica',    'build'),
            ('atencion_cliente', 'Atención al Cliente', 'support_agent'),
            ('tiempo_entrega',   'Puntualidad',         'schedule'),
        ]
        for key, label, icon in areas:
            vals = [e.get(key) for e in encuestas if e.get(key) is not None]
            avg  = sum(vals) / len(vals) if vals else 0
            pct  = (avg / 5) * 100

            with ui.element('div').classes('w-full mb-4'):
                with ui.row().classes('w-full items-center justify-between mb-1'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon(icon, size='14px').classes('text-[#274495]')
                        ui.label(label).classes('text-xs font-bold text-gray-600')
                    ui.label(f'{avg:.1f}/5').classes('text-xs font-black text-[#274495]')
                with ui.element('div').classes(
                        'w-full h-2 bg-gray-100 rounded-full overflow-hidden'):
                    ui.element('div').style(
                        f'width:{pct:.0f}%;'
                        'background:linear-gradient(90deg,#274495,#4f78e0);'
                    ).classes('h-full rounded-full')


# ─────────────────────────────────────────────────────────────────────────────
#  PANEL DE ALERTAS
# ─────────────────────────────────────────────────────────────────────────────

def _render_alerts(stock_alerts, activas):
    pendientes = [o for o in activas if o.estado == 'APROBACIÓN']
    total      = len(stock_alerts) + len(pendientes)

    with ui.card().classes(
            'bg-white border border-gray-100 p-6 rounded-2xl shadow-sm flex-1'):
        with ui.row().classes('w-full items-center justify-between mb-4'):
            with ui.column().classes('gap-0'):
                ui.label('Alertas').classes('text-base font-black text-gray-800')
                ui.label('Requieren atención').classes('text-xs text-gray-400 font-medium')
            if total > 0:
                with ui.element('div').classes(
                        'w-6 h-6 rounded-full bg-red-500 flex items-center '
                        'justify-center text-[10px] font-black text-white'):
                    ui.label(str(total))

        if not stock_alerts and not pendientes:
            with ui.column().classes('w-full items-center py-8'):
                ui.icon('verified', size='40px').classes('text-green-100')
                ui.label('Sin alertas activas').classes('text-gray-300 text-sm mt-2')
            return

        with ui.scroll_area().classes('w-full').style('max-height:180px'):
            for item in stock_alerts[:5]:
                _alert_row('inventory_2', '#ef4444', '#fef2f2',
                            f'Stock bajo: {item.nombre}',
                            f'Quedan {item.stock} unidades (mín. {item.stock_minimo})')
            for o in pendientes[:3]:
                _alert_row('pending_actions', '#f59e0b', '#fffbeb',
                            'Esperando aprobación del cliente',
                            f'Orden {o.consecutivo} · pendiente de respuesta')


def _alert_row(icon, color, bg, title, detail):
    with ui.element('div').classes(
            'flex items-start gap-3 p-3 rounded-xl mb-2').style(f'background:{bg}'):
        with ui.element('div').classes('p-1.5 rounded-lg flex-shrink-0').style(
                f'background:{color}20'):
            ui.icon(icon, size='16px').style(f'color:{color}')
        with ui.column().classes('gap-0 flex-1'):
            ui.label(title).classes('text-xs font-bold text-gray-800')
            ui.label(detail).classes('text-[10px] text-gray-500 font-medium')


# ─────────────────────────────────────────────────────────────────────────────
#  VOZ DEL CLIENTE
# ─────────────────────────────────────────────────────────────────────────────

def _render_voice(encuestas):
    with ui.card().classes(
            'bg-white border border-gray-100 p-6 rounded-2xl shadow-sm flex-1'):
        with ui.column().classes('gap-0 mb-4'):
            ui.label('Voz del Cliente').classes('text-base font-black text-gray-800')
            ui.label('Últimas opiniones recibidas').classes('text-xs text-gray-400 font-medium')

        con_comentario = [e for e in encuestas if e.get('comentarios', '').strip()]
        recientes = sorted(con_comentario,
                           key=lambda x: x.get('fecha_encuesta', ''),
                           reverse=True)[:3]

        if not recientes:
            with ui.column().classes('w-full items-center py-8'):
                ui.icon('chat_bubble_outline', size='40px').classes('text-gray-100')
                ui.label('Sin comentarios aún').classes('text-gray-300 text-sm mt-2')
            return

        for en in recientes:
            stars_n  = int((en.get('recomendacion', 0) or 0) / 2)
            star_str = '★' * stars_n + '☆' * (5 - stars_n)
            fecha    = (en.get('fecha_encuesta', '') or '')[:10]

            with ui.element('div').classes(
                    'w-full p-4 rounded-xl border border-gray-100 mb-3 '
                    'hover:border-blue-100 transition-colors bg-gray-50/50'):
                ui.label(f'"{en["comentarios"]}"').classes(
                    'text-xs text-gray-700 italic leading-relaxed')
                with ui.row().classes('w-full items-center justify-between mt-2'):
                    ui.label(star_str).classes('text-amber-400 text-xs')
                    ui.label(fecha).classes('text-[9px] text-gray-300 font-bold')
