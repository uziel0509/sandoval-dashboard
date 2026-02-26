"""
SANDOVAL Dashboard - Splash Screen 3D Animado
Pantalla de bienvenida profesional con animaciones 3D
"""

from nicegui import ui
import asyncio

SPLASH_CSS = '''
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@800;900&display=swap');

.splash-container {
    position: fixed;
    top: 0; left: 0;
    width: 100vw;
    height: 100vh;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #274495 100%);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    animation: splashFadeOut 0.8s ease 2.5s forwards;
}

@keyframes splashFadeOut {
    to {
        opacity: 0;
        pointer-events: none;
    }
}

.splash-logo-wrapper {
    position: relative;
    perspective: 1000px;
    margin-bottom: 40px;
}

.splash-logo {
    width: 160px;
    height: 160px;
    border-radius: 28px;
    box-shadow: 
        0 25px 60px rgba(39, 68, 149, 0.4),
        0 0 80px rgba(39, 68, 149, 0.3),
        inset 0 -5px 20px rgba(0,0,0,0.2);
    animation: logo3DFloat 2s ease-in-out infinite;
    transform-style: preserve-3d;
    border: 3px solid rgba(255,255,255,0.1);
}

@keyframes logo3DFloat {
    0%, 100% {
        transform: translateY(0) rotateY(0deg) rotateX(0deg);
    }
    25% {
        transform: translateY(-10px) rotateY(5deg) rotateX(5deg);
    }
    50% {
        transform: translateY(0) rotateY(0deg) rotateX(0deg);
    }
    75% {
        transform: translateY(-10px) rotateY(-5deg) rotateX(-5deg);
    }
}

.splash-gears {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 280px;
    height: 280px;
    pointer-events: none;
}

.gear {
    position: absolute;
    width: 80px;
    height: 80px;
    font-size: 80px;
    opacity: 0.15;
    filter: drop-shadow(0 0 20px rgba(39, 68, 149, 0.6));
}

.gear-1 {
    top: -20px;
    left: 50%;
    transform: translateX(-50%);
    animation: rotateGear 3s linear infinite;
}

.gear-2 {
    bottom: -20px;
    right: 20px;
    animation: rotateGearReverse 4s linear infinite;
}

.gear-3 {
    bottom: -20px;
    left: 20px;
    animation: rotateGear 3.5s linear infinite;
}

@keyframes rotateGear {
    from { transform: translateX(-50%) rotate(0deg); }
    to { transform: translateX(-50%) rotate(360deg); }
}

@keyframes rotateGearReverse {
    from { transform: rotate(0deg); }
    to { transform: rotate(-360deg); }
}

.splash-title {
    font-family: 'Outfit', sans-serif;
    font-size: 32px;
    font-weight: 900;
    color: white;
    text-align: center;
    margin-bottom: 8px;
    letter-spacing: -0.5px;
    text-shadow: 0 4px 20px rgba(0,0,0,0.3);
    animation: titleSlideUp 0.8s ease 0.3s both;
}

@keyframes titleSlideUp {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.splash-subtitle {
    font-size: 14px;
    font-weight: 600;
    color: rgba(255,255,255,0.7);
    text-transform: uppercase;
    letter-spacing: 3px;
    margin-bottom: 50px;
    animation: titleSlideUp 0.8s ease 0.5s both;
}

.splash-loader {
    width: 200px;
    height: 4px;
    background: rgba(255,255,255,0.1);
    border-radius: 10px;
    overflow: hidden;
    position: relative;
    animation: titleSlideUp 0.8s ease 0.7s both;
}

.splash-loader-bar {
    height: 100%;
    background: linear-gradient(90deg, #3b82f6, #274495, #60a5fa);
    background-size: 200% 100%;
    border-radius: 10px;
    animation: loaderProgress 2s ease-in-out forwards, loaderShine 1.5s ease-in-out infinite;
    box-shadow: 0 0 20px rgba(39, 68, 149, 0.8);
}

@keyframes loaderProgress {
    from { width: 0%; }
    to { width: 100%; }
}

@keyframes loaderShine {
    0%, 100% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
}

.splash-tools {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    opacity: 0.08;
    pointer-events: none;
}

.tool-icon {
    position: absolute;
    font-size: 40px;
    animation: toolFloat 20s linear infinite;
}

.tool-1 { top: 10%; left: 10%; animation-delay: 0s; }
.tool-2 { top: 20%; right: 15%; animation-delay: 2s; }
.tool-3 { bottom: 15%; left: 20%; animation-delay: 4s; }
.tool-4 { bottom: 20%; right: 10%; animation-delay: 6s; }
.tool-5 { top: 50%; left: 5%; animation-delay: 1s; }
.tool-6 { top: 50%; right: 5%; animation-delay: 3s; }

@keyframes toolFloat {
    0%, 100% {
        transform: translateY(0) rotate(0deg);
    }
    25% {
        transform: translateY(-30px) rotate(5deg);
    }
    50% {
        transform: translateY(0) rotate(0deg);
    }
    75% {
        transform: translateY(30px) rotate(-5deg);
    }
}

.splash-version {
    position: absolute;
    bottom: 30px;
    font-size: 11px;
    color: rgba(255,255,255,0.4);
    letter-spacing: 2px;
    font-weight: 600;
}
</style>
'''

def show_splash():
    """Muestra el splash screen 3D animado"""
    ui.add_head_html(SPLASH_CSS)
    
    splash = ui.element('div').classes('splash-container')
    with splash:
        # Iconos de herramientas flotantes de fondo
        tools_bg = ui.html('''
        <div class="splash-tools">
            <div class="tool-icon tool-1">🔧</div>
            <div class="tool-icon tool-2">🔩</div>
            <div class="tool-icon tool-3">⚙️</div>
            <div class="tool-icon tool-4">🛠️</div>
            <div class="tool-icon tool-5">🚗</div>
            <div class="tool-icon tool-6">🔩</div>
        </div>
        ''')
        
        # Logo wrapper con engranajes
        with ui.element('div').classes('splash-logo-wrapper'):
            # Engranajes animados
            ui.html('''
            <div class="splash-gears">
                <div class="gear gear-1">⚙️</div>
                <div class="gear gear-2">⚙️</div>
                <div class="gear gear-3">⚙️</div>
            </div>
            ''')
            
            # Logo
            ui.image('/assets/logo_sandoval.jpg').classes('splash-logo')
        
        # Título y subtítulo
        ui.html('<div class="splash-title">MECÁNICA Y REPUESTOS<br>SANDOVAL EIRL</div>')
        ui.html('<div class="splash-subtitle">Sistema Profesional de Gestión</div>')
        
        # Barra de carga
        ui.html('''
        <div class="splash-loader">
            <div class="splash-loader-bar"></div>
        </div>
        ''')
        
        # Versión
        ui.html('<div class="splash-version">v2.0 PRO · 2026</div>')
    
    # Auto-ocultar después de 3 segundos
    async def hide_splash():
        await asyncio.sleep(3)
        splash.delete()
    
    ui.timer(0.1, hide_splash, once=True)
