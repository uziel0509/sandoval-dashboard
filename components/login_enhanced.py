"""
SANDOVAL Dashboard - Login 3D Mejorado
Página de login con animaciones 3D y efectos visuales profesionales
"""

from nicegui import ui, app
from utils.models import get_db, Usuario, Cliente, Vehiculo, verify_password
from datetime import datetime

def show_login_enhanced():
    """Renderiza login mejorado con animaciones 3D"""
    
    ui.add_head_html('''
    <style>
        body { 
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 30%, #274495 100%);
            background-size: 400% 400%;
            animation: gradientShift 15s ease infinite;
            position: relative;
            overflow-x: hidden;
            overflow-y: auto !important;
            min-height: 100vh;
        }
        @keyframes gradientShift {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        
        /* Partículas de fondo */
        .login-particles {
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            pointer-events: none;
            overflow: hidden;
            z-index: 0;
        }
        .particle {
            position: absolute;
            width: 3px; height: 3px;
            background: rgba(255,255,255,0.5);
            border-radius: 50%;
            animation: particleFloat 20s linear infinite;
        }
        @keyframes particleFloat {
            0% { transform: translateY(100vh) scale(0); opacity: 0; }
            10% { opacity: 1; }
            90% { opacity: 1; }
            100% { transform: translateY(-10vh) scale(1); opacity: 0; }
        }
        .particle:nth-child(1) { left: 10%; animation-delay: 0s; }
        .particle:nth-child(2) { left: 20%; animation-delay: 2s; }
        .particle:nth-child(3) { left: 30%; animation-delay: 4s; }
        .particle:nth-child(4) { left: 40%; animation-delay: 1s; }
        .particle:nth-child(5) { left: 50%; animation-delay: 3s; }
        .particle:nth-child(6) { left: 60%; animation-delay: 5s; }
        .particle:nth-child(7) { left: 70%; animation-delay: 2.5s; }
        .particle:nth-child(8) { left: 80%; animation-delay: 4.5s; }
        .particle:nth-child(9) { left: 90%; animation-delay: 1.5s; }
        
        /* Herramientas flotantes */
        .login-tools {
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            pointer-events: none;
            opacity: 0.06;
            z-index: 0;
        }
        .tool-float {
            position: absolute;
            font-size: 50px;
            animation: toolRotate 25s linear infinite;
        }
        @keyframes toolRotate {
            0% { transform: rotate(0deg) translateY(0); }
            50% { transform: rotate(180deg) translateY(-30px); }
            100% { transform: rotate(360deg) translateY(0); }
        }
        .tool-1 { top: 10%; left: 10%; animation-delay: 0s; }
        .tool-2 { top: 20%; right: 15%; animation-delay: 3s; }
        .tool-3 { bottom: 20%; left: 15%; animation-delay: 6s; }
        .tool-4 { bottom: 15%; right: 10%; animation-delay: 9s; }
        
        /* Card de login 3D */
        .login-card-3d {
            transform-style: preserve-3d;
            perspective: 1000px;
            animation: cardEntrance 0.8s cubic-bezier(0.4, 0, 0.2, 1) forwards;
            position: relative;
            z-index: 10;
        }
        @keyframes cardEntrance {
            from {
                opacity: 0;
                transform: translateY(50px) rotateX(-15deg) scale(0.9);
            }
            to {
                opacity: 1;
                transform: translateY(0) rotateX(0deg) scale(1);
            }
        }
        
        /* Logo 3D flotante */
        .logo-3d-float {
            animation: logo3DFloat 3s ease-in-out infinite;
            filter: drop-shadow(0 10px 30px rgba(39, 68, 149, 0.6));
        }
        @keyframes logo3DFloat {
            0%, 100% { transform: translateY(0) scale(1); }
            50% { transform: translateY(-8px) scale(1.03); }
        }
    </style>
    ''')
    
    with ui.column().classes('w-full min-h-screen items-center justify-center p-4').style('position: relative; z-index: 1; overflow-y: auto;'):
        # Partículas y herramientas de fondo
        ui.html('''
        <div class="login-particles">
            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>
        </div>
        <div class="login-tools">
            <div class="tool-float tool-1">🔧</div>
            <div class="tool-float tool-2">⚙️</div>
            <div class="tool-float tool-3">🛠️</div>
            <div class="tool-float tool-4">🚗</div>
        </div>
        ''')
        
        # Card principal con glassmorphism - SIN restricción de altura
        with ui.card().classes('w-full max-w-md login-card-3d').style(
            'background: rgba(255, 255, 255, 0.95);'
            'backdrop-filter: blur(20px);'
            'border: 1px solid rgba(255, 255, 255, 0.3);'
            'box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);'
            'padding: 1.25rem 1.5rem;'
            'border-radius: 24px;'
            'margin: 10px 0;'
        ):
            
            with ui.column().classes('w-full items-center mb-3'):
                ui.image('/assets/logo_sandoval.jpg').classes('w-16 h-16 mb-2 object-contain rounded-xl shadow-2xl logo-3d-float')
                ui.label('MECÁNICA Y REPUESTOS').classes('text-[10px] text-blue-900 font-black tracking-[0.2em] uppercase mb-0')
                ui.label('SANDOVAL EIRL').classes('text-2xl font-black text-gray-900 tracking-tighter mb-1')
                ui.label('Sistema Profesional de Gestión').classes('text-xs text-gray-500 font-semibold tracking-wide')

            # Tabs con estilo mejorado
            with ui.tabs().classes('w-full mb-2').style(
                'background: linear-gradient(135deg, #f1f5f9, #e2e8f0);'
                'border-radius: 12px;'
                'padding: 4px;'
                'box-shadow: inset 0 2px 4px rgba(0,0,0,0.06);'
            ) as tabs:
                t_staff = ui.tab('👔 PERSONAL', icon='badge').classes('font-bold text-xs')
                t_client = ui.tab('🚗 SOY CLIENTE', icon='directions_car').classes('font-bold text-xs')

            error_label = ui.label('').classes('text-red-600 text-xs text-center w-full mb-1 font-semibold')
            error_label.visible = False

            with ui.tab_panels(tabs, value=t_staff).classes('w-full bg-transparent').style('min-height: 200px;'):
                # --- LOGIN PERSONAL ---
                with ui.tab_panel(t_staff).classes('p-2'):
                    ui.label('Acceso para empleados del taller').classes('text-xs text-gray-500 mb-2 text-center font-medium')
                    
                    with ui.column().classes('w-full gap-2'):
                        staff_user_in = ui.input('Usuario', placeholder='Ingrese su usuario').props('outlined dense').classes('w-full').style('border-radius: 10px;')
                        staff_pass_in = ui.input('Contraseña', password=True, password_toggle_button=True, placeholder='Ingrese su contraseña').props('outlined dense').classes('w-full').style('border-radius: 10px;')

                    async def handle_staff_login():
                        db = get_db()
                        try:
                            u_val = (staff_user_in.value or '').strip()
                            p_val = staff_pass_in.value or ''
                            user = db.query(Usuario).filter_by(username=u_val, activo=True).first()
                            if user and verify_password(p_val, user.password_hash):
                                from utils.auth import _set_session
                                _set_session(user.id, user.nombre, user.rol)
                                user.ultimo_login = datetime.now()
                                db.commit()
                                ui.navigate.to('/')
                            else:
                                error_label.text = '❌ Usuario o contraseña incorrectos'
                                error_label.visible = True
                        except Exception as e:
                            if "response to the browser has already been built" not in str(e):
                                error_label.text = '⚠️ Error al conectar con el servidor'
                                error_label.visible = True
                            else:
                                ui.navigate.to('/')
                        finally: 
                            db.close()

                    
                    ui.button('🔓 Entrar al Sistema', on_click=handle_staff_login, icon='login').classes('w-full btn-sandoval h-10 text-sm font-bold shadow-xl mt-2').style('border-radius: 10px;')

                # --- LOGIN CLIENTE ---
                with ui.tab_panel(t_client).classes('p-2'):
                    ui.label('Consulte el estado de su vehículo en tiempo real').classes('text-xs text-gray-500 mb-2 text-center font-medium')
                    
                    with ui.column().classes('w-full gap-2'):
                        client_placa_in = ui.input('🚗 Placa del Vehículo', placeholder='Ej: ABC-123').props('outlined dense').classes('w-full').style('border-radius: 10px;')
                        client_pass_in = ui.input('🔑 Contraseña', password=True, password_toggle_button=True, placeholder='Su DNI o RUC').props('outlined dense').classes('w-full').style('border-radius: 10px;')
                    
                    ui.label('💡 Su contraseña inicial es su DNI o RUC').classes('text-[9px] text-blue-700 mb-1 text-center bg-blue-50 p-1.5 rounded-lg border border-blue-100 mt-1')

                    async def handle_client_login():
                        db = get_db()
                        try:
                            p_val = (client_placa_in.value or '').strip().upper()
                            pass_val = (client_pass_in.value or '').strip()
                            
                            if not p_val or not pass_val:
                                error_label.text = '⚠️ Ingrese su placa y contraseña'
                                error_label.visible = True
                                return
                            
                            v = db.query(Vehiculo).filter_by(placa=p_val).first()
                            if not v:
                                error_label.text = '❌ Placa no registrada en el sistema'
                                error_label.visible = True
                                return
                            
                            cliente = db.query(Cliente).filter_by(id=v.cliente_id).first()
                            if not cliente:
                                error_label.text = '❌ Cliente no encontrado'
                                error_label.visible = True
                                return
                            
                            # Verificar contraseña
                            pass_ok = False
                            if cliente.pin_acceso:
                                pass_ok = verify_password(pass_val, cliente.pin_acceso)
                            else:
                                pass_ok = (pass_val == cliente.id)
                            
                            if pass_ok:
                                from utils.auth import _set_session
                                _set_session(v.cliente_id, '', 'cliente', is_client=True, plate=v.placa)
                                ui.navigate.to('/')
                            else:
                                error_label.text = '❌ Contraseña incorrecta. Use su DNI/RUC como contraseña inicial.'
                                error_label.visible = True
                        except Exception as e:
                            if "response to the browser has already been built" not in str(e):
                                error_label.text = '⚠️ Error al validar datos'
                                error_label.visible = True
                            else:
                                ui.navigate.to('/')
                        finally: 
                            db.close()

                    
                    ui.button('🔓 INGRESAR AL PORTAL', on_click=handle_client_login, icon='login').classes('w-full btn-sandoval h-10 text-sm font-bold shadow-xl mt-2').style('border-radius: 10px;')

            # Ayuda expandible (más compacta)
            with ui.expansion('❓ Ayuda', icon='help_outline').classes('w-full mt-2').style(
                'background: linear-gradient(135deg, #f1f5f9, #e2e8f0);'
                'border-radius: 10px;'
                'border: 1px solid rgba(226, 232, 240, 0.8);'
            ):
                ui.html('''
                <div style="padding: 6px; color: #64748b; font-size: 9px; line-height: 1.3;">
                    <p style="margin-bottom: 4px;"><strong>👔 Personal:</strong> Usuario y contraseña asignados</p>
                    <p style="margin-bottom: 4px;"><strong>🚗 Clientes:</strong> <strong>Placa</strong> + <strong>DNI/RUC</strong></p>
                    <p style="margin-top: 6px; padding-top: 6px; border-top: 1px solid #e2e8f0;"><strong>📞</strong> +51 999 999 999</p>
                </div>
                ''')
            
            # Footer (más compacto)
            ui.html('''
            <div style="text-align: center; margin-top: 10px; padding-top: 10px; border-top: 1px solid #e2e8f0;">
                <div style="font-size: 7px; color: #94a3b8; font-weight: 600; letter-spacing: 1.5px; margin-bottom: 2px;">SANDOVAL v2.0 PRO</div>
                <div style="font-size: 6px; color: #cbd5e1; font-weight: 500;">© 2026 SANDOVAL EIRL</div>
            </div>
            ''')
