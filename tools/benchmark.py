"""Mede o tempo dos dois motores sobre os mesmos dados. Fica fora da suíte de testes.

Tempo medido em CI compartilhado é ruidoso demais para virar asserção; os números vão
para o README junto com a descrição da máquina.

Uso: python tools/benchmark.py --orders 10000 100000 --repeat 3
"""

from __future__ import annotations

import argparse
import platform
import tempfile
import time
from pathlib import Path

from generate import generate

from reconcile.engines import ENGINE_NAMES, Engine, get_engine


def main() -> None:
    parser = argparse.ArgumentParser(description="Compara o tempo dos motores.")
    parser.add_argument("--orders", type=int, nargs="+", default=[10_000, 100_000])
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()

    print(f"Python {platform.python_version()} | {platform.platform()} | {platform.processor()}")
    print("| Pedidos | Motor | Melhor de N (s) |")
    print("|---|---|---|")
    with tempfile.TemporaryDirectory() as tmp:
        for orders in args.orders:
            erp, crm = generate(orders, Path(tmp, str(orders)), seed=42)
            for name in ENGINE_NAMES:
                engine = get_engine(name)
                best = min(_timed(engine, erp, crm) for _ in range(args.repeat))
                print(f"| {orders:,} | {name} | {best:.2f} |")


def _timed(engine: Engine, erp: Path, crm: Path) -> float:
    start = time.perf_counter()
    engine(erp, crm)
    return time.perf_counter() - start


if __name__ == "__main__":
    main()
