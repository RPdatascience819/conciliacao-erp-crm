"""Registro dos motores. O motor pandas só é importado quando pedido."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from reconcile.contract import ReconciliationResult

Engine = Callable[[Path, Path], ReconciliationResult]

ENGINE_NAMES = ("stdlib", "pandas")


class EngineUnavailable(Exception):
    """O motor pedido precisa de uma dependência que não está instalada."""


def get_engine(name: str) -> Engine:
    if name == "stdlib":
        from reconcile.engines import stdlib_engine

        return stdlib_engine.reconcile
    if name == "pandas":
        try:
            from reconcile.engines import pandas_engine
        except ModuleNotFoundError as exc:
            if exc.name != "pandas":
                raise
            raise EngineUnavailable(
                "o motor pandas precisa do pandas instalado: pip install .[pandas]"
            ) from None
        return pandas_engine.reconcile
    raise ValueError(f"motor desconhecido: {name!r}")
