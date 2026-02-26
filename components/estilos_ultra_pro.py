"""
SANDOVAL Dashboard - Estilos Ultra Profesionales
Mejoras visuales premium sin modificar funcionalidades
"""

ESTILOS_ULTRA_PROFESIONALES = '''
<style>
/* ═══════════════════════════════════════════════════════════════
   SANDOVAL DASHBOARD - ESTILOS ULTRA PROFESIONALES v3.0
   ═══════════════════════════════════════════════════════════════ */

/* ─────────────────────────────────────────────────────────────
   TABLAS MEJORADAS CON EFECTOS 3D
   ───────────────────────────────────────────────────────────── */

.q-table {
    background: rgba(255, 255, 255, 0.98) !important;
    backdrop-filter: blur(10px) !important;
    border-radius: 16px !important;
    overflow: hidden !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04) !important;
}

.q-table thead tr {
    background: linear-gradient(135deg, #f8fafc, #f1f5f9) !important;
    border-bottom: 2px solid #e2e8f0 !important;
}

.q-table thead th {
    font-weight: 700 !important;
    font-size: 0.85rem !important;
    color: #475569 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
    padding: 16px 12px !important;
}

.q-table tbody tr {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    border-bottom: 1px solid #f1f5f9 !important;
}

.q-table tbody tr:hover {
    background: linear-gradient(90deg, rgba(39, 68, 149, 0.03), transparent) !important;
    transform: translateX(4px) !important;
    box-shadow: -4px 0 0 0 #274495 inset !important;
}

.q-table tbody td {
    padding: 14px 12px !important;
    color: #64748b !important;
    font-size: 0.875rem !important;
}

/* ─────────────────────────────────────────────────────────────
   INPUTS Y FORMULARIOS PREMIUM
   ───────────────────────────────────────────────────────────── */

.q-field__control {
    border-radius: 12px !important;
    background: rgba(248, 250, 252, 0.8) !important;
    border: 1px solid #e2e8f0 !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.q-field__control:hover {
    border-color: #cbd5e1 !important;
    background: rgba(241, 245, 249, 0.9) !important;
}

.q-field--focused .q-field__control {
    border-color: #274495 !important;
    background: white !important;
    box-shadow: 0 0 0 3px rgba(39, 68, 149, 0.1) !important;
}

.q-field__label {
    color: #64748b !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
}

.q-field--focused .q-field__label {
    color: #274495 !important;
}

/* Select mejorado */
.q-select .q-field__native {
    color: #1e293b !important;
    font-weight: 500 !important;
}

/* Textarea mejorado */
.q-textarea .q-field__control {
    min-height: 100px !important;
}

/* ─────────────────────────────────────────────────────────────
   BOTONES ULTRA PREMIUM
   ───────────────────────────────────────────────────────────── */

.q-btn {
    border-radius: 12px !important;
    font-weight: 600 !important;
    letter-spacing: 0.3px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    text-transform: none !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06) !important;
}

.q-btn:not(.q-btn--flat):hover {
    transform: translateY(-2px) scale(1.02) !important;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.12) !important;
}

.q-btn:active {
    transform: translateY(0) scale(0.98) !important;
}

/* Botón primario (azul corporativo) */
.q-btn.bg-blue-900,
.q-btn[style*="background:#274495"],
.q-btn[style*="background: #274495"] {
    background: linear-gradient(135deg, #274495, #1e367a) !important;
    box-shadow: 0 4px 14px rgba(39, 68, 149, 0.3) !important;
}

.q-btn.bg-blue-900:hover,
.q-btn[style*="background:#274495"]:hover,
.q-btn[style*="background: #274495"]:hover {
    background: linear-gradient(135deg, #1e367a, #152a5e) !important;
    box-shadow: 0 8px 24px rgba(39, 68, 149, 0.4) !important;
}

/* Botón verde (éxito) */
.q-btn.bg-green-600,
.q-btn[style*="background:#059669"] {
    background: linear-gradient(135deg, #059669, #047857) !important;
    box-shadow: 0 4px 14px rgba(5, 150, 105, 0.3) !important;
}

/* Botón rojo (peligro) */
.q-btn.bg-red-600,
.q-btn[style*="background:#dc2626"] {
    background: linear-gradient(135deg, #dc2626, #b91c1c) !important;
    box-shadow: 0 4px 14px rgba(220, 38, 38, 0.3) !important;
}

/* Botón naranja (advertencia) */
.q-btn.bg-orange-500,
.q-btn[style*="background:#f59e0b"] {
    background: linear-gradient(135deg, #f59e0b, #d97706) !important;
    box-shadow: 0 4px 14px rgba(245, 158, 11, 0.3) !important;
}

/* Iconos de botones */
.q-btn .q-icon {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.q-btn:hover .q-icon {
    transform: scale(1.1) rotate(5deg) !important;
}

/* ─────────────────────────────────────────────────────────────
   BADGES Y CHIPS MODERNOS
   ───────────────────────────────────────────────────────────── */

.q-badge,
.q-chip {
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.75rem !important;
    padding: 6px 12px !important;
    letter-spacing: 0.3px !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08) !important;
    transition: all 0.3s ease !important;
}

.q-badge:hover,
.q-chip:hover {
    transform: scale(1.05) !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12) !important;
}

/* ─────────────────────────────────────────────────────────────
   MODALS Y DIALOGS PREMIUM
   ───────────────────────────────────────────────────────────── */

.q-dialog__backdrop {
    backdrop-filter: blur(8px) !important;
    background: rgba(15, 23, 42, 0.6) !important;
}

.q-card {
    border-radius: 20px !important;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2) !important;
    animation: modalSlideIn 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

@keyframes modalSlideIn {
    from {
        opacity: 0;
        transform: translateY(-30px) scale(0.95);
    }
    to {
        opacity: 1;
        transform: translateY(0) scale(1);
    }
}

.q-card__section {
    padding: 24px !important;
}

.q-card__actions {
    padding: 20px 24px !important;
    background: linear-gradient(180deg, transparent, rgba(248, 250, 252, 0.5)) !important;
}

/* ─────────────────────────────────────────────────────────────
   TABS MODERNOS
   ───────────────────────────────────────────────────────────── */

.q-tabs {
    background: linear-gradient(135deg, #f8fafc, #f1f5f9) !important;
    border-radius: 14px !important;
    padding: 6px !important;
}

.q-tab {
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.q-tab--active {
    background: white !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
    color: #274495 !important;
}

.q-tab__indicator {
    display: none !important;
}

/* ─────────────────────────────────────────────────────────────
   TOOLTIPS PREMIUM
   ───────────────────────────────────────────────────────────── */

.q-tooltip {
    background: rgba(30, 41, 59, 0.98) !important;
    backdrop-filter: blur(10px) !important;
    border-radius: 8px !important;
    padding: 8px 12px !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2) !important;
}

/* ─────────────────────────────────────────────────────────────
   PROGRESS BARS Y SPINNERS
   ───────────────────────────────────────────────────────────── */

.q-linear-progress {
    border-radius: 10px !important;
    height: 8px !important;
    overflow: hidden !important;
}

.q-linear-progress__track {
    background: #f1f5f9 !important;
}

.q-linear-progress__model {
    background: linear-gradient(90deg, #274495, #60a5fa) !important;
    box-shadow: 0 0 12px rgba(39, 68, 149, 0.4) !important;
}

.q-spinner {
    filter: drop-shadow(0 2px 8px rgba(39, 68, 149, 0.3)) !important;
}

/* ─────────────────────────────────────────────────────────────
   CHECKBOXES Y RADIO BUTTONS
   ───────────────────────────────────────────────────────────── */

.q-checkbox__inner,
.q-radio__inner {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.q-checkbox__inner:hover,
.q-radio__inner:hover {
    transform: scale(1.1) !important;
}

.q-checkbox__svg,
.q-radio__inner {
    color: #274495 !important;
}

/* ─────────────────────────────────────────────────────────────
   SEPARADORES Y DIVIDERS
   ───────────────────────────────────────────────────────────── */

.q-separator {
    background: linear-gradient(90deg, transparent, #e2e8f0, transparent) !important;
    height: 1px !important;
}

/* ─────────────────────────────────────────────────────────────
   EXPANSIONES Y ACCORDIONS
   ───────────────────────────────────────────────────────────── */

.q-expansion-item {
    background: white !important;
    border: 1px solid #f1f5f9 !important;
    border-radius: 12px !important;
    margin-bottom: 12px !important;
    transition: all 0.3s ease !important;
}

.q-expansion-item:hover {
    border-color: #e2e8f0 !important;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04) !important;
}

.q-expansion-item__container {
    border-radius: 12px !important;
}

/* ─────────────────────────────────────────────────────────────
   MEJORAS PARA ICONOS GLOBALES
   ───────────────────────────────────────────────────────────── */

.q-icon,
.material-icons {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

/* Iconos clickeables */
.q-btn .q-icon,
[onclick] .q-icon,
.cursor-pointer .q-icon {
    cursor: pointer !important;
}

.q-btn:hover .q-icon,
[onclick]:hover .q-icon,
.cursor-pointer:hover .q-icon {
    transform: scale(1.1) rotate(5deg) !important;
    filter: drop-shadow(0 2px 4px currentColor) !important;
}

/* ─────────────────────────────────────────────────────────────
   NOTIFICACIONES MEJORADAS
   ───────────────────────────────────────────────────────────── */

.q-notification {
    border-radius: 16px !important;
    backdrop-filter: blur(20px) !important;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15) !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    animation: notificationSlide 0.4s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

@keyframes notificationSlide {
    from {
        opacity: 0;
        transform: translateX(100px);
    }
    to {
        opacity: 1;
        transform: translateX(0);
    }
}

/* ─────────────────────────────────────────────────────────────
   MEJORAS PARA LISTAS
   ───────────────────────────────────────────────────────────── */

.q-list {
    padding: 8px !important;
}

.q-item {
    border-radius: 10px !important;
    transition: all 0.3s ease !important;
    margin-bottom: 4px !important;
}

.q-item:hover {
    background: rgba(39, 68, 149, 0.05) !important;
    transform: translateX(4px) !important;
}

.q-item__section--avatar {
    padding-right: 16px !important;
}

/* ─────────────────────────────────────────────────────────────
   SCROLLBAR ULTRA PREMIUM
   ───────────────────────────────────────────────────────────── */

::-webkit-scrollbar {
    width: 10px !important;
    height: 10px !important;
}

::-webkit-scrollbar-track {
    background: linear-gradient(180deg, #f8fafc, #f1f5f9) !important;
    border-radius: 10px !important;
    margin: 4px !important;
}

::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, #cbd5e1, #94a3b8) !important;
    border-radius: 10px !important;
    border: 2px solid #f8fafc !important;
    transition: all 0.3s ease !important;
}

::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(180deg, #94a3b8, #64748b) !important;
    border-color: #f1f5f9 !important;
}

/* ─────────────────────────────────────────────────────────────
   ANIMACIONES DE ENTRADA GLOBAL
   ───────────────────────────────────────────────────────────── */

.q-page {
    animation: pageEnter 0.5s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

@keyframes pageEnter {
    from {
        opacity: 0;
        transform: translateY(15px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* ─────────────────────────────────────────────────────────────
   ESTADOS HOVER PARA CARDS
   ───────────────────────────────────────────────────────────── */

.q-card:not(.no-hover):hover {
    transform: translateY(-4px) scale(1.01) !important;
}

/* ─────────────────────────────────────────────────────────────
   MEJORAS PARA FECHAS Y PICKERS
   ───────────────────────────────────────────────────────────── */

.q-date {
    border-radius: 16px !important;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1) !important;
}

.q-date__header {
    background: linear-gradient(135deg, #274495, #1e367a) !important;
}

.q-date__calendar-item--in .q-btn {
    background: #274495 !important;
}

.q-date__calendar-item--in .q-btn:hover {
    background: #1e367a !important;
}

/* ─────────────────────────────────────────────────────────────
   MEJORAS RESPONSIVAS
   ───────────────────────────────────────────────────────────── */

@media (max-width: 768px) {
    .q-table tbody tr:hover {
        transform: translateX(2px) !important;
    }
    
    .q-btn:hover {
        transform: translateY(-1px) scale(1.01) !important;
    }
}
</style>
'''
