"""
SANDOVAL Dashboard - Gestión de Usuarios
Administración de usuarios, roles y registro de actividad
"""

from nicegui import ui
from utils.models import get_db, Usuario, Actividad, hash_password, log_actividad
from utils.auth import get_current_user, require_role
from datetime import datetime
import theme


def show_usuarios(container):
    with container:
        user = get_current_user()
        if not user or user['rol'] != 'admin':
            with ui.card().classes('w-full bg-red-50 border border-red-200 p-8 text-center'):
                ui.icon('lock', size='48px').classes('text-red-400')
                ui.label('Acceso denegado').classes('text-xl font-bold text-red-700 mt-2')
                ui.label('Solo los administradores pueden gestionar usuarios.').classes('text-gray-600')
            return
        
        state = {}
        
        # Header Corporativo Minimalista
        with ui.row().classes('w-full items-center justify-between mb-4 fade-in py-5 px-8 bg-white border border-gray-100 rounded-xl shadow-sm'):
            with ui.row().classes('items-center gap-4'):
                ui.icon('manage_accounts', size='32px').classes('text-[#274495]')
                ui.label('GESTIÓN DE USUARIOS').classes('text-xl font-extrabold text-[#274495] tracking-tight')
            ui.button('Nuevo Usuario', icon='person_add',
                on_click=lambda: open_user_dialog(table_container)
            ).classes('btn-sandoval')
        
        with ui.tabs().classes('w-full text-gray-600 bg-white border-b border-gray-200') as tabs:
            users_tab = ui.tab('Usuarios', icon='people').props('flat')
            activity_tab = ui.tab('Registro de Actividad', icon='history').props('flat')
        
        with ui.tab_panels(tabs, value=users_tab).classes('w-full bg-transparent'):
            with ui.tab_panel(users_tab).classes('p-0 pt-4'):
                table_container = ui.column().classes('w-full')
                refresh_users_table(table_container)
            
            with ui.tab_panel(activity_tab).classes('p-0 pt-4'):
                show_activity_log()


def refresh_users_table(container):
    container.clear()
    db = get_db()
    try:
        users = db.query(Usuario).all()
        
        with container:
            columns = [
                {'name': 'username', 'label': 'Usuario', 'field': 'username', 'align': 'left'},
                {'name': 'nombre', 'label': 'Nombre', 'field': 'nombre', 'align': 'left'},
                {'name': 'rol', 'label': 'Rol', 'field': 'rol', 'align': 'center'},
                {'name': 'email', 'label': 'Email', 'field': 'email', 'align': 'left'},
                {'name': 'activo', 'label': 'Estado', 'field': 'activo', 'align': 'center'},
                {'name': 'ultimo_login', 'label': 'Último Login', 'field': 'ultimo_login', 'align': 'center'},
            ]
            
            rows = []
            for u in users:
                rows.append({
                    'id': u.id,
                    'username': u.username,
                    'nombre': u.nombre,
                    'rol': u.rol.upper(),
                    'email': u.email or '',
                    'activo': 'Activo' if u.activo else 'Inactivo',
                    'activo_bool': u.activo,
                    'ultimo_login': u.ultimo_login.strftime('%Y-%m-%d %H:%M') if u.ultimo_login else 'Nunca',
                })
            
            table = ui.table(columns=columns, rows=rows, row_key='username').classes('w-full bg-white text-black')
            table.props('flat bordered dense binary-state-sort')
            
            table.add_slot('body-cell-rol', '''
                <q-td :props="props">
                    <q-badge 
                        :color="props.row.rol === 'ADMIN' ? 'red-6' : (props.row.rol === 'TECNICO' ? 'green-6' : 'blue-6')" 
                        :label="props.row.rol" 
                        class="font-bold"
                    />
                </q-td>
            ''')
            
            table.add_slot('body-cell-username', r'''
                <q-td :props="props">
                    <div class="row items-center no-wrap">
                        <span class="q-mr-sm text-bold">{{ props.row.username }}</span>
                        <q-btn flat dense icon="edit" color="primary" size="sm" @click="$parent.$emit('edit', props.row)" />
                    </div>
                </q-td>
            ''')
            
            table.on('edit', lambda e: open_user_dialog(container, e.args.get('id')))
    finally:
        db.close()


def open_user_dialog(table_container, edit_id=None):
    existing = None
    if edit_id:
        db = get_db()
        try:
            existing = db.query(Usuario).filter_by(id=edit_id).first()
            if existing:
                existing = {
                    'id': existing.id, 'username': existing.username,
                    'nombre': existing.nombre, 'rol': existing.rol,
                    'email': existing.email or '', 'activo': existing.activo,
                }
        finally:
            db.close()
    
    title = 'Editar Usuario' if existing else 'Nuevo Usuario'
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg bg-white p-0 border border-gray-200 shadow-xl'):
        with ui.row().classes('w-full justify-between items-center p-4 border-b border-gray-200 bg-[#f5f5f9]'):
            ui.label(title).classes('text-xl font-bold text-gray-800')
            ui.button(icon='close', on_click=dialog.close).props('flat round color=grey-8 size=sm')

        with ui.column().classes('w-full p-6 gap-3'):
            username_input = ui.input('Usuario *', value=existing['username'] if existing else '').props(
                'outlined dense bg-color=white' + (' readonly' if existing else '')
            ).classes('w-full')
            nombre_input = ui.input('Nombre completo *', value=existing['nombre'] if existing else '').props('outlined dense bg-color=white').classes('w-full')
            email_input = ui.input('Email', value=existing['email'] if existing else '').props('outlined dense type=email bg-color=white').classes('w-full')
            
            rol_select = ui.select(
                {'admin': 'Administrador', 'tecnico': 'Técnico', 'recepcionista': 'Recepcionista'},
                value=existing['rol'] if existing else 'tecnico', label='Rol *'
            ).props('outlined dense bg-color=white').classes('w-full')
            
            if not existing:
                password_input = ui.input('Contraseña *', password=True, password_toggle_button=True).props('outlined dense bg-color=white').classes('w-full')
            else:
                password_input = ui.input('Nueva contraseña (dejar vacío para no cambiar)', password=True, password_toggle_button=True).props('outlined dense bg-color=white').classes('w-full')
                activo_check = ui.checkbox('Usuario activo', value=existing['activo']).classes('text-gray-800')
        
        with ui.row().classes('w-full justify-end gap-2 p-4 border-t border-gray-200 bg-gray-50'):
            ui.button('Cancelar', on_click=dialog.close).props('flat color=grey-8')
            
            def guardar():
                if not username_input.value or not nombre_input.value:
                    theme.notify_error('Usuario y Nombre son obligatorios')
                    return
                
                db = get_db()
                try:
                    if existing:
                        user = db.query(Usuario).filter_by(id=existing['id']).first()
                        if user:
                            user.nombre = nombre_input.value.strip()
                            user.email = email_input.value.strip() if email_input.value else ''
                            user.rol = rol_select.value
                            user.activo = activo_check.value
                            if password_input.value:
                                user.password_hash = hash_password(password_input.value)
                            db.commit()
                            log_actividad(f'Usuario editado: {user.username}', 'usuarios')
                    else:
                        if not password_input.value:
                            theme.notify_error('La contraseña es obligatoria')
                            return
                        if db.query(Usuario).filter_by(username=username_input.value.strip()).first():
                            theme.notify_error('El usuario ya existe')
                            return
                        new_user = Usuario(
                            username=username_input.value.strip(),
                            password_hash=hash_password(password_input.value),
                            nombre=nombre_input.value.strip(),
                            email=email_input.value.strip() if email_input.value else '',
                            rol=rol_select.value,
                        )
                        db.add(new_user)
                        db.commit()
                        log_actividad(f'Usuario creado: {new_user.username}', 'usuarios')
                    
                    theme.notify_success('Usuario guardado exitosamente')
                    dialog.close()
                    refresh_users_table(table_container)
                except Exception as e:
                    db.rollback()
                    theme.notify_error(f'Error: {str(e)}')
                finally:
                    db.close()
            
            ui.button('Guardar', icon='save', on_click=guardar).classes('btn-sandoval px-10')
    
    dialog.open()


def show_activity_log():
    """Muestra el registro de actividad"""
    db = get_db()
    try:
        activities = db.query(Actividad).order_by(Actividad.fecha.desc()).limit(100).all()
        
        if not activities:
            with ui.card().classes('w-full bg-white border border-gray-200 p-8 text-center'):
                ui.icon('history_toggle_off', size='48px').classes('text-gray-400')
                ui.label('No hay actividad reciente').classes('text-gray-500 mt-2')
            return
        
        columns = [
            {'name': 'fecha', 'label': 'Fecha', 'field': 'fecha', 'align': 'center'},
            {'name': 'accion', 'label': 'Acción', 'field': 'accion', 'align': 'left'},
            {'name': 'modulo', 'label': 'Módulo', 'field': 'modulo', 'align': 'center'},
            {'name': 'usuario', 'label': 'Usuario', 'field': 'usuario', 'align': 'center'},
        ]
        
        rows = []
        for a in activities:
            rows.append({
                'fecha': a.fecha.strftime('%Y-%m-%d %H:%M') if a.fecha else '',
                'accion': a.accion,
                'modulo': a.modulo,
                'usuario': a.usuario.nombre if a.usuario else 'Sistema',
            })
        
        table = ui.table(columns=columns, rows=rows, row_key='fecha').classes('w-full bg-white text-black')
        table.props('flat bordered dense rows-per-page-options="[25, 50, 100]"')
    finally:
        db.close()
