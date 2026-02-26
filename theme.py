"""
SANDOVAL Dashboard - Sistema de Tema Visual v2.0
Colores corporativos, animaciones y diseño profesional
"""

from nicegui import ui

# Paleta de colores SANDOVAL - BLUE CORPORATE THEME
MENU_BG = '#ffffff'
PAGE_BG = '#f5f5f9'
CARD_BG = '#ffffff'
TEXT_PRIMARY = '#1f2937' # Dark blue-gray
TEXT_SECONDARY = '#6b7280' # Cool gray
BORDER = '#e5e7eb'
ACCENT_LIME = '#274495' # Changed to Corporate Blue

# Mantenemos compatibilidad
DARK_BG = PAGE_BG 
DRAWER_BG = MENU_BG

# Estados del flujo de trabajo con colores - Muted/Professional
ESTADOS_CONFIG = {
    'RECEPCIÓN':    {'icon': 'input',         'color': 'slate-600',  'hex': '#475569', 'order': 0},
    'DIAGNÓSTICO':  {'icon': 'search',        'color': 'blue-900',   'hex': '#1e3a8a', 'order': 1},
    'REPUESTOS':    {'icon': 'build_circle',  'color': 'blue-800',   'hex': '#1e40af', 'order': 2},
    'APROBACIÓN':   {'icon': 'check_circle',  'color': 'blue-900',   'hex': '#274495', 'order': 3},
    'REPARACIÓN':   {'icon': 'construction',  'color': 'blue-700',   'hex': '#1d4ed8', 'order': 4},
    'CONTROL':      {'icon': 'verified',      'color': 'slate-700',  'hex': '#334155', 'order': 5},
    'ENTREGA':      {'icon': 'local_shipping','color': 'slate-800',  'hex': '#1e293b', 'order': 6},
    'ARCHIVADO':    {'icon': 'archive',       'color': 'slate-400',  'hex': '#94a3b8', 'order': 7},
}

def frame(nav_title: str):
    """
    Crea el marco principal del dashboard - TEMA AZUL CORPORATIVO
    """
    # Agregar JavaScript para conexión estable
    try:
        from components.conexion_estable import CONEXION_ESTABLE_JS
        ui.add_head_html(CONEXION_ESTABLE_JS)
    except ImportError:
        pass
    
    ui.add_head_html('''
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;900&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
        <style>
            /* Fuente base para la aplicación */
            html, body, .nicegui-content { 
                font-family: 'Outfit', 'Inter', -apple-system, sans-serif; 
            }
            
            html, body {
                height: 100%;
                overflow-y: auto !important;
                overflow-x: hidden !important;
            }
            
            /* Asegurar que los iconos NO se vean afectados por el cambio de fuente */
            .material-icons, .q-icon {
                font-family: 'Material Icons' !important;
            }

            body { 
                background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
                color: #1e293b;
                margin: 0; 
                -webkit-font-smoothing: antialiased;
                animation: gradientShift 15s ease infinite;
                background-size: 200% 200%;
            }

            @keyframes gradientShift {
                0%, 100% { background-position: 0% 50%; }
                50% { background-position: 100% 50%; }
            }

            .q-drawer { 
                background: rgba(255, 255, 255, 0.95);
                backdrop-filter: blur(10px);
                border-right: 1px solid rgba(226, 232, 240, 0.8);
                box-shadow: 2px 0 20px rgba(0, 0, 0, 0.03);
            }

            /* Padding de la página principal */
            .nicegui-content { 
                padding: 32px !important; 
                max-width: 1600px;
                margin: 0 auto;
                animation: contentFadeIn 0.6s ease;
                overflow-y: auto !important;
                overflow-x: hidden !important;
                height: 100vh !important;
                box-sizing: border-box !important;
            }
            
            /* Asegurar que el contenedor de Quasar también tenga scroll */
            .q-page-container {
                overflow-y: auto !important;
                height: 100vh !important;
            }
            
            .q-page {
                overflow-y: auto !important;
                min-height: auto !important;
            }

            @keyframes contentFadeIn {
                from {
                    opacity: 0;
                    transform: translateY(20px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            /* Scrollbar elegante */
            ::-webkit-scrollbar { width: 8px; height: 8px; }
            ::-webkit-scrollbar-track { 
                background: rgba(241, 245, 249, 0.5); 
                border-radius: 10px;
            }
            ::-webkit-scrollbar-thumb { 
                background: linear-gradient(180deg, #cbd5e1, #94a3b8); 
                border-radius: 10px;
                transition: background 0.3s;
            }
            ::-webkit-scrollbar-thumb:hover { 
                background: linear-gradient(180deg, #94a3b8, #64748b); 
            }
            
            /* Botón corporativo - AZUL SANDOVAL con efecto 3D */
            .btn-sandoval {
                background: linear-gradient(135deg, #274495 0%, #1e367a 100%) !important;
                color: white !important;
                font-weight: 700 !important;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                border-radius: 12px !important;
                padding: 12px 28px !important;
                text-transform: none !important;
                box-shadow: 
                    0 4px 6px -1px rgba(39, 68, 149, 0.2),
                    0 2px 4px -1px rgba(39, 68, 149, 0.1),
                    inset 0 -2px 5px rgba(0, 0, 0, 0.1);
                position: relative;
                overflow: hidden;
            }
            .btn-sandoval::before {
                content: '';
                position: absolute;
                top: 0; left: -100%;
                width: 100%; height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
                transition: left 0.5s;
            }
            .btn-sandoval:hover::before {
                left: 100%;
            }
            .btn-sandoval:hover {
                background: linear-gradient(135deg, #1e367a 0%, #152a5e 100%) !important;
                transform: translateY(-2px) scale(1.02);
                box-shadow: 
                    0 12px 20px -3px rgba(39, 68, 149, 0.3),
                    0 4px 6px -2px rgba(39, 68, 149, 0.15),
                    inset 0 -2px 5px rgba(0, 0, 0, 0.15);
            }
            .btn-sandoval:active {
                transform: translateY(0) scale(0.98);
            }
            
            /* Sidebar items - Alineación perfecta "Recta" con efectos 3D */
            .sidebar-item {
                border-radius: 14px !important;
                margin: 6px 14px !important;
                color: #475569 !important;
                font-weight: 600 !important;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                min-height: 50px !important;
                text-transform: none !important;
                font-size: 0.875rem !important;
                padding: 0 18px !important;
                position: relative;
                overflow: hidden;
            }
            .sidebar-item::before {
                content: '';
                position: absolute;
                left: 0; top: 0;
                width: 4px; height: 100%;
                background: linear-gradient(180deg, #274495, #60a5fa);
                transform: scaleY(0);
                transition: transform 0.3s ease;
            }
            .sidebar-item:hover {
                background: linear-gradient(135deg, #f1f5f9 0%, #e8f0fb 100%) !important;
                color: #274495 !important;
                transform: translateX(4px) scale(1.02);
                box-shadow: 
                    0 4px 12px rgba(39, 68, 149, 0.08),
                    inset 0 0 0 1px rgba(39, 68, 149, 0.1);
            }
            .sidebar-item:hover::before {
                transform: scaleY(1);
            }
            .sidebar-item:active {
                transform: translateX(2px) scale(0.98);
            }
            /* Forzar el contenedor interno de Quasar a ser una fila alineada a la izquierda */
            .sidebar-item .q-btn__content {
                justify-content: flex-start !important;
                flex-wrap: nowrap !important;
            }
            .sidebar-item .q-icon {
                font-size: 24px !important;
                width: 36px !important;
                margin-right: 14px !important;
                color: #94a3b8 !important;
                display: flex !important;
                justify-content: center !important;
                transition: all 0.3s ease;
                filter: drop-shadow(0 0 0 transparent);
            }
            .sidebar-item:hover .q-icon {
                color: #274495 !important;
                transform: scale(1.1) rotate(5deg);
                filter: drop-shadow(0 2px 4px rgba(39, 68, 149, 0.2));
            }

            /* Cards minimalistas con efecto 3D y glassmorphism */
            .card-sandoval {
                background: rgba(255, 255, 255, 0.85) !important;
                backdrop-filter: blur(10px) !important;
                border: 1px solid rgba(241, 245, 249, 0.8) !important;
                border-radius: 24px !important;
                box-shadow: 
                    0 4px 6px -1px rgba(0, 0, 0, 0.03),
                    0 2px 4px -1px rgba(0, 0, 0, 0.02),
                    inset 0 0 0 1px rgba(255, 255, 255, 0.5) !important;
                transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
                position: relative;
                overflow: hidden;
            }
            .card-sandoval::before {
                content: '';
                position: absolute;
                top: 0; left: 0;
                right: 0; height: 3px;
                background: linear-gradient(90deg, #274495, #60a5fa, #274495);
                background-size: 200% 100%;
                opacity: 0;
                transition: opacity 0.4s;
            }
            .card-sandoval:hover {
                border-color: rgba(226, 232, 240, 1) !important;
                transform: translateY(-4px) scale(1.01);
                box-shadow: 
                    0 20px 40px -8px rgba(39, 68, 149, 0.08),
                    0 8px 16px -4px rgba(39, 68, 149, 0.04),
                    inset 0 0 0 1px rgba(255, 255, 255, 0.8) !important;
            }
            .card-sandoval:hover::before {
                opacity: 1;
                animation: shimmer 2s linear infinite;
            }
            @keyframes shimmer {
                0% { background-position: -200% 0; }
                100% { background-position: 200% 0; }
            }
            
            h1, h2, h3, .text-xl, .text-2xl {
                font-family: 'Outfit', sans-serif !important;
                font-weight: 800 !important;
                letter-spacing: -0.02em !important;
                color: #0f172a !important;
                text-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);
            }

            /* Animación de entrada suave para elementos */
            .fade-in {
                animation: fadeIn 0.6s ease-out forwards;
            }
            @keyframes fadeIn {
                from { 
                    opacity: 0; 
                    transform: translateY(15px) scale(0.98);
                }
                to { 
                    opacity: 1; 
                    transform: translateY(0) scale(1);
                }
            }

            /* Efecto hover para iconos */
            .icon-hover {
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }
            .icon-hover:hover {
                transform: scale(1.15) rotate(10deg);
                filter: drop-shadow(0 4px 8px rgba(39, 68, 149, 0.3));
            }

            /* Loading spinner mejorado */
            @keyframes spin3D {
                0% { transform: rotate(0deg) rotateY(0deg); }
                50% { transform: rotate(180deg) rotateY(180deg); }
                100% { transform: rotate(360deg) rotateY(360deg); }
            }

            .spinner-3d {
                animation: spin3D 1.5s cubic-bezier(0.4, 0, 0.2, 1) infinite;
            }

            /* Efectos de brillo para elementos premium */
            .shine-effect {
                position: relative;
                overflow: hidden;
            }
            .shine-effect::after {
                content: '';
                position: absolute;
                top: -50%; left: -50%;
                width: 200%; height: 200%;
                background: linear-gradient(45deg, transparent 30%, rgba(255,255,255,0.3) 50%, transparent 70%);
                transform: rotate(45deg);
                animation: shine 3s ease-in-out infinite;
            }
            @keyframes shine {
                0%, 100% { transform: translateX(-100%) translateY(-100%) rotate(45deg); }
                50% { transform: translateX(100%) translateY(100%) rotate(45deg); }
            }

            /* ═══════════════════════════════════════════════════════════════
               MEJORAS 3D PARA GRÁFICOS DE PLOTLY
               ═══════════════════════════════════════════════════════════════ */

            /* Contenedor de gráficos con efecto 3D */
            .plotly-graph-div {
                filter: drop-shadow(0 10px 25px rgba(39, 68, 149, 0.08)) !important;
                transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1) !important;
                border-radius: 16px !important;
            }

            .plotly-graph-div:hover {
                filter: drop-shadow(0 15px 40px rgba(39, 68, 149, 0.15)) !important;
                transform: translateY(-3px) scale(1.01) !important;
            }

            /* Tooltips mejorados */
            .plotly .hoverlayer .hovertext {
                background: rgba(255, 255, 255, 0.98) !important;
                backdrop-filter: blur(10px) !important;
                border: 1px solid rgba(226, 232, 240, 0.8) !important;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15) !important;
                border-radius: 12px !important;
                font-family: 'Outfit', sans-serif !important;
            }

            /* Mejoras para pie charts */
            .plotly .slice path {
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
                filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1)) !important;
            }

            .plotly .slice path:hover {
                filter: drop-shadow(0 4px 12px rgba(39, 68, 149, 0.3)) brightness(1.05) !important;
            }

            /* Mejoras para las barras */
            .plotly .bars path {
                transition: all 0.3s ease !important;
            }

            .plotly .bars path:hover {
                filter: brightness(1.1) drop-shadow(0 4px 12px currentColor) !important;
            }

            /* Cards con gráficos */
            .card-sandoval:has(.plotly-graph-div) {
                background: linear-gradient(135deg, rgba(255,255,255,0.98), rgba(248,250,252,0.95)) !important;
            }

            /* ═══════════════════════════════════════════════════════════════
               MEJORAS ULTRA PROFESIONALES - TABLAS
               ═══════════════════════════════════════════════════════════════ */

            .q-table {
                background: rgba(255, 255, 255, 0.98) !important;
                backdrop-filter: blur(10px) !important;
                border-radius: 16px !important;
                overflow: hidden !important;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04) !important;
            }

            .q-table thead tr {
                background: linear-gradient(135deg, #f8fafc, #f1f5f9) !important;
                border-bottom: 2px solid #e2e8f0 !important;
            }

            .q-table thead th {
                font-weight: 700 !important;
                font-size: 0.85rem !important;
                color: #475569 !important;
                text-transform: uppercase !important;
                letter-spacing: 0.5px !important;
                padding: 16px 12px !important;
            }

            .q-table tbody tr {
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
                border-bottom: 1px solid #f1f5f9 !important;
            }

            .q-table tbody tr:hover {
                background: linear-gradient(90deg, rgba(39, 68, 149, 0.03), transparent) !important;
                transform: translateX(4px) !important;
                box-shadow: -4px 0 0 0 #274495 inset !important;
            }

            .q-table tbody td {
                padding: 14px 12px !important;
                color: #64748b !important;
                font-size: 0.875rem !important;
            }

            /* INPUTS Y FORMULARIOS PREMIUM */
            .q-field__control {
                border-radius: 12px !important;
                background: rgba(248, 250, 252, 0.8) !important;
                border: 1px solid #e2e8f0 !important;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
            }

            .q-field__control:hover {
                border-color: #cbd5e1 !important;
                background: rgba(241, 245, 249, 0.9) !important;
            }

            .q-field--focused .q-field__control {
                border-color: #274495 !important;
                background: white !important;
                box-shadow: 0 0 0 3px rgba(39, 68, 149, 0.1) !important;
            }

            /* BOTONES ULTRA PREMIUM */
            .q-btn:not(.q-btn--flat):hover {
                transform: translateY(-2px) scale(1.02) !important;
                box-shadow: 0 8px 20px rgba(0, 0, 0, 0.12) !important;
            }

            .q-btn:active {
                transform: translateY(0) scale(0.98) !important;
            }

            /* MODALS PREMIUM */
            .q-dialog__backdrop {
                backdrop-filter: blur(8px) !important;
                background: rgba(15, 23, 42, 0.6) !important;
            }

            .q-card {
                border-radius: 20px !important;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2) !important;
            }
        </style>
    ''')
    
    # Header
    with ui.header().classes('bg-white text-gray-800 border-b border-gray-200 h-16 shadow-none'):
        with ui.row().classes('w-full items-center justify-between px-6 h-full'):
            # Left side: Menu + Site Title
            with ui.row().classes('items-center gap-4'):
                ui.button(on_click=lambda: left_drawer.toggle(), icon='menu').props('flat color=grey-8').classes('p-2')
                with ui.row().classes('items-center gap-3'):
                    ui.image('/assets/logo_sandoval.jpg').classes('w-10 h-10 rounded-lg shadow-sm border border-gray-100 object-contain bg-white')
                    ui.label('MECÁNICA Y REPUESTOS SANDOVAL EIRL').classes('text-base font-bold text-gray-800 tracking-tight')
            
            # Right side: User Profile + Actions
            with ui.row().classes('items-center gap-6'):
                with ui.row().classes('items-center gap-2'):
                    ui.button(icon='refresh', on_click=lambda: ui.run_javascript('location.reload()')).props('flat color=grey-7 dense round size=sm').tooltip('Actualizar')
                    
                    notif_btn = ui.button(icon='notifications', on_click=lambda: _show_notifications_panel()).props('flat color=grey-7 dense round size=sm').tooltip('Notificaciones')
                    try:
                        from utils.auth import get_current_user as _gcu
                        from utils.notifications import get_notification_count, get_client_notifications
                        _u = _gcu()
                        if _u and _u.get('rol') == 'cliente':
                            count = len(get_client_notifications(_u.get('id'), _u.get('placa', '')))
                        else:
                            count = get_notification_count()
                        if count > 0:
                            notif_btn.badge(str(count), color='red-6')
                    except Exception:
                        pass
                
                # Perfil de Usuario
                try:
                    from utils.auth import get_current_user
                    user = get_current_user()
                    if user:
                        with ui.row().classes('items-center gap-3 pl-4 border-l border-gray-100 py-1 hover:bg-gray-50 rounded-lg px-2 cursor-pointer transition-colors'):
                            ui.avatar(user['nombre'][:2].upper(), color='blue-9', text_color='white').props('size=sm').classes('font-bold shadow-sm')
                            with ui.column().classes('gap-0 hidden md:flex'):
                                ui.label(user['nombre']).classes('text-xs font-bold leading-tight text-gray-800')
                                ui.label(user['rol'].upper()).classes('text-[9px] text-[#274495] leading-tight font-extrabold tracking-wider')
                except Exception:
                    pass
    
    left_drawer = ui.left_drawer(value=True).classes('bg-white text-gray-800').props('width=280 bordered')
    
    return left_drawer

def notify_success(msg: str):
    ui.notify(msg, type='positive', position='top-right', close_button=True)

def notify_error(msg: str):
    ui.notify(msg, type='negative', position='top-right', close_button=True)

def notify_info(msg: str):
    ui.notify(msg, type='info', position='top-right')

def notify_warning(msg: str):
    ui.notify(msg, type='warning', position='top-right')

def _show_notifications_panel():
    """Muestra panel lateral de notificaciones"""
    try:
        from utils.auth import get_current_user
        from utils.notifications import get_notifications, get_client_notifications
        user = get_current_user()
        if user and user.get('rol') == 'cliente':
            raw = get_client_notifications(user.get('id'), user.get('placa', ''))
            # Convertir formato cliente al formato admin para reutilizar el mismo render
            notifs = []
            for n in raw:
                notifs.append({
                    'icon': 'notifications',
                    'color': 'green-6' if n.get('icon_cls') == 'verde' else ('blue-6' if n.get('icon_cls') == 'azul' else 'orange-6'),
                    'title': n.get('titulo', ''),
                    'detail': n.get('desc', ''),
                    'time': n.get('tiempo', ''),
                    'type': 'info',
                })
        else:
            notifs = get_notifications()
    except Exception:
        notifs = []

    hay_nuevas = any(n.get('type') == 'warning' for n in notifs)

    with ui.dialog() as dialog, ui.card().classes('bg-white p-6 w-96 max-h-[560px] border-0 shadow-2xl card-sandoval'):
        with ui.row().classes('w-full items-center justify-between mb-4'):
            ui.label('Notificaciones').classes('text-xl font-bold text-gray-800')
            with ui.row().classes('gap-2 items-center'):
                if hay_nuevas:
                    def _marcar_vistas_admin():
                        try:
                            from utils.notifications import marcar_citas_vistas_admin
                            marcar_citas_vistas_admin()
                        except Exception:
                            pass
                        ui.notify('Notificaciones marcadas como vistas', type='positive', position='top')
                        dialog.close()
                    ui.button('✓ Marcar vistas', on_click=_marcar_vistas_admin).props('flat dense').classes('text-xs text-blue-600 font-semibold')
                ui.button(icon='close', on_click=dialog.close).props('flat round color=grey-6 size=sm')

        if not notifs:
            with ui.column().classes('w-full items-center py-10'):
                ui.icon('notifications_none', size='48px').classes('text-gray-200 mb-2')
                ui.label('Sin notificaciones nuevas').classes('text-gray-400 text-sm')
        else:
            with ui.scroll_area().classes('w-full').style('max-height: 420px'):
                for n in notifs:
                    es_nueva = n.get('type') == 'warning'
                    border_cls = 'border-blue-400 bg-blue-50' if es_nueva else 'border-gray-100 bg-white'
                    with ui.card().classes(f'w-full border p-4 mb-3 card-sandoval {border_cls}'):
                        with ui.row().classes('items-start gap-3'):
                            ui.icon(n['icon'], size='24px').classes(f'text-{n["color"]} opacity-90 mt-1')
                            with ui.column().classes('gap-1 flex-1'):
                                ui.label(n['title']).classes('text-gray-900 text-sm font-bold')
                                ui.label(n['detail']).classes('text-gray-500 text-xs leading-relaxed')
                                ui.label(n.get('time', '')).classes('text-gray-400 text-[10px] mt-1 font-medium')
    dialog.open()


def confirm_dialog(title: str, message: str, on_confirm, on_cancel=None):
    """Diálogo de confirmación elegante"""
    with ui.dialog() as dialog, ui.card().classes('bg-white p-8 w-[400px] border-0 shadow-2xl card-sandoval'):
        with ui.column().classes('w-full gap-4 items-center'):
            ui.icon('help_outline', size='64px').classes('text-blue-600')
            ui.label(title).classes('text-2xl font-bold text-gray-800')
            ui.label(message).classes('text-gray-500 text-center leading-relaxed')
            
            with ui.row().classes('w-full justify-center gap-3 mt-6'):
                ui.button('Cancelar', on_click=lambda: (dialog.close(), on_cancel() if on_cancel else None)).props('flat color=grey-7').classes('px-6 rounded-lg')
                ui.button('Confirmar', on_click=lambda: (dialog.close(), on_confirm())).classes('btn-sandoval px-8')
    
    dialog.open()
    return dialog
    
    dialog.open()
    return dialog
