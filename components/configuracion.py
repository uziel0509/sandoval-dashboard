"""
SANDOVAL Dashboard - Configuración del Sistema
Usa SQLite via ConfigSistema
"""

from nicegui import ui
from utils.models import get_db, ConfigSistema, get_config, set_config, Usuario
import json
import theme

def show_config(container):
    with container:
        # Header Corporativo Minimalista
        with ui.row().classes('w-full items-center justify-between mb-4 fade-in py-5 px-8 bg-white border border-gray-100 rounded-xl shadow-sm'):
            with ui.row().classes('items-center gap-4'):
                ui.icon('settings', size='32px').classes('text-[#274495]')
                ui.label('CONFIGURACIÓN DEL SISTEMA').classes('text-xl font-extrabold text-[#274495] tracking-tight')
        
        with ui.tabs().classes('w-full text-gray-600') as tabs:
            empresa_tab = ui.tab('Empresa', icon='business').classes('mx-2')
            tecnicos_tab = ui.tab('Técnicos', icon='engineering').classes('mx-2')
            qr_tab = ui.tab('Portal QR', icon='qr_code').classes('mx-2')
            sistema_tab = ui.tab('Sistema', icon='tune').classes('mx-2')
        
        with ui.tab_panels(tabs, value=empresa_tab).classes('w-full bg-transparent'):
            with ui.tab_panel(empresa_tab):
                _empresa_form()
            with ui.tab_panel(tecnicos_tab):
                _tecnicos_form()
            with ui.tab_panel(qr_tab):
                _qr_portal_section()
            with ui.tab_panel(sistema_tab):
                _sistema_form()

def _empresa_form():
    with ui.card().classes('w-full max-w-2xl bg-white border border-gray-200 p-6 shadow-sm'):
        ui.label('Datos de la Empresa').classes('text-xl font-bold text-gray-800 mb-4')
        nombre_i = ui.input('Razón Social', value=get_config('empresa_nombre', '')).props('outlined dense bg-color=white').classes('w-full')
        ruc_i = ui.input('RUC', value=get_config('empresa_ruc', '')).props('outlined dense bg-color=white').classes('w-full')
        dir_i = ui.input('Dirección', value=get_config('empresa_direccion', '')).props('outlined dense bg-color=white').classes('w-full')
        tel_i = ui.input('Teléfono', value=get_config('empresa_telefono', '')).props('outlined dense bg-color=white').classes('w-full')
        email_i = ui.input('Email', value=get_config('empresa_email', '')).props('outlined dense bg-color=white').classes('w-full')
        
        def guardar():
            set_config('empresa_nombre', nombre_i.value)
            set_config('empresa_ruc', ruc_i.value)
            set_config('empresa_direccion', dir_i.value)
            set_config('empresa_telefono', tel_i.value)
            set_config('empresa_email', email_i.value)
            theme.notify_success('Configuración guardada')
        ui.button('Guardar', icon='save', on_click=guardar).props('unelevated color=primary text-color=white font-bold').classes('mt-4 px-6')

def _tecnicos_form():
    with ui.card().classes('w-full max-w-2xl bg-white border border-gray-200 p-6 shadow-sm'):
        ui.label('Técnicos del Taller').classes('text-xl font-bold text-gray-800 mb-4')
        
        db = get_db()
        try:
            tecnicos = db.query(Usuario).filter_by(rol='tecnico', activo=True).all()
        finally:
            db.close()
        
        if tecnicos:
            with ui.column().classes('w-full gap-2'):
                for t in tecnicos:
                    with ui.row().classes('w-full items-center gap-3 py-3 border-b border-gray-100 last:border-0'):
                        ui.avatar(icon='engineering', color='blue-1', text_color='blue-8').classes('rounded-lg')
                        with ui.column().classes('gap-0 flex-1'):
                            ui.label(t.nombre).classes('text-gray-800 font-bold')
                            ui.label(t.username).classes('text-gray-500 text-sm')
                        ui.badge('ACTIVO', color='green-6')
        else:
            with ui.column().classes('w-full items-center py-6'):
                ui.icon('engineering', size='48px').classes('text-gray-300')
                ui.label('No hay técnicos registrados').classes('text-gray-400 mt-2')
        
        ui.label('Para gestionar técnicos, usa la sección de Usuarios con rol "Técnico".').classes('text-gray-500 text-sm mt-4 italic')

def _sistema_form():
    with ui.card().classes('w-full max-w-2xl bg-white border border-gray-200 p-6 shadow-sm'):
        ui.label('Configuración del Sistema').classes('text-xl font-bold text-gray-800 mb-4')
        igv_i = ui.input('IGV (%)', value=get_config('igv_porcentaje', '18')).props('outlined dense type=number bg-color=white').classes('w-48')
        moneda_sel = ui.select(['PEN', 'USD'], value=get_config('moneda', 'PEN'), label='Moneda').props('outlined dense bg-color=white').classes('w-48')
        
        def guardar():
            set_config('igv_porcentaje', igv_i.value)
            set_config('moneda', moneda_sel.value)
            theme.notify_success('Configuración guardada')
        ui.button('Guardar', icon='save', on_click=guardar).props('unelevated color=primary text-color=white font-bold').classes('mt-4 px-6')
    
    with ui.card().classes('w-full max-w-2xl bg-white border border-gray-200 p-6 mt-4 shadow-sm'):
        ui.label('Información del Sistema').classes('text-xl font-bold text-gray-800 mb-4')
        with ui.column().classes('gap-2'):
            ui.label('Versión: 2.0 Pro').classes('text-gray-600')
            ui.label('Base de datos: SQLite').classes('text-gray-600')
            ui.label('Framework: NiceGUI + SQLAlchemy').classes('text-gray-600')
            ui.label('Auth: Login con roles (Admin/Técnico/Recepcionista)').classes('text-gray-600')
            ui.label('© 2026 MECÁNICA Y REPUESTOS SANDOVAL EIRL').classes('text-gray-400 text-sm mt-4')

def _qr_portal_section():
    # Intentar detectar la URL actual de forma inteligente
    import socket
    try: host = socket.gethostbyname(socket.gethostname())
    except: host = '127.0.0.1'
    
    default_url = get_config('dominio_taller', f'http://{host}:3000')
    
    with ui.column().classes('w-full items-center gap-6 p-4'):
        with ui.card().classes('w-full max-w-xl bg-white border border-gray-200 p-8 shadow-xl rounded-[40px] text-center'):
            ui.icon('qr_code_2', size='56px').classes('text-[#274495] mb-4')
            ui.label('PORTAL MÓVIL SANDOVAL').classes('text-2xl font-black text-gray-900 tracking-tighter')
            ui.label('Genera el acceso directo para tus clientes').classes('text-gray-400 text-[10px] font-bold uppercase tracking-widest mb-6')
            
            with ui.column().classes('w-full gap-4 text-left'):
                ui.label('1. URL de Acceso (Dashboard)').classes('text-[10px] font-black text-blue-600 uppercase tracking-widest')
                with ui.row().classes('w-full items-center gap-2'):
                    url_i = ui.input('Dominio / IP del Taller', value=default_url).props('outlined dense bg-color=white').classes('flex-1')
                ui.label('Ejemplo: https://sandovaldashboard.com o http://190.12.1.25:3000').classes('text-[10px] text-gray-400 italic')

            # Previsualización dinámica
            img_cont = ui.column().classes('w-full items-center mt-8 p-10 bg-slate-50 rounded-[32px] border-2 border-dashed border-gray-200 relative overflow-hidden')
            
            # Decoración
            with img_cont:
                ui.element('div').classes('absolute -top-10 -right-10 w-32 h-32 bg-blue-100/30 rounded-full blur-3xl')
                ui.element('div').classes('absolute -bottom-10 -left-10 w-32 h-32 bg-emerald-100/30 rounded-full blur-3xl')

                qr_display = ui.image().classes('w-48 h-48 shadow-2xl border-8 border-white rounded-2xl cursor-pointer hover:scale-105 transition-transform').style('background:white;')
                url_display = ui.label().classes('text-[10px] font-black text-blue-500 mt-6 tracking-widest uppercase')
                
                with ui.row().classes('mt-8 gap-3'):
                    ui.button('Descargar QR', icon='download', on_click=lambda: ui.download(qr_display.source)).props('unelevated rounded color=green-6 shadow-sm')
                    ui.button('Guardar URL', icon='save', on_click=lambda: (set_config('dominio_taller', url_i.value), theme.notify_success('URL Guardada'))).props('unelevated rounded color=primary shadow-sm')

            def update_qr():
                base = url_i.value.strip().rstrip('/')
                if not base: return
                final_target = f"{base}/app/"
                qr_display.source = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={final_target}"
                url_display.set_text(final_target)

            url_i.on('change', update_qr)
            ui.timer(0.2, update_qr, once=True) # Carga inicial

        with ui.card().classes('w-full max-w-xl bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-100 p-8 rounded-[32px]'):
            with ui.row().classes('items-start gap-4 flex-nowrap'):
                ui.icon('auto_awesome', size='32px', color='blue-6')
                with ui.column().classes('gap-2'):
                    ui.label('¿CÓMO MODERNIZAR TU TALLER?').classes('text-sm font-black text-blue-900 tracking-tight')
                    ui.label('• Imprime este código y colócalo en el mostrador de recepción.').classes('text-xs text-blue-800/80 font-medium')
                    ui.label('• El cliente lo escanea y entra directo a su historial de reparaciones.').classes('text-xs text-blue-800/80 font-medium')
                    ui.label('• ¡Dales una experiencia 100% digital y transparente!').classes('text-xs text-blue-900 font-black mt-2 italic')
