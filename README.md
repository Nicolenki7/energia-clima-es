# Energía y clima en España · pipeline de ingesta

Ingesta horaria de **precio de la luz (PVPC)** y **clima** para responder una pregunta
concreta: *¿qué explica el precio horario y a qué hora conviene consumir?*

Ninguna de las dos fuentes pide API key, así que cualquiera puede clonar el repo,
correr el pipeline y obtener los mismos números. Esa es la condición para que las
cifras de cualquier informe posterior se puedan auditar.

## Fuentes

| Fuente | Qué trae | Auth | Grano |
|---|---|---|---|
| [REE · apidatos](https://apidatos.ree.es) | Precio PVPC y precio del mercado spot | ninguna | hora (PVPC) y 15 min (spot) |
| [Open-Meteo · archive](https://archive-api.open-meteo.com) | Temperatura, radiación, precipitación, viento | ninguna | hora |

## Arquitectura

```
REE apidatos ─┐
              ├─► extract ─► staging (DuckDB) ─► marts (vistas) ─► CSV / artefacto
Open-Meteo ───┘
```

- **Staging**: `stg_pvpc`, `stg_clima`, con clave primaria `(zona, ts_utc)` y `(ciudad, ts_utc)`.
- **Marts**: `stg_precio_hora`, `mart_hora_energia` (precio × ciudad), `mart_dia_zona`,
  `mart_dia_ciudad`, `mart_hora_del_dia`.
- **Idempotencia**: cada corrida borra la ventana que va a escribir y la reinserta, con
  `INSERT OR REPLACE`. Correr dos veces el mismo rango deja exactamente las mismas filas
  (verificado: 336 filas de precio y 504 de clima tras tres corridas con solapamiento).
- **Ventana de 7 días por defecto**: Open-Meteo publica los datos definitivos con unos
  días de retraso, así que el cron reingiere de más y no solo "ayer".

## Uso

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m src.pipeline --days 7                              # últimos 7 días
python -m src.pipeline --start 2024-01-01 --end 2024-01-07    # ventana explícita
python -m src.pipeline --days 365 --chunk-days 30             # backfill de un año
```

La base queda en `data/energia.duckdb`. Consulta rápida:

```bash
python - <<'PY'
import duckdb
print(duckdb.sql("SELECT * FROM 'data/energia.duckdb'.mart_dia_zona ORDER BY dia_local DESC LIMIT 10").df())
PY
```

## Programación y consumo

`.github/workflows/ingest.yml` corre todos los días a las 06:15 UTC y también a mano
(`workflow_dispatch`, con la ventana y el tamaño de tramo como parámetros). Además del
artefacto, publica los marts en CSV en la rama `data`, que es la que consume el informe
de Power BI por URL:

```
https://raw.githubusercontent.com/Nicolenki7/energia-clima-es/data/mart_dia_zona.csv
```

El backfill inicial se pide a mano:

```bash
gh workflow run ingest.yml -f days=365 -f chunk_days=30
```

## Decisiones y límites conocidos

- **Zona horaria del almacenamiento**: todo se guarda en UTC sin zona (`ts_utc`) y la
  conversión se hace en la extracción, para que el join precio↔clima no dependa del
  cambio de hora.
- **Zona horaria del borrado**: la ventana del usuario está en hora de Madrid y los
  datos se guardan en UTC. Si no se convierte, el borrado no cubre lo insertado y la
  clave primaria explota en la segunda corrida. Pasó en la primera versión.
- **Día y hora de negocio en Madrid**: en DuckDB, `timezone('Europe/Madrid', ts)`
  interpreta el timestamp como si ya fuera de Madrid y devuelve el instante UTC, o sea
  al revés. La forma correcta es `(ts_utc AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Madrid'`.
- **Grano**: el clima existe una vez por hora y ciudad, y el precio una vez por hora y
  serie después de normalizarlo. Agregar todo junto contaría cada hora tres veces (una
  por ciudad) y los promedios de precio saldrían mal; por eso hay marts separados y el
  cruce ocurre en la vista horaria.
- **Granularidad desigual de REE**: el PVPC viene una vez por hora, pero el precio del
  mercado spot viene cada 15 minutos (cuatro filas por hora). Si se agrega el crudo,
  el spot tendría 96 "horas" por día y el join con el clima quedaría nulo en tres de
  cada cuatro filas. Por eso `stg_precio_hora` colapsa cada serie a una fila por hora
  antes de cualquier agregación, y guarda cuántas observaciones promedió. Con eso un
  día normal tiene 24 horas, 23 el día que se adelanta la hora y 25 el que se atrasa.
- **`LEFT JOIN` precio → clima**: si falta una hora de clima, la fila de precio se
  conserva con nulos en vez de desaparecer. Un hueco debe verse, no esconderse.
- **Rangos largos en REE**: además de los 503, la API responde 400 "datos no
  disponibles" cuando el rango pedido es grande, aunque esos mismos días pedidos de a
  poco sí estén. Por eso un tramo rechazado se reintenta partido a la mitad hasta que
  entra; si un solo día falla de verdad, se anota y la corrida informa el hueco en vez
  de rellenarlo.
- **Series de REE**: el endpoint devuelve dos series, `PVPC` (lo que paga un hogar con
  tarifa regulada) y `Precio mercado spot` (el mayorista). Se cargan ambas y se
  distinguen por la columna `zona`.
- **Reintentos**: la API de REE devuelve 503 intermitentes si se piden varias ventanas
  seguidas. `src/http.py` reintenta con backoff exponencial (5 intentos) en lugar de
  romper la corrida.
- **Sin datos de consumo**: el informe responde sobre precio y clima, no sobre demanda
  horaria real. Para cerrar ese círculo, la fuente siguiente es Red Eléctrica
  (demanda real por hora).
- **Sin base de datos servida**: DuckDB deja el proyecto reproducible sin
  infraestructura. El paso siguiente, si hace falta servir el dato a Power BI en vivo,
  es cargar los marts en Postgres (Supabase).
