-- Marts: se reconstruyen en cada corrida (vistas, no tablas).
-- El join es por ts_utc, la única clave que ambas fuentes comparten sin ambigüedad.
-- Día y hora de negocio son los de Madrid: "a qué hora conviene consumir" no tiene
-- sentido en UTC.
--
-- Ojo con el grano: el precio existe una vez por hora y zona, el clima una vez por
-- hora y ciudad. Si se agregara todo junto, cada hora se contaría tres veces (una por
-- ciudad) y los promedios de precio saldrían mal. Por eso precio y clima se resumen
-- en marts separados y se cruzan recién en la vista horaria.
--
-- Ojo con la zona horaria: en DuckDB, timezone('Europe/Madrid', ts) interpreta el
-- timestamp como si YA fuera de Madrid y devuelve el instante UTC, o sea al revés de
-- lo que uno quiere. La forma correcta es encadenar AT TIME ZONE:
--     (ts_utc AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Madrid'

CREATE OR REPLACE VIEW mart_hora_energia AS
WITH base AS (
    SELECT
        p.ts_utc,
        ((p.ts_utc AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Madrid') AS ts_local,
        p.zona,
        p.precio_eur_mwh,
        c.ciudad,
        c.temp_c,
        c.radiacion_wm2,
        c.precipitacion_mm,
        c.viento_kmh
    FROM stg_pvpc p
    LEFT JOIN stg_clima c USING (ts_utc)
)
SELECT
    ts_utc,
    ts_local,
    zona,
    precio_eur_mwh,
    precio_eur_mwh / 1000.0                      AS precio_eur_kwh,
    ciudad,
    temp_c,
    radiacion_wm2,
    precipitacion_mm,
    viento_kmh,
    ts_local::DATE                               AS dia_local,
    extract(hour FROM ts_local)                  AS hora_local
FROM base;

-- Precio por día y zona: 24 filas por día y serie.
CREATE OR REPLACE VIEW mart_dia_zona AS
WITH base AS (
    SELECT
        zona,
        ((ts_utc AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Madrid') AS ts_local,
        precio_eur_mwh
    FROM stg_pvpc
)
SELECT
    zona,
    ts_local::DATE            AS dia_local,
    count(*)                  AS horas,
    round(avg(precio_eur_mwh), 2) AS precio_medio_eur_mwh,
    round(min(precio_eur_mwh), 2) AS precio_min_eur_mwh,
    round(max(precio_eur_mwh), 2) AS precio_max_eur_mwh
FROM base
GROUP BY zona, ts_local::DATE;

-- Clima por día y ciudad: 24 filas por día y ciudad.
CREATE OR REPLACE VIEW mart_dia_ciudad AS
WITH base AS (
    SELECT
        ciudad,
        ((ts_utc AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Madrid') AS ts_local,
        temp_c,
        radiacion_wm2,
        precipitacion_mm
    FROM stg_clima
)
SELECT
    ciudad,
    ts_local::DATE               AS dia_local,
    count(*)                     AS horas,
    round(avg(temp_c), 1)        AS temp_media_c,
    round(min(temp_c), 1)        AS temp_min_c,
    round(max(temp_c), 1)        AS temp_max_c,
    round(sum(radiacion_wm2) / 1000.0, 1) AS radiacion_kwh_m2,
    round(sum(precipitacion_mm), 1)       AS precipitacion_mm
FROM base
GROUP BY ciudad, ts_local::DATE;

-- Hora del día: en qué franja conviene consumir, por zona y serie.
CREATE OR REPLACE VIEW mart_hora_del_dia AS
WITH base AS (
    SELECT
        zona,
        ((ts_utc AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Madrid') AS ts_local,
        precio_eur_mwh
    FROM stg_pvpc
)
SELECT
    zona,
    extract(hour FROM ts_local)   AS hora_local,
    round(avg(precio_eur_mwh), 2) AS precio_medio_eur_mwh,
    count(*)                      AS observaciones
FROM base
GROUP BY zona, extract(hour FROM ts_local);
