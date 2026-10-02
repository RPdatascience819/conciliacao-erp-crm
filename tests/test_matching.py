"""Casamento por order_id em arquivos sem nenhuma linha rejeitada."""

from __future__ import annotations

from decimal import Decimal

from conftest import HEADER, Run

from reconcile.contract import Order, Pair


def test_groups_orders_by_presence_and_amount(run: Run) -> None:
    result = run(
        HEADER + "A,10.00,Ana,2024-01-01\nB,20.00,Bia,2024-01-02\nC,30.00,Caio,2024-01-03\n",
        HEADER + "B,20.01,Bia,2024-01-02\nA,10,Ana,2024-01-01\nD,40.00,Duda,2024-01-04\n",
    )
    assert result.matched == (
        Pair(
            erp=Order("A", Decimal("10.00"), "Ana", "2024-01-01", line=2),
            crm=Order("A", Decimal("10"), "Ana", "2024-01-01", line=3),
        ),
    )
    assert [p.erp.order_id for p in result.amount_mismatch] == ["B"]
    assert result.amount_mismatch[0].crm.amount - result.amount_mismatch[0].erp.amount == Decimal(
        "0.01"
    )
    assert result.missing_in_erp == (Order("D", Decimal("40.00"), "Duda", "2024-01-04", line=4),)
    assert result.missing_in_crm == (Order("C", Decimal("30.00"), "Caio", "2024-01-03", line=4),)
    assert result.rejected == ()
    assert (result.erp_rows_read, result.crm_rows_read) == (3, 3)


def test_ids_are_compared_exactly_and_case_sensitive(run: Run) -> None:
    result = run(HEADER + "ped-1,1,a,d\n", HEADER + "PED-1,1,a,d\n")
    assert [o.order_id for o in result.missing_in_crm] == ["ped-1"]
    assert [o.order_id for o in result.missing_in_erp] == ["PED-1"]


def test_amounts_compared_by_value_not_text(run: Run) -> None:
    result = run(HEADER + "A,-0,a,d\nB,00100,b,d\n", HEADER + "A,0.00,a,d\nB,100,b,d\n")
    assert [p.erp.order_id for p in result.matched] == ["A", "B"]


def test_output_groups_are_sorted_by_order_id_code_point(run: Run) -> None:
    ids = ["b", "B", "a10", "a2", "Á"]
    erp = HEADER + "".join(f"{i},1,c,d\n" for i in ids)
    result = run(erp, HEADER)
    assert [o.order_id for o in result.missing_in_crm] == sorted(ids)  # B < a10 < a2 < b < Á


def test_context_columns_pass_through_untouched(run: Run) -> None:
    result = run(
        HEADER + '007,1,00123,01/02/2024\n"N\nL",2,"Silva, Ana",ontem\n',
        HEADER + "007,1,00123,2024-02-01\n",
    )
    pair = result.matched[0]
    assert (pair.erp.order_id, pair.erp.customer, pair.erp.order_date) == (
        "007",
        "00123",
        "01/02/2024",
    )
    assert pair.crm.order_date == "2024-02-01"
    multiline = result.missing_in_crm[0]
    assert (multiline.order_id, multiline.customer, multiline.order_date) == (
        "N\nL",
        "Silva, Ana",
        "ontem",
    )


def test_line_is_record_position_not_physical_line(run: Run) -> None:
    result = run(HEADER + 'A,1,"duas\nlinhas",d\nB,1,c,d\n', HEADER)
    assert [o.line for o in result.missing_in_crm] == [2, 3]


def test_extra_columns_are_ignored(run: Run) -> None:
    result = run(
        "region,order_date,order_id,notes,customer,amount\nSul,d,A,x,c,5\n",
        HEADER + "A,5.0,c,d\n",
    )
    assert result.matched[0].erp == Order("A", Decimal("5"), "c", "d", line=2)


def test_header_only_files_reconcile_to_nothing(run: Run) -> None:
    result = run(HEADER, HEADER.rstrip("\n"))
    assert result.matched == result.amount_mismatch == ()
    assert result.missing_in_erp == result.missing_in_crm == ()
    assert result.rejected == ()
    assert (result.erp_rows_read, result.crm_rows_read) == (0, 0)


def test_bom_and_crlf_are_accepted(run: Run) -> None:
    crlf = HEADER.replace("\n", "\r\n") + "A,1,c,d\r\n"
    result = run("\N{BYTE ORDER MARK}" + crlf, HEADER + "A,1,c,d\n")
    assert [p.erp.order_id for p in result.matched] == ["A"]


def test_cr_only_line_endings_are_accepted(run: Run) -> None:
    # "CSV (Macintosh)" do Excel termina as linhas só com "\r".
    cr = (HEADER + "A,1,c,d\nB,2,c,d\n").replace("\n", "\r")
    result = run(cr, HEADER + "A,1,c,d\n")
    assert [p.erp.order_id for p in result.matched] == ["A"]
    assert [o.order_id for o in result.missing_in_crm] == ["B"]
    assert result.erp_rows_read == 2
