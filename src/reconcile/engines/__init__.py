"""Registro dos motores. O motor pandas só é importado quando pedido."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from reconcile.contract import ReconciliationResult

Engine = Callable[[Path, Path], ReconciliationResult]

ENGINE_NAMES = ("stdlib",)


class EngineUnavailable(Exception):
    """O motor pedido precisa de uma dependência que não está instalada."""


def get_engine(name: str) -> Engine:
    if name == "stdlib":
        from reconcile.engines import stdlib_engine

        return stdlib_engine.reconcile
    raise ValueError(f"motor desconhecido: {name!r}")
