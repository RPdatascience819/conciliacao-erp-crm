"""Propriedades que valem para qualquer par de CSVs, nos dois motores ao mesmo tempo."""

from __future__ import annotations

import csv
import io
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from reconcile.contract import ReconciliationResult
from reconcile.engines import get_engine

HEADER = ["order_id", "amount", "customer", "order_date"]

# Alfabeto pequeno para forçar colisões de ID e casamentos entre os lados.
ids = st.sampled_from(["A", "B", "C", "a", " A", "A ", "", "  ", "007"])
amounts = st.sampled_from(["1", "1.0", "1.00", "2", "-1", "0", "1.005", "abc", "", "1e3", "NaN"])
texts = st.sampled_from(["c", "", "00123", "Silva, Ana", 'dito "x"', "duas\nlinhas"])

good_rows = st.tuples(ids, amounts, texts, texts).map(list)
# Linhas com campos de menos, de mais, ou vazias (lista vazia vira linha em branco).
ragged_rows = st.sampled_from([0, 1, 2, 3, 5, 6]).flatmap(
    lambda n: st.lists(texts | ids, min_size=n, max_size=n)
)
rows = st.one_of(good_rows, good_rows, good_rows, ragged_rows)
files = st.lists(rows, max_size=12)


def to_csv(records: list[list[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(records)
    return buffer.getvalue()


def reconcile_both(erp: str, crm: str) -> tuple[ReconciliationResult, ReconciliationResult]:
    with tempfile.TemporaryDirectory() as tmp:
        erp_path, crm_path = Path(tmp, "erp.csv"), Path(tmp, "crm.csv")
        erp_path.write_bytes(erp.encode("utf-8"))
        crm_path.write_bytes(crm.encode("utf-8"))
        return (
            get_engine("stdlib")(erp_path, crm_path),
            get_engine("pandas")(erp_path, crm_path),
        )


# deadline=None: o motor pandas passa com folga dos 200 ms padrão por exemplo em
# máquinas lentas de CI, e um tempo variável não pode reprovar um teste de lógica.
@settings(deadline=None, max_examples=200)
@given(erp=files, crm=files)
def test_engines_agree_and_every_row_lands_exactly_once(
    erp: list[list[str]], crm: list[list[str]]
) -> None:
    stdlib_result, pandas_result = reconcile_both(to_csv(erp), to_csv(crm))

    # 1. Diferencial: os dois motores devolvem exatamente o mesmo resultado.
    assert stdlib_result == pandas_result
    result = stdlib_result

    # 2. Partição: cada linha de dados aparece em exatamente um lugar do resultado.
    seen = [(r.source, r.line) for r in result.rejected]
    for pair in result.matched + result.amount_mismatch:
        seen += [("erp", pair.erp.line), ("crm", pair.crm.line)]
    seen += [("crm", o.line) for o in result.missing_in_erp]
    seen += [("erp", o.line) for o in result.missing_in_crm]
    expected = [("erp", n) for n in range(2, result.erp_rows_read + 2)]
    expected += [("crm", n) for n in range(2, result.crm_rows_read + 2)]
    assert sorted(seen) == sorted(expected)

    # 3. Fechamento: as duas equações do summary.md.
    matched, mismatch = len(result.matched), len(result.amount_mismatch)
    erp_rejected = sum(r.source == "erp" for r in result.rejected)
    crm_rejected = sum(r.source == "crm" for r in result.rejected)
    assert result.erp_rows_read == erp_rejected + matched + mismatch + len(result.missing_in_crm)
    assert result.crm_rows_read == crm_rejected + matched + mismatch + len(result.missing_in_erp)

    # 4. Coerência: matched tem valores iguais; amount_mismatch, diferentes.
    assert all(p.erp.amount == p.crm.amount for p in result.matched)
    assert all(p.erp.amount != p.crm.amount for p in result.amount_mismatch)
