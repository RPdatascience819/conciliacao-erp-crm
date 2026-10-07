from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from olist import build_extracts  # noqa: E402

from reconcile.engines import get_engine  # noqa: E402

ORDERS = (
    "order_id,customer_id,order_status,order_purchase_timestamp\n"
    "o1,c1,delivered,2017-10-02 10:56:33\n"
    "o2,c2,delivered,2018-07-24 20:41:37\n"
    "o3,c3,delivered,2018-08-08 08:38:49\n"
)
PAYMENTS = (
    "order_id,payment_sequential,payment_type,payment_installments,payment_value\n"
    "o1,1,credit_card,1,10.5\n"
    "o1,2,voucher,1,5.00\n"
    "o2,1,boleto,1,20.00\n"
    "o4,1,boleto,1,1.005\n"
)
ITEMS = (
    "order_id,order_item_id,product_id,seller_id,shipping_limit_date,price,freight_value\n"
    "o1,1,p1,s1,2017-10-06 11:07:15,10.00,2.00\n"
    "o1,2,p4,s1,2017-10-06 11:07:15,2.00,1.50\n"
    "o2,1,p2,s2,2018-07-30 03:24:27,18.00,1.99\n"
    "o3,1,p3,s3,2018-08-13 08:55:23,7.00,0.00\n"
)


def make_archive(path: Path, payments: str = PAYMENTS) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("olist_orders_dataset.csv", ORDERS)
        archive.writestr("olist_order_payments_dataset.csv", payments)
        archive.writestr("olist_order_items_dataset.csv", ITEMS)
    return path


def test_extracts_sum_payments_and_items_per_order(tmp_path: Path) -> None:
    erp, crm = build_extracts(make_archive(tmp_path / "olist.zip"), tmp_path / "out")
    assert erp.read_bytes().decode("utf-8") == (
        "order_id,amount,customer,order_date\n"
        "o1,15.50,c1,2017-10-02\n"
        "o2,20.00,c2,2018-07-24\n"
        "o4,1.005,,\n"
    )
    assert crm.read_bytes().decode("utf-8") == (
        "order_id,amount,customer,order_date\n"
        "o1,15.50,c1,2017-10-02\n"
        "o2,19.99,c2,2018-07-24\n"
        "o3,7.00,c3,2018-08-08\n"
    )


def test_extracts_reconcile_into_every_group(tmp_path: Path) -> None:
    erp, crm = build_extracts(make_archive(tmp_path / "olist.zip"), tmp_path / "out")
    result = get_engine("stdlib")(erp, crm)
    assert [p.erp.order_id for p in result.matched] == ["o1"]
    assert [p.erp.order_id for p in result.amount_mismatch] == ["o2"]
    assert [o.order_id for o in result.missing_in_erp] == ["o3"]
    # Valor com 3 casas não é arredondado na extração: chega à quarentena como veio.
    assert [(r.raw["order_id"], r.reason.value) for r in result.rejected] == [
        ("o4", "invalid_amount")
    ]


# Decimal() aceitaria " 10.00", "1_000", dígitos de outro alfabeto e notação científica, e
# quebraria com "" e "abc". Nada disso pode ser corrigido na extração (P10): o valor cru vai
# para o extrato e a conciliação o põe em quarentena.
@pytest.mark.parametrize(
    "raw",
    [
        " 10.00",
        "1_000",
        "\N{ARABIC-INDIC DIGIT ONE}\N{ARABIC-INDIC DIGIT ZERO}",
        "1.5E+1",
        "",
        "abc",
    ],
)
def test_raw_value_outside_contract_reaches_quarantine_unchanged(tmp_path: Path, raw: str) -> None:
    payments = PAYMENTS.replace("o1,2,voucher,1,5.00", f'o1,2,voucher,1,"{raw}"')
    erp, crm = build_extracts(make_archive(tmp_path / "olist.zip", payments), tmp_path / "out")
    result = get_engine("stdlib")(erp, crm)
    assert [(r.raw["order_id"], r.raw["amount"], r.reason.value) for r in result.rejected] == [
        ("o1", raw, "invalid_amount"),
        ("o4", "1.005", "invalid_amount"),
    ]
