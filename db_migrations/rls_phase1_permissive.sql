-- ============================================================
-- SANDOVAL — Row Level Security (RLS) — Fase 1
-- ============================================================
-- ESTRATEGIA: defensa en profundidad sin romper código existente.
-- - Policy permisiva: si app.taller_id NO está seteada, deja pasar TODO.
-- - Si está seteada, filtra por ese taller.
-- - NO usar FORCE ROW LEVEL SECURITY hasta que el middleware se haya validado.
--
-- IMPACTO ESPERADO: ZERO regresión funcional. Sistema sigue trabajando igual.
-- BENEFICIO INMEDIATO: cada nueva sesión PG que setee app.taller_id obtendrá
-- aislamiento automático aunque el código olvide filtrar.
-- ============================================================

-- Helper: GRANT bypass NO se usa. sandoval_user es no-superuser y SÍ
-- queda sujeto a las policies. Pero la policy es permisiva por default.

-- Función helper para evitar repetir la lógica en cada policy
CREATE OR REPLACE FUNCTION app_current_taller() RETURNS integer AS $$
DECLARE
    v text;
BEGIN
    v := current_setting('app.taller_id', true);
    IF v IS NULL OR v = '' THEN
        RETURN NULL;
    END IF;
    BEGIN
        RETURN v::integer;
    EXCEPTION WHEN others THEN
        RETURN NULL;
    END;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION app_current_taller() IS
'Devuelve el taller_id de la sesión actual desde app.taller_id (SET LOCAL), o NULL si no está seteado.';

-- Política reutilizable a través de macro: la replicamos en cada tabla con el mismo patrón
-- Pattern: USING (app_current_taller() IS NULL OR taller_id = app_current_taller())

-- ─── Tabla: clientes ─────────────────────────────────────────
ALTER TABLE public.clientes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.clientes;
CREATE POLICY tenant_isolation ON public.clientes
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: vehiculos ────────────────────────────────────────
ALTER TABLE public.vehiculos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.vehiculos;
CREATE POLICY tenant_isolation ON public.vehiculos
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: ordenes ──────────────────────────────────────────
ALTER TABLE public.ordenes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.ordenes;
CREATE POLICY tenant_isolation ON public.ordenes
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: inventario ───────────────────────────────────────
ALTER TABLE public.inventario ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.inventario;
CREATE POLICY tenant_isolation ON public.inventario
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: facturas ─────────────────────────────────────────
ALTER TABLE public.facturas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.facturas;
CREATE POLICY tenant_isolation ON public.facturas
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: notas_venta ──────────────────────────────────────
ALTER TABLE public.notas_venta ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.notas_venta;
CREATE POLICY tenant_isolation ON public.notas_venta
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: cotizaciones ─────────────────────────────────────
ALTER TABLE public.cotizaciones ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.cotizaciones;
CREATE POLICY tenant_isolation ON public.cotizaciones
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: proveedores ──────────────────────────────────────
ALTER TABLE public.proveedores ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.proveedores;
CREATE POLICY tenant_isolation ON public.proveedores
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: creditos ─────────────────────────────────────────
ALTER TABLE public.creditos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.creditos;
CREATE POLICY tenant_isolation ON public.creditos
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: abonos_credito ───────────────────────────────────
ALTER TABLE public.abonos_credito ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.abonos_credito;
CREATE POLICY tenant_isolation ON public.abonos_credito
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: citas ────────────────────────────────────────────
ALTER TABLE public.citas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.citas;
CREATE POLICY tenant_isolation ON public.citas
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: cierres_caja ─────────────────────────────────────
ALTER TABLE public.cierres_caja ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.cierres_caja;
CREATE POLICY tenant_isolation ON public.cierres_caja
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: gastos_operacionales ─────────────────────────────
ALTER TABLE public.gastos_operacionales ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.gastos_operacionales;
CREATE POLICY tenant_isolation ON public.gastos_operacionales
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: cuentas_bancarias ────────────────────────────────
ALTER TABLE public.cuentas_bancarias ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.cuentas_bancarias;
CREATE POLICY tenant_isolation ON public.cuentas_bancarias
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: trabajadores ─────────────────────────────────────
ALTER TABLE public.trabajadores ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.trabajadores;
CREATE POLICY tenant_isolation ON public.trabajadores
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: pagos_trabajadores ───────────────────────────────
ALTER TABLE public.pagos_trabajadores ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.pagos_trabajadores;
CREATE POLICY tenant_isolation ON public.pagos_trabajadores
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: usuarios ─────────────────────────────────────────
ALTER TABLE public.usuarios ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.usuarios;
CREATE POLICY tenant_isolation ON public.usuarios
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: actividades ──────────────────────────────────────
ALTER TABLE public.actividades ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.actividades;
CREATE POLICY tenant_isolation ON public.actividades
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: ordenes_computadoras ─────────────────────────────
ALTER TABLE public.ordenes_computadoras ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.ordenes_computadoras;
CREATE POLICY tenant_isolation ON public.ordenes_computadoras
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: short_links ──────────────────────────────────────
ALTER TABLE public.short_links ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.short_links;
CREATE POLICY tenant_isolation ON public.short_links
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: push_subscriptions ───────────────────────────────
ALTER TABLE public.push_subscriptions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.push_subscriptions;
CREATE POLICY tenant_isolation ON public.push_subscriptions
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: config_sistema ───────────────────────────────────
ALTER TABLE public.config_sistema ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.config_sistema;
CREATE POLICY tenant_isolation ON public.config_sistema
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: eventos_seguridad ────────────────────────────────
ALTER TABLE public.eventos_seguridad ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.eventos_seguridad;
CREATE POLICY tenant_isolation ON public.eventos_seguridad
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: ips_bloqueadas ───────────────────────────────────
ALTER TABLE public.ips_bloqueadas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.ips_bloqueadas;
CREATE POLICY tenant_isolation ON public.ips_bloqueadas
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());

-- ─── Tabla: talleres_pagos ───────────────────────────────────
ALTER TABLE public.talleres_pagos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.talleres_pagos;
CREATE POLICY tenant_isolation ON public.talleres_pagos
    AS PERMISSIVE FOR ALL TO PUBLIC
    USING (app_current_taller() IS NULL OR taller_id = app_current_taller())
    WITH CHECK (app_current_taller() IS NULL OR taller_id = app_current_taller());
