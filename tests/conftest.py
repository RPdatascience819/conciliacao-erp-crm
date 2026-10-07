from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from reconcile.contract import ReconciliationResult
from reconcile.engines import ENGINE_NAMES, Engine, get_engine

HEADER = "order_id,amount,customer,order_date\n"

Run = Callable[[str, str], ReconciliationResult]


@pytest.fixture(params=ENGINE_NAMES)
def engine(request: pytest.FixtureRequest) -> Engine:
    """Todo teste que usa este fixture roda uma vez em cada motor."""
    return get_engine(request.param)


@pytest.fixture
def write_csv(tmp_path: Path) -> Callable[[str, str], Path]:
    def write(name: str, content: str) -> Path:
        path = tmp_path / name
        path.write_bytes(content.encode("utf-8"))  # bytes: nada de tradução de "\n"
        return path

    return write


@pytest.fixture
def run(engine: Engine, write_csv: Callable[[str, str], Path]) -> Run:
    """Grava os dois CSVs (texto completo, com cabeçalho) e concilia."""

    def run_(erp: str, crm: str) -> ReconciliationResult:
        return engine(write_csv("erp.csv", erp), write_csv("crm.csv", crm))

    return run_
