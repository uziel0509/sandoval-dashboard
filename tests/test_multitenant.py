"""
test_multitenant.py — auditoría automática del filtro taller_id.

Objetivo: prevenir que un PR nuevo introduzca una query sobre una tabla
multi-tenant sin filtrarla por taller_id. Se puede correr en CI como gate.

Ejecutar:
    cd /var/www/sandoval && /var/www/sandoval/venv/bin/python -m pytest tests/test_multitenant.py -v
"""
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ROUTERS = ROOT / "routers"
UTILS = ROOT / "utils"

# Tablas que SIEMPRE deben filtrarse por taller_id cuando se leen/escriben.
MULTITENANT_TABLES = {
    "clientes", "vehiculos", "ordenes", "items_inventario",
    "movimientos_inventario", "notas_venta", "facturas",
    "cotizaciones", "creditos", "pagos_credito", "citas",
    "actividad", "caja_movimientos", "usuarios", "proveedores",
    "notas_caja", "presupuestos", "configuracion",
}

# Patrones que matchean SELECT/UPDATE/INSERT/DELETE ... tabla
SQL_VERB_RX = re.compile(
    r"(?:FROM|JOIN|UPDATE|INTO|DELETE\s+FROM)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)


def _extract_sql_statements(py_text: str) -> list[tuple[int, str]]:
    """Devuelve lista (linea_aprox, sql) de todos los text("...") del archivo.

    Cubre text("..."), text('...'), text(\"\"\"...\"\"\")  y f-strings.
    Es una heurística — no un parser SQL — suficiente para auditoría.
    """
    results: list[tuple[int, str]] = []
    # text( ... ) con delimitadores variados. re.DOTALL para multilinea.
    pattern = re.compile(r"text\s*\(\s*(?:f)?([\"']{1,3})(.*?)\1\s*\)", re.DOTALL)
    for m in pattern.finditer(py_text):
        sql = m.group(2)
        line = py_text.count("\n", 0, m.start()) + 1
        results.append((line, sql))
    return results


def _statement_touches_multitenant(sql: str) -> set[str]:
    tables_found: set[str] = set()
    for m in SQL_VERB_RX.finditer(sql):
        t = m.group(1).lower()
        if t in MULTITENANT_TABLES:
            tables_found.add(t)
    return tables_found


def _iter_python_files():
    for folder in (ROUTERS, UTILS):
        if not folder.exists():
            continue
        for path in folder.glob("*.py"):
            if path.name.startswith("_") and path.name != "_common.py":
                continue
            if ".bak" in path.name:
                continue
            yield path


def _find_offenders():
    """Escanea routers/ y utils/ buscando queries multi-tenant sin filtro."""
    offenders = []
    for path in _iter_python_files():
        src = path.read_text(encoding="utf-8", errors="ignore")
        for line, sql in _extract_sql_statements(src):
            tables = _statement_touches_multitenant(sql)
            if not tables:
                continue
            # Reglas de seguridad: si la query es un INSERT que cita taller_id
            # en la columna, también lo aceptamos. Si menciona 'taller_id' en
            # cualquier parte (WHERE / VALUES), asumimos que filtra.
            if "taller_id" in sql:
                continue
            # Los selects globales de catalogo (ej "SELECT 1 FROM usuarios LIMIT 1")
            # para healthchecks suelen incluir 'LIMIT 1' sin WHERE. Lo marcamos
            # igualmente; el dev debe agregar taller_id o excluir explícitamente.
            offenders.append({
                "file": str(path.relative_to(ROOT)),
                "line": line,
                "tables": sorted(tables),
                "sql": re.sub(r"\s+", " ", sql).strip()[:200],
            })
    return offenders


def test_tenant_helpers_available():
    """Los helpers nuevos deben estar importables desde routers._common."""
    import sys
    sys.path.insert(0, str(ROOT))
    from routers._common import tenant_sql, tenant_filter, _tenant_id  # noqa: F401

    # tenant_sql inyecta taller_id desde el JWT
    stmt, params = tenant_sql(
        "SELECT 1 FROM clientes WHERE taller_id=:taller_id",
        tok={"taller_id": 42},
    )
    assert params["taller_id"] == 42

    # 2026-04-29: comportamiento estricto post-audit. Sin tok valido,
    # _tenant_id() lanza HTTPException 401 (anti-IDOR). Este es el nuevo
    # contrato para evitar fallback silencioso a taller_id=1 en multi-tenant.
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        tenant_sql("SELECT 1 FROM clientes WHERE taller_id=:taller_id")
    assert exc_info.value.status_code == 401

    # query sin 'taller_id' en el SQL debe fallar: previene olvidos
    with pytest.raises(AssertionError):
        tenant_sql("SELECT 1 FROM clientes", tok={"taller_id": 1})


def test_no_multitenant_query_without_filter():
    """CI gate: ningún SELECT/UPDATE/DELETE sobre tabla multi-tenant sin taller_id."""
    offenders = _find_offenders()
    if offenders:
        msg_lines = [f"{len(offenders)} queries multi-tenant sin filtro por taller_id:"]
        for o in offenders[:50]:
            msg_lines.append(
                f"  {o['file']}:{o['line']}  tablas={o['tables']}\n    {o['sql']}"
            )
        if len(offenders) > 50:
            msg_lines.append(f"  … y {len(offenders) - 50} más")
        pytest.fail("\n".join(msg_lines))


def test_extract_sql_smoke():
    """Smoke: el extractor reconoce text(\"...\") simples."""
    fake = 'db.execute(text("SELECT * FROM clientes WHERE taller_id=:t"))'
    stmts = _extract_sql_statements(fake)
    assert len(stmts) == 1
    assert "clientes" in _statement_touches_multitenant(stmts[0][1])
