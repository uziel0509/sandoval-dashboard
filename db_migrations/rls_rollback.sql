-- ============================================================
-- SANDOVAL — RLS rollback completo (revierte Fase 1 y Fase 2)
-- Aplicar como postgres superuser:
--   sudo -u postgres psql sandoval_saas -f /tmp/rls_rollback.sql
-- ============================================================
DO $$
DECLARE
    t text;
BEGIN
    FOR t IN
        SELECT table_name FROM information_schema.columns
        WHERE column_name = 'taller_id' AND table_schema = 'public'
    LOOP
        EXECUTE format('ALTER TABLE public.%I NO FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON public.%I', t);
        RAISE NOTICE 'RLS reverted on %', t;
    END LOOP;
END $$;

DROP FUNCTION IF EXISTS app_current_taller();
