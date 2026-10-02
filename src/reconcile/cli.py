"""Linha de comando: argumentos -> motor -> gravação -> resumo no terminal."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from reconcile.contract import InputError, ReconciliationResult
from reconcile.engines import ENGINE_NAMES, EngineUnavailable, get_engine
from reconcile.inputs import fingerprint
from reconcile.writer import write_outputs

EXIT_CLEAN = 0  # executou; tudo conciliado
EXIT_DIVERGENT = 1  # executou; há divergências e/ou rejeições
EXIT_ERROR = 2  # não executou: erro de uso ou de arquivo (argparse também usa 2)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        engine = get_engine(args.engine)
        result = engine(args.erp, args.crm)
        erp_input, crm_input = fingerprint(args.erp), fingerprint(args.crm)
    except (InputError, EngineUnavailable) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return EXIT_ERROR
    try:
        write_outputs(result, erp_input, crm_input, args.out)
    except OSError as exc:
        print(f"erro: não foi possível gravar em {args.out}: {exc.strerror}", file=sys.stderr)
        return EXIT_ERROR
    _report(args.engine, result, args.out)
    divergent = (
        result.amount_mismatch or result.missing_in_erp or result.missing_in_crm or result.rejected
    )
    return EXIT_DIVERGENT if divergent else EXIT_CLEAN


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reconcile", description="Concilia pedidos entre extratos CSV do ERP e do CRM."
    )
    parser.add_argument("--erp", required=True, type=Path, help="CSV exportado do ERP")
    parser.add_argument("--crm", required=True, type=Path, help="CSV exportado do CRM")
    parser.add_argument(
        "--out", type=Path, default=Path("output"), help="pasta de saída (padrão: output/)"
    )
    parser.add_argument(
        "--engine", choices=ENGINE_NAMES, default="stdlib", help="motor (padrão: stdlib)"
    )
    return parser


def _report(engine: str, result: ReconciliationResult, out_dir: Path) -> None:
    print(f"motor: {engine}")
    print(
        f"matched: {len(result.matched)} | amount_mismatch: {len(result.amount_mismatch)} | "
        f"missing_in_erp: {len(result.missing_in_erp)} | "
        f"missing_in_crm: {len(result.missing_in_crm)} | rejected: {len(result.rejected)}"
    )
    print(f"saída: {out_dir}")
