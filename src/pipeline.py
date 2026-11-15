"""Pipeline de ingesta: precio PVPC (REE) + clima horario (Open-Meteo) -> DuckDB.

Uso:
    python -m src.pipeline --days 7
    python -m src.pipeline --start 2024-01-01 --end 2024-01-07

Sin argumentos ingiere los últimos 7 días hasta ayer, que es la ventana que
necesita el cron diario (Open-Meteo publica los datos definitivos con retraso).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from src.load import cargar
from src.sources.openmeteo import fetch_clima
from src.sources.ree import fetch_pvpc

DB_POR_DEFECTO = "data/energia.duckdb"
TZ_LOCAL = ZoneInfo("Europe/Madrid")


def a_utc(momento: datetime) -> datetime:
    """Hora local de Madrid -> UTC sin zona, que es como se guarda en DuckDB."""
    return momento.replace(tzinfo=TZ_LOCAL).astimezone(timezone.utc).replace(tzinfo=None)


def resolver_ventana(
    start: str | None, end: str | None, days: int
) -> tuple[datetime, datetime]:
    """Devuelve la ventana [inicio, fin) en hora local de Madrid."""
    if start:
        inicio = datetime.combine(date.fromisoformat(start), time(0, 0))
    else:
        inicio = datetime.combine(date.today() - timedelta(days=days), time(0, 0))

    if end:
        fin = datetime.combine(date.fromisoformat(end) + timedelta(days=1), time(0, 0))
    else:
        fin = datetime.combine(date.today(), time(0, 0))

    if fin <= inicio:
        raise SystemExit(f"Ventana inválida: {inicio} -> {fin}")
    return inicio, fin


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", help="fecha inicial YYYY-MM-DD (hora local)")
    parser.add_argument("--end", help="fecha final YYYY-MM-DD, inclusive")
    parser.add_argument("--days", type=int, default=7, help="ventana hacia atrás")
    parser.add_argument("--db", default=DB_POR_DEFECTO, help="ruta del DuckDB")
    args = parser.parse_args(argv)

    inicio, fin = resolver_ventana(args.start, args.end, args.days)
    print(f"ventana: {inicio:%Y-%m-%d} -> {fin - timedelta(days=1):%Y-%m-%d}")

    print("extrayendo PVPC (REE)...")
    precio = fetch_pvpc(inicio, fin - timedelta(minutes=1))
    print(f"  {len(precio)} filas, zonas: {sorted(precio['zona'].unique())}")

    print("extrayendo clima (Open-Meteo)...")
    clima = fetch_clima(inicio, fin - timedelta(minutes=1))
    print(f"  {len(clima)} filas, ciudades: {sorted(clima['ciudad'].unique())}")

    resumen = cargar(
        db_path=Path(args.db),
        precio=precio,
        clima=clima,
        ventana=(a_utc(inicio), a_utc(fin)),
    )

    print("resumen:")
    for clave, valor in resumen.items():
        print(f"  {clave}: {valor}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
