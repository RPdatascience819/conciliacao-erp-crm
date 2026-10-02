"""Motor da biblioteca padrão: csv + decimal, linha a linha."""

from __future__ import annotations

import csv
import io
from collections import Counter
from decimal import Decimal
from pathlib import Path

from reconcile.contract import (
    InputError,
    Order,
    Pair,
    Reason,
    ReconciliationResult,
    Rejected,
    Source,
    column_positions,
    is_valid_amount,
    raw_fields,
    read_text,
)


def reconcile(erp_path: Path, crm_path: Path) -> ReconciliationResult:
    erp_orders, erp_rejected, erp_rows = _load(erp_path, "erp")
    crm_orders, crm_rejected, crm_rows = _load(crm_path, "crm")

    matched: list[Pair] = []
    amount_mismatch: list[Pair] = []
    for order_id in sorted(erp_orders.keys() & crm_orders.keys()):
        pair = Pair(erp=erp_orders[order_id], crm=crm_orders[order_id])
        (matched if pair.erp.amount == pair.crm.amount else amount_mismatch).append(pair)

    return ReconciliationResult(
        matched=tuple(matched),
        amount_mismatch=tuple(amount_mismatch),
        missing_in_erp=tuple(crm_orders[i] for i in sorted(crm_orders.keys() - erp_orders.keys())),
        missing_in_crm=tuple(erp_orders[i] for i in sorted(erp_orders.keys() - crm_orders.keys())),
        rejected=tuple(erp_rejected + crm_rejected),
        erp_rows_read=erp_rows,
        crm_rows_read=crm_rows,
    )


def _read_records(path: Path) -> list[list[str]]:
    text = read_text(path)
    try:
        # strict=True: uma aspa nunca fechada vira erro, em vez de engolir o resto do arquivo.
        return list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as exc:
        raise InputError(f"{path}: CSV inválido ({exc})") from None


def _load(path: Path, source: Source) -> tuple[dict[str, Order], list[Rejected], int]:
    header, *rows = _read_records(path)
    positions = column_positions(path, header)
    width = len(header)
    id_pos = positions["order_id"]

    def probable_id(fields: list[str]) -> str:
        # Linha malformada participa da duplicidade pelo campo na posição do order_id.
        return fields[id_pos] if len(fields) > id_pos else ""

    id_counts = Counter(i for i in map(probable_id, rows) if i.strip())

    orders: dict[str, Order] = {}
    rejected: list[Rejected] = []
    for line, fields in enumerate(rows, start=2):
        reason = _reason(fields, width, positions, id_counts)
        if reason is None:
            order_id = fields[id_pos]
            orders[order_id] = Order(
                order_id=order_id,
                amount=Decimal(fields[positions["amount"]]),
                customer=fields[positions["customer"]],
                order_date=fields[positions["order_date"]],
                line=line,
            )
        else:
            rejected.append(
                Rejected(
                    source=source,
                    line=line,
                    reason=reason,
                    raw=raw_fields(header, fields),
                    extra_fields=tuple(fields[width:]),
                )
            )
    return orders, rejected, len(rows)


def _reason(
    fields: list[str], width: int, positions: dict[str, int], id_counts: Counter[str]
) -> Reason | None:
    if len(fields) != width:
        return Reason.MALFORMED_ROW
    order_id = fields[positions["order_id"]]
    if not order_id.strip():
        return Reason.MISSING_ID
    if order_id != order_id.strip():
        return Reason.ID_WHITESPACE
    if id_counts[order_id] > 1:
        return Reason.DUPLICATE_ID
    if not is_valid_amount(fields[positions["amount"]]):
        return Reason.INVALID_AMOUNT
    return None
