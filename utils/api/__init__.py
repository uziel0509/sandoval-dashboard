"""utils.api package — modulos del API REST por dominio.

Refactor B-FULL del 2026-04-29: split de utils/api_service.py (3.599 LOC, 99 fns)
en 13 modulos por dominio para mejorar mantenibilidad, testing y onboarding.

ARQUITECTURA:
    common.py     — helpers compartidos (auth, json, cors)
    ratelimit.py  — state in-memory (login attempts, locks)
    tenant.py     — multi-tenancy / RLS helpers
    auth.py       — login, logout, me
    ordenes.py    — 22 endpoints CRUD orden
    cliente.py    — 11 endpoints portal cliente
    flota.py      — 14 handlers admin/cliente flota empresarial
    inventario.py — 4 endpoints
    facturas.py   — 3 endpoints mobile OCR
    notas_citas.py — 4 endpoints
    reportes.py   — 2 endpoints + dashboard
    lookup.py     — 2 endpoints CODART RUC/DNI
    push.py       — 4 endpoints VAPID
    routes.py     — register_api_routes (entry point unico)

Compatibilidad: utils/api_service.py se convierte en SHIM que re-exporta
todo desde aqui, manteniendo compat con main.py + api_extensions.py +
api_mobile_admin.py + push_api.py + rls_session.py + tests.
"""
