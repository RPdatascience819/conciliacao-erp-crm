"""Teste de fumaça do gerador: a saída dele concilia, fecha as contas e os motores concordam."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from generate import generate  # noqa: E402

from reconcile.engines import get_engine  # noqa: E402


def test_generated_data_reconciles_and_closes(tmp_path: Path) -> None:
    erp, crm = generate(2_000, tmp_path, seed=7)
    result = get_engine("stdlib")(erp, crm)
    assert result == get_engine("pandas")(erp, crm)

    assert result.matched and result.amount_mismatch and result.rejected
    assert result.missing_in_erp and result.missing_in_crm
    reasons = {r.reason.value for r in result.rejected}
    assert {"invalid_amount", "duplicate_id", "malformed_row"} <= reasons

    erp_rejected = sum(r.source == "erp" for r in result.rejected)
    crm_rejected = sum(r.source == "crm" for r in result.rejected)
    both = len(result.matched) + len(result.amount_mismatch)
    assert result.erp_rows_read == erp_rejected + both + len(result.missing_in_crm)
    assert result.crm_rows_read == crm_rejected + both + len(result.missing_in_erp)


def test_same_seed_same_bytes(tmp_path: Path) -> None:
    first = generate(500, tmp_path / "a", seed=1)
    second = generate(500, tmp_path / "b", seed=1)
    assert [p.read_bytes() for p in first] == [p.read_bytes() for p in second]
