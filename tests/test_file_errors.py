"""Problemas de arquivo interrompem; os dois motores dão o mesmo erro."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import HEADER

from reconcile.contract import InputError
from reconcile.engines import Engine

WriteCsv = Callable[[str, str], Path]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "arquivo vazio"),
        ("order_id,amount,customer\nA,1,c\n", "faltam colunas obrigatórias: order_date"),
        ("\nA,1,c,d\n", "faltam colunas obrigatórias"),
        ("order_id,amount,customer,order_date,amount\n", "coluna repetida"),
        (HEADER + 'A,"1,c,d\nB,2,c,d\n', "CSV inválido"),
        (HEADER + 'A,"1"x,c,d\n', "CSV inválido"),
    ],
)
def test_file_level_problems_raise_input_error_with_path(
    engine: Engine, write_csv: WriteCsv, content: str, message: str
) -> None:
    bad = write_csv("ruim.csv", content)
    good = write_csv("bom.csv", HEADER)
    with pytest.raises(InputError, match=message) as exc:
        engine(bad, good)
    assert "ruim.csv" in str(exc.value)


def test_non_utf8_content(engine: Engine, write_csv: WriteCsv, tmp_path: Path) -> None:
    bad = tmp_path / "latin1.csv"
    bad.write_bytes(HEADER.encode() + "A,1,José,d\n".encode("latin-1"))
    with pytest.raises(InputError, match="não é UTF-8"):
        engine(write_csv("bom.csv", HEADER), bad)


def test_missing_file(engine: Engine, write_csv: WriteCsv, tmp_path: Path) -> None:
    with pytest.raises(InputError, match="não encontrado"):
        engine(tmp_path / "sumiu.csv", write_csv("bom.csv", HEADER))
