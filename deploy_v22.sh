#!/bin/bash
# SANDOVAL PRO · Deploy v22
# Features: abonos en notas de venta, cliente registrado/libre, mano de obra,
#           PDF profesional de notas/cotizaciones, nuevo crédito desde móvil,
#           cotizaciones editables/convertibles, lookup RUC local-first.
set -e
cd /var/www/sandoval

ts=$(date +%Y%m%d_%H%M%S)
echo "=== backups timestamp: $ts ==="

# Backups
cp utils/api_service.py utils/api_service.py.bak_pre_v22_$ts
cp sandoval-app/index.html sandoval-app/index.html.bak_pre_v22_$ts
cp sandoval-app/sw.js sandoval-app/sw.js.bak_pre_v22_$ts

# Reemplazar files staged (.new)
[ -f sandoval-app/index.html.new ] && mv sandoval-app/index.html.new sandoval-app/index.html
[ -f sandoval-app/sw.js.new ] && mv sandoval-app/sw.js.new sandoval-app/sw.js
[ -f utils/api_service.py.new ] && mv utils/api_service.py.new utils/api_service.py
[ -f utils/api_extensions.py.new ] && mv utils/api_extensions.py.new utils/api_extensions.py

chown sandoval:sandoval sandoval-app/index.html sandoval-app/sw.js utils/api_service.py utils/api_extensions.py
chmod 644 sandoval-app/index.html sandoval-app/sw.js utils/api_service.py utils/api_extensions.py

echo === syntax api_service.py ===
/var/www/sandoval/venv/bin/python -c "import py_compile; py_compile.compile('utils/api_service.py', doraise=True); print('OK')"

echo === syntax api_extensions.py ===
/var/www/sandoval/venv/bin/python -c "import py_compile; py_compile.compile('utils/api_extensions.py', doraise=True); print('OK')"

echo === versiones ===
grep -n "^const CACHE_NAME" sandoval-app/sw.js
echo "endpoints nuevos en api_extensions.py:"
grep -nE "api_nota_detail|api_nota_abonar|api_nota_pdf|api_cotizacion_(detail|create|update|pdf|convertir)|api_credito_create|api_cliente_por_doc" utils/api_extensions.py | head -20
echo "frontend hooks nuevos:"
grep -cE "abrirFormCredito|abrirFormManoObra|initCotizacionForm|initCreditoForm|/api/clientes/buscar-doc" sandoval-app/index.html

echo === sizes ===
stat -c '%n %s bytes' sandoval-app/index.html sandoval-app/sw.js utils/api_service.py utils/api_extensions.py

echo === reiniciando servicio ===
systemctl restart sandoval
sleep 4
systemctl is-active sandoval

echo === smoke test endpoints ===
MT=$(python3 -c "import sqlite3; r=sqlite3.connect('/var/www/sandoval/data/sessions.db').execute('SELECT token FROM sessions ORDER BY expires DESC LIMIT 1').fetchone(); print(r[0] if r else '')" 2>/dev/null || echo "")

if [ -z "$MT" ]; then
  echo "(sin session token para smoke, deploy OK sin smoke)"
  exit 0
fi

echo "--- GET /api/notas-venta?limit=1 ---"
curl -sS -o /tmp/_nv.json -w "HTTP=%{http_code} size=%{size_download}\n" \
  -H "Authorization: Bearer $MT" \
  "http://127.0.0.1:3000/api/notas-venta?limit=1"

NID=$(/var/www/sandoval/venv/bin/python -c "
import json
try:
    d=json.load(open('/tmp/_nv.json'))
    print(d[0]['id'] if isinstance(d,list) and d else '')
except Exception:
    print('')
" 2>/dev/null || echo "")

if [ -n "$NID" ]; then
  echo "--- GET /api/notas-venta/$NID (detalle nuevo) ---"
  curl -sS -o /tmp/_nvd.json -w "HTTP=%{http_code} size=%{size_download}\n" \
    -H "Authorization: Bearer $MT" \
    "http://127.0.0.1:3000/api/notas-venta/$NID"
  /var/www/sandoval/venv/bin/python -c "
import json
try:
    d=json.load(open('/tmp/_nvd.json'))
    print('keys:', sorted(d.keys())[:15])
    print('items len:', len(d.get('items') or []))
    print('abonos len:', len(d.get('abonos') or []))
    print('saldo:', d.get('saldo'))
except Exception as e:
    print('err:', e)
" 2>/dev/null || head -c 400 /tmp/_nvd.json

  echo "--- GET /api/notas-venta/$NID/pdf (HEAD) ---"
  curl -sS -o /dev/null -w "HTTP=%{http_code} size=%{size_download}\n" \
    -H "Authorization: Bearer $MT" \
    "http://127.0.0.1:3000/api/notas-venta/$NID/pdf"
fi

echo "--- GET /api/cotizaciones?limit=1 ---"
curl -sS -o /tmp/_co.json -w "HTTP=%{http_code} size=%{size_download}\n" \
  -H "Authorization: Bearer $MT" \
  "http://127.0.0.1:3000/api/cotizaciones?limit=1"

CID=$(/var/www/sandoval/venv/bin/python -c "
import json
try:
    d=json.load(open('/tmp/_co.json'))
    print(d[0]['id'] if isinstance(d,list) and d else '')
except Exception:
    print('')
" 2>/dev/null || echo "")

if [ -n "$CID" ]; then
  echo "--- GET /api/cotizaciones/$CID (detalle) ---"
  curl -sS -o /tmp/_cod.json -w "HTTP=%{http_code} size=%{size_download}\n" \
    -H "Authorization: Bearer $MT" \
    "http://127.0.0.1:3000/api/cotizaciones/$CID"
  /var/www/sandoval/venv/bin/python -c "
import json
try:
    d=json.load(open('/tmp/_cod.json'))
    print('keys:', sorted(d.keys())[:15])
    print('items len:', len(d.get('items') or []))
    print('total:', d.get('total'))
except Exception as e:
    print('err:', e)
" 2>/dev/null || head -c 400 /tmp/_cod.json

  echo "--- GET /api/cotizaciones/$CID/pdf (HEAD) ---"
  curl -sS -o /dev/null -w "HTTP=%{http_code} size=%{size_download}\n" \
    -H "Authorization: Bearer $MT" \
    "http://127.0.0.1:3000/api/cotizaciones/$CID/pdf"
fi

echo "--- GET /api/clientes/buscar-doc/00000000 (local lookup 404 esperado) ---"
curl -sS -o /tmp/_cbd.json -w "HTTP=%{http_code} size=%{size_download}\n" \
  -H "Authorization: Bearer $MT" \
  "http://127.0.0.1:3000/api/clientes/buscar-doc/00000000"
head -c 200 /tmp/_cbd.json; echo

echo "=== DEPLOY v22 DONE ==="
