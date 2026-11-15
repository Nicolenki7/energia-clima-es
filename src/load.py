"""Carga idempotente en DuckDB: staging + marts.

Regla: cada corrida borra la ventana de fechas que va a escribir y la vuelve a
insertar. Correr dos veces el mismo rango deja exactamente las mismas filas.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

SQL_MARTS = Path(__file__).resolve().parents[1] / "sql" / "marts.sql"

DDL = """
CREATE TABLE IF NOT EXISTS stg_pvpc (
    zona            VARCHAR NOT NULL,
    ts_utc          TIMESTAMP NOT NULL,
    precio_eur_mwh  DOUBLE NOT NULL,
    PRIMARY KEY (zona, ts_utc)
);
CREATE TABLE IF NOT EXISTS stg_clima (
    ciudad           VARCHAR NOT NULL,
    ts_utc           TIMESTAMP NOT NULL,
    temp_c           DOUBLE,
    radiacion_wm2    DOUBLE,
    precipitacion_mm DOUBLE,
    viento_kmh       DOUBLE,
    PRIMARY KEY (ciudad, ts_utc)
);
"""


def _insertar(con: duckdb.DuckDBPyConnection, tabla: str, df: pd.DataFrame) -> int:
    columnas = ", ".join(df.columns)
    marcadores = ", ".join("?" for _ in df.columns)
    filas = [tuple(fila) for fila in df.itertuples(index=False, name=None)]
    if filas:
        # INSERT OR REPLACE: si una fuente revisa un valor pasado, gana el nuevo
        # y la clave primaria evita duplicados aunque la ventana se superponga.
        con.executemany(
            f"INSERT OR REPLACE INTO {tabla} ({columnas}) VALUES ({marcadores})", filas
        )
    return len(filas)


def cargar(
    db_path: Path,
    precio: pd.DataFrame,
    clima: pd.DataFrame,
    ventana: tuple[datetime, datetime],
) -> dict[str, int]:
    """Escribe la ventana en staging y reconstruye los marts."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    inicio, fin = ventana

    # Las fuentes devuelven alguna hora de más alrededor del rango pedido.
    # Se recorta a la ventana para que staging y marts tengan exactamente el mismo borde.
    precio = precio[(precio["ts_utc"] >= inicio) & (precio["ts_utc"] < fin)]
    clima = clima[(clima["ts_utc"] >= inicio) & (clima["ts_utc"] < fin)]

    con = duckdb.connect(str(db_path))
    try:
        con.execute(DDL)
        con.execute("DELETE FROM stg_pvpc  WHERE ts_utc >= ? AND ts_utc < ?", [inicio, fin])
        con.execute("DELETE FROM stg_clima WHERE ts_utc >= ? AND ts_utc < ?", [inicio, fin])
        filas_precio = _insertar(con, "stg_pvpc", precio)
        filas_clima = _insertar(con, "stg_clima", clima)
        con.execute(SQL_MARTS.read_text(encoding="utf-8"))
        total_precio = con.execute("SELECT count(*) FROM stg_pvpc").fetchone()[0]
        total_clima = con.execute("SELECT count(*) FROM stg_clima").fetchone()[0]
    finally:
        con.close()

    return {
        "filas_precio_ventana": filas_precio,
        "filas_clima_ventana": filas_clima,
        "total_precio": int(total_precio),
        "total_clima": int(total_clima),
    }
