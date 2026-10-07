"""Gera um par de CSVs sintéticos em escala, com defeitos plantados em taxas configuráveis.

Uso: python tools/generate.py --orders 100000 --out data/ --seed 42
"""

from __future__ import annotations

import argparse
import csv
import random
from dataclasses import asdict, dataclass
from pathlib import Path

HEADER = ["order_id", "amount", "customer", "order_date"]
INVALID_AMOUNTS = ["1e3", "NaN", "R$ 10", "1,000.00", "10.005", ""]


@dataclass(frozen=True)
class Rates:
    """Probabilidade de cada defeito, por pedido. No máximo um defeito por pedido."""

    only_erp: float = 0.01
    only_crm: float = 0.01
    mismatch: float = 0.02
    invalid_amount: float = 0.005
    duplicate: float = 0.005
    malformed: float = 0.002


def generate(
    orders: int, out_dir: Path, seed: int, rates: Rates | None = None
) -> tuple[Path, Path]:
    rng = random.Random(seed)
    rates = rates or Rates()
    erp: list[list[str]] = []
    crm: list[list[str]] = []
    for n in range(orders):
        cents = rng.randint(-5_000, 500_000)  # negativos são estornos
        row = [f"PED-{n:07d}", _money(cents), f"cliente-{rng.randint(1, 5_000):05d}", _date(rng)]
        copy = list(row)
        match _pick_defect(rng, rates):
            case "only_erp":
                erp.append(row)
            case "only_crm":
                crm.append(row)
            case "mismatch":
                copy[1] = _money(cents + rng.choice([-1, 1]) * rng.randint(1, 10_000))
                erp.append(row)
                crm.append(copy)
            case "invalid_amount":
                copy[1] = rng.choice(INVALID_AMOUNTS)
                erp.append(row)
                crm.append(copy)
            case "duplicate":
                erp.append(row)
                crm.extend([copy, list(copy)])
            case "malformed":
                erp.append(row)
                crm.append(copy[:2])
            case _:
                erp.append(row)
                crm.append(copy)
    rng.shuffle(crm)  # a ordem dos extratos não é a mesma nos dois sistemas
    out_dir.mkdir(parents=True, exist_ok=True)
    return _write(out_dir / "erp_orders.csv", erp), _write(out_dir / "crm_orders.csv", crm)


def _pick_defect(rng: random.Random, rates: Rates) -> str | None:
    roll = rng.random()
    for name, rate in asdict(rates).items():
        if roll < rate:
            return name
        roll -= rate
    return None


def _money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def _date(rng: random.Random) -> str:
    return f"2024-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"


def _write(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera CSVs sintéticos de ERP e CRM.")
    parser.add_argument("--orders", type=int, default=10_000)
    parser.add_argument("--out", type=Path, default=Path("data"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    erp, crm = generate(args.orders, args.out, args.seed)
    print(f"gerados: {erp} e {crm}")


if __name__ == "__main__":
    main()
