"""
SANDOVAL Dashboard - Portal del Cliente Ultra Profesional v3.0
Experiencia premium para clientes del taller
"""

PORTAL_CLIENTE_PREMIUM_CSS = '''
<style>
/* ═══════════════════════════════════════════════════════════════
   PORTAL DEL CLIENTE - DISEÑO ULTRA PROFESIONAL v3.0
   ═══════════════════════════════════════════════════════════════ */

/* Hero Section Premium */
.portal-hero {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 30%, #274495 100%);
    padding: 3rem 2rem;
    border-radius: 28px;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
    box-shadow: 0 20px 60px rgba(39, 68, 149, 0.2);
    animation: heroSlideIn 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes heroSlideIn {
    from {
        opacity: 0;
        transform: translateY(-30px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.portal-hero::before {
    content: '';
    position: absolute;
    top: 0;
    right: 0;
    width: 300px;
    height: 300px;
    background: radial-gradient(circle, rgba(96, 165, 250, 0.2), transparent);
    border-radius: 50%;
    animation: heroGlow 3s ease-in-out infinite;
}

@keyframes heroGlow {
    0%, 100% { transform: scale(1); opacity: 0.5; }
    50% { transform: scale(1.2); opacity: 0.8; }
}

/* KPI Cards Mejoradas */
.portal-stat-card {
    background: rgba(255, 255, 255, 0.98);
    backdrop-filter: blur(20px);
    border-radius: 20px;
    padding: 1.5rem;
    border: 1px solid rgba(226, 232, 240, 0.6);
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
}

.portal-stat-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 4px;
    background: linear-gradient(90deg, var(--color-start), var(--color-end));
    transform: scaleX(0);
    transform-origin: left;
    transition: transform 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

.portal-stat-card:hover::before {
    transform: scaleX(1);
}

.portal-stat-card:hover {
    transform: translateY(-8px) scale(1.02);
    box-shadow: 0 20px 40px rgba(39, 68, 149, 0.12);
    border-color: rgba(39, 68, 149, 0.3);
}

.portal-stat-icon {
    width: 64px;
    height: 64px;
    border-radius: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 32px;
    margin-bottom: 1rem;
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
}

.portal-stat-card:hover .portal-stat-icon {
    transform: scale(1.1) rotate(5deg);
}

.portal-stat-icon::after {
    content: '';
    position: absolute;
    inset: -4px;
    border-radius: 20px;
    background: inherit;
    opacity: 0.3;
    filter: blur(12px);
    z-index: -1;
}

/* Tracker Mejorado */
.portal-tracker-premium {
    background: linear-gradient(135deg, rgba(255,255,255,0.98), rgba(248,250,252,0.95));
    backdrop-filter: blur(20px);
    border-radius: 24px;
    padding: 2rem;
    border: 1px solid rgba(226, 232, 240, 0.8);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.06);
    position: relative;
    overflow: visible;
    margin-bottom: 2rem;
}

.portal-tracker-premium::before {
    content: '';
    position: absolute;
    top: -2px;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, #274495, #60a5fa, #274495);
    background-size: 200% 100%;
    animation: trackerShimmer 3s linear infinite;
    border-radius: 24px 24px 0 0;
}

@keyframes trackerShimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}

/* Timeline Vertical Mejorada */
.portal-timeline {
    position: relative;
    padding-left: 3rem;
}

.portal-timeline::before {
    content: '';
    position: absolute;
    left: 1.25rem;
    top: 0;
    bottom: 0;
    width: 3px;
    background: linear-gradient(180deg, #274495, #60a5fa, #e2e8f0);
    border-radius: 10px;
}

.portal-timeline-item {
    position: relative;
    padding: 1.5rem;
    background: white;
    border-radius: 16px;
    margin-bottom: 1.5rem;
    border: 1px solid #f1f5f9;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    animation: timelineSlideIn 0.5s ease-out backwards;
}

.portal-timeline-item:nth-child(1) { animation-delay: 0.1s; }
.portal-timeline-item:nth-child(2) { animation-delay: 0.2s; }
.portal-timeline-item:nth-child(3) { animation-delay: 0.3s; }
.portal-timeline-item:nth-child(4) { animation-delay: 0.4s; }

@keyframes timelineSlideIn {
    from {
        opacity: 0;
        transform: translateX(-30px);
    }
    to {
        opacity: 1;
        transform: translateX(0);
    }
}

.portal-timeline-item:hover {
    transform: translateX(8px);
    box-shadow: 0 8px 24px rgba(39, 68, 149, 0.1);
    border-color: rgba(39, 68, 149, 0.2);
}

.portal-timeline-dot {
    position: absolute;
    left: -2.7rem;
    top: 1.5rem;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    border: 3px solid white;
    z-index: 2;
    transition: all 0.3s ease;
}

.portal-timeline-item.active .portal-timeline-dot {
    animation: dotPulse 2s ease-in-out infinite;
}

@keyframes dotPulse {
    0%, 100% { 
        box-shadow: 0 0 0 0 currentColor;
        transform: scale(1);
    }
    50% { 
        box-shadow: 0 0 0 8px transparent;
        transform: scale(1.2);
    }
}

/* Cards de Servicios Premium */
.portal-service-card {
    background: white;
    border-radius: 20px;
    padding: 1.5rem;
    border: 1px solid #f1f5f9;
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
}

.portal-service-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(39, 68, 149, 0.05), transparent);
    transition: left 0.6s;
}

.portal-service-card:hover::before {
    left: 100%;
}

.portal-service-card:hover {
    transform: translateY(-6px) scale(1.02);
    box-shadow: 0 16px 40px rgba(39, 68, 149, 0.12);
    border-color: rgba(39, 68, 149, 0.3);
}

/* Badges Animados */
.portal-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    border-radius: 12px;
    font-size: 0.875rem;
    font-weight: 700;
    letter-spacing: 0.3px;
    transition: all 0.3s ease;
    animation: badgeFloat 0.5s ease-out;
}

@keyframes badgeFloat {
    from {
        opacity: 0;
        transform: translateY(-10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.portal-badge:hover {
    transform: scale(1.08);
    box-shadow: 0 4px 12px currentColor;
}

/* Botones Premium */
.portal-btn-primary {
    background: linear-gradient(135deg, #274495, #1e367a);
    color: white;
    padding: 1rem 2rem;
    border-radius: 14px;
    font-weight: 700;
    border: none;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 8px 20px rgba(39, 68, 149, 0.3);
    position: relative;
    overflow: hidden;
}

.portal-btn-primary::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 0;
    height: 0;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.3);
    transform: translate(-50%, -50%);
    transition: width 0.6s, height 0.6s;
}

.portal-btn-primary:hover::before {
    width: 300px;
    height: 300px;
}

.portal-btn-primary:hover {
    transform: translateY(-3px) scale(1.02);
    box-shadow: 0 12px 30px rgba(39, 68, 149, 0.4);
}

.portal-btn-primary:active {
    transform: translateY(-1px) scale(0.98);
}

/* Notificaciones Premium */
.portal-notification {
    background: white;
    border-radius: 16px;
    padding: 1.25rem;
    border-left: 4px solid;
    margin-bottom: 1rem;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    animation: notifSlide 0.5s ease-out backwards;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

@keyframes notifSlide {
    from {
        opacity: 0;
        transform: translateX(40px);
    }
    to {
        opacity: 1;
        transform: translateX(0);
    }
}

.portal-notification:hover {
    transform: translateX(-4px);
    box-shadow: 0 8px 24px rgba(39, 68, 149, 0.12);
}

.portal-notification.nueva {
    animation: notifPulseGlow 2s ease-in-out infinite;
}

@keyframes notifPulseGlow {
    0%, 100% { box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06); }
    50% { box-shadow: 0 4px 20px rgba(39, 68, 149, 0.2), 0 0 0 4px rgba(39, 68, 149, 0.1); }
}

/* Tabla de Historial Mejorada */
.portal-history-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    background: white;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04);
}

.portal-history-table thead {
    background: linear-gradient(135deg, #f8fafc, #f1f5f9);
}

.portal-history-table th {
    padding: 1rem;
    text-align: left;
    font-weight: 700;
    font-size: 0.875rem;
    color: #475569;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 2px solid #e2e8f0;
}

.portal-history-table tbody tr {
    transition: all 0.3s ease;
    border-bottom: 1px solid #f1f5f9;
}

.portal-history-table tbody tr:hover {
    background: linear-gradient(90deg, rgba(39, 68, 149, 0.03), transparent);
    transform: translateX(4px);
}

.portal-history-table td {
    padding: 1rem;
    color: #64748b;
    font-size: 0.875rem;
}

/* Skeleton Loaders */
.portal-skeleton {
    background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
    background-size: 200% 100%;
    animation: skeletonWave 1.5s ease-in-out infinite;
    border-radius: 8px;
}

@keyframes skeletonWave {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}

/* Responsive Improvements */
@media (max-width: 768px) {
    .portal-hero {
        padding: 2rem 1.5rem;
    }
    
    .portal-stat-card:hover {
        transform: translateY(-4px) scale(1.01);
    }
    
    .portal-timeline {
        padding-left: 2rem;
    }
}

/* Scroll Suave */
.portal-scroll-container {
    scroll-behavior: smooth;
}

/* Animación de Entrada General */
.portal-fade-in {
    animation: portalFadeIn 0.6s ease-out;
}

@keyframes portalFadeIn {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}
</style>
'''
