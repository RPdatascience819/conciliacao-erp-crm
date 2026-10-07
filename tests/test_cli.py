from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import HEADER

import reconcile.engines
from reconcile.cli import main

WriteCsv = Callable[[str, str], Path]


def args(erp: Path, crm: Path, out: Path, engine: str = "stdlib") -> list[str]:
    return ["--erp", str(erp), "--crm", str(crm), "--out", str(out), "--engine", engine]


@pytest.mark.parametrize("engine", ["stdlib", "pandas"])
def test_exit_0_when_everything_reconciles(
    write_csv: WriteCsv, tmp_path: Path, capsys: pytest.CaptureFixture[str], engine: str
) -> None:
    erp = write_csv("erp.csv", HEADER + "A,1,c,d\n")
    crm = write_csv("crm.csv", HEADER + "A,1.00,c,d\n")
    assert main(args(erp, crm, tmp_path / "out", engine)) == 0
    stdout = capsys.readouterr().out
    assert f"motor: {engine}" in stdout
    assert "matched: 1" in stdout
    assert (tmp_path / "out" / "summary.md").exists()


@pytest.mark.parametrize(
    ("erp_rows", "crm_rows"),
    [("A,1,c,d\n", "A,2,c,d\n"), ("A,1,c,d\n", ""), ("", "A,1,c,d\n"), ("A,x,c,d\n", "")],
)
def test_exit_1_on_any_divergence_or_rejection(
    write_csv: WriteCsv, tmp_path: Path, erp_rows: str, crm_rows: str
) -> None:
    erp = write_csv("erp.csv", HEADER + erp_rows)
    crm = write_csv("crm.csv", HEADER + crm_rows)
    assert main(args(erp, crm, tmp_path / "out")) == 1


def test_exit_2_on_file_error_without_traceback_and_without_output(
    write_csv: WriteCsv, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    erp = write_csv("erp.csv", "order_id,amount\n")
    crm = write_csv("crm.csv", HEADER)
    assert main(args(erp, crm, tmp_path / "out")) == 2
    err = capsys.readouterr().err
    assert err.startswith("erro: ") and "erp.csv" in err and "Traceback" not in err
    assert len(err.strip().splitlines()) == 1
    assert not (tmp_path / "out").exists()


def test_exit_2_when_out_is_an_existing_file(write_csv: WriteCsv, tmp_path: Path) -> None:
    erp = write_csv("erp.csv", HEADER)
    crm = write_csv("crm.csv", HEADER)
    blocker = tmp_path / "out"
    blocker.write_text("sou um arquivo", encoding="utf-8")
    assert main(args(erp, crm, blocker)) == 2


def test_exit_2_on_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--erp", "x.csv"])
    assert exc.value.code == 2


def test_missing_pandas_gives_install_hint(
    write_csv: WriteCsv,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # None em sys.modules faz "import pandas" falhar com ModuleNotFoundError, como se
    # o pandas não estivesse instalado. O motor sai do cache para ser importado de novo.
    monkeypatch.setitem(sys.modules, "pandas", None)
    monkeypatch.delitem(sys.modules, "reconcile.engines.pandas_engine", raising=False)
    monkeypatch.delattr(reconcile.engines, "pandas_engine", raising=False)
    erp = write_csv("erp.csv", HEADER)
    crm = write_csv("crm.csv", HEADER)
    assert main(args(erp, crm, tmp_path / "out", "pandas")) == 2
    assert "pip install .[pandas]" in capsys.readouterr().err


def test_default_out_dir_is_output(
    write_csv: WriteCsv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    erp = write_csv("erp.csv", HEADER)
    crm = write_csv("crm.csv", HEADER)
    monkeypatch.chdir(tmp_path)
    assert main(["--erp", str(erp), "--crm", str(crm)]) == 0
    assert (tmp_path / "output" / "matched.csv").exists()


def test_write_error_names_the_file_and_says_nothing_changed(
    write_csv: WriteCsv,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def replace(src: object, dst: object) -> None:
        raise PermissionError(13, "Acesso negado", str(tmp_path / "out" / "matched.csv"))

    monkeypatch.setattr("reconcile.writer.os.replace", replace)
    erp = write_csv("erp.csv", HEADER)
    crm = write_csv("crm.csv", HEADER)
    assert main(args(erp, crm, tmp_path / "out")) == 2
    err = capsys.readouterr().err
    assert len(err.strip().splitlines()) == 1 and "Traceback" not in err
    assert "matched.csv" in err and "Acesso negado" in err
    assert "nenhuma saída foi alterada" in err


def test_terminal_without_utf8_keeps_exit_code_and_message(
    write_csv: WriteCsv, tmp_path: Path
) -> None:
    # Num pipe do Windows o stdout é cp1252: "Δ" não existe nele e o print quebrava depois
    # de gravar, saindo com 1 ("há divergências") num caso todo conciliado.
    erp = write_csv("erp.csv", HEADER + "A,1,c,d\n")
    crm = write_csv("crm.csv", HEADER + "A,1.00,c,d\n")
    out = tmp_path / "saída-Δ"
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    done = subprocess.run(
        [sys.executable, "-m", "reconcile", *args(erp, crm, out)],
        capture_output=True,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert f"saída: {out}" in done.stdout.decode("utf-8")
