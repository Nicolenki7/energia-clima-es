"""Precios de la luz (PVPC) desde la API abierta de REE.

API apidatos.ree.es: no requiere token ni registro.
Devuelve series horarias en EUR/MWh por zona (península, Canarias, Baleares).
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import requests

from src.http import get_json

URL = "https://apidatos.ree.es/es/datos/mercados/precios-mercados-tiempo-real"
TZ_MADRID = "Europe/Madrid"


def fetch_pvpc(start: datetime, end: datetime, timeout: int = 30) -> pd.DataFrame:
    """Descarga el precio horario PVPC entre dos fechas (inclusive, en hora local).

    Devuelve columnas: zona, ts_utc, precio_eur_mwh.
    El timestamp se normaliza a UTC sin zona para que el join con el clima sea exacto.
    """
    params = {
        "start_date": start.strftime("%Y-%m-%dT%H:%M"),
        "end_date": end.strftime("%Y-%m-%dT%H:%M"),
        "time_trunc": "hour",
    }
    payload = get_json(URL, params, timeout=timeout)

    filas: list[dict] = []
    for serie in payload.get("included", []):
        zona = serie.get("type") or str(serie.get("id"))
        valores = serie.get("attributes", {}).get("values", [])
        for valor in valores:
            filas.append(
                {
                    "zona": zona,
                    "ts_local": valor["datetime"],
                    "precio_eur_mwh": valor["value"],
                }
            )

    if not filas:
        raise ValueError("REE no devolvió valores para el rango pedido")

    df = pd.DataFrame(filas)
    df["ts_utc"] = (
        pd.to_datetime(df["ts_local"], utc=True)
        .dt.tz_convert("UTC")
        .dt.tz_localize(None)
    )
    df["precio_eur_mwh"] = pd.to_numeric(df["precio_eur_mwh"], errors="coerce")
    df = df.dropna(subset=["precio_eur_mwh"])
    return df[["zona", "ts_utc", "precio_eur_mwh"]].drop_duplicates(["zona", "ts_utc"])
