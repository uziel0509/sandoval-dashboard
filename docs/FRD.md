# FRD — SANDOVAL PRO

> **Functional Requirements Document — v5.3**
> Fecha: 2026-05-02 (post hardening DB + nuevo módulo Practicantes en diseño)
> Versión anterior: v5.2 (2026-04-29 noche, post B-FULL refactor)

---

## 1. Arquitectura técnica

```
Internet (HTTPS 443)
    │
    ▼
nginx [TLS Let's Encrypt + HSTS preload (2 años) + CSP + Rate Limit + 11 Security Headers]
    │
    ├─ /admin/             → Admin SPA Vue 3 estático
    ├─ /admin/api/*        → uvicorn FastAPI [router prefix /admin]
    │                         · /admin/api/login (rate limit DB-backed)
    │                         · /admin/api/logout (revoca jti en jwt_revoked)
    │                         · /admin/api/me, clientes, ordenes, etc.
    ├─ /api/*              → FastAPI (PWA + cliente, sesión SQLite)
    │                         · /api/login (rate limit DB-backed + alertas Telegram)
    │                         · /api/cliente/*, /api/ordenes/*
    ├─ /superadmin/*       → super_admin_router (SECRET_KEY estricto, no fallback)
    ├─ /app/, /portal/*    → portales staff y cliente
    ├─ /healthz            → checks DB + disco + sandoval-bot
    ├─ /favicon.ico, /robots.txt
    │
    ▼
uvicorn (puerto 3000, 1 worker)
    │
    └─ PostgreSQL 16 (Unix socket / TCP local)
        · 36 tablas, RLS FORCE STRICT en 26
        · sandoval_user (least-privilege)
        · jwt_revoked tabla blacklist
        · eventos_seguridad audit log
    +
    └─ sandoval-bot.service (worker independiente Telegram)
```

## 2. Endpoints REST

### 2.1 API Admin (JWT con jti, prefijo `/admin/api/*`)

| Método | Path | Función | Auth |
|--------|------|---------|------|
| POST | `/admin/api/login` | Auth admin → JWT con jti UUID, exp 10h | Pública |
| GET | `/admin/api/me` | Usuario del token | JWT |
| **POST** | **`/admin/api/logout`** | **Revoca jti agregándolo a `jwt_revoked`** | JWT |
| GET/POST/PUT/DEL | `/admin/api/clientes` | CRUD clientes | JWT staff |
| GET/POST/PUT/DEL | `/admin/api/vehiculos` | CRUD vehículos + 9 cols conductor | JWT staff |
| GET/POST/PUT/DEL | `/admin/api/ordenes` | Órdenes 7 fases | JWT staff |
| POST | `/admin/api/ordenes/{id}/fotos` | Upload con `validate_upload_bytes` | JWT staff |
| GET/POST/PUT | `/admin/api/inventario` | Inventario NUMERIC(12,2) | JWT staff |
| GET/POST | `/admin/api/cotizaciones` | Cotización con firma digital | JWT staff |
| POST | `/admin/api/facturas/{id}/imagen` | Upload con magic-bytes | JWT staff |
| POST | `/admin/api/config/firma` | Firma titular con magic-bytes + PIL | JWT admin estricto |
| GET | `/admin/api/finanzas/dashboard` | KPIs operativos | JWT admin |
| GET/POST/PUT/DEL | `/admin/api/usuarios` | CRUD staff con `validate_password_strength` | JWT admin estricto |

### 2.2 API PWA + Cliente (sesión SQLite, prefijo `/api/*`)

| Método | Path | Función | Auth |
|--------|------|---------|------|
| POST | `/api/login` | Login PWA + alertas Telegram brute force | Pública |
| POST | `/api/logout` | Borra sesión SQLite | Sesión |
| POST | `/api/cliente/login` | Login cliente / conductor | Pública |
| GET | `/api/cliente/mis-ordenes` | Órdenes del cliente | Sesión |
| GET | `/api/cliente/mi-flota` | Flota empresarial | Sesión |
| POST | `/api/cliente/aprobar/{token}` | Aprobación pública por URL token | Pública |
| GET | `/api/ordenes/{id}/informe-final.pdf` | Informe + scanner OBD anexado | Sesión |
| POST | `/api/ordenes/{id}/registrar-abono` | Pago parcial con `AbonoPayload` Pydantic | Sesión staff |
| POST | `/api/cliente/cambiar-pin` | Cambio PIN cliente | Sesión cliente |
| POST | `/api/push/subscribe` | Suscripción push VAPID | Sesión |
| GET | `/api/push/vapid-key` | Public key VAPID | Pública |

### 2.3 Endpoints de monitoreo / health

| Método | Path | Función |
|--------|------|---------|
| GET | `/healthz` | DB ping + disk free + sandoval-bot status. JSON `{"ok": true, "checks": {...}}`. 503 si algo falla |

## 3. Modelo de datos

### 3.1 Tablas críticas (RLS FORCE STRICT)

```sql
talleres (id, nombre, ruc, plan, precio_mensual NUMERIC(12,2), activo, ...)
usuarios (id, taller_id, username, password_hash, rol, activo, ultimo_login)
    -- password_hash acepta: $argon2id$, $2b$, salt:hex (PBKDF2)
    -- rehash automático en cada login exitoso

clientes (id, taller_id, nombre, documento, tipo_cliente DEFAULT 'individual', ...)
vehiculos (placa, taller_id, cliente_id, conductor_*, ...)
ordenes (consecutivo PK, taller_id, cliente_id, vehiculo_placa,
         estado, monto_cobrado NUMERIC(12,2), items_cotizacion JSON, ...)

facturas (id, taller_id, proveedor, numero_factura, fecha,
          subtotal NUMERIC(12,2), igv NUMERIC(12,2), total NUMERIC(12,2),
          notas, ruc_proveedor, ...)
    -- trigger trg_facturas_igv_check bloquea mercadería con igv=0 sin justificación

notas_venta (id, taller_id, numero, fecha, cliente_id,
             subtotal/igv/total/monto_pagado NUMERIC(12,2), pagos JSON, items JSON, ...)

inventario (codigo PK, taller_id, nombre, costo NUMERIC(12,2),
            precio NUMERIC(12,2), stock, ...)

cierres_caja (12 columnas dinero NUMERIC(12,2): efectivo, yape, tarjeta, etc.)
```

### 3.2 Tablas auditoría/seguridad

```sql
eventos_seguridad (id, taller_id, tipo, severidad, ip, user_id,
                   endpoint, descripcion, payload_sanitizado, bloqueado, fecha)
    -- instrumentada Tier 2: brute_force, idor_attempt, upload_malicious,
    --   token_revocado_uso, login_admin_critico

jwt_revoked (jti PK VARCHAR(64), exp, revoked_at, user_id, reason)
    -- blacklist JWT con auto-cleanup vía función SQL

actividades  (audit log de operaciones por taller)
flota_audit_log (audit empresarial multi-conductor)
rate_limit_log  (rate limit detallado por endpoint)

sandoval_check_igv_factura()  -- función PL/pgSQL trigger preventivo IGV
cleanup_jwt_revoked()         -- limpia revocaciones expiradas

-- 11 CHECK constraints (FASE 3)
chk_facturas_subtotal_nn / chk_facturas_igv_nn / chk_facturas_total_nn
chk_nv_subtotal_nn / chk_nv_igv_nn / chk_nv_total_nn / chk_nv_monto_pagado_nn
chk_ord_monto_cobrado_nn
chk_inv_costo_nn / chk_inv_precio_nn / chk_inv_stock_nn
```

### 3.3 Pydantic schemas (validación entrada)

```python
# utils/schemas.py — Pydantic v2

class LoginPayload(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=4, max_length=128)
    @field_validator('username')
    def _normalize_username(cls, v): return v.strip().lower()

class AbonoPayload(BaseModel):
    monto: float = Field(..., gt=0, le=99_999_999.99)
    metodo_pago: str  # whitelist: efectivo/yape/plin/transferencia/tarjeta/credito
    observaciones: Optional[str] = Field(None, max_length=500)

class OrdenCreatePayload(BaseModel):
    cliente_id: str
    vehiculo_placa: str
    motivo: str = Field(..., min_length=3, max_length=500)
    items: List[OrdenItemPayload] = Field(default_factory=list, max_length=200)

class FacturaPayload(BaseModel):
    proveedor, numero_factura, fecha
    subtotal, igv, total: float = Field(..., ge=0, le=999_999.99)
    ruc_proveedor: str = Field(default='', pattern=r'^\d{11}$|^$')
    @model_validator(mode='after')
    def _coherencia_total(self):  # total = subtotal + igv ±0.51

class CambioPasswordPayload, ClienteAprobarPayload, OrdenItemPayload
```

## 4. Flujos críticos

### 4.1 Login Admin (con rehash + alertas)
1. `POST /admin/api/login` → Pydantic LoginPayload normaliza username
2. `_check_login_rate_limit(db, ip)` (DB-backed, 5/15min)
3. `verify_password(pwd, stored_hash)` — compat Argon2/bcrypt/PBKDF2-100k unificado
4. Si OK y hash es legacy → silenciosamente re-hash a Argon2id
5. Genera JWT con `jti = uuid4().hex`, exp = 10h, devuelve token
6. Si fallo → `track_login_failure(ip, username)`. 5 fallos en 15min → CRIT + Telegram alert + insert `eventos_seguridad`

### 4.2 Logout Admin (revocación real)
1. `POST /admin/api/logout` con Bearer token
2. Decodifica jti + exp (incluso si token expiró)
3. `INSERT INTO jwt_revoked (jti, exp, user_id, reason='logout')`
4. Próximo intento de uso → 401 + `track_revoked_token_use` → Telegram CRIT

### 4.3 Upload con magic-bytes
1. Cliente envía multipart/form-data
2. python-multipart 0.0.27 parsea (CVE 2024-53981 cerrado)
3. `safe_extension(filename)` filtra a whitelist
4. `validate_upload_bytes(content, ext)`: magic match (FFD8 jpeg, 89PNG, %PDF-, RIFF webp, etc.) + size ≤ 15MB
5. Si rechaza → `track_upload_rejected` → Telegram WARN
6. Guarda con `chmod 644`

### 4.4 RLS multi-tenancy
1. `TallerContextMiddleware` setea `app.taller_id` desde JWT en cada request
2. `get_db()` aplica `apply_rls_to_session()` con el ContextVar
3. PG ejecuta queries — RLS FORCE STRICT verifica `taller_id = app_current_taller()`
4. Al cerrar `db.close()` (patched) → resetea `app.taller_id = ''` antes de devolver al pool
5. **Sin fuga de contexto entre requests del pool**

### 4.5 Backup nocturno cifrado
1. 02:00 cron `sandoval_backup.sh`
2. `pg_dump | gzip` → `sandoval_YYYY-MM-DD.sql.gz`
3. `gpg --symmetric --cipher-algo AES256 --passphrase-file /root/.backup_gpg_passphrase`
4. Borra el `.sql.gz` plano
5. `git push` a repo privado GitHub `adbeel/sandoval-backups` (solo cifrado)

### 4.6 /healthz
1. `GET /healthz` — sin auth requerido
2. Verifica DB ping (`SELECT 1`)
3. Disk free GB (warn si < 1GB)
4. Estado `sandoval-bot` (systemctl is-active)
5. Retorna JSON 200 si todo OK, 503 si algo falla

## 5. Seguridad de aplicación (NFR)

| NFR | Implementación v5.0 |
|-----|---------------------|
| Auth | JWT con jti revocable + sesión SQLite |
| Token transport | **Cookies HttpOnly + Secure + SameSite=Lax** (preferido) + Authorization header (legacy compat). Dual-auth via `utils/auth_cookies.py` helpers. Wrapper global `window.fetch` en 4 portales agrega `credentials: 'include'` automático. |
| Anti-XSS tokens | Cookies HttpOnly: JS no puede leer el token aunque haya XSS injection. Localstorage compat queda como fallback durante transición. |
| Logout server-side | 4 portales llaman `/admin/api/logout` o `/api/logout` antes de limpiar localStorage. Backend revoca jti en `jwt_revoked` + envía `Set-Cookie: sandoval_token=; Max-Age=0` para borrar cookie del navegador. |
| Hash | Argon2id + compat layer (`utils/models.py:hash_password/verify_password/needs_rehash`) |
| Política contraseñas | `utils/password_policy.py` — mín 10 chars + complejidad + anti-comunes |
| Timing attacks | `hmac.compare_digest` consistente |
| Multi-tenancy | RLS FORCE STRICT + reset GUC en `db.close()` |
| Subida archivos | `utils/upload_validator.py` magic-bytes + size cap 15MB |
| Rate limit | Nginx (login 5/m, api 60/m) + DB-backed admin + alertas Telegram |
| Logs auditoría | `utils/security_events.py` instrumentada |
| Backup off-site | AES-256 GPG → GitHub privado |
| Retención | 4 crons: evidencias 365d, PDFs 90d, backups 30d, sessions exp |
| Escaneo CVE | Cron diario `pip-audit` |
| Headers HTTP | 11 headers + HSTS preload 2 años |
| TLS | Let's Encrypt auto-renew |
| CORS | Específico al dominio |
| /healthz | Endpoint público con DB+disco+bot status |
| SECRET_KEY | Estricto, sin fallback (ambos `_common.py` y `super_admin_router.py`) |
| init_db | Sin credenciales por defecto. Requiere `BOOTSTRAP_ADMIN_PASSWORD` env |

## 6. Tests automatizados

**46 tests pasando** distribuidos en 2 archivos:

`tests/test_audit_changes.py` con **28 tests**:
- TestPasswordHashing (5): Argon2id + compat layers + needs_rehash
- TestPasswordPolicy (5): min length, complexity, common, strong, cliente exempt
- TestUploadValidator (7): jpeg/png/pdf/spoofed/oversize/invalid-ext
- TestPydanticSchemas (5): login, abono, factura coherence
- TestHealthz (1): GET /healthz returns 200 with db ok
- TestSanity (5): no default creds, no SECRET_KEY fallback, no PBKDF2 260k duplicate, HSTS preload, no /open-whatsapp

`tests/test_cookies_dual_auth.py` con **18 tests** (Punto 1):
- TestAuthCookiesHelpers (3): imports OK, set_token_cookie httponly+secure+samesite, clear_token_cookie max-age=0
- TestExtractTokenDualAuth (6): header / cookie admin / cookie cliente / cookie legacy / header priority / absent
- TestFrontendsMigrated (8): wrapper inyectado y logout endpoint cableado en los 4 portales
- TestLoginEndpointReturnsCookie (1): login con creds inválidos → 401 sin Set-Cookie

## 7. Performance

| Métrica | Target | Medido |
|---------|--------|--------|
| `/admin/index.html` | < 200ms | ~10ms |
| `/admin/api/clientes` | < 300ms | ~150ms |
| `/api/cliente/mis-ordenes` | < 400ms | ~200ms |
| `/healthz` (5/5 verde) | < 100ms | ~50ms |
| Concurrent users (1 worker) | 50 | aprox |
| pytest 46 tests | < 2s | 1.87s |
| Backup full DB | < 5 min | ~30s |

## 8. Dependencias externas

| Servicio | Uso | Criticidad |
|----------|-----|------------|
| Hostinger VPS | Hosting | Alta |
| Let's Encrypt | TLS | Alta |
| GitHub privado | Off-site backup cifrado | Alta |
| API CODART | RUC/DNI lookup | Media |
| Telegram Bot API | Subir facturas + alertas seg | Media |
| python-multipart 0.0.27 | Multipart parser (CVE-2024-53981 cerrada) | Alta |
| argon2-cffi 25.1.0 | Hash Argon2id | Alta |
| pip-audit | Escaneo CVE diario | Media |

---

## 8. MÓDULO PRACTICANTES — Especificación Funcional v5.3 (NUEVO)

### 8.1 Modelo de datos
2 tablas nuevas con RLS forzado: `practicantes` (~25 cols) + `pagos_practicantes` (8 cols). DDL completo aprobado por postgres-pro disponible en `db_migrations/2026_practicantes.sql`.

**Campos principales practicantes**: id, taller_id, dni (UNIQUE por taller), apellidos, nombres, fecha_nacimiento, sexo, telefono, email, direccion, distrito, departamento, universidad_instituto, carrera, ciclo_actual, tipo_practica (preprofesional/profesional), supervisor_id (FK a trabajadores), area_asignada (mecanica/repuestos/administracion), fecha_inicio_convenio, fecha_fin_convenio, monto_subvencion_mensual, estado (activo/completado/suspendido/desvinculado), convenio_pdf_path, foto_path, observaciones, fecha_creacion, fecha_actualizacion, creado_por.

**CHECK constraints**: dni 8 dígitos, sexo M/F/X, ciclo 1-12, tipo en enum, área en enum, estado en enum, fecha_fin > fecha_inicio, subvencion >= 0, fecha_nacimiento >= 14 años atrás.

**Índices**: UNIQUE (taller_id,dni), por taller, parcial activos, vencimiento.

### 8.2 Endpoints REST (8 totales) en `routers/practicantes.py`

- GET /api/practicantes (list paginado, filtros estado/area)
- GET /api/practicantes/{id} (detalle)
- POST /api/practicantes (admin, crear)
- PUT /api/practicantes/{id} (admin, edit con audit en eventos_seguridad)
- DELETE /api/practicantes/{id} (admin, soft-delete a desvinculado)
- POST /api/practicantes/{id}/pagar (staff, registra pago + asiento contable automatico)
- DELETE /api/practicantes/pagos/{pago_id} (admin, audit)
- GET /api/practicantes/resumen (KPIs: activos, subvencion mensual, proximos a vencer)

### 8.3 Cuentas PCGE involucradas (Ley 28518 + D.L. 1401)

Asiento mensual al pagar subvencion:
- Debe 6291 (Subvenciones practicantes) por monto subvencion
- Debe 6271 (ESSALUD practicantes 15%) si aplica
- Haber 4039 (ESSALUD por pagar)
- Haber 4151 (Subvenciones por pagar)

Cancelacion al pagar:
- Debe 4151 / Debe 4039
- Haber 1041 (transferencia) o Haber 101 (efectivo)

Implementar en `utils/contabilidad_engine.py:generar_asiento_pago_practicante()`.

### 8.4 Frontend admin SPA — 7 zonas a modificar (~420 LOC)

1. menuItems agregar entry practicantes (icono school)
2. Refs setup: practicantesRows, practicantesResumen, practicantesSelected, practicantesPagos
3. loadPage bloque para 'practicantes'
4. saveModal pathMap: practicante -> /api/practicantes
5. openModal titles/icons
6. Template HTML con tabla + filtros + KPIs
7. Funciones: editarPracticante, eliminarPracticante, pagarSubvencion, verConvenioPDF

### 8.5 Validaciones y seguridad

- DNI: regex 8 digitos + rechazar 00000000/99999999
- Email validacion formato + max 100 chars
- Foto: validate_upload_bytes (jpeg/png/webp), max 5MB
- PDF convenio: validate_upload_bytes (PDF magic bytes), max 10MB
- Audit trail PII: cada UPDATE/DELETE en eventos_seguridad
- Cumplimiento Ley 29733 PII Peru

### 8.6 Plan ejecutivo de archivos

ARCHIVOS NUEVOS (4):
1. db_migrations/2026_practicantes.sql (110 LOC)
2. routers/practicantes.py (280 LOC)
3. tests/test_practicantes.py (160 LOC)
4. Funcion en utils/contabilidad_engine.py (50 LOC)

ARCHIVOS MODIFICAR (3):
5. admin_router.py (1 linea import)
6. static/admin/index.html (7 zonas, ~420 LOC)
7. tests/test_multitenant.py (1 linea)

TOTAL: ~1,021 LOC nuevas, ~3 horas implementacion + 1h testing.

### 8.7 Trampas conocidas a evitar

1. URL duplicada (bug Flotas reciente): SIEMPRE api('/api/practicantes') NO api('/admin/api/practicantes')
2. pre_deploy_check.py obligatorio antes de subir admin/index.html
3. Vue 3: toda ref expuesta en return debe estar declarada en setup
4. RLS: confiar en TallerContextMiddleware o usar _setup_flota_ctx explicito
5. tutor_id es nullable: usar LEFT JOIN no INNER JOIN
6. Soft-delete (no DELETE fisico) por retencion 5 anos Ley 29733

---

**Mantenido por:** Equipo SANDOVAL PRO + auditoría OWASP abril 2026 (multi-fase) + 10 agentes auditoría 2026-05-02 + Hardening pre-launch FASE 0+1+2 (2026-05-04 — ver CLAUDE.md sección 16+17)
**Próxima revisión:** Q3 2026

---

## Anexo cambios técnicos 2026-05-04

### Endpoints/funciones nuevas
- SQL: `parse_fecha_text(text) RETURNS date` — parser de fechas DD/MM/YYYY + ISO inmutable.
- Python: `utils/_async_helpers.py:fire_and_forget(fn, *args, **kw)` — pool acotado reemplaza Thread daemon.
- Python: `utils/api/ratelimit.py:check_endpoint_rate_limit(endpoint, ip, max_per_min)` y `enforce_endpoint_rate_limit(request, label, max_per_min)`.

### Schema DB extendido
- `practicantes` +7 cols SUNAFIL + 3 CHECKs (chk_prac_edad_min, chk_prac_modalidad, chk_prac_subvencion_pos).
- `flota_audit_log` ahora con RLS FORCE + policy `tenant_isolation`.

### Endpoints validados con Pydantic V2
- `POST /admin/api/login` → `LoginPayload`
- `POST /api/ordenes/{cons}/abono` → `AbonoPayload`
- `POST /api/facturas` → `FacturaPayload`

### Middleware nuevo
- `CORSMiddleware` con `allow_origins` explícitos (no wildcard) + `allow_credentials=True`.
- `@app.exception_handler(Exception)` — log centralizado en `eventos_seguridad`.

---

## Anexo cambios técnicos 2026-05-04 ronda 2 (post auditoría externa)

### Funciones/módulos nuevos
- `utils/csrf.py` — `CSRFMiddleware` ASGI con Double Submit Cookie + helpers `set_csrf_cookie()`, `is_exempt(path, method)`. Aplica solo cuando hay cookie de auth (Bearer puro queda exento).
- `super_admin_router.py:_is_jti_revoked(db, jti)`, `_sa_check_rate_limit(db, ip)`, `_sa_log_rate_attempt(db, ip, success, email)`, `_get_secret_legacy()`.
- `routers/twofa.py:_fail_2fa(reason, status)` — helper local que loggea fail en `rate_limit_log` antes de raise.

### Endpoints nuevos
- `POST /superadmin/api/logout` — revoca jti del super_admin actual hasta su exp natural.

### Schema DB (sin migraciones nuevas — todo aprovecha tablas existentes)
- `rate_limit_log(ip, endpoint, username, ok, ts)` — ahora también recibe entries de `/superadmin/api/login` y `2fa:{user_id}`.
- `jwt_revoked(jti, exp, revoked_at, user_id, reason)` — ahora también recibe `reason='logout_sa'` del super admin.

### Validaciones nuevas
- `validate_upload_bytes(content, ext)` aplicado a `api_orden_evidencia` (era solo content_type del cliente).
- CSRF token validation timing-safe con `hmac.compare_digest` en TODA mutación con cookie de auth.

### Frontend admin SPA actualizado
- `_getCookie(name)` + `_csrfHeaders(method)` helpers en setup().
- `api(path, opts)` envía `X-CSRF-Token` header en POST/PUT/PATCH/DELETE.
- Manejo de 403 CSRF: console.warn + reload (por si la cookie expiró).

---

## Anexo cambios técnicos 2026-05-05 (ronda 3 — auditoría externa #2)

### Migración Alembic neutralizada
- `alembic/versions/85e6c9a54657_initial_schema_2026.py`: `upgrade()` y `downgrade()` ahora son `pass`. El esquema vive en `utils/models.py:init_db()`. Header ASCII art documenta razón.

### Endpoints modificados
- `POST /admin/api/login/2fa`: ahora setea cookie HttpOnly `sandoval_token` (antes solo body `{"token": ...}`).
- `POST /admin/api/logout`: cascada `Authorization: Bearer` → cookie `sandoval_token` via `get_token_from_request(request, cookie_name=COOKIE_ADMIN_NAME)`.

### Schema DB
- `cotizacion_items`: ENABLE+FORCE RLS + policy `tenant_isolation_via_parent` (EXISTS via FK a `cotizaciones`).
- `factura_items`: ADD FK formal a `facturas` + ENABLE+FORCE RLS + misma policy.
- 9 tablas globales con `COMMENT ON TABLE` documentando por qué NO requieren RLS.

### nginx
- `client_max_body_size 500M → 50M` en `/etc/nginx/sites-enabled/sandoval`.
- Verificado live: `curl -H 'Content-Length: 60000000'` → HTTP 413 ANTES de uvicorn.

### Refactors menores
- `routers/twofa.py`: imports `JSONResponse` + `set_token_cookie` + `import json` movidos al top-level (eran 4 imports duplicados dentro de funciones).
