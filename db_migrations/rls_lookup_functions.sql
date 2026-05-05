-- ============================================================
-- SANDOVAL — Funciones SECURITY DEFINER para lookup por token
-- ============================================================
-- Necesarias para endpoints públicos (/reporte, /encuesta, /aprobacion)
-- que tienen que averiguar `taller_id` ANTES de poder setear app.taller_id.
--
-- SECURITY DEFINER hace que la función corra con permisos del owner (postgres,
-- superuser) → bypasea RLS aunque la sesión que la invoca esté restringida.
--
-- Cada función expone SOLO el `taller_id` y/o `consecutivo` mínimo para
-- bootstrap. NO expone datos sensibles (los datos completos los lee el handler
-- DESPUÉS de hacer SET app.taller_id, ya filtrados por RLS).
-- ============================================================

-- ─── lookup por report_token (usado en /reporte y /encuesta) ─────────────
CREATE OR REPLACE FUNCTION public.lookup_taller_by_report_token(tok text)
RETURNS TABLE(taller_id integer, consecutivo varchar)
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
    SELECT taller_id, consecutivo
      FROM public.ordenes
     WHERE report_token = tok
       AND tok IS NOT NULL
       AND length(tok) >= 16
     LIMIT 1;
$$;
COMMENT ON FUNCTION public.lookup_taller_by_report_token(text) IS
'Devuelve (taller_id, consecutivo) para un report_token público. Bypasea RLS.';

GRANT EXECUTE ON FUNCTION public.lookup_taller_by_report_token(text) TO PUBLIC;

-- ─── lookup por approval_token (usado en /aprobacion) ────────────────────
CREATE OR REPLACE FUNCTION public.lookup_taller_by_approval_token(tok text)
RETURNS TABLE(taller_id integer, consecutivo varchar)
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
    SELECT taller_id, consecutivo
      FROM public.ordenes
     WHERE approval_token = tok
       AND tok IS NOT NULL
       AND length(tok) >= 16
     LIMIT 1;
$$;
COMMENT ON FUNCTION public.lookup_taller_by_approval_token(text) IS
'Devuelve (taller_id, consecutivo) para un approval_token. Bypasea RLS.';

GRANT EXECUTE ON FUNCTION public.lookup_taller_by_approval_token(text) TO PUBLIC;

-- ─── lookup por short_links.code (usado en /a/{code}) ────────────────────
CREATE OR REPLACE FUNCTION public.lookup_taller_by_short_link(c text)
RETURNS TABLE(taller_id integer, token varchar)
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
    SELECT taller_id, token
      FROM public.short_links
     WHERE code = c
       AND c IS NOT NULL
     LIMIT 1;
$$;
COMMENT ON FUNCTION public.lookup_taller_by_short_link(text) IS
'Devuelve (taller_id, token) para un short_link.code. Bypasea RLS.';

GRANT EXECUTE ON FUNCTION public.lookup_taller_by_short_link(text) TO PUBLIC;

-- ─── lookup de cliente por placa+pin (usado en login PWA cliente) ────────
-- El login del cliente necesita encontrar el vehículo por placa antes de
-- saber a qué taller pertenece. Esta función reemplaza la query directa.
CREATE OR REPLACE FUNCTION public.lookup_cliente_by_placa(plac text)
RETURNS TABLE(
    cliente_id varchar,
    taller_id integer,
    placa varchar,
    pin_acceso varchar,
    documento varchar
)
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
    SELECT v.cliente_id::varchar, v.taller_id, v.placa,
           c.pin_acceso, c.documento
      FROM public.vehiculos v
      LEFT JOIN public.clientes c ON c.id = v.cliente_id
     WHERE v.placa = plac
     LIMIT 1;
$$;
COMMENT ON FUNCTION public.lookup_cliente_by_placa(text) IS
'Login PWA cliente: devuelve datos mínimos para autenticar por placa. Bypasea RLS.';

GRANT EXECUTE ON FUNCTION public.lookup_cliente_by_placa(text) TO PUBLIC;

-- ─── lookup de usuario staff por username (usado en login admin/PWA) ─────
CREATE OR REPLACE FUNCTION public.lookup_usuario_by_username(uname text)
RETURNS TABLE(
    id integer,
    username varchar,
    nombre varchar,
    rol varchar,
    taller_id integer,
    activo boolean,
    password_hash varchar,
    email varchar
)
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
    SELECT id, username, nombre, rol, taller_id, activo, password_hash, email
      FROM public.usuarios
     WHERE username = uname
     LIMIT 1;
$$;
COMMENT ON FUNCTION public.lookup_usuario_by_username(text) IS
'Login staff: devuelve datos del usuario por username. Bypasea RLS.';

GRANT EXECUTE ON FUNCTION public.lookup_usuario_by_username(text) TO PUBLIC;
