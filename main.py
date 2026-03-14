"""
MECÁNICA Y REPUESTOS SANDOVAL EIRL - Dashboard v2.0
Sistema de Gestión de Taller Mecánico completo
NiceGUI + SQLite + Auth + Aprobación Pública
"""

from nicegui import ui, app
import sys
import traceback
import datetime
import os
from dotenv import load_dotenv
load_dotenv()

# Configurar NiceGUI para máxima estabilidad
app.config.reconnect_timeout = 60.0  # 60 segundos para reconectar

# ─── Logging ───
log_file = "sandoval_boot.txt"
if os.path.exists(log_file):
    try: os.remove(log_file)
    except: pass

def log_boot(msg):
    with open(log_file, "a", encoding='utf-8') as f:
        f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(f"[BOOT] {msg}")

log_boot("Iniciando SANDOVAL Dashboard v2.0...")

try:
    # Directorios necesarios
    for d in ['data', 'pdfs', 'backups', 'assets', 'exports']:
        os.makedirs(d, exist_ok=True)
    
    app.add_static_files('/assets', 'assets')
    app.add_static_files('/evidencia', 'static/evidencia')
    app.add_static_files('/pdfs', 'pdfs')
    log_boot("Assets registrados")
    
    # ─── Inicializar Base de Datos ───
    from utils.models import init_db, migrate_json_to_db
    init_db()
    # Pre-poblar API Key de Groq si no existe
    from utils.models import get_config, set_config
    if not get_config('groq_api_key'):
        set_config('groq_api_key', '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')
    log_boot("Base de datos SQLite inicializada")
    
    # migrate_json_to_db()
    # log_boot("Migración JSON completada")
    
    import theme
    log_boot("Theme importado")
    
    from utils.auth import get_current_user, show_login_page, logout, tiene_permiso, _set_session
    from components import (
        sidebar, clientes, proveedores, ordenes_servicio,
        inventario, metricas, vehiculos, reportes, configuracion,
        usuarios, citas, rentabilidad, notas_venta,
        facturas, asistente_ia
    )
    from pages.approval import approval_page
    from pages.reporte_entrega import reporte_entrega_page
    from pages.encuesta import encuesta_page
    from pages import portal_cliente
    log_boot("Todos los componentes importados")

    # ─── REST API para la PWA móvil ───
    from utils.api_service import register_api_routes
    register_api_routes(app)
    app.add_static_files('/app/static', 'sandoval-app')
    log_boot("API REST y PWA registrados")

    # Ruta explícita para servir la PWA (index.html)
    from starlette.responses import FileResponse
    @app.get('/app')
    @app.get('/app/')
    async def serve_pwa():
        return FileResponse('sandoval-app/index.html')

    @app.get('/app/sw.js')
    async def serve_sw():
        return FileResponse('sandoval-app/sw.js', media_type='application/javascript')

    @app.get('/app/manifest.json')
    async def serve_manifest():
        return FileResponse('sandoval-app/manifest.json', media_type='application/json')

    # ─── Abrir WhatsApp en navegador externo (compatible pywebview) ───
    @app.get('/open-whatsapp')
    def open_whatsapp(phone: str = '51999999999', msg: str = 'Hola, necesito información sobre mi vehículo'):
        import webbrowser, urllib.parse
        url = f"https://wa.me/{phone}?text={urllib.parse.quote(msg)}"
        webbrowser.open(url)
        return {'ok': True}

    # ─── Página de Login con Splash Screen ───
    @ui.page('/login')
    def login_page():
        # No redirigir a PWA, usar NiceGUI responsive
        pass
        try:
            from components.login_enhanced import show_login_enhanced
            from components.splash_screen import show_splash
            show_splash()
            show_login_enhanced()
        except ImportError:
            show_login_page()

    # ─── Página de Aprobación Pública (sin login) ───
    @ui.page('/aprobacion/{token}')
    def public_approval(token: str):
        approval_page(token)

    # ─── Reporte de Entrega Público (sin login) ───
    @ui.page('/reporte/{token}')
    def public_reporte(token: str):
        reporte_entrega_page(token)

    # ─── Encuesta de Satisfacción Pública (sin login) ───
    @ui.page('/encuesta/{token}')
    def public_encuesta(token: str):
        encuesta_page(token)

    # ─── Dashboard Principal ───
    @ui.page('/')
    def main_page():
        ui.add_head_html('''
        <script>
            (function() {
                var ua = navigator.userAgent || '';
                var isMobile = /Android|iPhone|iPad|iPod|IEMobile|Opera Mini|BlackBerry|Mobile/i.test(ua);
                if (isMobile) {
                    window.location.replace('/app/');
                }
            })();
        </script>
        ''')
        try:
            user = get_current_user()
            if not user:
                log_boot("No hay sesión -> Redirigiendo a /login")
                ui.navigate.to('/login')
                return
            
            log_boot(f"{user['nombre']} ({user['rol']}) abrió dashboard")
            _build_dashboard(user)
            
        except Exception as e:
            log_boot(f"ERROR CRITICO: {traceback.format_exc()}")
            ui.label(f"Error: {str(e)}").classes('text-red-500 text-xl font-bold')
            ui.label(traceback.format_exc()).classes('text-red-400 font-mono text-xs whitespace-pre')
    
    
    def _build_dashboard(user):
        """Construye el dashboard completo para un usuario autenticado"""
        is_client = user.get('rol') == 'cliente'
        
        drawer = theme.frame('SANDOVAL Dashboard')
        content_area = ui.column().classes('p-6 w-full gap-4')
        
        def render_content(page_name):
            log_boot(f"-> {page_name}")
            # Cerrar sidebar en móvil automáticamente al navegar
            ui.run_javascript('''
                if (window.innerWidth <= 768) {
                    var backdrop = document.querySelector(".q-drawer__backdrop");
                    if (backdrop) { backdrop.click(); }
                }
            ''')
            content_area.clear()
            try:
                if page_name == 'dashboard':
                    if is_client:
                        portal_cliente.show_portal(content_area)
                    else:
                        metricas.show_dashboard(content_area)
                elif page_name == 'portal_cliente':
                    portal_cliente.show_portal(content_area)
                elif page_name in ('clientes', 'nuevo_cliente'):
                    clientes.show_clientes(content_area)
                elif page_name == 'vehiculos':
                    vehiculos.show_vehiculos(content_area)
                elif page_name == 'proveedores':
                    proveedores.show_proveedores(content_area)
                elif page_name in ('ordenes', 'nueva_orden'):
                    ordenes_servicio.show_ordenes(content_area)
                elif page_name == 'inventario':
                    inventario.show_inventario(content_area)
                elif page_name == 'notas_venta':
                    notas_venta.show_notas_venta(content_area)
                elif page_name == 'facturas':
                    facturas.show_facturas(content_area)
                elif page_name == 'asistente_ia':
                    asistente_ia.show_asistente(content_area)
                elif page_name == 'citas':
                    citas.show_citas(content_area)
                elif page_name == 'reportes':
                    reportes.show_reportes(content_area)
                elif page_name == 'rentabilidad':
                    rentabilidad.show_rentabilidad(content_area)
                elif page_name == 'usuarios':
                    usuarios.show_usuarios(content_area)
                elif page_name == 'config':
                    configuracion.show_config(content_area)
                else:
                    with content_area:
                        ui.label(f'Módulo "{page_name}" en desarrollo...').classes('text-gray-400 text-xl')
            except Exception as e:
                log_boot(f"Error en {page_name}: {traceback.format_exc()}")
                with content_area:
                    ui.label(f"Error cargando {page_name}").classes("text-red-500 text-xl font-bold")
                    ui.label(str(e)).classes("text-red-400 font-mono text-sm")
        
        sidebar.create_sidebar(drawer, on_navigate=render_content)
        render_content('dashboard')
    
    
    # ─── Iniciar servidor ───
    log_boot("Iniciando servidor NiceGUI...")
    ui.run(
        title='SANDOVAL Dashboard',
        dark=False,
        host='0.0.0.0',
        port=3000,
        reload=False,
        show=False,
        reconnect_timeout=60.0,  # 60 segundos
        binding_refresh_interval=1.0,  # Reducir frecuencia aún más
        favicon='🚗',
        storage_secret=os.getenv('STORAGE_SECRET', 'sandoval-secret-2026-xyz'),
        viewport='width=device-width, initial-scale=1, user-scalable=yes'
    )

except Exception as e:
    log_boot(f"ERROR FATAL: {traceback.format_exc()}")
    print(f"ERROR FATAL: {e}")
    traceback.print_exc()
