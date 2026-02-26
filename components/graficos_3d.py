"""
SANDOVAL Dashboard - Mejoras 3D para Gráficos
Estilos CSS para gráficos con efectos 3D y animaciones
"""

GRAFICOS_3D_CSS = '''
<style>
/* ═══════════════════════════════════════════════════════════════
   MEJORAS 3D PARA GRÁFICOS DE PLOTLY
   ═══════════════════════════════════════════════════════════════ */

/* Contenedor de gráficos con efecto 3D */
.plotly-graph-div {
    filter: drop-shadow(0 10px 25px rgba(39, 68, 149, 0.08));
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    border-radius: 16px;
    overflow: visible !important;
}

.plotly-graph-div:hover {
    filter: drop-shadow(0 15px 40px rgba(39, 68, 149, 0.15));
    transform: translateY(-3px) scale(1.01);
}

/* Animación de entrada para gráficos */
.plotly-graph-div {
    animation: chartFadeIn 0.8s ease-out;
}

@keyframes chartFadeIn {
    from {
        opacity: 0;
        transform: translateY(20px) scale(0.95);
    }
    to {
        opacity: 1;
        transform: translateY(0) scale(1);
    }
}

/* Mejoras para las barras de Plotly */
.plotly .bars path {
    transition: all 0.3s ease;
}

.plotly .bars path:hover {
    filter: brightness(1.1) drop-shadow(0 4px 12px currentColor);
}

/* Mejoras para pie charts */
.plotly .slice path {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1));
}

.plotly .slice path:hover {
    filter: drop-shadow(0 4px 12px rgba(39, 68, 149, 0.3)) brightness(1.05);
    transform: scale(1.02);
}

/* Mejoras para líneas de gráficos */
.plotly .scatter .point {
    transition: all 0.3s ease;
}

.plotly .scatter .point:hover {
    filter: drop-shadow(0 0 8px currentColor);
    transform: scale(1.3);
}

/* Tooltips mejorados */
.plotly .hoverlayer .hovertext {
    background: rgba(255, 255, 255, 0.98) !important;
    backdrop-filter: blur(10px);
    border: 1px solid rgba(226, 232, 240, 0.8) !important;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15) !important;
    border-radius: 12px !important;
    padding: 12px !important;
    font-family: 'Outfit', sans-serif !important;
}

.plotly .hoverlayer .hovertext path {
    fill: rgba(255, 255, 255, 0.98) !important;
    stroke: rgba(226, 232, 240, 0.8) !important;
}

/* Leyendas mejoradas */
.plotly .legend {
    filter: drop-shadow(0 2px 8px rgba(0, 0, 0, 0.05));
}

.plotly .legend .legendtoggle {
    transition: all 0.3s ease;
}

.plotly .legend .legendtoggle:hover {
    transform: scale(1.05);
}

/* Grid lines sutiles */
.plotly .gridlayer .grid line {
    stroke: #e2e8f0 !important;
    stroke-opacity: 0.6 !important;
}

/* Ejes mejorados */
.plotly .xaxis line,
.plotly .yaxis line {
    stroke: #cbd5e1 !important;
    stroke-width: 1.5 !important;
}

/* Texto de los ejes con mejor tipografía */
.plotly .xtick text,
.plotly .ytick text {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 500 !important;
    fill: #64748b !important;
}

/* Animación para hover en elementos del gráfico */
@keyframes elementPulse {
    0%, 100% {
        transform: scale(1);
        opacity: 1;
    }
    50% {
        transform: scale(1.05);
        opacity: 0.9;
    }
}

/* Cards de gráficos con glassmorphism */
.card-sandoval:has(.plotly-graph-div) {
    background: linear-gradient(135deg, rgba(255,255,255,0.98), rgba(248,250,252,0.95)) !important;
    backdrop-filter: blur(10px);
    position: relative;
    overflow: visible !important;
}

.card-sandoval:has(.plotly-graph-div)::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, #274495, #60a5fa, #274495);
    background-size: 200% 100%;
    opacity: 0;
    transition: opacity 0.4s;
    border-radius: 20px 20px 0 0;
}

.card-sandoval:has(.plotly-graph-div):hover::before {
    opacity: 1;
    animation: shimmer 2s linear infinite;
}

@keyframes shimmer {
    0% {
        background-position: -200% 0;
    }
    100% {
        background-position: 200% 0;
    }
}

/* Modebar (herramientas de Plotly) mejorado */
.plotly .modebar {
    background: rgba(255, 255, 255, 0.95) !important;
    backdrop-filter: blur(10px);
    border: 1px solid rgba(226, 232, 240, 0.8) !important;
    border-radius: 8px !important;
    padding: 4px !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05) !important;
}

.plotly .modebar-btn {
    transition: all 0.2s ease;
}

.plotly .modebar-btn:hover {
    background: rgba(39, 68, 149, 0.1) !important;
    transform: scale(1.1);
}

/* Responsive: reducir efectos en móviles */
@media (max-width: 768px) {
    .plotly-graph-div:hover {
        transform: translateY(-2px) scale(1.005);
    }
    
    .card-sandoval:has(.plotly-graph-div):hover::before {
        opacity: 0.5;
    }
}

/* Loading state para gráficos */
.plotly-graph-div.loading {
    opacity: 0.6;
    pointer-events: none;
    filter: blur(2px);
}

.plotly-graph-div.loading::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 40px;
    height: 40px;
    margin: -20px 0 0 -20px;
    border: 4px solid rgba(39, 68, 149, 0.2);
    border-top-color: #274495;
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    to {
        transform: rotate(360deg);
    }
}

/* Smooth transitions para cambios de datos */
.plotly .trace {
    transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Estilo para números grandes en anotaciones */
.plotly .annotation-text {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 800 !important;
    text-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

/* Mejoras para gráficos de dona */
.plotly .slice {
    cursor: pointer;
}

.plotly .slice:hover {
    filter: brightness(1.08);
}

/* Bordes suaves para áreas de gráficos */
.plotly .plot {
    border-radius: 12px;
}

/* Efecto brillante al cargar */
@keyframes chartShine {
    0% {
        opacity: 0;
        transform: translateX(-100%);
    }
    50% {
        opacity: 0.5;
    }
    100% {
        opacity: 0;
        transform: translateX(100%);
    }
}

.plotly-graph-div::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 50%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
    animation: chartShine 2s ease-in-out;
    pointer-events: none;
    z-index: 10;
}
</style>
'''
