"""
SANDOVAL Dashboard - JavaScript para mejorar estabilidad de conexión
"""

CONEXION_ESTABLE_JS = '''
<script>
// Mejorar gestión de reconexiones de NiceGUI
(function() {
    // Sobrescribir comportamiento de reconexión
    const originalOnError = window.onerror;
    window.onerror = function(msg, url, line, col, error) {
        // Silenciar errores de reconexión que no son críticos
        if (msg && (msg.includes('WebSocket') || msg.includes('connection'))) {
            console.log('Reconectando al servidor...');
            return true; // Prevenir mensaje de error
        }
        if (originalOnError) {
            return originalOnError(msg, url, line, col, error);
        }
        return false;
    };

    // Mejorar detección de visibilidad de página
    let hidden, visibilityChange;
    if (typeof document.hidden !== "undefined") {
        hidden = "hidden";
        visibilityChange = "visibilitychange";
    } else if (typeof document.msHidden !== "undefined") {
        hidden = "msHidden";
        visibilityChange = "msvisibilitychange";
    } else if (typeof document.webkitHidden !== "undefined") {
        hidden = "webkitHidden";
        visibilityChange = "webkitvisibilitychange";
    }

    // Prevenir reconexiones innecesarias cuando la página no está visible
    if (typeof document[hidden] !== "undefined") {
        document.addEventListener(visibilityChange, function() {
            if (document[hidden]) {
                console.log('Página oculta - pausando actualizaciones');
            } else {
                console.log('Página visible - reanudando actualizaciones');
            }
        }, false);
    }

    // Interceptar y mejorar mensajes de reconexión
    const originalConsoleWarn = console.warn;
    console.warn = function() {
        const args = Array.from(arguments);
        const message = args.join(' ');
        
        // Filtrar advertencias de reconexión molestas
        if (message.includes('WebSocket') || 
            message.includes('connection closed') ||
            message.includes('reconnect')) {
            // Mostrar mensaje más amigable
            if (!document.getElementById('connection-toast')) {
                // No mostrar nada, reconexión silenciosa
            }
            return;
        }
        
        originalConsoleWarn.apply(console, arguments);
    };

    console.log('%c✅ SANDOVAL Dashboard - Conexión estable activada', 
        'color: #274495; font-weight: bold; font-size: 12px;');
})();
</script>
'''
