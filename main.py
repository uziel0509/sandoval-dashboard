"""
MECÁNICA Y REPUESTOS SANDOVAL EIRL - Backend principal v3.0
============================================================
FastAPI + uvicorn (sin NiceGUI). Sirve:
  - /                       → HTML SPA Vue3 (admin) [redirige a /app/ en móvil]
  - /admin/                 → mismo HTML SPA
  - /app/, /app/sw.js, /app/manifest.json, /app/static/* → PWA móvil
  - /login                  → HTML puro (utils/login_html.py)
  - /portal                 → 301 → /app/ (la PWA cliente cubre el portal)
  - /portal-logout          → limpieza de sesión + redirect /login
  - /aprobacion/{token}     → HTML puro (pages/approval.py)
  - /reporte/{token}        → HTML puro (utils/reporte_publico.py)
  - /encuesta/{token}       → HTML puro (utils/encuesta_publica.py)
  - /a/{code}               → short link → /aprobacion/{token}
  - /api/...                → REST API (utils/api_service.py)
  - /admin/api/...          → REST API admin SPA (routers/*.py)
  - /superadmin/...         → portal super-admin (super_admin_router.py)
  - /assets, /evidencia, /pdfs, /facturas, /static/* → estáticos
"""
import datetime
import os
import sys
import traceback

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse, HTMLResponse, JSONResponse, RedirectResponse,
)
from fastapi.staticfiles import StaticFiles

# ── Routers admin/super-admin (FastAPI APIRouter, sin NiceGUI) ────────────
from admin_router import router as admin_router
from super_admin_router import router as sa_router


# ── psycopg2: NUMERIC -> float (preserva compat JSON tras migracion REAL->NUMERIC) ──
try:
    import psycopg2.extensions as _pe
    _pe.register_type(_pe.new_type(_pe.DECIMAL.values, 'DECIMAL2FLOAT', lambda v, c: float(v) if v is not None else None))
except Exception as _e:
    pass

load_dotenv()

# ── Logging boot ──────────────────────────────────────────────────────────
LOG_FILE = "sandoval_boot.txt"
if os.path.exists(LOG_FILE):
    try:
        os.remove(LOG_FILE)
    except OSError:
        pass


def log_boot(msg: str) -> None:
    line = f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass
    print(f"[BOOT] {msg}")


log_boot("Iniciando SANDOVAL Backend v3.0 (FastAPI puro, sin NiceGUI)…")

# ── FastAPI app ───────────────────────────────────────────────────────────
# 2026-05-04 FASE1.1: openapi_url=None desactiva /openapi.json
# (antes devolvia 500 y exponia stack traces).
app = FastAPI(
    title="SANDOVAL Dashboard",
    description="Sistema de gestión de talleres mecánicos.",
    version="3.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# ── CORS estricto (cookies HttpOnly requieren origin especifico) ──────────
# 2026-05-04 FASE1.1: reemplazo del _cors() manual con wildcard.
from fastapi.middleware.cors import CORSMiddleware
_CORS_ORIGINS = [
    "https://xn--mecnicarysandoval-8ob.com",
    "https://www.xn--mecnicarysandoval-8ob.com",
    "https://mecánicarysandoval.com",
    "https://www.mecánicarysandoval.com",
]
# extra origins desde .env (futuros sub-talleres en multi-tenant)
_extra = os.getenv("CORS_EXTRA_ORIGINS", "").strip()
if _extra:
    _CORS_ORIGINS.extend([o.strip() for o in _extra.split(",") if o.strip()])
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-CSRF-Token"],
    max_age=600,
)

# ── CSRF middleware (P2-B1, 2026-05-04) ───────────────────────────────────
# Double Submit Cookie: cookie csrf_token (no HttpOnly) + header X-CSRF-Token.
# Aplica solo a métodos POST/PUT/PATCH/DELETE; exenta /api/login, /healthz,
# /aprobacion/, /reporte/, /encuesta/, /api/lookup/, webhooks, estáticos.
from utils.csrf import CSRFMiddleware
app.add_middleware(CSRFMiddleware)

# ── Middleware de aislamiento multi-tenant (Row Level Security) ───────────
# Decodifica el token (JWT admin o sesión SQLite PWA/cliente) y deja
# `taller_id` en un ContextVar. utils/models.py:get_db() lee ese ContextVar
# y ejecuta SET app.taller_id sobre la conexión PG, activando las policies
# RLS para esta sesión.
from utils.rls_session import TallerContextMiddleware, with_taller
app.add_middleware(TallerContextMiddleware)


# ── Exception handler global (FASE1.3) ────────────────────────────────────
# Cualquier excepcion no manejada se loguea en eventos_seguridad y devuelve
# JSON estructurado en lugar de stack trace al usuario.
from fastapi import HTTPException as _HTTPExc
@app.exception_handler(Exception)
async def _global_exc_handler(request: Request, exc: Exception):
    # Re-lanzar HTTPException explicitas (FastAPI ya las maneja)
    if isinstance(exc, _HTTPExc):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    import logging as _lg
    _lg.getLogger("sandoval.errors").exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    # Persistir en eventos_seguridad sin romper si la DB tambien falla
    try:
        from utils.models import get_db
        from sqlalchemy import text as _t
        _db = get_db()
        try:
            _db.execute(_t("SET app.taller_id = 0"))
            _db.execute(_t(
                "INSERT INTO eventos_seguridad "
                "(taller_id, tipo, severidad, ip, endpoint, descripcion, fecha) "
                "VALUES (0, '500_unhandled', 'ERROR', :ip, :ep, :desc, NOW())"
            ), {
                "ip":   (request.client.host if request.client else "")[:64],
                "ep":   f"{request.method} {request.url.path}"[:200],
                "desc": f"{type(exc).__name__}: {str(exc)[:400]}",
            })
            _db.commit()
        finally:
            _db.close()
    except Exception:
        pass
    return JSONResponse(status_code=500, content={"error": "Error interno del servidor"})

try:
    # ── Crear directorios necesarios ──────────────────────────────────────
    for d in ("data", "pdfs", "backups", "assets", "exports"):
        os.makedirs(d, exist_ok=True)

    # ── Montar estáticos (FastAPI puro, sin nicegui.add_static_files) ────
    # Cada mount se envuelve en try porque algún directorio puede no existir
    # en entornos de desarrollo (no debe tumbar el boot).
    def _mount(path: str, directory: str) -> None:
        try:
            if os.path.isdir(directory):
                app.mount(path, StaticFiles(directory=directory), name=path.strip("/").replace("/", "_") or "root")
            else:
                log_boot(f"  [WARN] mount {path} → {directory} (directorio no existe)")
        except Exception as _e:
            log_boot(f"  [WARN] no se pudo montar {path}: {_e}")

    _mount("/assets",            "assets")
    _mount("/evidencia",         "static/evidencia")
    _mount("/static/evidencia",  "static/evidencia")  # backward compat
    _mount("/pdfs",              "pdfs")
    _mount("/facturas",          "static/facturas")
    _mount("/static/temp_docs",  "static/temp_docs")
    _mount("/superadmin/static", "static")
    _mount("/admin-assets",      "static/admin")
    _mount("/app/static",        "sandoval-app")
    log_boot("Estáticos montados")

    app.include_router(sa_router)
    app.include_router(admin_router)
    log_boot("Admin Portal v2 registrado en /admin")
    log_boot("Super Admin Portal registrado en /superadmin")

    # ── Inicializar Base de Datos ─────────────────────────────────────────
    # Operaciones admin de boot (init_db, set_config) escriben en tablas con
    # RLS — necesitan taller_id en contexto. Usamos taller=1 (taller propietario).
    from utils.models import init_db, get_config, set_config
    init_db()
    with with_taller(1):
        groq_key_env = os.getenv("GROQ_API_KEY", "")
        if groq_key_env and not get_config("groq_api_key"):
            set_config("groq_api_key", groq_key_env)
    log_boot("Base de datos inicializada (PostgreSQL)")

    # ── REST API para PWA móvil + portal cliente ──────────────────────────
    from utils.api.routes import register_api_routes
    register_api_routes(app)
    log_boot("API REST registrada")

    # ── Web Push (VAPID) para notificaciones PWA ──────────────────────────
    try:
        from utils.push_api import register_push_routes
        register_push_routes(app)
        log_boot("Web Push endpoints registrados")
    except Exception as _e:
        log_boot(f"[WARN] Push endpoints no registrados: {_e}")

    # ── Páginas públicas HTML puro ────────────────────────────────────────
    from pages.approval import approval_html, process_approval_response
    from utils.login_html import render_login_html
    from utils.reporte_publico import (
        render_reporte_publico,
        get_taller_id_by_token as _taller_id_by_report_token,
        get_consecutivo_by_token as _consec_by_report_token,
    )
    from utils.encuesta_publica import (
        render_encuesta_publica,
        submit_encuesta,
    )

    # ── Ruta raíz: PC = admin SPA, móvil = PWA ───────────────────────────
    _ADMIN_HTML_PATH = "/var/www/sandoval/static/admin/index.html"

    def _is_mobile(ua: str) -> bool:
        ua = (ua or "").lower()
        return any(x in ua for x in (
            "android", "iphone", "ipad", "ipod", "iemobile", "mobile",
        ))

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        # Movil  PWA, PC  portal cliente PC (login nuevo verde Sandoval)
        if _is_mobile(request.headers.get("user-agent", "")):
            return RedirectResponse("/app/", status_code=302)
        return RedirectResponse("/portal/pc/", status_code=302)


    @app.get("/favicon.ico", include_in_schema=False)
    async def serve_favicon():
        return FileResponse("favicon.ico", media_type="image/png")

    @app.get("/robots.txt", include_in_schema=False)
    async def serve_robots():
        return FileResponse("robots.txt", media_type="text/plain")


    # 2026-04-29 audit V15: endpoint /healthz para monitoreo / load balancer
    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        """Health check: valida DB, disco, servicios."""
        import shutil as _sh
        from sqlalchemy import text as _t
        status = {"ok": True, "checks": {}}
        # DB
        try:
            from utils.models import get_db
            _db = get_db()
            try:
                _db.execute(_t("SELECT 1")).scalar()
                status["checks"]["db"] = "ok"
            finally:
                _db.close()
        except Exception as _e:
            status["ok"] = False
            status["checks"]["db"] = f"fail: {type(_e).__name__}"
        # Disco
        try:
            usage = _sh.disk_usage("/var/www/sandoval")
            free_gb = usage.free / (1024**3)
            status["checks"]["disk_free_gb"] = round(free_gb, 2)
            if free_gb < 1.0:
                status["ok"] = False
                status["checks"]["disk_warn"] = "menos de 1GB libre"
        except Exception as _e:
            status["checks"]["disk"] = f"fail: {type(_e).__name__}"
        # Sandoval-bot service
        import subprocess as _sp
        try:
            r = _sp.run(["systemctl", "is-active", "sandoval-bot"], capture_output=True, text=True, timeout=2)
            status["checks"]["sandoval_bot"] = r.stdout.strip()
        except Exception:
            status["checks"]["sandoval_bot"] = "unknown"
        return JSONResponse(status, status_code=200 if status["ok"] else 503)

    # ── PWA móvil ─────────────────────────────────────────────────────────
    @app.get("/app")
    @app.get("/app/")
    async def serve_pwa():
        return FileResponse(
            "sandoval-app/index.html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )

    @app.get("/app/sw.js")
    async def serve_sw():
        return FileResponse(
            "sandoval-app/sw.js",
            media_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/app/manifest.json")
    async def serve_manifest():
        return FileResponse(
            "sandoval-app/manifest.json",
            media_type="application/json",
        )

    # ── /login (HTML puro) ────────────────────────────────────────────────
    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if _is_mobile(request.headers.get("user-agent", "")):
            return RedirectResponse("/app/", status_code=302)
        return HTMLResponse(
            content=render_login_html(),
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "X-Robots-Tag": "noindex, nofollow",
            },
        )

    # ── /portal y /portal-logout (compatibilidad de URLs viejas) ─────────
    @app.get("/portal")
    async def portal_redirect():
        return RedirectResponse("/app/", status_code=301)

    @app.get("/portal-logout")
    @app.post("/portal-logout")
    async def portal_logout():
        resp = RedirectResponse("/login", status_code=302)
        resp.delete_cookie("sandoval_api_token")
        resp.delete_cookie("session")
        return resp

    # ── /aprobacion/{token} (HTML puro, con bypass RLS via SECURITY DEFINER) ──
    def _lookup_taller_by_approval(tok: str):
        """Devuelve taller_id de un approval_token usando función SD que bypasea RLS.
        Fallback a query directa si la función no existe (BD no migrada)."""
        from sqlalchemy import text as _sa_text
        from utils.models import get_db as _get_db_l
        if not tok or len(tok) < 16:
            return None
        db = _get_db_l()
        try:
            try:
                row = db.execute(_sa_text(
                    "SELECT taller_id FROM lookup_taller_by_approval_token(:t)"
                ), {"t": tok}).fetchone()
            except Exception:
                row = db.execute(_sa_text(
                    "SELECT taller_id FROM ordenes WHERE approval_token=:t LIMIT 1"
                ), {"t": tok}).fetchone()
            return int(row[0]) if row and row[0] is not None else None
        finally:
            db.close()

    @app.get("/aprobacion/{token}", response_class=HTMLResponse)
    async def public_approval(token: str):
        tid = _lookup_taller_by_approval(token)
        with with_taller(tid):
            html = approval_html(token)
        return HTMLResponse(
            content=html,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "X-Robots-Tag": "noindex, nofollow",
            },
        )

    @app.get("/a/{code}")
    async def short_link_redirect(code: str):
        from sqlalchemy import text as _sa_text
        from utils.models import get_db as _get_db_sl
        db = _get_db_sl()
        try:
            try:
                row = db.execute(_sa_text(
                    "SELECT token FROM lookup_taller_by_short_link(:c)"
                ), {"c": code}).fetchone()
            except Exception:
                row = db.execute(_sa_text(
                    "SELECT token FROM short_links WHERE code=:c LIMIT 1"
                ), {"c": code}).fetchone()
        finally:
            db.close()
        if not row:
            return HTMLResponse(
                '<!doctype html><meta charset=utf-8><title>Enlace no encontrado</title>'
                '<body style="font-family:system-ui;text-align:center;padding:60px">'
                '<h1 style="color:#dc2626">Enlace no encontrado</h1>'
                '<p>Este enlace corto no es válido o ha expirado.</p></body>',
                status_code=404,
            )
        return RedirectResponse(f"/aprobacion/{row[0]}", status_code=302)

    @app.post("/api/aprobacion/{token}/respond")
    async def public_approval_respond(token: str, request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        status = (body.get("status") or "").strip().lower()
        comentario = (body.get("comentario") or "").strip()
        tid = _lookup_taller_by_approval(token)
        with with_taller(tid):
            result = process_approval_response(token, status, comentario)
        code = 200 if result.get("ok") else 400
        return JSONResponse(content=result, status_code=code)

    # ── /reporte/{token} (HTML puro nuevo) ───────────────────────────────
    @app.get("/reporte/{token}", response_class=HTMLResponse)
    async def public_reporte(token: str):
        html, status = render_reporte_publico(token)
        return HTMLResponse(content=html, status_code=status, headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "X-Robots-Tag": "noindex, nofollow",
        })

    @app.get("/api/reporte/{token}/pdf")
    async def public_reporte_pdf(token: str):
        consecutivo = _consec_by_report_token(token)
        taller_id = _taller_id_by_report_token(token)
        if not consecutivo or taller_id is None:
            return HTMLResponse(
                '<!doctype html><meta charset=utf-8><title>No encontrado</title>'
                '<body style="font-family:system-ui;text-align:center;padding:60px">'
                '<h1 style="color:#dc2626">Enlace inválido o expirado</h1></body>',
                status_code=404)
        try:
            from utils.pdf_informe_orden import generar_informe_orden
            # generar_informe_orden abre su propia DB session — necesita el
            # taller_id en el ContextVar para que RLS lo deje leer.
            with with_taller(taller_id):
                pdf_path = generar_informe_orden(consecutivo, taller_id)
        except Exception as _e:
            return JSONResponse({"error": f"No se pudo generar el PDF: {_e}"}, status_code=500)
        safe = consecutivo.replace("/", "_").replace(" ", "_").replace("#", "")
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"reporte_{safe}.pdf",
            headers={"Cache-Control": "no-store"},
        )

    # ── /encuesta/{token} (HTML puro nuevo) ──────────────────────────────
    @app.get("/encuesta/{token}", response_class=HTMLResponse)
    async def public_encuesta(token: str):
        html, status = render_encuesta_publica(token)
        return HTMLResponse(content=html, status_code=status, headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "X-Robots-Tag": "noindex, nofollow",
        })

    @app.post("/api/encuesta/{token}/submit")
    async def public_encuesta_submit(token: str, request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        result, status = submit_encuesta(token, body)
        return JSONResponse(content=result, status_code=status)

    # /open-whatsapp eliminado 2026-04-29 (webbrowser.open server-side es no-op en VPS headless)

    log_boot("Páginas HTML registradas")

except Exception:
    log_boot(f"ERROR FATAL en setup: {traceback.format_exc()}")
    print(f"ERROR FATAL: {traceback.format_exc()}")
    sys.exit(1)


# ── Iniciar servidor uvicorn ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    log_boot("Iniciando servidor uvicorn en 0.0.0.0:3000…")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=3000,
        log_level="info",
        access_log=False,            # nginx ya loguea
        proxy_headers=True,           # respetar X-Forwarded-* del nginx
        forwarded_allow_ips="127.0.0.1",
    )
