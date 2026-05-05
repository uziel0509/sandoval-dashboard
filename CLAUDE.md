# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Contexto global del proyecto. Léelo SIEMPRE antes de cualquier tarea.
> **Última actualización:** 2026-05-05 (madrugada — sesión maratón hardening: migración localStorage→Cookie HttpOnly en 3/4 portales, CSRF expand a 2 cookies, super_admin sin JWT en URL, nginx rate limit a TODAS las rutas login, pre_deploy_check portable, P0 audit fixes 13 agentes)

## 1. Qué es el proyecto

**SANDOVAL PRO** es un SaaS multi-tenant para talleres mecánicos en Perú. Cliente anchor: **Mecánica y Repuestos Sandoval E.I.R.L.** (Sechura, Piura — RUC 20608755111). Titular gerente: Milton Fabio Sandoval Horna.

**Dominio**: `mecánicarysandoval.com` (IDN punycode: `xn--mecnicarysandoval-8ob.com`)

## 1.1 Workspace local vs producción

Este workspace local NO ejecuta la app — el código vivo corre en el VPS Hostinger (sección 4). El árbol bajo [var/www/sandoval/](var/www/sandoval/) es un **espejo parcial/desactualizado** (tiene componentes NiceGUI legacy ya eliminados en producción). Para cualquier verificación real:

- **Leer estado actual** → `plink ... root@... "cat /var/www/sandoval/<file>"` o `pscp` para descargar.
- **Asumir que el VPS es la fuente de verdad**, no el árbol local.
- El [README.md](var/www/sandoval/README.md) describe el sistema NiceGUI v2.0 — está obsoleto, ignorarlo.

## 1.2 Comandos de uso frecuente

Todos los comandos remotos vía `plink -ssh -batch -pwfile tmp/_pwfile.txt root@187.77.62.67 "<cmd>"` (sección 4).

| Tarea | Comando |
|-------|---------|
| Reiniciar app | `systemctl restart sandoval && sleep 2 && systemctl is-active sandoval` |
| Ver errores recientes | `journalctl -u sandoval --since '20 seconds ago' \| grep -iE 'error\|exception' \| tail` |
| Smoke test prod | `curl -sk -o /dev/null -w 'HTTP %{http_code}\n' https://xn--mecnicarysandoval-8ob.com/<path>` |
| Tests pytest (en VPS) | `cd /var/www/sandoval && python -m pytest tests/ -v` (httpx contra localhost:3000, NO TestClient) |
| Test único | `python -m pytest tests/test_<file>.py::<func> -v` |
| Pre-deploy check (CRÍTICO antes de subir admin/index.html) | `python3 /var/www/sandoval/scripts/pre_deploy_check.py` |
| Validar JS local antes de subir | `node --check <archivo.js>` (extraer `<script>` del HTML primero) |
| Backup antes de deploy | `cp index.html index.html.bak_$(date +%Y%m%d_%H%M)` |
| Ver tablas DB | `sudo -u postgres psql sandoval_saas -c "\dt"` |
| Setear contexto RLS antes de query manual | `SET app.taller_id = <N>;` o `_setup_flota_ctx(db, taller_id)` en código |
| Subir archivo al VPS | `pscp -batch -pwfile tmp/_pwfile.txt <local> root@187.77.62.67:<remote>` |

## 2. Arquitectura

```
Internet ─(HTTPS 443)─> nginx ─(HTTP 3000)─> uvicorn (FastAPI) ─> PostgreSQL 16
```

- VPS: **Hostinger** — IP `187.77.62.67`, hostname `srv1434478`
- Stack: Python 3.12 + FastAPI + SQLAlchemy Core + uvicorn (NiceGUI eliminado 2026-04-24)
- DB: PostgreSQL `sandoval_saas` (user `sandoval_user`), 36 tablas, RLS forzado en 25
- Proxy: Nginx con TLS Let's Encrypt + CSP + rate limit

## 3. Los 4 portales (todos en producción)

| Portal | Path | Tecnología | Auth |
|--------|------|------------|------|
| Admin SPA PC | `/admin/index.html` | Vue 3 CDN, ~1.4MB | JWT en `/admin/api/*` |
| PWA Staff móvil | `/sandoval-app/index.html` | Vanilla JS + SW, ~922KB | sesión SQLite |
| Portal Cliente PC | `/portal-cliente/pc/index.html` | Vanilla, ~123KB, login 3D azul | sesión SQLite |
| Portal Cliente móvil | `/portal-cliente/index.html` | Vanilla + SW + manifest, ~656KB | sesión SQLite |

Las 4 apps comparten 6 keys de localStorage: `sandoval_token`, `sandoval_user`, `sandoval_client_token`, `sandoval_client_user`, `sandoval_remember`, `sandoval_remember_placa`.

## 4. Conexión al VPS (CRÍTICO)

```bash
plink -ssh -batch \
  -hostkey "ssh-ed25519 256 SHA256:u9TO1A+/O9Tp1ggp6LnJDo4f8AeZ89f7MdHXdhOoRRg" \
  -pwfile "c:/Users/Adbeel Sandoval/Desktop/proyecto fijo/tmp/_pwfile.txt" \
  root@187.77.62.67 "<COMANDO>"
```

Para subir archivos: `pscp` con los mismos flags. **NUNCA hardcodear el password** — siempre `-pwfile`.

## 5. Reglas no negociables

### ⛔ REGLA ABSOLUTA — NO TOCAR EL LOGIN SIN PERMISO EXPLÍCITO

El login de admin/cliente está **DOCUMENTADO Y FUNCIONANDO**. Cualquier cambio al login DEBE pedir permiso al usuario primero. Histórico: en 2 ocasiones se rompió por edits no autorizados (pantalla blanca, splash colgado).

**Lógica REAL del login cliente (`utils/flota.py:detect_login_role`):**

| Caso | Credencial | Rol token JWT | Vista |
|------|-----------|---------------|-------|
| Conductor con PIN custom asignado | placa + PIN custom (`conductor_pin_hash`) | `rol='conductor'` | Solo SU placa, NO aprueba cotizaciones |
| Conductor SIN PIN asignado (default) | placa + **RUC de la empresa cliente** (clientes.documento) | `rol='conductor'` (PIN inicial) | Solo SU placa, NO aprueba |
| Jefe de empresa | **cualquier placa** de su flota + PIN propio del jefe (`clientes.pin_acceso`) | `rol='cliente'` (jefe) | TODA la flota, aprueba |
| Cliente individual | placa + DNI/PIN propio | `rol='cliente'` | Solo su(s) vehículo(s) |

**NO confundir**:
- El RUC YA NO es credencial de jefe (eso fue arreglado en fix de seguridad 2026-04-26 — antes sí, ahora NO).
- El RUC SÍ sigue siendo credencial inicial del conductor, hasta que el admin le asigne un PIN custom.
- El `conductor_pin_hash = NULL` **NO BLOQUEA** el login — significa que el conductor entra con RUC.

**Login admin:**
- `/admin/api/login` con username + password (Argon2id)
- Si usuario tiene `totp_enabled=TRUE` → segundo paso `/admin/api/login/2fa` con código

**Login 3D animado** (admin SPA `static/admin/index.html`):
- Toggle Admin/Cliente: al click "Cliente" redirige a `/portal/pc/` (que ya tiene el flujo completo cliente con detección automática de rol).

**ANTES de tocar cualquier código de login**:
1. PEDIR PERMISO al usuario, exponiendo qué se cambia y por qué.
2. Probar cambios en local + `node --check` antes de subir.
3. Mantener backups antes de deployar (`cp index.html index.html.bak_$(date +%Y%m%d_%H%M)`).
4. Después de subir, hacer hard reload + curl smoke test inmediato.

### 🛡️ PROTOCOLO OBLIGATORIO PRE-DEPLOY (anti-bug login 2026-04-30)

**SIEMPRE correr el pre-deploy check ANTES de subir admin/index.html al VPS:**

```bash
python3 /var/www/sandoval/scripts/pre_deploy_check.py
# o local:
python3 "c:/Users/Adbeel Sandoval/Desktop/proyecto fijo/tmp/pre_deploy_check.py"
```

El script valida:
1. **JS sintaxis** con `node --check` (detecta `try` sin `catch`, llaves desbalanceadas, etc.)
2. **Refs en `return {}` vs declaraciones en `setup()`** — Vue silencia ReferenceError en runtime → splash colgado
3. **24 refs CRÍTICAS del login** (`loginUser`, `doLogin`, `page`, `go`, `reload`, `fmt`, `toast`, `api`, `horaActual`, etc.) deben estar declaradas

Exit code 0 = deploy aprobado. Exit code 1 = NO subir, login se colgará.

**Bug histórico bloqueado por este check** (2026-04-30): el script `restaurar_dashboard_pro.py` eliminó accidentalmente ~120 líneas del setup() incluyendo `doLogin`, `page`, `go`, `reload`. JS era sintácticamente válido (no falló `node --check`) pero Vue lanzaba ReferenceError silencioso al evaluar `return { ... }` y nunca montaba. El splash quedaba visible por horas.



### 5.1 Multi-tenancy
- Cada query que toca tabla con `taller_id` DEBE filtrar por `taller_id` del JWT, NO de constante.
- 21/22 routers usan `_tenant_id(tok)` correctamente. Solo `auth.py` usa `TALLER_ID=1` (justificado pre-token).
- RLS forzado en 25 tablas con policy `tenant_isolation USING (taller_id = app_current_taller())`.
- **ANTES de cualquier `db.query(...)`** que toque tablas con RLS: ejecutar `_setup_flota_ctx(db, taller_id)` para setear el GUC.

### 5.2 Integridad financiera
- Dinero **YA migrado a `NUMERIC(12,2)`** en `facturas`, `notas_venta`, `ordenes`, `inventario` (migración 2026-04-29).
- IGV Perú = 18%:
  - **Cuenta 4011** (IGV ventas — débito fiscal) — corregido 2026-04-30 (antes erróneo 40111).
  - **Cuenta 40111** (IGV compras — crédito fiscal).
  - Trigger `trg_facturas_igv_check` valida que IGV>0 si tipo=mercadería.
- Motor contable IGV (post 2026-04-30): si `subtotal == total` (sin desglose), trata `total` como bruto: `igv = total*18/118`. Aplica a notas y compras.
- Trigger `trg_orden_check_cobrado` previene `monto_cobrado > total` (sobre-cobro).
- Trigger `trg_doble_partida` (DEFERRABLE) valida `Σ debe = Σ haber` por asiento.
- Función SQL `orden_total(items_json)` suma items_cotizacion (array) — **NO usar `items_cotizacion->>'total'` que es NULL**.
- 15 CHECK constraints anti-negativo en columnas de dinero (incluye asiento_lineas).
- **Caja agrupa por fecha real del abono** (vía `pagos[].fecha` JSON), no por `fecha_dt` de la orden.
- 343 asientos contables retroactivos generados (75 ventas + 268 compras = S/103,834.67, debe=haber).

### 5.3 Auth dual + Cookies HttpOnly + 2FA TOTP (2026-04-30)
- `/admin/api/*` → JWT HS256 firmado con `SECRET_KEY+"_admin_v2"` (10h TTL, jti UUID + blacklist `jwt_revoked`).
- `/api/*` → sesión SQLite en `utils/sessions.db` (PWA + clientes).
- **Cookies HttpOnly + Secure + SameSite=Lax** activas en los 4 portales. Backend dual-auth: acepta cookie OR `Authorization: Bearer` legacy.
- Admin SPA usa **`credentials: 'include'` en TODOS los fetch** (5 sitios) post 2026-04-30.
- `SECRET_KEY` obligatorio en `.env` — sin fallback público.
- Hash passwords: Argon2id + compat layer (bcrypt/PBKDF2 detection) + rehash automático on login.
- **2FA TOTP (RFC 6238)** activo en `routers/twofa.py` (200 LOC):
  - `POST /admin/api/2fa/enroll` → genera secret 32 chars + QR PNG base64
  - `POST /admin/api/2fa/verify` → activa 2FA y emite 10 backup codes (sha256)
  - `POST /admin/api/2fa/disable` → desactiva (acepta TOTP code o backup)
  - `POST /admin/api/login/2fa` → paso 2 del login (`temp_token` 5 min TTL + code)
  - Tabla `usuarios` ampliada: `totp_secret`, `totp_enabled`, `totp_backup_codes` (JSON), `totp_enrolled_at`
  - Frontend: UI completa en página Configuración con QR + códigos respaldo + disable

### 5.4 Login 3D animado (2026-04-30)
- Portado del portal-cliente/pc al admin SPA. CSS `~/static/admin/index.html` líneas 184-388 (CSS) y 208-329 (HTML).
- Cubo 3D con halo + 3 anillos orbitales + sparks orbitando + logo con `transform-style: preserve-3d` rotando en X/Y.
- Animaciones: `@keyframes slLogoMove` 16s, `@keyframes slOrbitR1/R2/R3`, `@keyframes slShineMove`.
- Reloj y fecha en vivo (`horaActual`, `fechaActual`).
- Dual-pane: brand izquierda (cubo 3D + name) + form derecha (con shimmer overlay).
- Soporte `logoutMsg` para mostrar "Sesión cerrada ✓" al hacer logout.

### 5.5 Hardening seguridad (2026-04-30)
- **UFW firewall**: `default deny incoming, allow outgoing`. Solo 22/80/443 abiertos. Resto bloqueado.
- **fail2ban**: activo (SSH brute force).
- **AIDE file integrity**: baseline 52MB en `/var/lib/aide/aide.db`. Cron diario 03:30 detecta cambios.
- **pip-audit semanal**: cron lunes 03:00 corre `/usr/local/bin/sandoval_cve_scan.sh` con alerta Telegram si HIGH/CRITICAL.
- **Logout admin**: limpia las 6 keys oficiales + invalida cookie HttpOnly server-side.
- **eventos_seguridad RLS**: setea `app.taller_id=0` para tokens revocados sin contexto.

### 5.4 Logo
- `/assets/logo_sandoval_trans.png` es activo de marca — **NUNCA reemplazar** por SVG inventado.

### 5.5 Testing post-deploy
Después de cada cambio en backend:
```bash
systemctl restart sandoval && sleep 2 && systemctl is-active sandoval
journalctl -u sandoval --since '20 seconds ago' | grep -iE 'error|exception' | tail
curl -sk -o /dev/null -w 'HTTP %{http_code}\n' https://xn--mecnicarysandoval-8ob.com/<path>
```

## 6. Mapa de endpoints (para evitar confusión)

### Admin (JWT, prefijo `/admin/api/`)
- `routers/auth.py` — login admin (línea 14)
- `routers/clientes.py`, `vehiculos.py`, `ordenes.py`, etc. — CRUD admin
- `routers/finanzas.py` — dashboard, KPIs
- `routers/caja.py` — endpoint activo `/api/caja` (gana sobre `api_mobile_admin` por orden de registro)
- `routers/citas.py` — `/api/citas` retorna `cliente` (nombre concatenado), `placa`, `telefono`
- `routers/notas_venta.py` — alias `/api/notas-venta` (con guion) además de `/api/notas_venta`
- 142+ endpoints declarados

### PWA + Cliente (sesión SQLite + cookie, prefijo `/api/`)
**Estructura post B-FULL refactor (2026-04-29)**: el monolito `utils/api_service.py` (3.599 LOC) fue dividido en **13 módulos** dentro de `utils/api/`. El archivo legacy se mantiene como SHIM con funciones reusadas por `api_extensions.py`, `api_mobile_admin.py`, `push_api.py`, `rls_session.py` y tests.

```
utils/api/
├── __init__.py
├── common.py          # _get_db, _setup_flota_ctx, _check_user_session, helpers RLS
├── ratelimit.py       # _rate_limit decorator (per-IP, per-endpoint)
├── tenant.py          # _tenant_id(tok), _require_admin, _require_staff
├── auth.py            # login_pwa, logout, sessions SQLite
├── ordenes.py         # 1.113 LOC — CRUD órdenes admin + staff
├── cliente.py         # 662 LOC — endpoints portal cliente
├── flota.py           # multi-conductor empresarial
├── inventario.py      # productos, stock, alertas
├── facturas.py        # 391 LOC — CRUD facturas + bot Telegram OCR
├── notas_citas.py     # notas de venta + citas (legacy combo)
├── reportes.py        # KPIs, dashboards
├── lookup.py          # CODART proxy RUC/DNI
├── push.py            # VAPID web push subscriptions
└── routes.py          # register_api_routes(app) — registra todos los add_api_route
```

`main.py:129` → `from utils.api.routes import register_api_routes`.

**Funciones con nombres parecidos** (TRAMPA común):
- `api_ordenes_list` (admin) ≠ `api_cliente_mis_ordenes` (cliente)
- `cliente_mi_flota` (jefe) ≠ `api_cliente_mi_flota` (helper)
- `admin_listar_flota` ≠ `cliente_mi_flota`

**Endpoints muertos / shadowed** (FastAPI usa la primera ruta registrada):
- `api_mobile_admin.py:107 api_caja_get` → muerto, `routers/caja.py` lo shadowa.
- `api_mobile_admin.py` aún registra varias rutas pero la mayoría están duplicadas en `routers/`.

## 7. Bugs históricos (lecciones aprendidas)

| Bug | Causa raíz | Lección |
|-----|-----------|---------|
| Modal video al login (50min) | SyntaxError silencioso en JS por bloque huérfano `logout()` | `node --check` después de cada edit JS |
| Conductor no aparece (1h10) | Modelo SQLAlchemy `Vehiculo` sin las 9 cols `conductor_*` | Verificar `\d tabla` vs `class XXX(Base)` |
| Endpoint mis-ordenes (30min) | Apliqué fix al endpoint admin en vez del cliente | `grep "add_api_route"` antes de fixear |
| Cache navegador (40min) | SW + cache HTTP múltiples | Cache-bust con `?v=mtime` dinámico |
| Subida firma 500 | `PermissionError` directorio root, no `sandoval` | `chown sandoval` + `chmod 644` en uploads |
| Pantalla blanca admin SPA | Variable expuesta en `return` Vue3 sin definir en `setup()` | Verificar TODA variable del return existe |
| Botón firma no abría selector | `@click="document.getElementById(...)"` inline en Vue3 | Definir función nombrada y exponerla, NO `document.X` inline |
| `@change="X()"` sin `$event` | Vue3 pasa undefined como event | Siempre `@change="X($event)"` |

## 7b. Anti-patterns Vue 3 críticos (causa pantalla blanca)

1. **Variable en return sin definir en setup**: `return { miFn }` cuando `miFn` no existe → ReferenceError → Vue no monta → pantalla blanca.
2. **`document.getElementById(...)` inline en `@click`**: Vue 3 lo evalúa como reactive expression. Solución: función nombrada en setup.
3. **`@change="fn()"` sin `$event`**: el handler recibe undefined. Usar `@change="fn($event)"`.
4. **Bloque JS huérfano dentro de `<script>` inline**: SyntaxError no se ve hasta que ejecuta. Validar con `node --check` extrayendo el script.
5. **`v-html` con datos sin sanitizar**: XSS. Sanitizar antes con escapeHtml.
6. **Mutation en computed**: `computed(() => { x.value = y })` rompe reactividad.
7. **`v-for` sin `:key`**: rerenders incorrectos con datos similares.

## 8. Estructura del repo (post B-FULL)

```
/var/www/sandoval/
├── main.py                   # uvicorn entry, TallerContextMiddleware setea app.taller_id GUC
├── routers/                  # 22 routers admin (JWT) — auth, clientes, vehiculos, ordenes,
│                             #   caja, citas, finanzas, gastos, inventario, notas_venta, etc.
├── utils/
│   ├── api/                  # 13 módulos refactor B-FULL (PWA/cliente endpoints)
│   │   ├── routes.py         # register_api_routes() entrypoint
│   │   ├── common.py, ratelimit.py, tenant.py, auth.py
│   │   ├── ordenes.py, cliente.py, flota.py, inventario.py
│   │   ├── facturas.py, notas_citas.py, reportes.py, lookup.py, push.py
│   ├── api_service.py        # SHIM legacy — funciones reusadas por api_extensions, api_mobile_admin
│   ├── api_extensions.py     # CRUDs adicionales legacy
│   ├── api_mobile_admin.py   # endpoints staff móvil (algunos shadoweados por routers/)
│   ├── push_api.py           # subscribe/unsubscribe push
│   ├── rls_session.py        # context manager RLS por request
│   ├── models.py             # SQLAlchemy ORM (verificar \d tabla vs class antes de usar getattr)
│   ├── pdf_generator.py      # PDFs cotización + helper _firma_block
│   ├── pdf_informe_orden.py  # informe completo orden
│   ├── pdf_cotizacion.py     # cotización standalone
│   ├── pdf_libros.py         # NUEVO — libros contables PLE-SUNAT
│   ├── contabilidad_engine.py # NUEVO — auto-genera asientos desde órdenes/notas/gastos
│   ├── flota.py              # multi-conductor empresarial
│   ├── notifications.py      # push VAPID + helpers cross-portal
│   └── telegram_bot.py       # bot 1 (OCR facturas)
├── pages/approval.py         # HTML aprobación pública
├── static/admin/             # admin SPA Vue 3 (~1.4MB)
├── sandoval-app/             # PWA staff (~922KB) + sw.js
├── portal-cliente/           # portal cliente móvil + sw.js + manifest
├── portal-cliente/pc/        # portal cliente PC + sw.js
├── assets/                   # logo, firma, fonts, sounds (notify.mp3)
├── tests/                    # pytest 125 tests (124 pass + 1 skip) — httpx contra localhost:3000
├── docs/                     # PRD/FRD/BRD v5.2
└── backups/                  # SQL diarios cifrados AES-256 GPG (7 días retención + 21 históricos)
```

### Refactor B-FULL (2026-04-29)
- `utils/api_service.py` 3.599 LOC → 13 módulos (4.219 LOC distribuidos)
- 22 sitios `items_cotizacion->>'total'` rotos → función SQL `orden_total()` + reemplazo
- 12 IDOR endpoints sweep (filtros `taller_id` explícitos en queries problemáticas)
- 125 tests pytest (era 49)
- Backups cifrados AES-256 + 21 históricos cifrados retroactivamente
- Trigger preventivo sobre-cobro

## 9. Cuándo usar cada agente especializado

- `sandoval-backend-engineer` → cambios en routers/, utils/api/, models, mapping de endpoints, RLS
- `sandoval-frontend-engineer` → los 4 portales, cache busting, validación JS Vue 3
- `sandoval-finance-auditor` → cualquier cosa con dinero (IGV, totales, cuadre, sobre-cobros)
- `sandoval-contador-experto` → módulo libros contables, asientos PCGE, declaraciones SUNAT, normas tributarias Perú
- `sandoval-sync-guardian` → bugs que tocan múltiples portales, sincronización de datos, push notifications
- `sandoval-bug-watcher` → análisis proactivo de logs/errores (NO bug específico, sino sweep general)
- `sandoval-deploy-tester` → validar que un fix funciona en el VPS real (curl + journalctl)
- `security-auditor` (genérico) → audit completo OWASP
- `security-reviewer` (genérico) → revisar código nuevo de auth/input

## 10. File-locks (anti-conflictos)

`~/.claude/team_locks.json` registra qué archivo está siendo editado por qué agente. ANTES de editar un archivo, el agente declara su intención. Si hay lock, espera o pide reasignación al team-lead.

## 11. 🛡️ MODO READ-ONLY para auditorías (REGLAS DE SEGURIDAD)

Cuando el team-lead invoca a un agente con la frase **"AUDITORÍA READ-ONLY"** o **"NO MODIFIQUES NADA"**, el agente DEBE seguir estas reglas SIN excepción:

### ✅ PERMITIDO en READ-ONLY

- Conectar al VPS con `plink -ssh -batch` (read commands solamente)
- Descargar archivos con `pscp` para análisis local
- Ejecutar `grep`, `cat` (limitado), `wc`, `ls`, `find` sobre rutas del proyecto
- Queries SQL `SELECT`, `\d`, `\dt`, `\df` en PostgreSQL
- `journalctl` con `--no-pager` para leer logs
- `curl -s -I` para HEAD requests
- `curl -s -o /dev/null -w '%{http_code}'` para smoke tests sin auth
- `systemctl status`, `systemctl is-active` (status only)
- `nginx -t` (test config sin reload)

### ❌ PROHIBIDO en READ-ONLY

- Cualquier `UPDATE`, `INSERT`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER` en DB
- Cualquier `Edit`, `Write` sobre archivos del VPS
- `systemctl restart/stop/start` cualquier servicio
- `chmod`, `chown`, `mv`, `rm`, `cp` sobre archivos en producción
- Leer credenciales: `/etc/shadow`, `/etc/passwd`, `/var/www/sandoval/.env`
- Leer `password_hash` de usuarios via SELECT
- Modificar `nginx.conf`, `settings.json`, archivos `.env`
- Cualquier comando que liste secretos (tokens, API keys, JWT secrets)

### 🛑 REGLA DE ESCALADO

Si el agente identifica un bug que requiere fix urgente durante audit READ-ONLY:
1. **NO aplica el fix**
2. Reporta al team-lead el bug con: archivo:línea, evidencia, fix sugerido
3. Espera autorización explícita del usuario antes de salir de READ-ONLY

### 🔐 Permisos a nivel sandbox (`~/.claude/settings.json`)

`permissions.allow` permite SSH/SCP al VPS específico `187.77.62.67`. `permissions.deny` bloquea comandos destructivos (DROP, TRUNCATE, rm -rf, leer .env, leer password_hash, stop services, etc.). Si un comando es bloqueado, el agente DEBE:
- NO bypassear la denegación
- Reportar al team-lead qué comando intentaba
- Esperar instrucción

## 12. Módulos nuevos en construcción (2026-04-29)

### 12.1 Libros Contables (sandoval-contador-experto)
- Tablas: `plan_cuentas` (PCGE Perú), `asientos_contables`, `asiento_lineas`
- Endpoints: `/admin/api/libros/{diario,mayor,inventario,ventas,compras,caja-bancos}`
- Engine: `utils/contabilidad_engine.py` auto-genera asientos desde órdenes cobradas, notas de venta, gastos, facturas
- PDF: `utils/pdf_libros.py` formato PLE-SUNAT (TXT con pipes para SIRE)
- Frontend: nueva sección en admin SPA "Contabilidad" con tabs: Plan de Cuentas, Asientos, Reportes

### 12.2 Push Notifications expandidas
- Helpers en `utils/notifications.py` (cada uno escribe a `notificaciones_push` + envía VAPID a subs):
  - `notify_admin_nueva_cita(cita_id)` → admin móvil + PC al agendar cliente
  - `notify_admin_orden_pendiente_aprobacion(orden_id)` → admin tras enviar cotización
  - `notify_admin_resumen_dia(taller_id)` → cron 20:00 con totales de caja
  - `notify_cliente_fase_avanzada(orden_id, fase)` → cliente al pasar de fase
  - `notify_cliente_aprobacion_requerida(orden_id)` → cliente cuando hay cotización lista
  - `notify_cliente_listo_entrega(orden_id)` → cliente al pasar a fase ENTREGA
- Cron job: `utils/cron_push.py` corre `notify_admin_resumen_dia` a las 20:00 hora Lima
- Sonido: SW postMessage a página activa → `new Audio('/assets/sounds/notify.mp3').play()`. Asset en `/assets/sounds/notify.mp3`.
- Service Workers: 4 SWs (PWA staff, cliente móvil, **cliente PC pendiente**, **admin SPA pendiente**) — todos manejan `push` event con sonido + vibración.
- Schema unificado payload: `{title, body, icon, badge, tag, url, sound, data:{type, entity_id}}`.

## 13. Bug-trampas conocidas (NO repetir)

| Trampa | Síntoma | Fix |
|--------|---------|-----|
| `items_cotizacion->>'total'` siempre NULL | Total caja S/0 cuando hay órdenes | Es array, no objeto. Usar función SQL `orden_total(items_json)` |
| Endpoint duplicado en `routers/` y `utils/api_mobile_admin.py` | Bug "fixeado" persiste | FastAPI usa la PRIMERA registrada. Borrar duplicado en api_mobile_admin |
| `add_api_route()` registrado pero ruta no responde | 404 a pesar de existir función | Verificar orden de `app.include_router` vs `register_api_routes` en main.py |
| `fase_data` columna que no existe | 500 al abrir orden | La col fue eliminada — usar `notas_orden` |
| Caja S/0 cuando NO hay movimientos hoy | Usuario reporta "bug" | NO es bug — mostrar fecha último movimiento en empty state |
| Service Worker cacheaba CSP viejo | Tests CSP fallan en navegador | Usuario debe `unregister SW` + hard reload, o bumpear `?v=` |
| TestClient FastAPI vs httpx | Tests fallan por SQLite local fallback | Usar httpx contra `http://localhost:3000` (servicio real con PG) |
| RLS bloquea silenciosamente | Query devuelve 0 filas inesperadas | `SET app.taller_id = X` antes de query, o usar `_setup_flota_ctx(db, taller_id)` |
| Caja muestra S/0 pero hubo cobro hoy | Usuario reporta "bug cobro" | Caja agrupa por `pagos[].fecha` (real del abono). Si abono del 29 con orden creada el 28 → cuenta en 29 ✓ |
| IGV ventas en cuenta 40111 (compras) | Declaración SUNAT mal | Usar `C_IGV_VENTA = "4011"` (no 40111). Fix 2026-04-30 |
| Notas con `subtotal == total` desbalancea asiento | "ValueError: Asiento desbalanceado" | Si subtotal=total, motor trata `total` como bruto: `igv = total*18/118`. Aplica también a compras |
| `sessions.db` propiedad de root | Login PWA/cliente roto silencioso | `chown sandoval:sandoval /var/www/sandoval/utils/sessions.db` |
| Inyectar `<script>` en template literal JS | Vue no monta, splash colgado | El parser HTML cierra al ver `</script>` literal aunque esté dentro de string. Escapar `<\/script>` o poner el script real ANTES/DESPUÉS del template literal |

## 14. Seguridad endurecida (2026-04-30)

### 14.1 Capas activas
1. **UFW firewall** (kernel): solo 22/80/443
2. **fail2ban** (capa SSH brute force)
3. **nginx rate limit** (5 req/min login, 60 req/min API)
4. **App rate limit DB** (`rate_limit_log`, max 5 fails/15min por IP)
5. **JWT revocable** (jti UUID + tabla `jwt_revoked`)
6. **2FA TOTP** activable por usuario (Google Authenticator/Authy)
7. **Cookies HttpOnly** + Secure + SameSite=Lax (anti-XSS y anti-CSRF)
8. **CSP** completa con whitelist de CDNs
9. **8 OWASP headers** (HSTS preload, X-Frame, COOP, CORP, etc.)
10. **systemd hardening** (User=sandoval, ProtectSystem=strict, etc.)
11. **AIDE file integrity** (cron 03:30 alerta Telegram)
12. **pip-audit semanal** (cron lunes 03:00 alerta CVEs HIGH/CRITICAL)
13. **Argon2id** + rehash automático (compat bcrypt/PBKDF2)
14. **RLS forzado** en 28 tablas
15. **Backups AES-256 GPG** diarios + 30 días retención

### 14.2 Acciones pendientes del usuario titular
- [ ] Mover `/root/.backup_gpg_passphrase` a USB offline + KeePassXC (single point of failure)
- [ ] Activar 2FA personal: Configuración → Activar 2FA → escanear QR con Google Authenticator
- [ ] Decidir Cloudflare Pro WAF ($20/mes) cuando se llegue a 5+ clientes

## 15. 📚 Catálogo de bugs históricos resueltos (consultar SIEMPRE antes de debuggear)

> Cada bug encontrado y arreglado se documenta aquí con: **síntoma exacto que vio el usuario**, **causa raíz técnica**, **fix con código real**, **archivo:línea**. Si vuelve a pasar algo similar, busca el síntoma en este catálogo ANTES de empezar de cero.

### BUG-001 — Imágenes de factura no se renderizan (mostrar icono roto)
- **Síntoma**: usuario sube foto de factura, el modal muestra "Click para ver imagen completa" como texto. Al abrir la imagen en URL directa, navegador muestra icono de imagen rota incluso en incógnito.
- **Síntomas falsos** (lo que aparenta pero NO es): cache del navegador, permisos del archivo, Service Worker.
- **Verificación rápida**:
  ```bash
  plink ... root@... "xxd /var/www/sandoval/static/facturas/<archivo>.jpg | head -1"
  ```
  Si NO empieza con `ffd8 ffe0` → archivo corrupto. Si empieza con `75ab 5a8a 66a0 7bf8 e97a 06da b1ee b8ff` → bug confirmado de prefijo basura.
- **Causa raíz**: el frontend mobile usa `canvas.toDataURL('image/jpeg')` que retorna `data:image/jpeg;base64,/9j/...`. El backend hacía `_b64.b64decode(body['imagen_base64'])` con el string COMPLETO incluyendo el prefijo `data:image/jpeg;base64,`. Python `b64decode` es permisivo y produce ~15 bytes basura prefijados al JPEG real.
- **Fix archivos existentes** (strip 15 bytes prefijados):
  ```bash
  cd /var/www/sandoval/static/facturas
  for F in factura_m_*.jpg; do
    if [ "$(head -c 2 "$F" | xxd -p)" != 'ffd8' ]; then
      OFFSET=$(head -c 32 "$F" | xxd -p -c 1 | nl -ba | awk '/ff/{f=NR; getline; if($2=="d8") {print f-1; exit}}')
      [ -n "$OFFSET" ] && [ "$OFFSET" -gt 0 ] && dd if="$F" of="$F.tmp" bs=1 skip=$OFFSET status=none && mv "$F.tmp" "$F"
    fi
  done
  ```
- **Fix backend** [`utils/api/facturas.py:234`]:
  ```python
  # ANTES (BUG):
  f.write(_b64.b64decode(body['imagen_base64']))

  # AHORA (fix 2026-04-30):
  _b64data = body['imagen_base64']
  if isinstance(_b64data, str) and ',' in _b64data and _b64data.startswith('data:'):
      _b64data = _b64data.split(',', 1)[1]   # strip "data:image/jpeg;base64,"
  f.write(_b64.b64decode(_b64data))
  ```
- **Lección**: cuando el navegador muestra "imagen rota" pero `curl` baja bytes correctos, verificar **magic bytes** del archivo en disco con `xxd | head -1`. Si magic != formato esperado, el archivo está corrupto desde el upload, NO es problema del navegador.

### BUG-002 — Splash colgado para siempre (Vue no monta)
- **Síntoma**: pantalla muestra el logo SANDOVAL EIRL girando indefinidamente. La SPA nunca aparece. Hard reload no arregla.
- **Verificación rápida**:
  ```bash
  python3 /var/www/sandoval/scripts/pre_deploy_check.py
  ```
  Si reporta refs críticas faltantes → BUG-002.
- **Causa raíz típica**: variable expuesta en `return {}` del `setup()` Vue 3 que NO está declarada en el setup → ReferenceError silencioso → Vue no monta → splash queda visible. JS es sintácticamente válido (pasa `node --check`) pero falla en runtime.
- **Causa raíz secundaria**: inyectar `<script>...</script>` SIN ESCAPAR dentro de un template literal JS — el parser HTML cierra el script real al primer `</script>` literal aunque esté dentro de string. Solución: usar `<\/script>` (con backslash) dentro del template literal.
- **Fix**: usar el script `pre_deploy_check.py` ANTES de cada deploy. Detecta los 3 bugs comunes:
  1. JS sintaxis (`node --check`)
  2. Refs en `return {}` no declaradas en `setup()`
  3. 24 refs CRÍTICAS del login presentes
- **Lección**: NUNCA subir `static/admin/index.html` sin pasar el pre-deploy check. JS válido ≠ Vue funcional.

### BUG-003 — Caja muestra S/0.00 cuando SÍ hubo cobros hoy
- **Síntoma**: usuario cobró órdenes hoy pero "Apertura/Cierre Caja" muestra S/0.00. La DB tiene los registros pero la caja no los suma.
- **Causa raíz**: query filtraba por `fecha_dt::date = CURRENT_DATE` (fecha de creación de la orden). Una orden creada el 28-abr y cobrada el 29-abr NO aparece en la caja del 29-abr porque su `fecha_dt` es del 28.
- **Fix** [`routers/caja.py` + `routers/dashboard.py`]: usar `pagos JSON` con fecha REAL del abono:
  ```sql
  WITH pagos_jsonb AS (
    SELECT (p->>'fecha')::date AS dia, (p->>'monto')::numeric AS monto, ...
    FROM ordenes o
    CROSS JOIN LATERAL json_array_elements(COALESCE(o.pagos, '[]'::json)) AS p
    WHERE o.taller_id = :t AND COALESCE(json_array_length(o.pagos), 0) > 0
  ),
  pagos_legacy AS (  -- fallback órdenes legacy con monto_cobrado pero pagos vacío
    SELECT o.fecha_dt::date AS dia, COALESCE(o.monto_cobrado, 0)::numeric AS monto, ...
    FROM ordenes o
    WHERE o.taller_id = :t AND COALESCE(o.monto_cobrado, 0) > 0
      AND (o.pagos IS NULL OR COALESCE(json_array_length(o.pagos), 0) = 0)
  )
  SELECT * FROM pagos_jsonb UNION ALL SELECT * FROM pagos_legacy
  ```
- **Lección**: `fecha_dt` es CREACIÓN, no cobro. Para flujo de caja real usar `pagos[].fecha` JSON.

### BUG-004 — IGV ventas en cuenta 40111 (PCGE incorrecto)
- **Síntoma**: declaración SUNAT mensual mal — IGV débito fiscal y crédito fiscal mezclados.
- **Causa raíz** [`utils/contabilidad_engine.py:28-29`]: `C_IGV_VENTA = "40111"` cuando debe ser `"4011"`. PCGE Perú: 4011 = IGV cuenta propia (débito), 40111 = IGV crédito fiscal compras.
- **Fix**:
  ```python
  C_IGV_VENTA  = "4011"     # IGV cuenta propia (débito fiscal de ventas)
  C_IGV_COMPRA = "40111"    # IGV crédito fiscal (de compras)
  ```
- **Acción adicional**: borrar asientos viejos de ventas y re-generar:
  ```sql
  DELETE FROM asiento_lineas WHERE asiento_id IN (
    SELECT id FROM asientos_contables WHERE taller_id=:t AND origen IN ('nota_venta','orden')
  );
  DELETE FROM asientos_contables WHERE taller_id=:t AND origen IN ('nota_venta','orden');
  ```
  Luego correr `seed_asientos.py` para regenerar.

### BUG-005 — Estado Resultados duplica gastos
- **Síntoma**: utilidad neta reportada negativa por ~S/9,380 más de lo real.
- **Causa raíz** [`routers/libros.py:524`]: query filtraba `cuenta_codigo LIKE '6%'` que captura tanto 60x (compras) como 63x/64x/65x (gastos), duplicando gastos que YA estaban en `gastos`.
- **Fix**:
  ```sql
  -- ANTES: WHERE l.cuenta_codigo LIKE '6%'
  -- AHORA: WHERE l.cuenta_codigo LIKE '60%'  -- solo clase 60 (compras mercadería)
  ```

### BUG-006 — Motor IGV desbalancea asiento (notas con subtotal=total)
- **Síntoma**: `ValueError: Asiento desbalanceado: debe=415.00 haber=489.70` al generar asiento de nota de venta.
- **Causa raíz** [`utils/contabilidad_engine.py:generar_asiento_nota_venta`]: notas pequeñas tienen `subtotal == total` (sin desglose IGV en DB). El motor calculaba `igv = subtotal * 0.18` que sumaba 18% encima del total → desbalance grande.
- **Fix**: si `subtotal == total` o no hay desglose, tratar `total` como bruto (con IGV incluido):
  ```python
  DOSCE = Decimal("0.01")
  if subtotal_db > 0 and igv_db > 0 and abs(subtotal_db + igv_db - total) <= DOSCE:
      igv = igv_db
      subtotal = total - igv  # ajuste de centavo para balancear
  else:
      # subtotal==total o sin desglose: total YA incluye IGV
      igv = _d2((total * Decimal("18")) / Decimal("118"))
      subtotal = total - igv
  ```
- Aplica también a `generar_asiento_factura_compra`.

### BUG-007 — Clientes muestran CLI-YYYYMMDD-NNN en vez de DNI/RUC
- **Síntoma**: tabla de clientes columna "DNI/RUC" muestra `CLI-20260428-001` en lugar del documento real.
- **Causa raíz**: `clientes.id` (PK) ahora es `CLI-YYYYMMDD-NNN`. El RUC/DNI real está en `clientes.documento`. Frontend mostraba `c.id`.
- **Fix** [`static/admin/index.html`]:
  ```html
  <!-- ANTES: -->
  <td>{{c.id||'—'}}</td>
  <!-- AHORA: -->
  <td>{{c.documento||c.id||'—'}}</td>
  ```
  Aplicar también a autocomplete de búsqueda de cliente y modal nueva orden.

### BUG-008 — Permisos archivos subidos (640 en vez de 644)
- **Síntoma**: `nginx error.log: open() ... failed (13: Permission denied)`. Archivo existe pero nginx (www-data) no puede leerlo.
- **Causa raíz**: el proceso uvicorn corre como `sandoval` con umask que produce 640 (`rw-r-----`). El grupo es `sandoval` pero nginx corre como `www-data` que NO está en ese grupo → 403.
- **Fix archivos existentes**:
  ```bash
  chmod 755 /var/www/sandoval /var/www/sandoval/static /var/www/sandoval/static/facturas
  chmod 644 /var/www/sandoval/static/facturas/*.{jpg,jpeg,png,pdf}
  ```
- **Fix endpoint upload** [`routers/facturas.py:151`, `utils/api/facturas.py:236`]:
  ```python
  with open(fpath, "wb") as out:
      out.write(content)
  try: os.chmod(fpath, 0o644)  # nginx www-data debe leer
  except Exception: pass
  ```
- **Fix nginx adicional** (anti negative cache): agregar `Cache-Control: no-cache` para `/facturas/`:
  ```nginx
  location /facturas/ {
      alias /var/www/sandoval/static/facturas/;
      add_header Cache-Control 'no-cache, must-revalidate' always;
      expires off;
  }
  ```

### BUG-009 — Gráficos Chart.js no se renderizan en Dashboard PRO
- **Síntoma**: Dashboard muestra cards y descripciones pero los `<canvas>` quedan vacíos. KPIs SÍ cargan (data llega del backend).
- **Causa raíz**: Vue 3 template refs (`ref="chIngGst"`) tienen timing impredecible con `<template v-if>`. Cuando `v-if` cambia de false a true, los `<canvas>` se montan PERO `chIngGst.value` aún apunta a `null` por un tick extra.
- **Fix**: cambiar `ref=` a `id=` (DOM IDs estables) y usar `getElementById`:
  ```html
  <!-- ANTES: -->
  <canvas ref="chIngGst"></canvas>

  <!-- AHORA: -->
  <canvas id="dproChIngGst"></canvas>
  ```
  ```javascript
  // ANTES:
  if (chIngGst.value) { new Chart(chIngGst.value.getContext('2d'), {...}) }

  // AHORA:
  const elIngGst = document.getElementById('dproChIngGst');
  if (elIngGst) { new Chart(elIngGst.getContext('2d'), {...}) }
  ```
- **Lección**: Vue refs son geniales para casos simples pero en `<template v-if>` complejos, `getElementById` es 100% confiable.

### BUG-010 — sessions.db propiedad de root (login PWA/cliente roto silencioso)
- **Síntoma**: usuarios PWA staff y portal cliente NO pueden hacer login. Backend responde 401 sin error visible.
- **Causa raíz**: `/var/www/sandoval/utils/sessions.db` quedó como `root:root` después de algún mantenimiento. El proceso uvicorn corre como `sandoval` y no puede escribir.
- **Fix**:
  ```bash
  chown sandoval:sandoval /var/www/sandoval/utils/sessions.db
  chmod 644 /var/www/sandoval/utils/sessions.db
  ```

### BUG-011 — Login con conductor sin PIN custom
- **Síntoma falso**: "los conductores no pueden hacer login porque tienen `conductor_pin_hash = NULL`".
- **Realidad**: el flujo de login del cliente (`utils/flota.py:detect_login_role`) tiene CASCADA:
  1. Si placa tiene `conductor_pin_hash` y password matchea → CONDUCTOR (PIN custom)
  2. Si NO tiene hash y password == documento del cliente (RUC) → CONDUCTOR (PIN inicial)
  3. Si no matchea como conductor, intentar como JEFE/CLIENTE
- **Lección**: `conductor_pin_hash = NULL` **NO BLOQUEA** el login — el conductor entra con el RUC de la empresa hasta que el admin le asigne PIN custom. **NO TOCAR** este flujo sin permiso (regla 5.0).

### Cómo agregar un nuevo bug a este catálogo
Cuando arregles un bug nuevo:
1. Numéralo (BUG-XXX) en orden secuencial
2. Documenta SÍNTOMA EXACTO que vio el usuario (no técnico, lo que él describiría)
3. Lista síntomas FALSOS para no confundirse otra vez
4. Comando de verificación rápida (curl, query, xxd, etc.)
5. Causa raíz TÉCNICA con archivo:línea exacto
6. Código del fix (antes/después)
7. Lección/principio aprendido

## 16. Hardening maratón 2026-05-05 (sesión madrugada)

Sesión post-auditoría externa #3 ChatGPT + 13 agentes especializados. 12 fixes P0+P1+P2 aplicados, 9 commits a GitHub previos + cambios de esta sesión.

### 16.1 Migración localStorage → Cookie HttpOnly (3/4 portales)
- **Admin SPA** (`static/admin/index.html`):
  - `const token = ref('')` (era `ref(localStorage.getItem('sandoval_token'))`).
  - `doLogin()`, `doLogin2FA()`, `logout()`, `onMounted()`, `hydrateSession()`: usan `credentials:'include'`. Backend setea cookie HttpOnly `sandoval_token` vía `Set-Cookie`.
  - 4 inline `fetch()` migrados (factura imagen, fotos orden, fotos fase, `_downloadAuthed`): cookie + CSRF, sin Bearer.
- **Portal cliente PC** (`portal-cliente/pc/index.html`):
  - `loadSession()` ahora `async` y llama `GET /api/auth/me` con `credentials:'include'`. Fallback transitorio lee localStorage para sesiones legacy.
  - `saveSession(token, user)` NO escribe a localStorage. Cookie HttpOnly seteada por backend en login.
  - `api()`: `credentials:'include'` + `_csrfHeaders` Double Submit + 403 CSRF reload handler.
- **Portal cliente móvil** (`portal-cliente/index.html`):
  - `loadSession()` async + `/api/auth/me`.
  - `api()`: `credentials:'include'` + X-CSRF-Token inline reader.
  - `fetchPdfBlob`, presupuesto.pdf descargas: cookie sin Bearer.
- **Super admin** (`static/super_admin.html`):
  - `doLogout()` ahora `async` + llama `POST /superadmin/api/logout` con Bearer header ANTES de limpiar localStorage (jti se revoca correctamente).
  - `impersonarTaller()`: backend ahora setea cookie HttpOnly `sandoval_token` con el JWT. Frontend abre `/admin/index.html?taller=...&impersonado=1` SIN token en URL (antes `/?sa_impersonate=TOKEN` filtraba JWT en logs nginx + Referer + historial).
  - localStorage eliminado en super_admin sigue pendiente (requiere endpoint `/superadmin/api/me` y refactor de hidratación).

### 16.2 CSRF expandido (Double Submit Cookie)
- `utils/csrf.py:AUTH_COOKIE_NAMES` ampliado de `("sandoval_token",)` a `("sandoval_token", "sandoval_client_token")`.
- Las 3 rutas PWA cliente (PC + móvil) ahora envían `X-CSRF-Token` en mutaciones.
- PWA staff (`/sandoval-app/`) — el frontend aún no envía CSRF, mantenido EXENTO.

### 16.3 Logout silencioso fix (P0-1)
- `routers/auth.py:_secret` faltaba en imports. Causa: la cascada de import en `_common.py` no exportaba `_secret` localmente. Síntoma: logout admin retornaba 500 silencioso si solo había cookie HttpOnly (sin Bearer header).

### 16.4 Logout 3 portales fix (P0-3)
- `portal-cliente/index.html` y `portal-cliente/pc/index.html` llamaban `/api/logout` (404). Cambiado a ruta canónica `/api/auth/logout`.
- `sandoval-app/index.html` ya estaba correcto.

### 16.5 Super admin impersonate sin JWT en URL (P0-4 + P2-3)
- Backend `/superadmin/api/talleres/{id}/impersonar` ahora setea `Set-Cookie: sandoval_token=...; HttpOnly; Secure; SameSite=Lax` con el token de impersonación + sigue retornando token en JSON (compat).
- TTL token impersonate: 15 min (`SA_IMPERSONATE_EXP_MINUTES`).
- Frontend abre `/admin/index.html?taller=...&impersonado=1` — la cookie HttpOnly hace la auth.

### 16.6 Nginx rate limit en TODAS las rutas login (P2-2)
- Antes: solo `/api/login` (PWA legacy) tenía `zone=login` (5r/m, burst 3).
- Ahora cubre además: `/api/login/2fa`, `/api/auth/login`, `/admin/api/login`, `/admin/api/login/2fa`, `/superadmin/api/login`.
- 6 `location =` blocks con limit_req_status 429.

### 16.7 pre_deploy_check.py portable (P2-1)
- `_default_admin_path()` busca admin/index.html en cascada: `SANDOVAL_ADMIN_HTML` env → VPS `/var/www/sandoval/static/...` → mirror local. Antes hardcoded a Windows path.
- Funciona ahora en VPS y en local sin override.

### 16.8 Backups fuera de webroot
- Backups nginx ahora en `/var/backups/nginx_sandoval/` (antes `.bak` en `sites-enabled` rompía nginx por declarar `limit_req_zone "login"` 2 veces).
- Backups super_admin/auth/csrf siguen en mismo dir (no son cargados por nginx).

### 16.9 Capas de seguridad tras esta sesión
- 16 capas activas (era 15):
  - Cookies HttpOnly+Secure+SameSite=Lax en 3 portales (admin SPA + portal cliente PC + móvil)
  - CSRF Double Submit cubre 2 cookies (era 1)
  - Rate limit estricto en 6 rutas login (era 1)
  - JWT NO aparece en URLs (super admin impersonate corregido)

### 16.10 Pendiente (roadmap)
- **P1-1 super_admin**: localStorage → cookie HttpOnly requiere endpoint `/superadmin/api/me` + actualizar `_verify_sa_token` para leer cookie `sandoval_sa_token` además de Bearer.
- **P1-1 PWA staff**: `sandoval-app/index.html` (~922KB) usa `sandoval_api_token` en localStorage. Migrar a cookie + CSRF helpers.
- **P1-3**: bot `deploy/sandoval-bot.service` corre como `User=root`. Cambiar a `sandoval` + hardening systemd (`ProtectSystem=strict`, `NoNewPrivileges`, etc.).
- **P1-4**: `/var/www/sandoval/pdfs/`, `/evidencia/`, `/facturas/` están bajo webroot. Mover a `/var/lib/sandoval/files/` y servir vía endpoint protegido con auth.
- **FastAPI score 4.2 → 8.5+**: `utils/schemas.py` tiene 7 schemas Pydantic V2; necesita 15+ más + `response_model=` declarations + `status_code=201/204` semánticos en 30+ endpoints.
- **P2-1 CI**: pipeline GitHub Actions con `pre_deploy_check.py` debe ELIMINAR `|| true` que silencia errores (verificar `.github/workflows/`).

### 16.11 BUG-012 — UnboundLocalError en admin_logout (cazado por backend-engineer audit)
- **Síntoma**: `POST /admin/api/logout` retornaba 500 cuando el token venía por header `Authorization: Bearer ...`. Logs: `UnboundLocalError: cannot access local variable 'COOKIE_ADMIN_NAME' where it is not associated with a value`.
- **Causa raíz** [`routers/auth.py:187`]: el bloque `try` dentro de la función tenía `from utils.auth_cookies import get_token_from_request, COOKIE_ADMIN_NAME`. Python detecta la asignación local (vía import) y trata `COOKIE_ADMIN_NAME` como variable local en TODA la función. Si el flujo entra por la rama Bearer (línea 183) y NO ejecuta el import dentro del try, el `clear_token_cookie(_resp, cookie_name=COOKIE_ADMIN_NAME)` de la línea 223 dispara UnboundLocalError porque la variable local nunca fue asignada — pero el import a nivel módulo (línea 158) está shadoweado.
- **Fix**: eliminar el `COOKIE_ADMIN_NAME` del import dentro del `try` (ya está a nivel módulo). Solo importar `get_token_from_request` ahí.
- **Lección**: NUNCA hacer `from X import Y` dentro de una función para una variable que YA está importada a nivel módulo y se usa más adelante en el cuerpo. Python convierte ese import en local-binding silencioso.


## 17. Hardening EXTREMO 2026-05-05 (sesión madrugada-tarde, post-auditoría sync-guardian)

Tras la sesión maratón documentada en sección 16, una segunda ronda detectó BUGs críticos que NINGUNA auditoría anterior había encontrado (ni ChatGPT externa, ni los 13 agentes internos).

### 17.1 Super admin migrado a Cookie HttpOnly (P1-1 cerrado)
- `super_admin_router.py`:
  - `_verify_sa_token()` ahora dual-auth: lee cookie `sandoval_sa_token` Y header Bearer (compat).
  - `POST /superadmin/api/login` setea `Set-Cookie: sandoval_sa_token` HttpOnly+Secure+SameSite=Lax (path=/superadmin, max_age=30min).
  - `GET /superadmin/api/me` (NUEVO) — endpoint de hidratación post-migración.
  - `POST /superadmin/api/logout` ahora lee también cookie + limpia con `delete_cookie`.
- `static/super_admin.html`:
  - `window.onload` async, hidrata via `/superadmin/api/me` con `credentials:'include'`.
  - Login NO escribe `sa_token` a localStorage. Limpia legacy automáticamente.
  - `api()` con `credentials:'include'` + `_saCsrfHeaders()` Double Submit + handler 403 CSRF reload.
- `utils/csrf.py:AUTH_COOKIE_NAMES` ahora `("sandoval_token", "sandoval_client_token", "sandoval_sa_token")`.
- **4/4 portales con HttpOnly cookies + CSRF Double Submit.**

### 17.2 BUGs P0 IDOR multi-tenancy (cazados por sandoval-sync-guardian)

5 endpoints de la PWA staff (`/api/*`) NO filtraban por `taller_id`. RLS era la única defensa, y si `app.taller_id` GUC no estaba seteado, un staff podía ver datos de OTROS talleres.

| BUG | Archivo | Función | Fix |
|-----|---------|---------|-----|
| BUG-013 | `utils/api/ordenes.py:51` | `api_ordenes_list` | Agregado `.filter(Orden.taller_id == taller_id)` + filter en cli/veh maps |
| BUG-014 | `utils/api/cliente.py:72` | `api_clientes_list` | Agregado `.filter(Cliente.taller_id == taller_id)` |
| BUG-015 | `utils/api/cliente.py:133` | `api_vehiculos_list` | Agregado `.filter(Vehiculo.taller_id == taller_id)` + 8 campos sync con admin SPA (color, conductor, año) |
| BUG-016 | `utils/api/inventario.py:39` | `api_inventario_list` | Agregado `.filter(ItemInventario.taller_id == taller_id)` + campos margen/estado_stock/codigo_barras/descripcion |
| BUG-017 | `utils/api/notas_citas.py:46` | `api_notas_list` + `api_citas_list` | Agregado filter taller_id + limit 50→200 |

Todos defense-in-depth: app filter + RLS GUC.

### 17.3 BUG-018 — Caja PWA reportaba totales ≠ admin SPA
- **Síntoma**: usuario veía S/ X en caja del admin SPA y S/ Y (distinto) en PWA staff. Confusión grave.
- **Causa raíz** [`utils/api_mobile_admin.py:122`]: query usaba `WHERE estado='ARCHIVADO' AND fecha_dt::date=CURRENT_DATE`. Esto:
  1. Solo contaba órdenes ARCHIVADAS (excluía ENTREGA con cobros parciales).
  2. Filtraba por `fecha_dt` (creación) en vez de `pagos[].fecha` (cobro real).
  3. Notas: `monto_pagado` sin fallback a `total` (subestimaba notas sin desglose).
- **Fix**: replica exacta de la CTE `_CTE_PAGOS` de `routers/caja.py` — pagos JSON unificados con legacy, fallback `NULLIF(monto_pagado, 0)`.

### 17.4 BUG-019 — Notas de venta con `estado='pagada'` (minúscula) vs admin `estado='PAGADO'`
- Inconsistencia de enum entre PWA y admin SPA.
- Filtros del admin no encontraban notas creadas por la PWA staff.
- **Fix**: PWA ahora setea `estado='PAGADO'`.

### 17.5 Capas de seguridad finales (post-sesión)
- 17 capas activas (era 16):
  - 4/4 portales con cookies HttpOnly+Secure+SameSite=Lax
  - CSRF Double Submit cubre **3 cookies** (era 2): admin + cliente + super_admin
  - **Defense-in-depth multi-tenancy**: app filter + RLS GUC en TODOS los endpoints staff

### 17.6 Pendiente roadmap final
- **PWA staff localStorage `sandoval_api_token`** — sigue activo (la cookie HttpOnly post-login admin lo cubre, pero la sesión SQLite cliente sigue en localStorage).
- **FastAPI score 4.2 → 8.5**: 22 schemas ya, falta `response_model=` y `status_code=` en 30+ endpoints (deferred para sesión con testing endpoint-por-endpoint).
- **Mover `/static/evidencia/` (1.5GB) fuera webroot** + endpoint protegido.
- **Cifrado PII at-rest con pgcrypto** (Ley 29733).
- **Soft-delete con derecho al olvido** + cron purge 90 días.
- **Observabilidad Prometheus + Grafana** + alertas Telegram.

