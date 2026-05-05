-- ============================================================
-- SANDOVAL — RLS Fase 2 (STRICT) — APLICAR SOLO TRAS MIDDLEWARE
-- ============================================================
-- PRE-REQUISITO: el backend DEBE setear app.taller_id en CADA request DB
-- (vía SET LOCAL app.taller_id = '...' o event listener SQLAlchemy).
--
-- Si se aplica este script SIN middleware → todas las queries devuelven
-- 0 filas (la app se ve vacía).
--
-- Cómo activar (un comando por tabla):
--   ALTER TABLE <tabla> FORCE ROW LEVEL SECURITY;
--   DROP POLICY tenant_isolation ON <tabla>;
--   CREATE POLICY tenant_isolation ON <tabla>
--     USING (taller_id = app_current_taller())
--     WITH CHECK (taller_id = app_current_taller());
-- ============================================================

-- Aplicar a TODAS las tablas con taller_id (descubrimiento dinámico):
DO $$
DECLARE
    t text;
BEGIN
    FOR t IN
        SELECT table_name FROM information_schema.columns
        WHERE column_name = 'taller_id' AND table_schema = 'public'
    LOOP
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON public.%I', t);
        EXECUTE format($p$
            CREATE POLICY tenant_isolation ON public.%I
                AS PERMISSIVE FOR ALL TO PUBLIC
                USING (taller_id = app_current_taller())
                WITH CHECK (taller_id = app_current_taller())
        $p$, t);
        RAISE NOTICE 'STRICT enabled on %', t;
    END LOOP;
END $$;
