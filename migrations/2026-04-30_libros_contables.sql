-- =============================================================================
-- migrations/2026-04-30_libros_contables.sql
-- Módulo Libros Contables SANDOVAL PRO
-- PCGE 2019, PLE-SUNAT, doble partida estricta
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. plan_cuentas
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plan_cuentas (
    id            SERIAL PRIMARY KEY,
    taller_id     INTEGER NOT NULL,
    codigo        VARCHAR(10) NOT NULL,
    nombre        VARCHAR(200) NOT NULL,
    tipo          VARCHAR(20) NOT NULL DEFAULT 'activo',
    -- activo | pasivo | patrimonio | ingreso | gasto | costo
    nivel         SMALLINT NOT NULL DEFAULT 1,
    padre_codigo  VARCHAR(10),
    activa        BOOLEAN NOT NULL DEFAULT TRUE,
    es_sistema    BOOLEAN NOT NULL DEFAULT FALSE,
    creado_en     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_plan_cuentas_taller_codigo UNIQUE (taller_id, codigo)
);

ALTER TABLE plan_cuentas ENABLE ROW LEVEL SECURITY;
ALTER TABLE plan_cuentas FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON plan_cuentas;
CREATE POLICY tenant_isolation ON plan_cuentas
    USING (taller_id = app_current_taller())
    WITH CHECK (taller_id = app_current_taller());

CREATE INDEX IF NOT EXISTS idx_plan_cuentas_taller_cod ON plan_cuentas(taller_id, codigo);

-- ---------------------------------------------------------------------------
-- 2. asientos_contables
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asientos_contables (
    id              SERIAL PRIMARY KEY,
    taller_id       INTEGER NOT NULL,
    numero          VARCHAR(20) NOT NULL,
    -- Formato: A-AAAAMM-NNNNN
    fecha           DATE NOT NULL,
    glosa           TEXT NOT NULL DEFAULT '',
    tipo            VARCHAR(30) NOT NULL DEFAULT 'diario',
    -- diario | apertura | cierre | ajuste | extorno
    origen          VARCHAR(30),
    -- orden | nota_venta | factura | gasto | abono | manual
    origen_id       VARCHAR(50),
    estado          VARCHAR(15) NOT NULL DEFAULT 'ACTIVO',
    -- ACTIVO | ANULADO
    anulado_por     INTEGER,
    -- FK a asientos_contables(id) del extorno
    anulado_en      TIMESTAMPTZ,
    usuario         VARCHAR(100),
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_asiento_taller_numero  UNIQUE (taller_id, numero),
    CONSTRAINT uq_asiento_origen         UNIQUE (taller_id, origen, origen_id),
    CONSTRAINT chk_estado_asiento CHECK (estado IN ('ACTIVO', 'ANULADO'))
);

ALTER TABLE asientos_contables ENABLE ROW LEVEL SECURITY;
ALTER TABLE asientos_contables FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON asientos_contables;
CREATE POLICY tenant_isolation ON asientos_contables
    USING (taller_id = app_current_taller())
    WITH CHECK (taller_id = app_current_taller());

CREATE INDEX IF NOT EXISTS idx_asiento_taller_fecha ON asientos_contables(taller_id, fecha);
CREATE INDEX IF NOT EXISTS idx_asiento_taller_origen ON asientos_contables(taller_id, origen, origen_id);
CREATE INDEX IF NOT EXISTS idx_asiento_estado ON asientos_contables(taller_id, estado);

-- ---------------------------------------------------------------------------
-- 3. asiento_lineas
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asiento_lineas (
    id              SERIAL PRIMARY KEY,
    asiento_id      INTEGER NOT NULL REFERENCES asientos_contables(id) ON DELETE CASCADE,
    taller_id       INTEGER NOT NULL,
    cuenta_codigo   VARCHAR(10) NOT NULL,
    cuenta_nombre   VARCHAR(200) NOT NULL DEFAULT '',
    debe            NUMERIC(14,2) NOT NULL DEFAULT 0,
    haber           NUMERIC(14,2) NOT NULL DEFAULT 0,
    glosa           TEXT NOT NULL DEFAULT '',
    orden           SMALLINT NOT NULL DEFAULT 0,
    CONSTRAINT chk_linea_debe_nn    CHECK (debe  >= 0),
    CONSTRAINT chk_linea_haber_nn   CHECK (haber >= 0),
    CONSTRAINT chk_linea_solo_uno   CHECK (NOT (debe > 0 AND haber > 0))
);

ALTER TABLE asiento_lineas ENABLE ROW LEVEL SECURITY;
ALTER TABLE asiento_lineas FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON asiento_lineas;
CREATE POLICY tenant_isolation ON asiento_lineas
    USING (taller_id = app_current_taller())
    WITH CHECK (taller_id = app_current_taller());

CREATE INDEX IF NOT EXISTS idx_linea_asiento ON asiento_lineas(asiento_id);
CREATE INDEX IF NOT EXISTS idx_linea_taller_cuenta ON asiento_lineas(taller_id, cuenta_codigo);

-- ---------------------------------------------------------------------------
-- 4. Trigger doble-partida (Σdebe = Σhaber por asiento)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_check_doble_partida() RETURNS TRIGGER AS $$
DECLARE
    total_debe  NUMERIC(14,2);
    total_haber NUMERIC(14,2);
BEGIN
    SELECT COALESCE(SUM(debe),0), COALESCE(SUM(haber),0)
    INTO   total_debe, total_haber
    FROM   asiento_lineas
    WHERE  asiento_id = NEW.asiento_id;

    IF total_debe <> total_haber THEN
        RAISE EXCEPTION 'Doble partida violada: debe=% haber=% en asiento_id=%',
              total_debe, total_haber, NEW.asiento_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_doble_partida ON asiento_lineas;
CREATE CONSTRAINT TRIGGER trg_doble_partida
    AFTER INSERT OR UPDATE OR DELETE ON asiento_lineas
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION fn_check_doble_partida();

-- ---------------------------------------------------------------------------
-- 5. Seed PCGE 2019 — cuentas mínimas para taller_id=1
--    La función _sembrar_cuentas en el engine replica para talleres nuevos.
-- ---------------------------------------------------------------------------
INSERT INTO plan_cuentas (taller_id, codigo, nombre, tipo, nivel, padre_codigo, es_sistema)
VALUES
    (1, '10',    'EFECTIVO Y EQUIVALENTES DE EFECTIVO', 'activo',    1, NULL,  TRUE),
    (1, '101',   'Caja',                                'activo',    2, '10',  TRUE),
    (1, '1041',  'Cuentas corrientes',                  'activo',    3, '104', TRUE),
    (1, '104',   'Cuentas corrientes en instituciones financieras', 'activo', 2, '10', TRUE),
    (1, '12',    'CUENTAS POR COBRAR COMERCIALES - TERCEROS', 'activo', 1, NULL, TRUE),
    (1, '1212',  'Emitidas en cartera',                 'activo',    3, '121', TRUE),
    (1, '121',   'Facturas, boletas y otros comprobantes por cobrar', 'activo', 2, '12', TRUE),
    (1, '20',    'MERCADERIAS',                         'activo',    1, NULL,  TRUE),
    (1, '201',   'Mercaderías manufacturadas',          'activo',    2, '20',  TRUE),
    (1, '40',    'TRIBUTOS, CONTRAPRESTACIONES Y APORTES', 'pasivo', 1, NULL,  TRUE),
    (1, '401',   'Gobierno central',                    'pasivo',    2, '40',  TRUE),
    (1, '4011',  'Impuesto General a las Ventas',       'pasivo',    3, '401', TRUE),
    (1, '40111', 'IGV - Cuenta propia',                 'pasivo',    4, '4011',TRUE),
    (1, '42',    'CUENTAS POR PAGAR COMERCIALES - TERCEROS', 'pasivo', 1, NULL, TRUE),
    (1, '421',   'Facturas, boletas y otros comprobantes por pagar', 'pasivo', 2, '42', TRUE),
    (1, '60',    'COMPRAS',                             'gasto',     1, NULL,  TRUE),
    (1, '601',   'Mercaderías',                         'gasto',     2, '60',  TRUE),
    (1, '63',    'GASTOS DE SERVICIOS PRESTADOS POR TERCEROS', 'gasto', 1, NULL, TRUE),
    (1, '631',   'Transportes, correos y gastos de viaje', 'gasto',  2, '63',  TRUE),
    (1, '634',   'Mantenimiento y reparaciones',        'gasto',     2, '63',  TRUE),
    (1, '636',   'Servicios básicos',                   'gasto',     2, '63',  TRUE),
    (1, '639',   'Otros servicios prestados por terceros', 'gasto',  2, '63',  TRUE),
    (1, '70',    'VENTAS',                              'ingreso',   1, NULL,  TRUE),
    (1, '7011',  'Mercaderías',                         'ingreso',   3, '701', TRUE),
    (1, '7012',  'Servicios',                           'ingreso',   3, '701', TRUE),
    (1, '701',   'Mercaderías',                         'ingreso',   2, '70',  TRUE),
    (1, '73',    'DESCUENTOS, REBAJAS Y BONIFICACIONES OBTENIDOS', 'ingreso', 1, NULL, TRUE),
    (1, '75',    'OTROS INGRESOS DE GESTIÓN',           'ingreso',   1, NULL,  TRUE),
    (1, '751',   'Otros ingresos de gestión',           'ingreso',   2, '75',  TRUE)
ON CONFLICT (taller_id, codigo) DO NOTHING;

COMMIT;

-- Permisos sandoval_user
GRANT SELECT, INSERT, UPDATE, DELETE ON plan_cuentas, asientos_contables, asiento_lineas TO sandoval_user;
GRANT USAGE, SELECT ON SEQUENCE plan_cuentas_id_seq, asientos_contables_id_seq, asiento_lineas_id_seq TO sandoval_user;

