"""Contrato compartilhado entre os motores: tipos do resultado e regras de formato.

Tudo aqui é especificação, não implementação. Cada motor lê e classifica as linhas do
seu jeito; o que é comum é o formato do resultado e as regras que definem um arquivo
e um valor válidos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Literal

REQUIRED_COLUMNS = ("order_id", "amount", "customer", "order_date")

# Usar sempre com fullmatch. [0-9] em vez de \d: em Python, \d aceita dígitos de
# qualquer alfabeto ("١٠٠" viraria 100 no Decimal). E fullmatch em vez de "^...$",
# porque "$" aceita uma quebra de linha no fim ("100\n").
AMOUNT_PATTERN = re.compile(r"-?[0-9]+(\.[0-9]{1,2})?")

Source = Literal["erp", "crm"]


class Reason(Enum):
    """Motivos de rejeição, na ordem de precedência (o primeiro que falhar vale)."""

    MALFORMED_ROW = "malformed_row"
    MISSING_ID = "missing_id"
    ID_WHITESPACE = "id_whitespace"
    DUPLICATE_ID = "duplicate_id"
    INVALID_AMOUNT = "invalid_amount"


@dataclass(frozen=True)
class Order:
    """Uma linha válida."""

    order_id: str
    amount: Decimal
    customer: str
    order_date: str
    line: int  # linha como a planilha mostra (cabeçalho = 1)


@dataclass(frozen=True)
class Rejected:
    source: Source
    line: int
    reason: Reason
    raw: dict[str, str]  # a linha como veio, por posição do cabeçalho
    extra_fields: tuple[str, ...]  # campos além do cabeçalho; vazio se não é malformada


@dataclass(frozen=True)
class Pair:
    """O pedido existe nos dois lados."""

    erp: Order
    crm: Order


@dataclass(frozen=True)
class ReconciliationResult:
    matched: tuple[Pair, ...]
    amount_mismatch: tuple[Pair, ...]
    missing_in_erp: tuple[Order, ...]  # só no CRM
    missing_in_crm: tuple[Order, ...]  # só no ERP
    rejected: tuple[Rejected, ...]
    erp_rows_read: int
    crm_rows_read: int


class InputError(Exception):
    """Arquivo que não dá para interpretar: a execução é interrompida (código 2)."""


def is_valid_amount(text: str) -> bool:
    return AMOUNT_PATTERN.fullmatch(text) is not None


def read_text(path: Path) -> str:
    """Lê o arquivo inteiro como UTF-8, aceitando o BOM que o Excel grava."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise InputError(f"{path}: arquivo não encontrado") from None
    except OSError as exc:
        raise InputError(f"{path}: não foi possível ler o arquivo ({exc.strerror})") from None
    try:
        # Decodifica sem tirar o BOM para que a posição do erro seja a do arquivo.
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputError(
            f"{path}: conteúdo não é UTF-8 (byte inválido na posição {exc.start})"
        ) from None
    text = text.removeprefix("\N{BYTE ORDER MARK}")
    if text == "":
        raise InputError(f"{path}: arquivo vazio, sem cabeçalho")
    return text


def column_positions(path: Path, header: list[str]) -> dict[str, int]:
    """Valida o cabeçalho e devolve a posição de cada coluna obrigatória.

    Nomes são comparados exatamente: "Order_ID" e " amount" não servem.
    """
    seen: set[str] = set()
    for name in header:
        if name in seen:
            raise InputError(f"{path}: coluna repetida no cabeçalho: {name!r}")
        seen.add(name)
    missing = [column for column in REQUIRED_COLUMNS if column not in seen]
    if missing:
        found = ", ".join(repr(name) for name in header) or "nenhuma coluna"
        raise InputError(
            f"{path}: faltam colunas obrigatórias: {', '.join(missing)} "
            f"(cabeçalho encontrado: {found})"
        )
    return {column: header.index(column) for column in REQUIRED_COLUMNS}


def raw_fields(header: list[str], fields: list[str]) -> dict[str, str]:
    """Preenche as colunas do cabeçalho por posição; as que faltam ficam vazias."""
    return {name: fields[i] if i < len(fields) else "" for i, name in enumerate(header)}
