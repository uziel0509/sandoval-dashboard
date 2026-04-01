"""
SANDOVAL Dashboard - Sistema de Autenticación
Login/logout con roles y permisos
Compatible con native mode (pywebview)
"""

from nicegui import ui, app
from utils.models import get_db, Usuario, verify_password, hash_password, log_actividad
from datetime import datetime
import traceback

# ─── Variable global de sesión (fallback para native mode) ───
_session_user = {}


def get_current_user() -> dict | None:
    """Obtiene el usuario de la sesión actual (Empleado o Cliente)"""
    try:
        # Usar app.storage.user (más estable para sesiones)
        storage = app.storage.user
        user_id = storage.get('sandoval_user_id')
        client_id = storage.get('sandoval_client_id')
        client_plate = storage.get('sandoval_client_plate')
        
        # 1. Verificar si es Empleado
        if user_id:
            db = get_db()
            try:
                from utils.models import Usuario
                user = db.query(Usuario).filter_by(id=int(user_id), activo=True).first()
                if user:
                    return {
                        'id': user.id,
                        'username': user.username,
                        'nombre': user.nombre,
                        'rol': user.rol,
                        'email': user.email,
                        'tipo': 'empleado'
                    }
            finally:
                db.close()
        
        # 2. Verificar si es Cliente
        if client_id and client_plate:
            db = get_db()
            try:
                from utils.models import Cliente
                cliente = db.query(Cliente).filter_by(id=client_id).first()
                if cliente:
                    return {
                        'id': cliente.id,
                        'nombre': f"{cliente.nombre} {cliente.apellidos}".strip(),
                        'rol': 'cliente',
                        'placa': client_plate,
                        'tipo': 'cliente'
                    }
            finally:
                db.close()

    except Exception as e:
        print(f"[AUTH] Error get_current_user: {e}")
    return None


def _set_session(user_id: int, nombre: str, rol: str, is_client: bool = False, plate: str = None):
    """Guarda sesión en app.storage.user"""
    if is_client:
        app.storage.user['sandoval_client_id'] = user_id
        app.storage.user['sandoval_client_plate'] = plate
        app.storage.user['sandoval_user_rol'] = 'cliente'
    else:
        app.storage.user['sandoval_user_id'] = user_id
        app.storage.user['sandoval_user_nombre'] = nombre
        app.storage.user['sandoval_user_rol'] = rol


def _clear_session():
    """Limpia la sesión de app.storage.user"""
    try:
        keys = ['sandoval_user_id', 'sandoval_user_nombre', 'sandoval_user_rol', 
                'sandoval_client_id', 'sandoval_client_plate']
        for k in keys:
            app.storage.user.pop(k, None)
    except Exception:
        pass


def require_auth():
    return get_current_user() is not None


def require_role(role: str) -> bool:
    user = get_current_user()
    if not user:
        return False
    if user['rol'] == 'admin':
        return True
    return user['rol'] == role


PERMISOS = {
    'admin': ['dashboard', 'ordenes', 'cotizaciones', 'creditos', 'clientes', 'vehiculos', 'proveedores', 'inventario', 'notas_venta', 'reportes', 'rentabilidad', 'config', 'usuarios', 'citas', 'facturas', 'asistente_ia'],
    'recepcionista': ['dashboard', 'ordenes', 'cotizaciones', 'creditos', 'clientes', 'vehiculos', 'notas_venta', 'citas', 'facturas'],
    'tecnico': ['dashboard', 'ordenes', 'inventario', 'notas_venta', 'asistente_ia'],
    'cliente': ['portal_cliente', 'citas'],
}


def tiene_permiso(modulo: str) -> bool:
    user = get_current_user()
    if not user:
        return False
    permisos = PERMISOS.get(user['rol'], [])
    return modulo in permisos


def show_login_page():
    """Renderiza la página de login completa con pestañas para Personal y Clientes"""
    # Si ya está logueado, enviar al inicio
    if get_current_user():
        ui.navigate.to('/')
        return

    ui.add_head_html('<style>body { background-color: #f8fafc; }</style>')
    
    with ui.column().classes('w-full min-h-screen items-center justify-center p-4'):
        with ui.card().classes('w-full max-w-md bg-white border border-gray-100 p-8 card-sandoval'):
            
            with ui.column().classes('w-full items-center mb-6'):
                ui.image('/assets/logo_sandoval.jpg').classes('w-20 h-20 mb-4 object-contain rounded-xl shadow-sm')
                ui.label('SANDOVAL EIRL').classes('text-2xl font-black text-gray-900 tracking-tighter')
                ui.label('Sistema de Gestión Automotriz').classes('text-[10px] text-gray-400 font-bold uppercase tracking-[0.2em]')

            with ui.tabs().classes('w-full mb-6 bg-gray-50 rounded-lg p-1') as tabs:
                t_staff = ui.tab('PERSONAL', icon='badge')
                t_client = ui.tab('SOY CLIENTE', icon='directions_car')

            error_label = ui.label('').classes('text-red-500 text-sm text-center w-full mb-4 font-medium')
            error_label.visible = False

            with ui.tab_panels(tabs, value=t_staff).classes('w-full bg-transparent'):
                # --- LOGIN PERSONAL ---
                with ui.tab_panel(t_staff):
                    staff_user_in = ui.input('Usuario').props('outlined dense').classes('w-full mb-3')
                    staff_pass_in = ui.input('Contraseña', password=True, password_toggle_button=True).props('outlined dense').classes('w-full mb-6')

                    async def handle_staff_login():
                        db = get_db()
                        try:
                            u_val = (staff_user_in.value or '').strip()
                            p_val = staff_pass_in.value or ''
                            user = db.query(Usuario).filter_by(username=u_val, activo=True).first()
                            if user and verify_password(p_val, user.password_hash):
                                _set_session(user.id, user.nombre, user.rol)
                                user.ultimo_login = datetime.now()
                                db.commit()
                                ui.navigate.to('/')
                            else:
                                error_label.text = 'Usuario o contraseña incorrectos'
                                error_label.visible = True
                        except Exception as e:
                            # Evitar mostrar el error interno al usuario si es congestión de respuesta
                            if "response to the browser has already been built" in str(e):
                                ui.navigate.to('/')
                            else:
                                error_label.text = 'Error al conectar con el servidor'
                                error_label.visible = True
                        finally: db.close()

                    ui.button('Entrar al Sistema', on_click=handle_staff_login).classes('w-full btn-sandoval h-12 shadow-md')

                # --- LOGIN CLIENTE ---
                with ui.tab_panel(t_client):
                    ui.label('Consulte el estado de su vehículo en tiempo real').classes('text-xs text-gray-400 mb-4 text-center')
                    client_placa_in = ui.input('Número de Placa', placeholder='ABC-123').props('outlined dense').classes('w-full mb-3')
                    client_pass_in = ui.input('Contraseña de acceso', password=True, password_toggle_button=True).props('outlined dense').classes('w-full mb-2')
                    ui.label('Su contraseña inicial es su DNI o RUC. Puede cambiarla desde su perfil.').classes('text-[10px] text-gray-400 mb-4 text-center')

                    async def handle_client_login():
                        from utils.models import Vehiculo, Cliente
                        db = get_db()
                        try:
                            p_val = (client_placa_in.value or '').strip().upper()
                            pass_val = (client_pass_in.value or '').strip()
                            if not p_val or not pass_val:
                                error_label.text = 'Ingrese su placa y contraseña'
                                error_label.visible = True
                                return
                            v = db.query(Vehiculo).filter_by(placa=p_val).first()
                            if not v:
                                error_label.text = 'Placa no registrada en el sistema'
                                error_label.visible = True
                                return
                            cliente = db.query(Cliente).filter_by(id=v.cliente_id).first()
                            if not cliente:
                                error_label.text = 'Cliente no encontrado'
                                error_label.visible = True
                                return
                            # Verificar contraseña: si tiene pin_acceso hasheado lo usa,
                            # si no → fallback a DNI/RUC (contraseña inicial)
                            pass_ok = False
                            if cliente.pin_acceso:
                                pass_ok = verify_password(pass_val, cliente.pin_acceso)
                            else:
                                pass_ok = (pass_val == cliente.id)
                            if pass_ok:
                                _set_session(v.cliente_id, '', 'cliente', is_client=True, plate=v.placa)
                                ui.navigate.to('/')
                            else:
                                error_label.text = 'Contraseña incorrecta. Su contraseña inicial es su DNI o RUC.'
                                error_label.visible = True
                        except Exception as e:
                            if "response to the browser has already been built" in str(e):
                                ui.navigate.to('/')
                            else:
                                error_label.text = 'Error al validar datos'
                                error_label.visible = True
                        finally: db.close()

                    ui.button('Ingresar al Portal', icon='login', on_click=handle_client_login).classes('w-full btn-sandoval h-12 shadow-md')

            with ui.expansion('Ayuda', icon='help_outline').classes('w-full text-gray-400 mt-6 pt-2'):
                ui.label('Personal: Ingrese su usuario y contraseña asignados.').classes('text-[10px] text-gray-400 text-center w-full')
                ui.label('Clientes: Use su placa + DNI/RUC como contraseña inicial.').classes('text-[10px] text-gray-400 text-center w-full')
                ui.label('Puede cambiar su contraseña desde su perfil una vez ingresado.').classes('text-[10px] text-gray-400 text-center w-full mt-1')
                ui.label('¿Problemas? Llame al taller: +51 999 999 999').classes('text-[10px] text-gray-400 text-center w-full mt-1')


def logout():
    """Cierra la sesión"""
    user = get_current_user()
    if user:
        try:
            log_actividad(f'Logout: {user["nombre"]}', 'auth', '', user['id'])
        except Exception:
            pass
    _clear_session()
    ui.navigate.to('/login')
