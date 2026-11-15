"""Clima horario desde Open-Meteo (archive API).

Sin API key. La API de archivo tiene ~5 días de latencia en los datos definitivos,
por eso el pipeline siempre reingiere una ventana solapada de días.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.http import get_json

URL = "https://archive-api.open-meteo.com/v1/archive"
TZ_MADRID = "Europe/Madrid"

CIUDADES: dict[str, tuple[float, float]] = {
    "Palma": (39.5696, 2.6502),
    "Madrid": (40.4168, -3.7038),
    "Barcelona": (41.3874, 2.1686),
}

VARIABLES = ["temperature_2m", "shortwave_radiation", "precipitation", "wind_speed_10m"]


def fetch_clima(
    start: datetime,
    end: datetime,
    ciudades: dict[str, tuple[float, float]] | None = None,
    timeout: int = 60,
) -> pd.DataFrame:
    """Descarga la serie horaria de cada ciudad.

    Devuelve columnas: ciudad, ts_utc, temp_c, radiacion_wm2, precipitacion_mm, viento_kmh.
    """
    frames: list[pd.DataFrame] = []
    for nombre, (lat, lon) in (ciudades or CIUDADES).items():
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "hourly": ",".join(VARIABLES),
            "timezone": TZ_MADRID,
        }
        horario = get_json(URL, params, timeout=timeout).get("hourly") or {}
        if not horario.get("time"):
            raise ValueError(f"Open-Meteo no devolvió horas para {nombre}")

        df = pd.DataFrame(
            {
                "tiempo_local": pd.to_datetime(horario["time"]),
                "temp_c": horario.get("temperature_2m"),
                "radiacion_wm2": horario.get("shortwave_radiation"),
                "precipitacion_mm": horario.get("precipitation"),
                "viento_kmh": horario.get("wind_speed_10m"),
            }
        )
        df["ts_utc"] = (
            df["tiempo_local"]
            .dt.tz_localize(TZ_MADRID, ambiguous="NaT", nonexistent="shift_forward")
            .dt.tz_convert("UTC")
            .dt.tz_localize(None)
        )
        df["ciudad"] = nombre
        frames.append(df.drop(columns=["tiempo_local"]))

    columnas = [
        "ciudad",
        "ts_utc",
        "temp_c",
        "radiacion_wm2",
        "precipitacion_mm",
        "viento_kmh",
    ]
    return pd.concat(frames, ignore_index=True)[columnas].drop_duplicates(
        ["ciudad", "ts_utc"]
    )
