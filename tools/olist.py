"""Estudo de caso com dados públicos: o Olist Brazilian E-commerce visto como ERP × CRM.

"ERP" é a soma dos pagamentos de cada pedido; "CRM" é a soma de preço + frete dos itens.
Os dados são da Olist, sob licença CC BY-NC-SA 4.0, e não ficam no repositório: o script
baixa o arquivo do Kaggle para data/olist/ (ignorada pelo git) e grava os extratos ao lado.

Uso: python tools/olist.py [--archive data/olist/archive.zip] [--out data/olist]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import shutil
import urllib.request
import zipfile
from collections import defaultdict
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

DATASET_URL = "https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce"
HEADER = ["order_id", "amount", "customer", "order_date"]


def build_extracts(archive_path: Path, out_dir: Path) -> tuple[Path, Path]:
    """Grava erp_orders.csv e crm_orders.csv a partir do zip do Olist."""
    with zipfile.ZipFile(archive_path) as archive:
        orders = {
            row["order_id"]: (row["customer_id"], row["order_purchase_timestamp"][:10])
            for row in _rows(archive, "olist_orders_dataset.csv")
        }
        erp: defaultdict[str, Decimal] = defaultdict(Decimal)
        for row in _rows(archive, "olist_order_payments_dataset.csv"):
            erp[row["order_id"]] += Decimal(row["payment_value"])
        crm: defaultdict[str, Decimal] = defaultdict(Decimal)
        for row in _rows(archive, "olist_order_items_dataset.csv"):
            crm[row["order_id"]] += Decimal(row["price"]) + Decimal(row["freight_value"])
    out_dir.mkdir(parents=True, exist_ok=True)
    erp_path, crm_path = out_dir / "erp_orders.csv", out_dir / "crm_orders.csv"
    _write(erp_path, erp, orders)
    _write(crm_path, crm, orders)
    return erp_path, crm_path


def _rows(archive: zipfile.ZipFile, name: str) -> Iterator[dict[str, str]]:
    with archive.open(name) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))


def _write(path: Path, totals: dict[str, Decimal], orders: dict[str, tuple[str, str]]) -> None:
    # str(Decimal) e não f"{:.2f}": a soma sai como veio, sem arredondar. Um valor fora do
    # formato numa versão futura do Olist vai para rejected.csv em vez de ser corrigido aqui.
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(HEADER)
        for order_id in sorted(totals):
            customer, order_date = orders.get(order_id, ("", ""))
            writer.writerow([order_id, str(totals[order_id]), customer, order_date])


def download(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(DATASET_URL, timeout=300) as response, dest.open("wb") as file:
        shutil.copyfileobj(response, file)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive", type=Path, default=Path("data/olist/archive.zip"))
    parser.add_argument("--out", type=Path, default=Path("data/olist"))
    args = parser.parse_args()
    if not args.archive.exists():
        print(f"baixando {DATASET_URL}")
        download(args.archive)
    with args.archive.open("rb") as file:
        # O Kaggle pode publicar versões novas: o hash identifica a que foi usada.
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    print(f"arquivo: {args.archive} (SHA-256 {digest})")
    erp_path, crm_path = build_extracts(args.archive, args.out)
    print(f"extratos: {erp_path} e {crm_path}")


if __name__ == "__main__":
    main()
