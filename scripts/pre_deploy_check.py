#!/usr/bin/env python3
"""Pre-deploy check OBLIGATORIO antes de subir admin/index.html al VPS.

Detecta los 3 bugs históricos que han colgado el login:
  1. SyntaxError JavaScript (try sin catch, llaves desbalanceadas, etc.)
  2. Refs en return {} del setup() que NO están declaradas en el setup
  3. Refs CRÍTICAS del login ausentes (loginUser, doLogin, page, go, etc.)

Uso:
  python3 pre_deploy_check.py [archivo.html]

Exit code:
  0 = OK, listo para deploy
  1 = bugs encontrados, NO subir

Documentado en CLAUDE.md sección 5.0 — REGLA ABSOLUTA NO TOCAR LOGIN.
"""
import re
import sys
import subprocess
from pathlib import Path

def _default_admin_path() -> str:
    """Resuelve la ruta del admin/index.html portable.

    Orden de búsqueda:
      1. Variable env SANDOVAL_ADMIN_HTML (override explícito).
      2. /var/www/sandoval/static/admin/index.html (VPS Linux).
      3. <repo>/var/www/sandoval/static/admin/index.html (mirror local).
      4. <repo>/static/admin/index.html (estructura alterna).
      5. Fallback portable basado en este archivo.
    """
    import os
    if os.environ.get('SANDOVAL_ADMIN_HTML'):
        return os.environ['SANDOVAL_ADMIN_HTML']
    here = Path(__file__).resolve()
    candidates = [
        Path('/var/www/sandoval/static/admin/index.html'),
        here.parent.parent / 'var' / 'www' / 'sandoval' / 'static' / 'admin' / 'index.html',
        here.parent.parent / 'static' / 'admin' / 'index.html',
        here.parent / 'var' / 'www' / 'sandoval' / 'static' / 'admin' / 'index.html',
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return str(candidates[0])  # devuelve el primero (Linux) aunque falle, deja error explícito


ADMIN = sys.argv[1] if len(sys.argv) > 1 else _default_admin_path()

# Refs CRÍTICAS que SIEMPRE deben existir en el setup() del admin SPA
CRITICAL_REFS = [
    # Login
    'loginUser', 'loginPass', 'showPass', 'loginLoading', 'loginErr',
    'loginRol', 'doLogin', 'logout',
    # Sesión
    'user', 'token', 'view',
    # Navegación
    'page', 'sideOpen', 'menuItems', 'pageTitle', 'go', 'reload',
    # Helpers básicos
    'fmt', 'toast', 'api',
    # Login 3D
    'horaActual', 'fechaActual', 'sesIdShort', 'logoutMsg',
]

errors = []


def check_js_syntax(html: str) -> str | None:
    """Extrae el script grande y valida con node --check."""
    scripts = re.findall(r'<script[^>]*>(.+?)</script>', html, re.DOTALL)
    if not scripts:
        return "No hay <script> en el HTML"
    big = max(scripts, key=len)
    tmpfile = Path(__file__).parent / '_pre_deploy_check.js'
    tmpfile.write_text(big, encoding='utf-8')
    res = subprocess.run(['node', '--check', str(tmpfile)],
                         capture_output=True, text=True)
    tmpfile.unlink(missing_ok=True)
    if res.returncode != 0:
        return f"node --check FAIL:\n{res.stderr[:500]}"
    return None


def check_return_vs_setup(html: str) -> list[str]:
    """Verifica que cada ref expuesta en `return {}` exista en el setup()."""
    scripts = re.findall(r'<script[^>]*>(.+?)</script>', html, re.DOTALL)
    big = max(scripts, key=len)

    # Encontrar el ÚLTIMO return { antes de }).mount — ese es el del setup principal
    mount_idx = big.rfind(').mount(')
    if mount_idx < 0:
        return ['No se encontró .mount(']
    # Buscar el último 'return {' antes de mount_idx
    return_idx = big.rfind('return {', 0, mount_idx)
    if return_idx < 0:
        return ['No se encontró return { antes de .mount(']
    # Encontrar el cierre del return: matching brace
    depth = 0
    end_ret = return_idx
    started = False
    for i in range(return_idx + len('return '), len(big)):
        ch = big[i]
        if ch == '{':
            depth += 1; started = True
        elif ch == '}':
            depth -= 1
            if started and depth == 0:
                end_ret = i; break
    return_block = big[return_idx + len('return {'):end_ret]
    setup_body = big[:return_idx]

    # Identificadores del return
    exposed = set()
    for line in return_block.split('\n'):
        line = line.split('//')[0].strip().rstrip(',')
        for tok in re.split(r'[,\s]+', line):
            tok = tok.strip()
            if tok and re.match(r'^[a-zA-Z_$][\w$]*$', tok):
                exposed.add(tok)

    # Identificadores definidos en setup_body
    defined = set()
    for m in re.finditer(r'\b(?:const|let|var|function|async function)\s+([a-zA-Z_$][\w$]*)\b', setup_body):
        defined.add(m.group(1))
    # Destructuring: const { X, Y } = ...
    for m in re.finditer(r'\bconst\s*\{\s*([^}]+)\s*\}\s*=', setup_body):
        for tok in re.split(r'[,\s]+', m.group(1)):
            tok = tok.split(':')[0].strip()
            if tok: defined.add(tok)
    # Identificadores del scope global accesibles desde setup (ref, computed, watch, etc.)
    GLOBAL_OK = {'ref', 'computed', 'onMounted', 'watch', 'nextTick', 'reactive',
                 'onBeforeUnmount', 'onUnmounted', 'inject', 'provide', 'Vue',
                 'Chart', 'createApp'}

    no_definidos = sorted(exposed - defined - GLOBAL_OK)
    return no_definidos


def check_critical_refs(html: str) -> list[str]:
    """Verifica que las refs críticas del login estén declaradas en setup()."""
    scripts = re.findall(r'<script[^>]*>(.+?)</script>', html, re.DOTALL)
    big = max(scripts, key=len)
    # Usar el setup_body completo hasta el último return { antes de mount
    mount_idx = big.rfind(').mount(')
    return_idx = big.rfind('return {', 0, mount_idx) if mount_idx > 0 else -1
    if return_idx < 0:
        return CRITICAL_REFS
    setup_body = big[:return_idx]
    missing = []
    for ref in CRITICAL_REFS:
        if not re.search(rf'\b(?:const|let|var|function|async function)\s+{re.escape(ref)}\b', setup_body):
            missing.append(ref)
    return missing


def main():
    print(f"[pre-deploy-check] Validando: {ADMIN}")
    html = Path(ADMIN).read_text(encoding='utf-8')
    print(f"  Tamaño: {len(html):,} bytes")

    # 1. Sintaxis JS
    js_err = check_js_syntax(html)
    if js_err:
        errors.append(f"[1/3] {js_err}")
    else:
        print("  [OK] JS sintaxis válida (node --check)")

    # 2. Refs return vs setup
    no_def = check_return_vs_setup(html)
    if no_def:
        errors.append(f"[2/3] {len(no_def)} refs expuestas en return{{}} pero NO declaradas: {no_def[:10]}")
    else:
        print(f"  [OK] Todas las refs del return están declaradas")

    # 3. Refs críticas del login
    missing = check_critical_refs(html)
    if missing:
        errors.append(f"[3/3] Refs CRÍTICAS del login ausentes: {missing}")
    else:
        print(f"  [OK] {len(CRITICAL_REFS)} refs críticas del login presentes")

    if errors:
        print()
        print("=" * 70)
        print("DEPLOY BLOQUEADO — Bugs encontrados:")
        print("=" * 70)
        for e in errors:
            print(f"  [X] {e}")
        print()
        print("ACCIÓN: NO subir al VPS hasta arreglar. Login se colgará.")
        sys.exit(1)
    print()
    print("=" * 70)
    print("[OK] DEPLOY APROBADO — Login no se colgará")
    print("=" * 70)
    sys.exit(0)


if __name__ == '__main__':
    main()
