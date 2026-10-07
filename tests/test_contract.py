from __future__ import annotations

from pathlib import Path

import pytest

from reconcile.contract import InputError, column_positions, is_valid_amount, read_text


@pytest.mark.parametrize("text", ["100", "100.5", "-20.00", "0", "-0", "00100"])
def test_valid_amounts(text: str) -> None:
    assert is_valid_amount(text)


@pytest.mark.parametrize(
    "text",
    [
        "100.005",
        "1,000.00",
        "R$ 10",
        "NaN",
        "Infinity",
        "1e3",
        "",
        " 100",
        "100 ",
        "+100",
        ".5",
        "100.",
        "١٠٠",
        "100\n",
    ],
)
def test_invalid_amounts(text: str) -> None:
    assert not is_valid_amount(text)


def test_read_text_strips_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "a.csv"
    path.write_bytes(b"\xef\xbb\xbforder_id\n")
    assert read_text(path) == "order_id\n"


def test_read_text_reports_position_of_invalid_byte(tmp_path: Path) -> None:
    path = tmp_path / "a.csv"
    path.write_bytes(b"ab\xe9\n")
    with pytest.raises(InputError, match=r"não é UTF-8.*posição 2"):
        read_text(path)


def test_read_text_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="não encontrado"):
        read_text(tmp_path / "nao_existe.csv")


@pytest.mark.parametrize("content", [b"", b"\xef\xbb\xbf"])
def test_read_text_rejects_empty_file(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "a.csv"
    path.write_bytes(content)
    with pytest.raises(InputError, match="arquivo vazio"):
        read_text(path)


def test_column_positions_accepts_extra_columns_in_any_order() -> None:
    header = ["customer", "extra", "order_date", "amount", "order_id"]
    assert column_positions(Path("x.csv"), header) == {
        "order_id": 4,
        "amount": 3,
        "customer": 0,
        "order_date": 2,
    }


def test_column_positions_compares_names_exactly() -> None:
    header = ["Order_ID", " amount", "customer", "order_date"]
    with pytest.raises(InputError, match=r"faltam colunas obrigatórias: order_id, amount") as exc:
        column_positions(Path("x.csv"), header)
    assert "' amount'" in str(exc.value)  # o nome encontrado aparece com o espaço visível


def test_column_positions_rejects_repeated_column() -> None:
    header = ["order_id", "amount", "customer", "order_date", "amount"]
    with pytest.raises(InputError, match="coluna repetida no cabeçalho: 'amount'"):
        column_positions(Path("x.csv"), header)
