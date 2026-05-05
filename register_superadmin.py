"""
Registra el super_admin_router en el main.py existente.
Ejecutar UNA sola vez después de copiar super_admin_router.py al VPS.
"""
import ast, sys

MAIN_PATH = '/var/www/sandoval/main.py'

with open(MAIN_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

print("=== REGISTER SUPER ADMIN ROUTER ===\n")

# ── Verificar si ya está registrado ─────────────────────────────────────
if 'super_admin_router' in content:
    print("✅ El router ya está registrado en main.py.")
    print("   No se realizaron cambios.")
    sys.exit(0)

# ── Añadir el import ─────────────────────────────────────────────────────
IMPORT_LINE = 'from super_admin_router import router as super_admin_router'

# Buscar el último import de la app para añadir después
import_targets = [
    'from fastapi import',
    'from nicegui import',
    'import uvicorn',
    'from utils',
    'from components',
]

insert_import_after = None
lines = content.split('\n')
for i, line in enumerate(lines):
    for target in import_targets:
        if line.startswith(target):
            insert_import_after = i

if insert_import_after is None:
    # Añadir al principio si no encontramos un buen lugar
    insert_import_after = 0

lines.insert(insert_import_after + 1, IMPORT_LINE)
content = '\n'.join(lines)
print(f"  ✅ Import añadido después de la línea {insert_import_after + 1}")

# ── Añadir app.include_router() ──────────────────────────────────────────
INCLUDE_LINE = 'app.include_router(super_admin_router)'

# Buscar app = FastAPI() para añadir include_router después
app_patterns = [
    'app = FastAPI(',
    'app = NiceGUI(',  # Por si acaso
]

insert_router_after = None
lines = content.split('\n')
for i, line in enumerate(lines):
    for pat in app_patterns:
        if pat in line:
            insert_router_after = i
            break

    # También buscar ui.run_with(app para añadir ANTES de esa línea
    if 'ui.run_with(app' in line or 'uvicorn.run' in line:
        # Añadir include_router justo ANTES de run_with o uvicorn.run
        # Pero solo si no hemos encontrado app = FastAPI todavía
        if insert_router_after is None:
            insert_router_after = i - 1

if insert_router_after is None:
    print("  ❌ No se encontró app = FastAPI() en main.py")
    print("     Añade manualmente: app.include_router(super_admin_router)")
    # Mostrar contexto del archivo
    for i, line in enumerate(lines[:50]):
        print(f"  L{i+1}: {line!r}")
else:
    # Verificar que no esté ya incluido
    if INCLUDE_LINE not in content:
        lines.insert(insert_router_after + 1, INCLUDE_LINE)
        content = '\n'.join(lines)
        print(f"  ✅ include_router añadido después de la línea {insert_router_after + 1}")
    else:
        print("  ⚠️  include_router ya existe")

# ── Verificar sintaxis ───────────────────────────────────────────────────
try:
    ast.parse(content)
    print("\n  ✅ Sintaxis OK")
except SyntaxError as e:
    print(f"\n  ❌ ERROR DE SINTAXIS en L{e.lineno}: {e.msg}")
    print("  El archivo NO fue guardado.")
    sys.exit(1)

# ── Guardar ──────────────────────────────────────────────────────────────
with open(MAIN_PATH, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\n✅ main.py actualizado correctamente.")
print("Reinicia el servicio: systemctl restart sandoval")
print("Super Admin: http://187.77.62.67:3000/superadmin")
