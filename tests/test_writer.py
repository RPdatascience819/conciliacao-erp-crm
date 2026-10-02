from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from reconcile.contract import Order, Pair, Reason, ReconciliationResult, Rejected
from reconcile.inputs import InputFile, fingerprint
from reconcile.writer import OUTPUT_FILES, format_amount, write_outputs

ERP_IN = InputFile(name="erp.csv", sha256="a" * 64)
CRM_IN = InputFile(name="crm.csv", sha256="b" * 64)


def order(order_id: str, amount: str, line: int, customer: str = "c") -> Order:
    return Order(order_id, Decimal(amount), customer, "2024-01-01", line)


RESULT = ReconciliationResult(
    matched=(Pair(order("A", "10.5", 2), order("A", "10.50", 3, "Ana")),),
    amount_mismatch=(Pair(order("B", "20", 3), order("B", "19.99", 2)),),
    missing_in_erp=(order("D", "-5", 4),),
    missing_in_crm=(order("C", "7", 4, "Silva, Ana"),),
    rejected=(
        Rejected(
            "erp",
            5,
            Reason.MALFORMED_ROW,
            {"order_id": "E", "amount": "1", "customer": "c", "order_date": "d"},
            ("x", "y,z"),
        ),
        Rejected(
            "crm",
            5,
            Reason.INVALID_AMOUNT,
            {"order_id": "F", "amount": "1e3", "customer": "c", "order_date": "d"},
            (),
        ),
    ),
    erp_rows_read=4,
    crm_rows_read=4,
)


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


@pytest.mark.parametrize(
    ("value", "text"),
    [("100", "100.00"), ("100.5", "100.50"), ("-20", "-20.00"), ("0.01", "0.01")],
)
def test_format_amount_uses_two_places(value: str, text: str) -> None:
    assert format_amount(Decimal(value)) == text


def test_writes_the_six_files_with_lf_and_utf8(tmp_path: Path) -> None:
    write_outputs(RESULT, ERP_IN, CRM_IN, tmp_path / "out")
    out = tmp_path / "out"
    assert sorted(p.name for p in out.iterdir()) == sorted(OUTPUT_FILES)
    for name in OUTPUT_FILES:
        assert b"\r\n" not in (out / name).read_bytes()


def test_csv_contents(tmp_path: Path) -> None:
    write_outputs(RESULT, ERP_IN, CRM_IN, tmp_path)
    assert read(tmp_path / "matched.csv") == (
        "order_id,amount,erp_customer,erp_order_date,crm_customer,crm_order_date\n"
        "A,10.50,c,2024-01-01,Ana,2024-01-01\n"
    )
    assert read(tmp_path / "amount_mismatch.csv") == (
        "order_id,erp_amount,crm_amount,difference,erp_customer,crm_customer,erp_line,crm_line\n"
        "B,20.00,19.99,-0.01,c,c,3,2\n"
    )
    assert read(tmp_path / "missing_in_erp.csv") == (
        "order_id,amount,customer,order_date,crm_line\nD,-5.00,c,2024-01-01,4\n"
    )
    assert read(tmp_path / "missing_in_crm.csv") == (
        'order_id,amount,customer,order_date,erp_line\nC,7.00,"Silva, Ana",2024-01-01,4\n'
    )
    assert read(tmp_path / "rejected.csv") == (
        "source,line,reason,order_id,amount,customer,order_date,extra_fields\n"
        'erp,5,malformed_row,E,1,c,d,"[""x"",""y,z""]"\n'
        "crm,5,invalid_amount,F,1e3,c,d,\n"
    )


def test_summary(tmp_path: Path) -> None:
    write_outputs(RESULT, ERP_IN, CRM_IN, tmp_path)
    summary = read(tmp_path / "summary.md")
    assert "`difference = crm_amount - erp_amount`" in summary
    assert f"| ERP | erp.csv | {'a' * 64} |" in summary
    assert "| matched | 1 |" in summary
    assert "Soma das diferenças em `amount_mismatch`: -0.01" in summary
    assert "| ERP | 4 | 1 | 1 | 1 | 1 | sim |" in summary
    assert "| CRM | 4 | 1 | 1 | 1 | 1 | sim |" in summary
    assert "| malformed_row | 1 | 0 |" in summary
    assert "| invalid_amount | 0 | 1 |" in summary
    assert "| duplicate_id | 0 | 0 |" in summary  # todo motivo aparece, mesmo zerado


def test_summary_shows_when_closure_fails(tmp_path: Path) -> None:
    broken = ReconciliationResult((), (), (), (), (), erp_rows_read=1, crm_rows_read=0)
    write_outputs(broken, ERP_IN, CRM_IN, tmp_path)
    assert "| ERP | 1 | 0 | 0 | 0 | 0 | NÃO |" in read(tmp_path / "summary.md")


def test_overwrites_previous_run_and_leaves_no_staging_dir(tmp_path: Path) -> None:
    (tmp_path / "matched.csv").write_text("velho", encoding="utf-8")
    write_outputs(RESULT, ERP_IN, CRM_IN, tmp_path)
    assert read(tmp_path / "matched.csv").startswith("order_id,")
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(OUTPUT_FILES)


def test_fingerprint_uses_name_and_sha256(tmp_path: Path) -> None:
    path = tmp_path / "pedidos.csv"
    path.write_bytes(b"abc")
    assert fingerprint(path) == InputFile(
        name="pedidos.csv",
        sha256="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    )
