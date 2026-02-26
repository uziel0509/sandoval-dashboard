"""
SANDOVAL Dashboard - Portal del Cliente 3D Mejorado
Estilos y animaciones adicionales para el portal del cliente
"""

PORTAL_3D_ENHANCEMENTS = '''
<style>
/* ═══════════════════════════════════════════════════════════════
   MEJORAS 3D Y ANIMACIONES PREMIUM PARA PORTAL DEL CLIENTE
   ═══════════════════════════════════════════════════════════════ */

/* Animación de entrada para todo el portal */
.portal-wrap {
    animation: portalFadeIn 0.8s ease-out;
}

@keyframes portalFadeIn {
    from {
        opacity: 0;
        transform: translateY(30px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* Stats cards con efecto 3D hover */
.p-stat {
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
}

.p-stat::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 100%; height: 100%;
    background: linear-gradient(135deg, rgba(39, 68, 149, 0.03), transparent);
    opacity: 0;
    transition: opacity 0.3s;
}

.p-stat:hover {
    transform: translateY(-6px) scale(1.02);
    box-shadow: 
        0 20px 40px -10px rgba(39, 68, 149, 0.15),
        inset 0 0 0 2px rgba(39, 68, 149, 0.1);
}

.p-stat:hover::before {
    opacity: 1;
}

.p-stat-icon {
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.p-stat:hover .p-stat-icon {
    transform: scale(1.15) rotate(8deg);
    background: linear-gradient(135deg, var(--azul-super-claro), rgba(96, 165, 250, 0.2));
}

.p-stat-num {
    animation: numberCountUp 1s ease-out;
}

@keyframes numberCountUp {
    from {
        opacity: 0;
        transform: translateY(10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* Tracker con animaciones mejoradas */
.p-tracker {
    background: linear-gradient(135deg, rgba(255,255,255,0.95), rgba(248,250,252,0.9));
    backdrop-filter: blur(10px);
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
}

.p-tracker::before {
    content: '';
    position: absolute;
    top: -2px; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg, #274495, #60a5fa, #274495);
    background-size: 200% 100%;
    animation: trackerShine 3s linear infinite;
}

@keyframes trackerShine {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}

/* Fases con animaciones de pulso mejoradas */
.phase-circle {
    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
}

.phase-item.active .phase-circle {
    animation: pulseRing3D 2s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

@keyframes pulseRing3D {
    0%, 100% { 
        box-shadow: 
            0 4px 20px rgba(35,86,168,.45),
            0 0 0 0 rgba(35,86,168,.4);
        transform: scale(1);
    }
    50% { 
        box-shadow: 
            0 4px 28px rgba(35,86,168,.8), 
            0 0 0 10px rgba(35,86,168,.0);
        transform: scale(1.05);
    }
}

.phase-item.done .phase-circle {
    animation: checkmarkBounce 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes checkmarkBounce {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.1); }
}

/* Cards con efecto glassmorphism mejorado */
.p-card {
    background: linear-gradient(135deg, rgba(255,255,255,0.95), rgba(248,250,252,0.9));
    backdrop-filter: blur(15px);
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
}

.p-card::after {
    content: '';
    position: absolute;
    top: 0; left: -100%;
    width: 50%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
    transition: left 0.6s;
}

.p-card:hover {
    transform: translateY(-4px);
    box-shadow: 
        0 20px 40px -10px rgba(26,58,107,.18),
        inset 0 0 0 1px rgba(255,255,255,0.5);
}

.p-card:hover::after {
    left: 100%;
}

/* Service rows con animación de entrada */
.p-service-row {
    animation: slideInLeft 0.4s ease-out backwards;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.p-service-row:nth-child(1) { animation-delay: 0.1s; }
.p-service-row:nth-child(2) { animation-delay: 0.15s; }
.p-service-row:nth-child(3) { animation-delay: 0.2s; }
.p-service-row:nth-child(4) { animation-delay: 0.25s; }
.p-service-row:nth-child(5) { animation-delay: 0.3s; }

@keyframes slideInLeft {
    from {
        opacity: 0;
        transform: translateX(-30px);
    }
    to {
        opacity: 1;
        transform: translateX(0);
    }
}

.p-service-row:hover {
    transform: translateX(4px) scale(1.01);
    box-shadow: 0 4px 12px rgba(39, 68, 149, 0.1);
}

/* Iconos con rotación 3D */
.p-sr-icon {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.p-service-row:hover .p-sr-icon {
    transform: scale(1.1) rotate(10deg);
    box-shadow: 0 4px 8px rgba(39, 68, 149, 0.15);
}

/* Botones con efecto 3D premium */
.p-btn-agendar {
    position: relative;
    overflow: hidden;
    box-shadow: 0 4px 14px rgba(26,58,107,.2);
}

.p-btn-agendar::before {
    content: '';
    position: absolute;
    top: 50%; left: 50%;
    width: 0; height: 0;
    border-radius: 50%;
    background: rgba(255,255,255,0.3);
    transform: translate(-50%, -50%);
    transition: width 0.6s, height 0.6s;
}

.p-btn-agendar:hover::before {
    width: 300px;
    height: 300px;
}

.p-btn-agendar:active {
    transform: translateY(-1px) scale(0.98);
}

/* Calendar strip con hover 3D */
.p-cal-day {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    transform-style: preserve-3d;
}

.p-cal-day:hover {
    transform: translateY(-6px) rotateX(10deg);
    box-shadow: 0 8px 20px rgba(39, 68, 149, 0.15);
}

.p-cal-day.selected {
    animation: selectBounce 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes selectBounce {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.1); }
}

/* Notificaciones con slide-in */
.p-notif-item {
    animation: notifSlideIn 0.5s ease-out backwards;
}

.p-notif-item:nth-child(1) { animation-delay: 0.1s; }
.p-notif-item:nth-child(2) { animation-delay: 0.2s; }
.p-notif-item:nth-child(3) { animation-delay: 0.3s; }

@keyframes notifSlideIn {
    from {
        opacity: 0;
        transform: translateX(40px);
    }
    to {
        opacity: 1;
        transform: translateX(0);
    }
}

.p-notif-item.nueva {
    animation: notifPulse 2s ease-in-out infinite;
}

@keyframes notifPulse {
    0%, 100% { 
        box-shadow: 0 0 0 0 rgba(39, 68, 149, 0.3);
    }
    50% { 
        box-shadow: 0 0 0 8px rgba(39, 68, 149, 0);
    }
}

/* Tabla historial con hover mejorado */
.p-hist-table tbody tr {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.p-hist-table tbody tr:hover {
    transform: translateX(4px);
    box-shadow: -3px 0 0 0 var(--azul);
}

/* Badges con animación */
.p-badge {
    animation: badgeFadeIn 0.4s ease-out;
    transition: all 0.3s;
}

@keyframes badgeFadeIn {
    from {
        opacity: 0;
        transform: scale(0.8);
    }
    to {
        opacity: 1;
        transform: scale(1);
    }
}

.p-badge:hover {
    transform: scale(1.05);
}

/* Foto del vehículo con efecto zoom */
.p-vehicle-placeholder {
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.p-vehicle-placeholder:hover {
    transform: scale(1.02);
    box-shadow: 0 12px 30px rgba(39, 68, 149, 0.15);
}

/* Section titles con underline animado */
.p-section-title {
    position: relative;
}

.p-section-title::after {
    content: '';
    position: absolute;
    bottom: -8px;
    left: 0;
    width: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--azul), var(--azul-claro));
    border-radius: 3px;
    transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.p-card:hover .p-section-title::after {
    width: 60px;
}

/* Loading spinner 3D para elementos */
.loading-spinner-3d {
    display: inline-block;
    width: 20px;
    height: 20px;
    border: 3px solid rgba(39, 68, 149, 0.2);
    border-top-color: var(--azul);
    border-radius: 50%;
    animation: spin3D 1s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

@keyframes spin3D {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

/* Efecto de brillo premium para botones importantes */
.btn-premium-shine {
    position: relative;
    overflow: hidden;
}

.btn-premium-shine::after {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: linear-gradient(45deg, transparent 30%, rgba(255,255,255,0.3) 50%, transparent 70%);
    transform: rotate(45deg);
    animation: shineEffect 3s ease-in-out infinite;
}

@keyframes shineEffect {
    0%, 100% { transform: translateX(-100%) translateY(-100%) rotate(45deg); }
    50% { transform: translateX(50%) translateY(50%) rotate(45deg); }
}

/* Responsive ajustes para animaciones */
@media (max-width: 768px) {
    .p-stat:hover {
        transform: translateY(-3px) scale(1.01);
    }
    
    .p-card:hover {
        transform: translateY(-2px);
    }
}

/* Smooth scroll para toda la página */
html {
    scroll-behavior: smooth;
}

/* Animación de carga para imágenes */
img {
    animation: imgFadeIn 0.6s ease-out;
}

@keyframes imgFadeIn {
    from {
        opacity: 0;
        filter: blur(5px);
    }
    to {
        opacity: 1;
        filter: blur(0);
    }
}
</style>
'''
