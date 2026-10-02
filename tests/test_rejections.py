"""Quarentena: cada linha rejeitada recebe um único motivo, na ordem de precedência."""

from __future__ import annotations

import pytest
from conftest import HEADER, Run

from reconcile.contract import Reason, Rejected


def reasons(run: Run, erp_rows: str) -> list[tuple[int, str]]:
    result = run(HEADER + erp_rows, HEADER)
    return [(r.line, r.reason.value) for r in result.rejected]


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ("A,1,c\n", "malformed_row"),
        ("A,1,c,d,x\n", "malformed_row"),
        (",1,c,d\n", "missing_id"),
        ("   ,1,c,d\n", "missing_id"),
        ("\xa0,1,c,d\n", "missing_id"),
        (" A,1,c,d\n", "id_whitespace"),
        ("A ,1,c,d\n", "id_whitespace"),
        ("\tA,1,c,d\n", "id_whitespace"),
        ("A,,c,d\n", "invalid_amount"),
        ("A,100.005,c,d\n", "invalid_amount"),
        ('A,"1,000.00",c,d\n', "invalid_amount"),
        ("A,R$ 10,c,d\n", "invalid_amount"),
        ("A,NaN,c,d\n", "invalid_amount"),
        ("A,Infinity,c,d\n", "invalid_amount"),
        ("A,1e3,c,d\n", "invalid_amount"),
        ("A,١٠٠,c,d\n", "invalid_amount"),
        ('A,"100\n",c,d\n', "invalid_amount"),
    ],
)
def test_single_reason_per_row(run: Run, row: str, reason: str) -> None:
    assert reasons(run, row) == [(2, reason)]


def test_every_copy_of_a_duplicate_id_is_rejected(run: Run) -> None:
    assert reasons(run, "A,1,c,d\nB,2,c,d\nA,1,c,d\n") == [(2, "duplicate_id"), (4, "duplicate_id")]


def test_duplicate_wins_over_invalid_amount(run: Run) -> None:
    assert reasons(run, "A,100.00,c,d\nA,abc,c,d\n") == [(2, "duplicate_id"), (3, "duplicate_id")]


def test_missing_id_wins_over_invalid_amount(run: Run) -> None:
    assert reasons(run, ",abc,c,d\n") == [(2, "missing_id")]


def test_duplicate_check_is_per_file(run: Run) -> None:
    result = run(HEADER + "A,1,c,d\n", HEADER + "A,1,c,d\n")
    assert result.rejected == () and len(result.matched) == 1


def test_malformed_row_makes_valid_rows_with_its_probable_id_duplicates(run: Run) -> None:
    # A linha 3 tem campos a menos, mas o campo na posição do order_id é "A".
    assert reasons(run, "A,1,c,d\nA,1\n") == [(2, "duplicate_id"), (3, "malformed_row")]


def test_malformed_row_without_probable_id_does_not_count(run: Run) -> None:
    header = "customer,amount,order_date,order_id\n"
    result = run(header + "c,1,d,A\nc,1\n", HEADER)
    assert [(r.line, r.reason.value) for r in result.rejected] == [(3, "malformed_row")]
    assert [o.order_id for o in result.missing_in_crm] == ["A"]


def test_blank_line_in_the_middle_is_malformed_and_counted(run: Run) -> None:
    result = run(HEADER + "A,1,c,d\n\nB,1,c,d\n", HEADER)
    assert [(r.line, r.reason.value) for r in result.rejected] == [(3, "malformed_row")]
    assert [o.line for o in result.missing_in_crm] == [2, 4]
    assert result.erp_rows_read == 3


def test_final_newline_is_not_a_blank_line_but_an_extra_one_is(run: Run) -> None:
    assert reasons(run, "A,1,c,d\n") == []
    assert reasons(run, "A,1,c,d\n\n") == [(3, "malformed_row")]


def test_rejected_keeps_the_row_as_it_came(run: Run) -> None:
    result = run(HEADER + " A,1.5,00123,ontem\n", HEADER)
    assert result.rejected == (
        Rejected(
            source="erp",
            line=2,
            reason=Reason.ID_WHITESPACE,
            raw={"order_id": " A", "amount": "1.5", "customer": "00123", "order_date": "ontem"},
            extra_fields=(),
        ),
    )


def test_malformed_row_fills_by_position_and_keeps_extra_fields(run: Run) -> None:
    result = run(HEADER + 'A,1,c,d,x,"y,z"\nB,2\n\n', HEADER)
    long_row, short_row, blank = result.rejected
    assert long_row.raw == {"order_id": "A", "amount": "1", "customer": "c", "order_date": "d"}
    assert long_row.extra_fields == ("x", "y,z")
    assert short_row.raw == {"order_id": "B", "amount": "2", "customer": "", "order_date": ""}
    assert short_row.extra_fields == ()
    assert blank.raw == {"order_id": "", "amount": "", "customer": "", "order_date": ""}


def test_rejected_sorted_erp_first_then_by_line(run: Run) -> None:
    result = run(HEADER + "A,x,c,d\n,1,c,d\n", HEADER + ",1,c,d\nB,x,c,d\n")
    assert [(r.source, r.line) for r in result.rejected] == [
        ("erp", 2),
        ("erp", 3),
        ("crm", 2),
        ("crm", 3),
    ]


def test_bare_cr_inside_unquoted_field_ends_the_row(run: Run) -> None:
    # Fora de aspas, "\r" sozinho termina a linha: o registro vira duas linhas malformadas.
    assert reasons(run, "A,1,c\rx,d\n") == [(2, "malformed_row"), (3, "malformed_row")]
