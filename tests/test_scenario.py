"""Ponta a ponta: a CLI, em cada motor, gera exatamente os bytes revisados em expected/.

Os arquivos esperados são regenerados à mão e revisados no git diff:

    python -m reconcile --erp tests/fixtures/scenario/erp_orders.csv \
        --crm tests/fixtures/scenario/crm_orders.csv --out tests/fixtures/scenario/expected

Não existe opção automática de "atualizar referências": ela convida a aprovar sem ler.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reconcile.cli import main
from reconcile.engines import ENGINE_NAMES
from reconcile.writer import OUTPUT_FILES

SCENARIO = Path(__file__).parent / "fixtures" / "scenario"


@pytest.mark.parametrize(
    "path", sorted(SCENARIO.rglob("*.*")), ids=lambda p: p.relative_to(SCENARIO).as_posix()
)
def test_fixtures_kept_lf_after_checkout(path: Path) -> None:
    # O .gitattributes marca tests/fixtures como -text. Sem isso, o checkout no Windows
    # converteria para CRLF, e o SHA-256 no summary.md e a comparação byte a byte quebrariam.
    assert b"\r" not in path.read_bytes()


@pytest.mark.parametrize("engine", ENGINE_NAMES)
@pytest.mark.parametrize("name", OUTPUT_FILES)
def test_output_matches_reviewed_file_byte_for_byte(tmp_path: Path, engine: str, name: str) -> None:
    code = main(
        [
            "--erp", str(SCENARIO / "erp_orders.csv"),
            "--crm", str(SCENARIO / "crm_orders.csv"),
            "--out", str(tmp_path),
            "--engine", engine,
        ]
    )  # fmt: skip
    assert code == 1  # o cenário tem divergências de propósito
    assert (tmp_path / name).read_bytes() == (SCENARIO / "expected" / name).read_bytes()
