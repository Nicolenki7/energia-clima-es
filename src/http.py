"""Cliente HTTP con reintentos y backoff exponencial.

La API abierta de REE devuelve 503 intermitentes cuando se piden varias ventanas
seguidas. Reintentar es parte del contrato de una ingesta, no un parche: una
corrida no debe fallar por un throttling transitorio.
"""
from __future__ import annotations

import time
from typing import Any

import requests

REINTENTABLES = {429, 500, 502, 503, 504}


class ErrorDeFuente(RuntimeError):
    """La fuente no respondió bien después de todos los reintentos."""


def get_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: int = 30,
    intentos: int = 5,
    espera_base: float = 2.0,
) -> dict[str, Any]:
    ultimo_error: Exception | None = None

    for intento in range(1, intentos + 1):
        try:
            respuesta = requests.get(url, params=params, timeout=timeout)
            if respuesta.status_code in REINTENTABLES:
                raise requests.HTTPError(f"HTTP {respuesta.status_code}")
            respuesta.raise_for_status()
            return respuesta.json()
        except (requests.RequestException, ValueError) as error:
            ultimo_error = error
            if intento < intentos:
                time.sleep(espera_base * (2 ** (intento - 1)))

    raise ErrorDeFuente(f"{url} falló tras {intentos} intentos: {ultimo_error}")
