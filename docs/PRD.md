# PRD — SANDOVAL PRO SaaS Multi-Tenant

> **Product Requirements Document — v5.3**
> Fecha: 2026-05-02 (post hardening DB completo + auditoría 10 agentes x2 + nuevo módulo Practicantes en roadmap)
> Versión anterior: v5.2 (2026-04-29 noche, post B-FULL refactor)
> Producto: SANDOVAL PRO
> Cliente anchor: Mecánica y Repuestos Sandoval E.I.R.L. (RUC 20608755111, Sechura - Piura)

---

## 1. Visión del producto

**SANDOVAL PRO** es un SaaS multi-tenant integral diseñado para **talleres mecánicos formales en Perú**. Cubre la operación completa: recepción, diagnóstico, cotización, aprobación digital del cliente, ejecución por fases, control de inventario, generación de comprobantes y portal cliente con seguimiento.

**Diferenciadores clave**:
- ✅ **4 portales sincronizados** (Admin SPA Vue 3, PWA Staff, Cliente PC, Cliente móvil PWA)
- ✅ **Multi-tenant real** con Row-Level Security FORCE en 26 tablas
- ✅ **Tropicalización Perú**: IGV 18%, RUC/DNI, integración API CODART
- ✅ **Trigger fiscal preventivo** anti-IGV-cero
- ✅ **Argon2id** + compat layer transparente (PBKDF2/bcrypt) con rehash automático en login
- ✅ **JWT revocable** con jti + tabla blacklist + endpoint /admin/api/logout funcional
- ✅ **Cookies HttpOnly + Secure + SameSite=Lax** anti-XSS (dual-auth con Authorization header legacy para compat)
- ✅ **Pydantic v2 schemas** en endpoints críticos
- ✅ **/healthz endpoint** consistente (DB + disco + servicios)
- ✅ **125 tests automatizados** (124 passed + 1 skip por DB orden inexistente, 100% verde)
- ✅ **Refactor B-FULL aplicado**: `utils/api_service.py` (3.599 LOC) → 13 módulos en `utils/api/` + shim retrocompatible
- ✅ **Función SQL `orden_total()`** corrige 22 sitios con cálculo dinámico desde array de items
- ✅ **Trigger `trg_orden_check_cobrado`** previene sobre-cobros (cobrado > total) al INSERT/UPDATE

## 2. Audiencia objetivo

### Cliente primario (B2B)
- Talleres mecánicos formales 1-15 trabajadores en Perú
- RUC activo, factura electrónica obligatoria SUNAT
- Ingresos S/120k - S/3M anuales

### Usuarios finales (B2B2C)
- **Admin del taller**: dueño / gerente. Acceso completo (con rol estricto vía `_require_admin_strict`).
- **Staff técnico/recepción**: acceso a sus fases vía `_require_staff` (alias semántico de `_require_admin` legacy).
- **Cliente final**: dueño del vehículo. Ve estado, aprueba presupuestos, descarga facturas.
- **Conductor empresarial**: múltiples vehículos de empresa cliente.

## 3. Alcance funcional (post-V5.0)

### 3.1 Módulos productivos

| Módulo | Estado | Notas v5.0 |
|--------|--------|------------|
| Gestión clientes (RUC/DNI lookup) | ✅ Producción | Tropicalizado Perú |
| Multi-conductor por flota empresarial | ✅ Producción | Único en mercado peruano |
| Catálogo vehículos | ✅ Producción | ORM ↔ DB sincronizado |
| Órdenes de trabajo (7 fases) | ✅ Producción | + Pydantic OrdenCreatePayload |
| Cotización con firma digital | ✅ Producción | URL token público |
| PDF cotización + informe + factura | ✅ Producción | Anexa PDFs scanner OBD |
| Inventario | ✅ Producción | NUMERIC(12,2) |
| Notas de venta | ✅ Producción | + monto_pagado parcial |
| Caja diaria | ✅ Producción | 12 totales |
| Facturas proveedor con bot Telegram | ✅ Producción | Trigger preventivo IGV |
| Portal cliente (PC + móvil) | ✅ Producción | Sesión SQLite + cleanup automático |
| Bot Telegram facturas | ✅ Producción | Worker independiente (`sandoval-bot.service`) |
| Push notifications (VAPID) | ✅ Producción | Service workers PWA |
| Sistema de citas | 🟡 Schema OK, UX limitada | Roadmap Q3 |
| Trabajadores y salarios | ✅ Producción | NUMERIC migrado |
| Créditos y abonos | ✅ Producción | + Pydantic AbonoPayload |

### 3.2 Módulos de seguridad (post FASE Q+H)

| Capa | Implementación |
|------|----------------|
| Auth admin | JWT HS256 con jti UUID + blacklist `jwt_revoked` + `/admin/api/logout` funcional |
| Auth PWA/cliente | Sesión SQLite con índice `idx_sessions_expires` + cron diario cleanup 03:50 |
| Token transport | **Cookies HttpOnly + Secure + SameSite=Lax** (preferido) + Authorization header (legacy compat). Dual-auth gradual sin downtime. |
| Anti-XSS | Cookies HttpOnly = JS no puede leer token aunque haya XSS. Wrapper `window.fetch` global en 4 portales agrega `credentials: 'include'` automático |
| Logout server-side | 4 portales llaman endpoint logout antes de limpiar localStorage. Backend revoca jti + borra cookie |
| Hash contraseñas | **Argon2id** (preferido) + bcrypt + PBKDF2 (compat layer) + rehash automático en login |
| Política contraseñas | Mín 10 chars + complejidad + anti-comunes + anti-secuencias (admin/staff; PIN cliente exempt) |
| Timing attacks | `hmac.compare_digest` en TODAS rutas de verificación |
| Multi-tenancy | RLS **FORCE STRICT** (no permissive) en 26 tablas + `taller_id` desde JWT + reset GUC en `db.close()` |
| TALLER_ID config | Configurable via env `SANDOVAL_TALLER_ID` (no más hardcoded) |
| Magic-bytes uploads | `validate_upload_bytes()` en 3 endpoints (fotos, facturas, firma) |
| Headers seguridad | HSTS preload + 2 años, CSP, COOP, CORP, Referrer-Policy, Permissions-Policy, X-Permitted-Cross-Domain-Policies, X-Download-Options |
| Rate limit | nginx (login 5/m, api 60/m burst 20) + app (DB-backed admin, in-memory PWA, alertas Telegram brute-force) |
| CORS | Específico al dominio |
| Eventos seguridad | Tabla `eventos_seguridad` instrumentada + alertas Telegram |
| /healthz endpoint | Valida DB + disco + sandoval-bot |
| Backup BD | Diario 02:00 → AES-256 GPG → push a GitHub privado |
| Retención | Cron diario: evidencias >365d, PDFs >90d, backups >30d, sessions expiradas |
| Escaneo CVE | Cron diario 03:45 `pip-audit` + alerta Telegram |
| TLS | Let's Encrypt + HSTS preload (max-age 2 años) |
| SECRET_KEY | Sin fallback; RuntimeError al boot si falta o <32 chars (en `_common.py` y `super_admin_router.py`) |
| init_db | NO siembra credenciales por defecto. Requiere `BOOTSTRAP_ADMIN_PASSWORD` env |
| /open-whatsapp endpoint | Eliminado (era no-op en VPS headless) |
| debug.html / diag.html | Movidos fuera de docroot |

### 3.3 Validación entrada (Pydantic v2)
Schemas en `utils/schemas.py` para los 5 endpoints más críticos:
- `LoginPayload` (admin/staff/cliente)
- `CambioPasswordPayload`
- `AbonoPayload` (con whitelist método pago: efectivo/yape/plin/transferencia/tarjeta/credito)
- `OrdenCreatePayload` con max 200 items
- `FacturaPayload` con coherencia total = subtotal + igv (tolerancia ±0.51)
- `ClienteAprobarPayload`

### 3.4 Tests automatizados (pytest)
**28 tests pasando** en `tests/test_audit_changes.py`:
- 5 tests Argon2id + compat layer (bcrypt/PBKDF2)
- 5 tests password policy
- 7 tests upload validator (jpeg/png/pdf/php-fake/oversize/etc.)
- 5 tests Pydantic schemas
- 1 test /healthz
- 5 tests sanity (verifica fixes aplicados)

## 4. KPIs de éxito

| KPI | Meta 12 meses | Estado actual |
|-----|---------------|---------------|
| Clientes activos pagando | 30 | 1 (anchor) |
| Retención mensual | ≥ 85% | n/a |
| Uptime SLA | 99.5% | 100% últimos 30d |
| Tiempo medio orden | < 5 días | medido |
| Adopción portal cliente | ≥ 60% | medido |
| Margen operativo SaaS | ≥ 95% | (S/35 VPS / cliente Pro S/249) |
| Tests passing | 100% | **124/124 ✅** + 1 skip |
| /healthz uptime | ≥ 99% | 100% verificado |
| CVE críticos sin parchear | 0 | 0 (pip-audit hoy) |
| Score auditoría OWASP | ≥ 8.0 | **~8.7/10** post v5.2 (B-FULL refactor + post-audit fixes + 21 backups cifrados retroactivamente) |

## 5. Pricing y monetización

### Plan SaaS suscripción

| Plan | Precio S/mes | Talleres | Usuarios | Órdenes/mes | Push | Bot TG | Scanner OBD |
|------|--------------|----------|----------|-------------|------|--------|-------------|
| Básico | 149 | 1 | 3 | 200 | ❌ | ❌ | ❌ |
| Pro | 249 | 1 | ∞ | ∞ | ✅ | ✅ | ✅ |
| Multi | 449 | 3 | ∞ | ∞ | ✅ | ✅ | ✅ + manager dashboard |

### Justificación post-v5.0
Con auditoría OWASP cubierta, /healthz, tests automatizados, JWT revocable, política contraseñas, Argon2id + magic-bytes uploads + retención automática + backups GPG, ahora SE PUEDE vender a clientes corporativos exigentes (concesionarios, flotas) que pagan plan **Multi S/449/mes**.

## 6. Roadmap

### Trimestre 2 2026 (mayo-junio)
- ✅ Pydantic schemas en endpoints críticos (5 implementados; faltan ~50)
- ✅ pytest baseline (28 tests; objetivo 60% cobertura = ~150 tests)
- ✅ **Hardening DB completo (2026-04-30)**: pgaudit, pg_stat_statements, idle_session_timeout, REVOKE TRIGGER/REFERENCES, 4 triggers integridad asientos+cierres, tuning memoria
- ✅ **Backfill facturas + endpoint /flota + modales abono con fecha (2026-05-02)**: 14 asientos contables regenerados, 47 pagos retroactivos soportados
- 🆕 **MÓDULO PRACTICANTES (en diseño, fase implementación)**: gestión de practicantes pre-profesional/profesional según D.L. 1401 Perú. Tabla nueva `practicantes` + `pagos_practicantes` con RLS. Cuentas PCGE 6271/6291/4039/4151. Cumplimiento Ley 28518 + Ley 29733 PII.
- 🟡 Migrar Vue 3 CDN → Vite local (mata `unsafe-eval`)
- 🟡 Cloudflare Free (WAF + DDoS + edge cache)
- 🟡 Cookies HttpOnly reemplazando localStorage (4 portales coordinados)
- 🟡 Refactor OPCIÓN A: extraer `_consultar_codart` y prompt OCR a función pura compartida `utils/factura_ocr.py`
- 🟡 Cifrado columnas PII (totp_secret, totp_backup_codes, dni practicantes) con pgcrypto
- 🟡 Configurar GitHub backup token (RPO actual 22h sin offsite) o migrar a Backblaze B2 con Object Lock

### Trimestre 3 2026 (julio-septiembre)
- Integración PSE SUNAT (NubeFact / FACTI)
- Módulo de citas/agenda con UX completa
- 2FA TOTP para admin (cuando entre primer cliente corporativo)
- Sentry APM + Prometheus + Grafana
- Refactor `utils/api_service.py` (3546 líneas → ~5 módulos)

### Trimestre 4 2026 (octubre-diciembre)
- Marketing 100 talleres formales Lima/Trujillo/Arequipa
- Programa partner (10% recurring a contadores referidores)
- 2do destino backup (Backblaze B2 ~$1/mes)

### Año 2 (escalado)
- Pentest profesional ($1.5k-3k USD)
- SOC 2 Type II audit (cuando ARR ≥ S/100k)
- Multi-region failover

## 7. Restricciones y compliance

- Stack fijo: Python 3.12 + FastAPI + uvicorn + PostgreSQL 16 + nginx
- VPS Hostinger S/35/mes (escala a S/180/mes con >10 clientes)
- Compliance Perú: IGV 18%, RUC 11 dígitos, DNI 8 dígitos, factura electrónica SUNAT vía PSE
- LPDP D.S. 003-2013: retención automática + audit trail + delete-on-request

## 8. Riesgos y mitigación

| Riesgo | P | Imp | Mitigación |
|--------|---|-----|-----------|
| SECRET_KEY filtrada de .env.bak antiguos | Baja | Alto | Rotar SECRET_KEY ya planeado (kill-switch global) |
| Bot Telegram sin separar IGV genera deuda fiscal | Media | Bajo | Trigger DB ya bloquea inserts inválidos |
| Pentester encuentra OWASP top 10 | Baja | Alto | Auditoría OWASP cubierta + 28 tests + Tier 1+2 |
| VPS Hostinger downtime | Baja | Alto | Backup off-site cifrado + /healthz + roadmap multi-region |
| Competidor importado entra agresivo | Media | Alto | Diferenciador: tropicalización Perú + bot Telegram + portal cliente |

---

**Aprobado por:** Milton Fabio Sandoval Horna (titular)
**Auditoría técnica abril 2026:** Inicial 14 fases + Tier 1+2 + FASE Q+Q++H + Pydantic + tests
**Próxima revisión:** Q3 2026

---

## 9. Cambios v5.2 → v5.3 (consolidado)

### Hardening DB (2026-04-30)
- 4 triggers integridad: `trg_asiento_solo_anular`, `trg_asiento_lineas_inmutables`, `trg_asiento_no_delete`, `trg_cierre_caja_inmutable`
- 7 CHECK anti-negativo en `cierres_caja`
- pgaudit `log='ddl,role'` + pg_stat_statements + auto_explain
- statement_timeout=30s DB / 15s sandoval_user, idle_in_transaction=5min, idle_session_timeout=10min
- Tuning: shared_buffers=1GB, effective_cache_size=2500MB, work_mem=8MB
- REVOKE TRIGGER, REFERENCES on sandoval_user (defensa profundidad)
- 28 tablas con FORCE ROW LEVEL SECURITY (era 26)

### OCR factura mejorado (2026-04-30 → 2026-05-02)
- Lectura de RUC con `rucs_detectados[]` (lista) en lugar de single guess
- Validación checksum SUNAT algoritmo módulo 11
- Cruce CODART para confirmar y traer razón social oficial
- precio_unitario hasta 4 decimales con Decimal exacto
- Anti-injection: whitelist media_type, límite 12MB imagen, validate_upload_bytes
- Cap 3 candidatos CODART (anti-DoS)
- Lock + cap LRU 5000 en `_codart_cache`
- Endpoint admin y mobile unificados (mismo prompt + lógica)

### Frontend admin SPA
- onMounted offline-tolerant: solo logout en 401/403
- SW v2 sin fetch handler (antes atrapaba con 503 fake → cerraba sesión móvil)
- Menú items corregidos: 'libros'→'contabilidad', 'flota'→'flotas'
- Modales abono con campo fecha en 3 endpoints (orden, nota, crédito)
- Modal abono nota nuevo (reemplaza prompt() simple)
- Endpoint nuevo `/api/clientes/{cid}/flota` para Gestión Flotas
- 4 URLs duplicadas `/admin/admin/api/.../flota/` corregidas

### Backfill datos
- 13 facturas con `total=0` actualizadas desde `items_json` (marca AUDIT-2026-05-01)
- 14 asientos contables regenerados post-backfill

### Pendientes documentados (no aplicados, requieren GO)
- Logout portal cliente móvil completar 6 keys (regla 5.0 — toca login, requiere autorización)
- Push notifications `InFailedSqlTransaction` (refactor `utils/notifications.py`)
- Template literal `${escapeHTML(o.factura_sunat)}` sin evaluar en portal-cliente/pc
- Eliminar JWT de localStorage (cambio arquitectónico mayor)
- AIDE baseline desactualizado (post-deploys legítimos)
- GitHub backup token vacío

## 10. MÓDULO PRACTICANTES (especificación nueva v5.3)

### 10.1 Justificación de negocio
Sandoval EIRL recibe practicantes pre-profesionales (Mecánica, Administración) bajo convenios con institutos/universidades. La gestión actual es manual (Excel + WhatsApp). Beneficios:
- Cumplimiento legal SUNAFIL (Decreto Legislativo 1401, Ley 28518 Modalidades Formativas)
- Generación automática de planilla de practicantes para reportes mensuales
- Contabilización automática de subvención + ESSALUD (15% si supera RMV)
- Audit trail PII (Ley 29733 Datos Personales Perú)
- Alertas convenio próximo a vencer (1 mes antes)

### 10.2 Casos de uso
- Admin registra practicante con datos académicos + convenio (PDF)
- Admin asigna supervisor (trabajador del taller)
- Sistema calcula subvención mensual + ESSALUD si aplica
- Staff registra pago mensual (genera asiento contable automático)
- Sistema alerta convenios a 30 días de vencer
- Reporte mensual exportable Excel/PDF "Planilla Practicantes" para SUNAFIL
- Al vencer convenio: estado pasa a 'completado' y se emite constancia PDF

### 10.3 Modelo de datos (DDL en sección 6 del FRD)
2 tablas nuevas: `practicantes` (~25 columnas) + `pagos_practicantes` (8 columnas). Ambas con RLS forzado, CHECKs, índices. Patrón inspirado en `trabajadores` + `pagos_trabajadores` pero NO subset (régimen legal distinto).

### 10.4 KPIs del módulo
- Practicantes activos
- Subvención mensual comprometida
- Convenios próximos a vencer (30/60/90 días)
- Total pagado año actual

---

## 11. Changelog 2026-05-04 — Hardening pre-launch FASE 0+1+2

### 11.1 BLOQUEANTES resueltos
- **2FA fail-open** [`routers/auth.py:86-114`] → fail-close. Antes excepción silenciaba 2FA, atacante bypaseaba con `sub` malformado.
- **PLE-SUNAT Compras inutilizable** [`utils/pdf_libros.py` + `routers/libros.py`]: nueva función SQL `parse_fecha_text(text) RETURNS date` parsea DD/MM/YYYY y YYYY-MM-DD; reemplazo `CAST(fecha AS date)` que fallaba en facturas peruanas.
- **14 CVEs en deps** → upgrade `aiohttp 3.13.5`, `pillow 12.2.0`, `pygments 2.20.0`, `python-dotenv 1.2.2`.

### 11.2 Hardening Fase 1
- `openapi_url=None` (cerrado), `CORSMiddleware` con whitelist origins + `allow_credentials=True`.
- Pydantic V2 wireado en `/admin/api/login`, `/api/ordenes/{c}/abono`, `/api/facturas`.
- `@app.exception_handler(Exception)` global → log a `eventos_seguridad`.
- `utils/_async_helpers.py:fire_and_forget` — `ThreadPoolExecutor` acotado reemplaza `Thread(daemon=True)` en notifications/push_dispatcher/notas_citas.

### 11.3 Hardening Fase 2
- Practicantes +7 campos SUNAFIL Ley 28518 (`numero_convenio_mtpe`, `modalidad`, `subvencion_economica`, `seguro_essalud`, `poliza_seguro`, `tutor_institucion`, `plan_aprendizaje_path`) + 3 CHECKs (edad ≥16, modalidad whitelist, subvención ≥0).
- Whitelist tipada `FIELD_TYPE` en UPDATE practicantes (CAST por tipo).
- Rate limit per-endpoint: lookup_ruc/dni 30/min, factura_ocr 20/min.

### 11.4 Multi-tenancy 100% JWT
- `inventario.py:139,143` + `api_service.py:3028,3032`: stock descuento ya NO hardcoded `taller_id=1`.
- `api/ordenes.py:333` + `api_service.py:733`: UPDATE `fecha_dt` toma `taller_id` del JWT.
- `flota_audit_log` ahora con RLS forzado → **32/32 tablas críticas con RLS**.

### 11.5 Bugs ad-hoc resueltos
- BUG-012 `notifications.py:206`: `cliente_id = str(...)` fix sesiones legacy.
- BUG-017 vista Equipo: restaurada del backup `bak_p1_etB_20260429`.
- BUG-018 flota `has_conductor`: TRUE si hay nombre/DNI/teléfono OR PIN.
- Marca/Modelo vehículo: `<input>` + `<datalist>` (escritura libre).

### 11.7 Hardening ronda 3 — POST AUDITORÍA EXTERNA #2 + 3 AGENTES (2026-05-05)
2da auditoría externa de ChatGPT-5.5 + 3 agentes verificadores (backend, security, sync GitHub-vs-VPS).
- **P0 (4)**: F1 alembic migration NEUTRALIZADA (era destructiva, DROP 20+ tablas), F4 2FA setea cookie HttpOnly, F6 logout admin lee cookie también, F8 nginx 500M→50M (DoS prevention).
- **Sec-reviewer (2)**: docstring F6 corregido + cookie_name explícito, imports twofa al top + limpieza json duplicados.
- **RLS coverage 32→34**: cotizacion_items + factura_items con policy via parent FK. 9 tablas globales documentadas con `COMMENT ON TABLE`.
- **Templates**: deploy/nginx.conf VPS sincronizado (era inicial Feb-26).
- BUGs documentados: BUG-025 a BUG-029 (ver `CLAUDE.md` sección 19.5).

### 11.6 Hardening ronda 2 — POST AUDITORÍA EXTERNA (mismo día 2026-05-04)
Auditoría externa estática de ChatGPT-5.5 detectó 8 puntos críticos válidos. Aplicados:
- **A1** [`utils/api/ordenes.py:581-615`]: `api_delete_orden` NameError + IDOR fallback eliminado.
- **A2** [`utils/rls_session.py:149-180`]: middleware lee 3 cookies (sandoval_token + client_token + api_token).
- **A3** [`super_admin_router.py`]: jti UUID + rate limit 3/15min + Argon2id + revocación logout + sesiones 30 min.
- **A4** [`utils/api/common.py` + `utils/api_service.py`]: `_cors()` wildcard eliminado (compat stub no-op).
- **A5** [`.env.example`]: `DB_URL` → `DATABASE_URL`.
- **B1** [`utils/csrf.py` nuevo + `main.py:106` + `static/admin/index.html:6366`]: CSRF Double Submit Cookie + middleware ASGI.
- **B4** [`utils/api/ordenes.py:362`]: `validate_upload_bytes()` magic bytes en evidencia.
- **B5** [`routers/twofa.py:200`]: 2FA fail-attempt registrado en `rate_limit_log`.
- **B6** [`requirements.txt`]: `pip freeze` 113 paquetes pinned (vs 9 sin versiones, con `nicegui` ya eliminado).
- **C1** [`deploy/sandoval.service` + `deploy/nginx.conf`]: templates actualizados a producción real (User=sandoval+hardening systemd, HTTPS+OWASP headers).
- BUGs documentados: BUG-019 a BUG-024 (ver `CLAUDE.md` sección 18.5).
