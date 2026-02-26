"""
SANDOVAL Dashboard - Sidebar (Menú Lateral)
Navegación con permisos por rol
"""

from nicegui import ui
from utils.auth import get_current_user, tiene_permiso, logout


def create_sidebar(drawer, on_navigate):
    user = get_current_user()
    
    with drawer:
        # Logo - Estilo Corporativo Moderno
        with ui.column().classes('w-full p-6 border-b border-gray-100 mb-2'):
            with ui.row().classes('items-center gap-4 w-full'):
                ui.image('/assets/logo_sandoval.jpg').classes('w-12 h-12 rounded-xl shadow-sm bg-white object-contain')
                with ui.column().classes('gap-0'):
                    ui.label('MECÁNICA Y REPUESTOS').classes('text-[8px] text-[#274495] font-black tracking-[0.2em] uppercase')
                    ui.label('SANDOVAL EIRL').classes('text-lg font-black text-gray-900 tracking-tighter')
        
        # Menú - Diseño Adaptativo por Rol
        if user and user.get('rol') == 'cliente':
            menu_items = [
                {'icon': 'directions_car', 'label': 'Mi Vehículo', 'page': 'dashboard', 'modulo': 'portal_cliente'},
            ]
        else:
            menu_items = [
                {'icon': 'dashboard',     'label': 'Dashboard',           'page': 'dashboard',    'modulo': 'dashboard'},
                {'icon': 'build',         'label': 'Órdenes de Servicio', 'page': 'ordenes',      'modulo': 'ordenes'},
                {'icon': 'people',        'label': 'Clientes',            'page': 'clientes',     'modulo': 'clientes'},
                {'icon': 'directions_car','label': 'Vehículos',           'page': 'vehiculos',    'modulo': 'vehiculos'},
                {'icon': 'store',         'label': 'Proveedores',         'page': 'proveedores',  'modulo': 'proveedores'},
                {'icon': 'inventory_2',   'label': 'Inventario',          'page': 'inventario',   'modulo': 'inventario'},
                {'icon': 'event',         'label': 'Citas / Agenda',      'page': 'citas',        'modulo': 'citas'},
                {'icon': 'assessment',    'label': 'Reportes',            'page': 'reportes',     'modulo': 'reportes'},
                {'icon': 'trending_up',   'label': 'Rentabilidad',        'page': 'rentabilidad', 'modulo': 'rentabilidad'},
                {'icon': 'manage_accounts','label': 'Usuarios',           'page': 'usuarios',     'modulo': 'usuarios'},
                {'icon': 'settings',      'label': 'Configuración',       'page': 'config',       'modulo': 'config'},
            ]
        
        with ui.column().classes('w-full gap-0.5'):
            for item in menu_items:
                if tiene_permiso(item['modulo']):
                    ui.button(
                        item['label'], icon=item['icon'],
                        on_click=lambda p=item['page']: on_navigate(p)
                    ).props('flat color=slate-600').classes('sidebar-item w-full')
        
        # Accesos rápidos (Solo para personal)
        if user and user.get('rol') != 'cliente':
            ui.separator().classes('my-4 mx-6 opacity-30')
            with ui.column().classes('w-full gap-0.5'):
                ui.label('ACCESOS RÁPIDOS').classes('text-[10px] text-gray-400 px-8 mb-2 font-black tracking-widest')
                if tiene_permiso('ordenes'):
                    ui.button('Nueva Orden', icon='add',
                        on_click=lambda: on_navigate('nueva_orden')
                    ).props('flat').classes('sidebar-item w-full font-bold')
                if tiene_permiso('clientes'):
                    ui.button('Nuevo Cliente', icon='person_add',
                        on_click=lambda: on_navigate('nuevo_cliente')
                    ).props('flat').classes('sidebar-item w-full')
        
        # User info + logout
        ui.space()
        with ui.column().classes('w-full p-6 border-t border-gray-100 mt-auto bg-gray-50/50'):
            if user:
                with ui.row().classes('w-full items-center gap-3 mb-4'):
                    ui.avatar(user['nombre'][:2].upper(), color='blue-9', text_color='white').classes('w-9 h-9 font-bold shadow-sm')
                    with ui.column().classes('gap-0 flex-1'):
                        ui.label(user['nombre']).classes('text-sm text-gray-800 font-bold leading-tight')
                        ui.label(user['rol'].upper()).classes('text-[10px] text-[#274495] font-bold')
                
                ui.button('Cerrar Sesión', icon='logout', on_click=lambda: logout()).props(
                    'flat color=red-7 dense text-sm'
                ).classes('w-full justify-start p-2 rounded-lg hover:bg-red-50')
            
            ui.label('© 2026 SANDOVAL EIRL').classes('text-[9px] text-gray-400 text-center w-full mt-2 font-medium tracking-wide')
