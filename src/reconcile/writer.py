"""Grava os 6 arquivos de saída a partir de um ReconciliationResult.

A mesma entrada gera os mesmos bytes, em qualquer motor e em qualquer sistema:
UTF-8, terminador de linha "\\n" fixo e nenhuma data, hora ou nome de motor.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
from collections.abc import Iterable, Sequence
from decimal import Decimal
from pathlib import Path

from reconcile.contract import Order, Pair, Reason, ReconciliationResult, Rejected
from reconcile.inputs import InputFile

OUTPUT_FILES = (
    "matched.csv",
    "amount_mismatch.csv",
    "missing_in_erp.csv",
    "missing_in_crm.csv",
    "rejected.csv",
    "summary.md",
)


def format_amount(value: Decimal) -> str:
    """Duas casas, só na apresentação: 100.5 vira 100.50."""
    return f"{value:.2f}"


def write_outputs(
    result: ReconciliationResult, erp_input: InputFile, crm_input: InputFile, out_dir: Path
) -> None:
    """Grava numa pasta temporária e só então move, para não misturar execuções."""
    out_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".reconcile-", dir=out_dir))
    try:
        _write_csv(
            staging / "matched.csv",
            [
                "order_id",
                "amount",
                "erp_customer",
                "erp_order_date",
                "crm_customer",
                "crm_order_date",
            ],
            (
                [
                    p.erp.order_id,
                    format_amount(p.erp.amount),
                    p.erp.customer,
                    p.erp.order_date,
                    p.crm.customer,
                    p.crm.order_date,
                ]
                for p in result.matched
            ),
        )
        _write_csv(
            staging / "amount_mismatch.csv",
            [
                "order_id",
                "erp_amount",
                "crm_amount",
                "difference",
                "erp_customer",
                "crm_customer",
                "erp_line",
                "crm_line",
            ],
            (
                [
                    p.erp.order_id,
                    format_amount(p.erp.amount),
                    format_amount(p.crm.amount),
                    format_amount(_difference(p)),
                    p.erp.customer,
                    p.crm.customer,
                    str(p.erp.line),
                    str(p.crm.line),
                ]
                for p in result.amount_mismatch
            ),
        )
        _write_csv(
            staging / "missing_in_erp.csv",
            ["order_id", "amount", "customer", "order_date", "crm_line"],
            (_missing_row(o) for o in result.missing_in_erp),
        )
        _write_csv(
            staging / "missing_in_crm.csv",
            ["order_id", "amount", "customer", "order_date", "erp_line"],
            (_missing_row(o) for o in result.missing_in_crm),
        )
        _write_csv(
            staging / "rejected.csv",
            [
                "source",
                "line",
                "reason",
                "order_id",
                "amount",
                "customer",
                "order_date",
                "extra_fields",
            ],
            (_rejected_row(r) for r in result.rejected),
        )
        with (staging / "summary.md").open("w", encoding="utf-8", newline="") as file:
            file.write(render_summary(result, erp_input, crm_input))
        for name in OUTPUT_FILES:
            os.replace(staging / name, out_dir / name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _difference(pair: Pair) -> Decimal:
    return pair.crm.amount - pair.erp.amount  # positivo: o CRM registrou mais


def _missing_row(order: Order) -> list[str]:
    return [
        order.order_id,
        format_amount(order.amount),
        order.customer,
        order.order_date,
        str(order.line),
    ]


def _rejected_row(rejected: Rejected) -> list[str]:
    extra = (
        json.dumps(list(rejected.extra_fields), ensure_ascii=False, separators=(",", ":"))
        if rejected.extra_fields
        else ""
    )
    raw = rejected.raw
    return [
        rejected.source,
        str(rejected.line),
        rejected.reason.value,
        raw.get("order_id", ""),
        raw.get("amount", ""),
        raw.get("customer", ""),
        raw.get("order_date", ""),
        extra,
    ]


def _row(*cells: object) -> str:
    """Uma linha de tabela Markdown; a barra vertical é escapada para não quebrá-la."""
    return "| " + " | ".join(str(cell).replace("|", r"\|") for cell in cells) + " |"


def render_summary(result: ReconciliationResult, erp_input: InputFile, crm_input: InputFile) -> str:
    def rejected_count(source: str, reason: Reason | None = None) -> int:
        return sum(
            1
            for r in result.rejected
            if r.source == source and (reason is None or r.reason == reason)
        )

    def closure(label: str, read: int, source: str, only_here: int) -> str:
        rejected = rejected_count(source)
        matched, mismatch = len(result.matched), len(result.amount_mismatch)
        closes = "sim" if read == rejected + matched + mismatch + only_here else "NÃO"
        return _row(label, read, rejected, matched, mismatch, only_here, closes)

    total_difference = sum((_difference(p) for p in result.amount_mismatch), Decimal(0))
    lines = [
        "# Resumo da conciliação",
        "",
        "Convenção de sinal: `difference = crm_amount - erp_amount` "
        "(positivo: o CRM registrou mais que o ERP).",
        "",
        "## Entradas",
        "",
        _row("Lado", "Arquivo", "SHA-256"),
        "|---|---|---|",
        _row("ERP", erp_input.name, erp_input.sha256),
        _row("CRM", crm_input.name, crm_input.sha256),
        "",
        "## Grupos",
        "",
        _row("Grupo", "Pedidos"),
        "|---|---|",
        _row("matched", len(result.matched)),
        _row("amount_mismatch", len(result.amount_mismatch)),
        _row("missing_in_erp", len(result.missing_in_erp)),
        _row("missing_in_crm", len(result.missing_in_crm)),
        _row("rejected", len(result.rejected)),
        "",
        f"Soma das diferenças em `amount_mismatch`: {format_amount(total_difference)}",
        "",
        "## Fechamento",
        "",
        'Cada linha lida de um arquivo está em exatamente um grupo. "Só neste lado" é '
        "`missing_in_crm` para o ERP e `missing_in_erp` para o CRM.",
        "",
        _row(
            "Lado",
            "Linhas lidas",
            "Rejeitadas",
            "matched",
            "amount_mismatch",
            "Só neste lado",
            "Fecha?",
        ),
        "|---|---|---|---|---|---|---|",
        closure("ERP", result.erp_rows_read, "erp", len(result.missing_in_crm)),
        closure("CRM", result.crm_rows_read, "crm", len(result.missing_in_erp)),
        "",
        "## Rejeições por motivo",
        "",
        _row("Motivo", "ERP", "CRM"),
        "|---|---|---|",
        *(
            _row(reason.value, rejected_count("erp", reason), rejected_count("crm", reason))
            for reason in Reason
        ),
    ]
    return "\n".join(lines) + "\n"
