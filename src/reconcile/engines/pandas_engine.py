"""Motor pandas: a mesma conciliação, com operações vetorizadas.

Tudo é lido como texto (dtype=str, na_filter=False): vazio continua "", zeros à
esquerda se mantêm e "NaN" é só texto. Com na_filter=False, o único NaN que sobra
no DataFrame é o preenchimento que o pandas põe nos campos que uma linha curta não
tem. É assim que o motor conta os campos de cada linha.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reconcile.contract import (
    AMOUNT_PATTERN,
    InputError,
    Order,
    Pair,
    Reason,
    ReconciliationResult,
    Rejected,
    Source,
    column_positions,
    raw_fields,
    read_text,
)

_READ_OPTIONS: dict[str, Any] = {
    "header": None,
    "dtype": str,
    "na_filter": False,
    "skip_blank_lines": False,  # linha vazia é malformed_row, não some
    "engine": "python",  # on_bad_lines com função só existe no motor python
}

_ORDER_COLUMNS = ["order_id", "amount", "customer", "order_date", "line"]


def reconcile(erp_path: Path, crm_path: Path) -> ReconciliationResult:
    erp, erp_rejected, erp_rows = _load(erp_path, "erp")
    crm, crm_rejected, crm_rows = _load(crm_path, "crm")

    merged = erp.merge(
        crm, on="order_id", how="outer", suffixes=("_erp", "_crm"), indicator=True
    ).sort_values("order_id", kind="stable")
    both = merged[merged["_merge"] == "both"]
    same_amount = both["amount_erp"] == both["amount_crm"]

    return ReconciliationResult(
        matched=_pairs(both[same_amount]),
        amount_mismatch=_pairs(both[~same_amount]),
        missing_in_erp=_orders(merged[merged["_merge"] == "right_only"], "_crm"),
        missing_in_crm=_orders(merged[merged["_merge"] == "left_only"], "_erp"),
        rejected=erp_rejected + crm_rejected,
        erp_rows_read=erp_rows,
        crm_rows_read=crm_rows,
    )


def _read_frame(path: Path) -> pd.DataFrame:
    """Lê o arquivo com uma coluna por campo, mesmo nas linhas com campos a mais.

    O pandas só aceita linhas mais largas que `names` por meio de on_bad_lines, e a
    função recebe a linha sem dizer a posição dela. Por isso a primeira leitura só
    mede a maior largura; se alguma linha passou da largura do cabeçalho, uma segunda
    leitura usa essa largura e nenhuma linha é desviada.
    """
    text = read_text(path)
    try:
        try:
            header = pd.read_csv(io.StringIO(text), nrows=1, **_READ_OPTIONS)
            width = header.shape[1]
        except pd.errors.EmptyDataError:  # primeiro registro é uma linha vazia
            width = 0
        if width == 0:
            column_positions(path, [])  # levanta "faltam colunas"
        too_wide: list[int] = []

        def measure(line: list[str]) -> None:
            too_wide.append(len(line))
            return None

        frame = pd.read_csv(
            io.StringIO(text), names=range(width), on_bad_lines=measure, **_READ_OPTIONS
        )
        if too_wide:
            frame = pd.read_csv(io.StringIO(text), names=range(max(too_wide)), **_READ_OPTIONS)
    except (pd.errors.ParserError, csv.Error) as exc:
        raise InputError(f"{path}: CSV inválido ({exc})") from None
    return frame


def _fields(row: pd.Series) -> list[str]:
    return [value for value in row.tolist() if isinstance(value, str)]


def _load(path: Path, source: Source) -> tuple[pd.DataFrame, tuple[Rejected, ...], int]:
    frame = _read_frame(path)
    header = _fields(frame.iloc[0])
    positions = column_positions(path, header)
    rows = frame.iloc[1:]

    field_count = rows.notna().sum(axis=1)
    ids = rows[positions["order_id"]].fillna("")  # ID provável; "" se a linha é curta
    stripped = ids.str.strip()
    filled = stripped != ""
    amounts = rows[positions["amount"]].fillna("")

    # np.select escolhe a primeira condição verdadeira: é a ordem de precedência.
    reasons = pd.Series(
        np.select(
            [
                field_count != len(header),
                ~filled,
                ids != stripped,
                ids.duplicated(keep=False) & filled,
                ~amounts.str.fullmatch(AMOUNT_PATTERN),
            ],
            [reason.value for reason in Reason],
            default="",
        ),
        index=rows.index,
    )

    valid = rows[reasons == ""]
    orders = pd.DataFrame(
        {
            "order_id": valid[positions["order_id"]],
            "amount": valid[positions["amount"]].map(Decimal),
            "customer": valid[positions["customer"]],
            "order_date": valid[positions["order_date"]],
            "line": valid.index + 1,  # índice 0 é o cabeçalho, linha 1 da planilha
        },
        columns=_ORDER_COLUMNS,
    )

    rejected = tuple(
        Rejected(
            source=source,
            line=index + 1,
            reason=Reason(reasons[index]),
            raw=raw_fields(header, fields),
            extra_fields=tuple(fields[len(header) :]),
        )
        for index, fields in ((i, _fields(row)) for i, row in rows[reasons != ""].iterrows())
    )
    return orders, rejected, len(rows)


def _order(row: Any, suffix: str) -> Order:
    return Order(
        order_id=row.order_id,
        amount=getattr(row, "amount" + suffix),
        customer=getattr(row, "customer" + suffix),
        order_date=getattr(row, "order_date" + suffix),
        line=int(getattr(row, "line" + suffix)),
    )


def _pairs(frame: pd.DataFrame) -> tuple[Pair, ...]:
    return tuple(
        Pair(erp=_order(row, "_erp"), crm=_order(row, "_crm"))
        for row in frame.itertuples(index=False)
    )


def _orders(frame: pd.DataFrame, suffix: str) -> tuple[Order, ...]:
    return tuple(_order(row, suffix) for row in frame.itertuples(index=False))
