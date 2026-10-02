# Conciliação ERP × CRM — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** uma CLI que concilia dois extratos CSV (ERP e CRM) com dois motores independentes (stdlib e pandas) que produzem saídas idênticas byte a byte, sem perder nenhuma linha.

**Architecture:** contrato compartilhado (`contract.py`: tipos do resultado, regex do valor, leitura UTF-8 e validação de cabeçalho) e dois motores que recebem caminhos e devolvem um `ReconciliationResult`. Gravação (`writer.py`), procedência (`inputs.py`) e CLI (`cli.py`) são comuns. Todos os testes de comportamento rodam nos dois motores por um único fixture parametrizado.

**Tech Stack:** Python ≥ 3.11, `csv` + `decimal` (motor stdlib), pandas ≥ 3.0 (motor pandas, opcional), pytest, hypothesis, ruff, mypy `--strict`, hatchling, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-29-conciliacao-erp-crm-design.md`

**Como este plano foi escrito.** Todo o código abaixo foi rascunhado e executado antes de entrar no plano: 162 testes passando em Python 3.11.15 e 3.14.6 com pandas 3.0.6, `ruff check`, `ruff format --check` e `mypy --strict` limpos. Mutações plantadas (regra de duplicidade desligada no motor pandas, precedência trocada, saída com CRLF) foram pegas pelos testes. Os comportamentos do pandas que a spec mandava conferir foram medidos, não supostos (ver "Decisões tomadas no plano").

## Global Constraints

- Python **≥ 3.11** (`requires-python = ">=3.11"`); CI em 3.11 e 3.14.
- O motor stdlib usa **só a biblioteca padrão**; `pip install .` não instala nada além do pacote.
- pandas é **dependência opcional** (`pip install .[pandas]`), importado só quando `--engine pandas` é escolhido. No desenvolvimento ele é **sempre** instalado (`.[pandas,dev]`): testes do motor pandas nunca são pulados.
- **Nunca alterar o dado antes de comparar:** sem `strip`, sem arredondamento; o que foge do formato vai para `rejected.csv` com um motivo.
- Valor válido: `re.fullmatch` com `-?[0-9]+(\.[0-9]{1,2})?`; nunca `\d`, nunca `float`.
- Saída determinística: UTF-8, terminador `"\n"` fixo, nada de data, hora ou nome do motor nos arquivos.
- Códigos de saída: 0 tudo conciliado, 1 divergências e/ou rejeições, 2 erro de uso ou de arquivo.
- **Comandos:** sempre o Python do venv do projeto, `.venv/Scripts/python` (Git Bash no Windows; no Linux, `.venv/bin/python`). Nunca `python` puro: nesta máquina ele aponta para o venv de outro projeto, sem pytest nem pandas.
- Commits pequenos, um por tarefa, mensagem em pt-BR no formato `tipo: descrição`, terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Aspas mal fechadas** (`A,"1,c,d` sem a aspa de fechamento): o `csv.reader` padrão engole o resto do arquivo num único campo, em silêncio. Esperado: erro de arquivo, código 2, nos dois motores. → `test_file_errors.py` (Tarefas 2 e 3), com `strict=True` no stdlib.
2. **Extratos do Windows**, com CRLF e BOM do Excel: devem conciliar igual a arquivos LF sem BOM. → `test_bom_and_crlf_are_accepted` (Tarefa 2).
3. **Checkout no Windows convertendo fixtures para CRLF** (`core.autocrlf`): o SHA-256 no `summary.md` e a comparação byte a byte quebrariam só na CI do Windows. → `.gitattributes` com `tests/fixtures/** -text` (Tarefa 1) e `test_fixtures_kept_lf_after_checkout` (Tarefa 6).
4. **Valores iguais com texto diferente** (`-0` × `0.00`, `00100` × `100`): o analista espera `matched`, porque a comparação é por valor `Decimal`, não por texto. → `test_amounts_compared_by_value_not_text` (Tarefa 2).
5. **`--out` apontando para um arquivo existente** (ou pasta sem permissão): esperado erro de uma linha e código 2, não *traceback*. → `test_exit_2_when_out_is_an_existing_file` (Tarefa 5).

## Decisões tomadas no plano

A spec deixou alguns pontos para "conferir durante o plano". Eles foram medidos assim:

| # | Decisão | Por quê |
|---|---|---|
| P1 | **Aspas mal fechadas interrompem** (código 2, "CSV inválido"). | Lacuna da spec, achada ao testar: sem `strict=True` o `csv.reader` engole o resto do arquivo num campo. O motor python do pandas já levanta `ParserError` nesse caso; com `strict=True` os dois concordam. É o princípio da Seção 4: arquivo que não dá para interpretar interrompe. |
| P2 | **Linha vazia tem 0 campos**, não "1 campo vazio" como a spec diz. | Medido: `csv.reader` devolve `[]` e o pandas devolve uma linha só de `NaN`. A classificação não muda (0 ≠ 4 → `malformed_row`, sem ID provável). |
| P3 | **Motor pandas:** `engine="python"`, `header=None`, `dtype=str`, `na_filter=False`, `skip_blank_lines=False`; leitura em duas passadas quando há linha larga. | Medido no pandas 3.0.6: linha **curta** é completada com `NaN` em silêncio; linha **longa** só é tratável por `on_bad_lines` com função, que existe só no motor python e não informa a posição da linha. A 1ª passada mede a maior largura; a 2ª lê com essa largura. Com `na_filter=False`, o único `NaN` restante é o preenchimento, então "campos não-`NaN`" é a contagem real de campos. |
| P4 | `read_text`, `column_positions` e `raw_fields` ficam no **contrato**. | Decodificar UTF-8 e validar o cabeçalho são especificação (como a regex): compartilhar garante mensagens de erro idênticas nos dois motores. A leitura do CSV, a classificação e o casamento continuam em cada motor. |
| P5 | Layout `src/` e módulos `engines/stdlib_engine.py` e `engines/pandas_engine.py`. | A árvore da spec é indicativa. Um módulo chamado `pandas.py` dentro do pacote confunde leitor e ferramentas com o pandas de verdade. |
| P6 | Mensagens, terminal e `summary.md` em pt-BR. | Coerente com a spec e com o analista; nomes de colunas e motivos continuam em inglês, como na spec. |
| P7 | `hypothesis`: `@settings(deadline=None)`. | A chave `deadline` foi conferida na documentação. Sem limite por exemplo, uma CI lenta não reprova um teste de lógica. |
| P8 | `-0` sai como `-0.00`. | Formatação com `f"{valor:.2f}"`, fiel ao sinal que veio. `-0` e `0` casam (`Decimal` igual). |
| P9 | Sem permissão de escrita em `--out` → código 2. | Falha de gravação é erro de arquivo, como os da Seção 4. |

## Estrutura de arquivos

```
.gitattributes              # LF no repositório; fixtures nunca convertidas
.gitignore
.github/workflows/ci.yml    # Ubuntu + Windows, 3.11 + 3.14
pyproject.toml              # hatchling; extras pandas e dev; ruff; mypy; pytest
README.md
src/reconcile/
  __init__.py
  __main__.py               # python -m reconcile
  contract.py               # tipos, Reason, regex, read_text, column_positions, raw_fields
  inputs.py                 # fingerprint(path) -> InputFile(name, sha256)
  writer.py                 # write_outputs, render_summary, format_amount
  cli.py                    # main(argv) -> código de saída
  engines/
    __init__.py             # ENGINE_NAMES, get_engine (import tardio do pandas)
    stdlib_engine.py        # reconcile(erp, crm) com csv + decimal
    pandas_engine.py        # reconcile(erp, crm) com pandas
tests/
  conftest.py               # fixtures engine (parametrizado), write_csv, run
  test_contract.py
  test_matching.py          # casamento, ordenação, texto preservado
  test_rejections.py        # motivos e precedência
  test_file_errors.py       # erros que interrompem
  test_writer.py
  test_cli.py
  test_scenario.py          # ponta a ponta, byte a byte
  test_properties.py        # hypothesis
  test_generate.py          # fumaça do gerador
  fixtures/scenario/        # 2 CSVs de entrada + expected/ (6 arquivos)
tools/
  generate.py               # dados sintéticos em escala
  benchmark.py              # stdlib × pandas, fora da suíte
```

---

### Task 1: Repositório, projeto e contrato

**Files:**
- Create: `.gitignore`, `.gitattributes`, `pyproject.toml`, `README.md`, `src/reconcile/__init__.py`, `src/reconcile/contract.py`
- Test: `tests/test_contract.py`

**Interfaces:**
- Consumes: nada.
- Produces (em `reconcile.contract`):
  - `REQUIRED_COLUMNS: tuple[str, ...]`, `AMOUNT_PATTERN: re.Pattern[str]`, `Source = Literal["erp", "crm"]`
  - `class Reason(Enum)`: `MALFORMED_ROW`, `MISSING_ID`, `ID_WHITESPACE`, `DUPLICATE_ID`, `INVALID_AMOUNT` (valores em minúsculas, nessa ordem de precedência)
  - dataclasses congeladas `Order(order_id, amount: Decimal, customer, order_date, line: int)`, `Rejected(source, line, reason, raw: dict[str, str], extra_fields: tuple[str, ...])`, `Pair(erp, crm)`, `ReconciliationResult(matched, amount_mismatch, missing_in_erp, missing_in_crm, rejected, erp_rows_read, crm_rows_read)`
  - `class InputError(Exception)`
  - `is_valid_amount(text: str) -> bool`, `read_text(path: Path) -> str`, `column_positions(path: Path, header: list[str]) -> dict[str, int]`, `raw_fields(header: list[str], fields: list[str]) -> dict[str, str]`

- [ ] **Step 1: Criar o repositório e gravar o design antes de qualquer código**

A spec e este plano entram sozinhos no primeiro commit, para que o histórico mostre que o design veio antes do código.

```bash
git init -b main
git add docs
git commit -m "docs: spec e plano da conciliação ERP × CRM" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: `git log --oneline` mostra 1 commit; `git show --stat HEAD` lista só os dois arquivos em `docs/superpowers/`.

- [ ] **Step 2: Criar `.gitignore`**

```gitignore
.venv/
__pycache__/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.hypothesis/
.coverage
dist/
build/
output/
data/
```

- [ ] **Step 3: Criar `.gitattributes`**

```gitattributes
* text=auto eol=lf
# Fixtures são comparadas byte a byte e têm o SHA-256 gravado no summary.md esperado:
# nenhuma conversão de fim de linha, em nenhum sistema.
tests/fixtures/** -text
```

- [ ] **Step 4: Criar `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "reconcile"
version = "0.1.0"
description = "Conciliação de pedidos entre extratos CSV de ERP e CRM, com dois motores equivalentes."
readme = "README.md"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
pandas = ["pandas>=3.0"]
dev = ["pytest>=8", "hypothesis>=6.100", "pytest-cov>=5", "ruff>=0.6", "mypy>=1.11"]

[project.scripts]
reconcile = "reconcile.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/reconcile"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "SIM"]

[tool.mypy]
python_version = "3.11"
strict = true
files = ["src", "tests"]

[[tool.mypy.overrides]]
module = ["pandas", "pandas.*"]
ignore_missing_imports = true
```

- [ ] **Step 5: Criar `README.md` provisório e o pacote**

`README.md` (o hatchling exige o arquivo citado em `readme`; o conteúdo final vem na Tarefa 9):

```markdown
# Conciliação ERP × CRM
```

`src/reconcile/__init__.py`:

```python
"""Conciliação de pedidos entre extratos CSV de ERP e CRM."""
```

- [ ] **Step 6: Criar o venv e instalar em modo editável**

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv -e ".[pandas,dev]"
.venv/Scripts/python -c "import reconcile, pandas, hypothesis; print(pandas.__version__)"
```

Expected: imprime uma versão `3.x` do pandas.

- [ ] **Step 7: Escrever os testes do contrato (vão falhar)**

`tests/test_contract.py`:

```python
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
```

- [ ] **Step 8: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_contract.py -q`
Expected: erro de coleta com `ModuleNotFoundError: No module named 'reconcile.contract'`.

- [ ] **Step 9: Implementar `src/reconcile/contract.py`**

```python
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
```

Atenção ao `"\N{BYTE ORDER MARK}"`: escreva o escape com o nome, como está. Um `\u` digitado pode chegar ao disco como o caractere invisível, que nenhuma revisão enxerga.

- [ ] **Step 10: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_contract.py -q`
Expected: `28 passed`.

- [ ] **Step 11: Lint, formatação e tipos**

```bash
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m ruff format --check src tests
.venv/Scripts/python -m mypy
```

Expected: `All checks passed!`, nenhum arquivo a reformatar, `Success: no issues found`.

- [ ] **Step 12: Commit**

```bash
git add .gitignore .gitattributes pyproject.toml README.md src tests
git commit -m "feat: projeto e contrato compartilhado entre os motores" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Motor stdlib

**Files:**
- Create: `src/reconcile/engines/__init__.py`, `src/reconcile/engines/stdlib_engine.py`, `tests/conftest.py`
- Test: `tests/test_matching.py`, `tests/test_rejections.py`, `tests/test_file_errors.py`

**Interfaces:**
- Consumes: tudo de `reconcile.contract` (Tarefa 1).
- Produces:
  - `reconcile.engines.Engine = Callable[[Path, Path], ReconciliationResult]`
  - `reconcile.engines.ENGINE_NAMES: tuple[str, ...]` (nesta tarefa, só `("stdlib",)`)
  - `reconcile.engines.EngineUnavailable(Exception)`, `reconcile.engines.get_engine(name: str) -> Engine`
  - `reconcile.engines.stdlib_engine.reconcile(erp_path: Path, crm_path: Path) -> ReconciliationResult`
  - fixtures de teste: `engine` (parametrizado por `ENGINE_NAMES`), `write_csv(name, content) -> Path`, `run(erp_text, crm_text) -> ReconciliationResult`; constante `HEADER` e alias `Run` em `tests/conftest.py`

Os testes desta tarefa são **a bateria dos dois motores**: na Tarefa 3, acrescentar `"pandas"` a `ENGINE_NAMES` faz cada um deles rodar também no motor pandas.

- [ ] **Step 1: Criar o registro de motores, por enquanto só com o stdlib**

`src/reconcile/engines/__init__.py`:

```python
"""Registro dos motores. O motor pandas só é importado quando pedido."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from reconcile.contract import ReconciliationResult

Engine = Callable[[Path, Path], ReconciliationResult]

ENGINE_NAMES = ("stdlib",)


class EngineUnavailable(Exception):
    """O motor pedido precisa de uma dependência que não está instalada."""


def get_engine(name: str) -> Engine:
    if name == "stdlib":
        from reconcile.engines import stdlib_engine

        return stdlib_engine.reconcile
    if name == "pandas":
        try:
            from reconcile.engines import pandas_engine
        except ModuleNotFoundError as exc:
            if exc.name != "pandas":
                raise
            raise EngineUnavailable(
                "o motor pandas precisa do pandas instalado: pip install .[pandas]"
            ) from None
        return pandas_engine.reconcile
    raise ValueError(f"motor desconhecido: {name!r}")
```

- [ ] **Step 2: Criar `tests/conftest.py`**

```python
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from reconcile.contract import ReconciliationResult
from reconcile.engines import ENGINE_NAMES, Engine, get_engine

HEADER = "order_id,amount,customer,order_date\n"

Run = Callable[[str, str], ReconciliationResult]


@pytest.fixture(params=ENGINE_NAMES)
def engine(request: pytest.FixtureRequest) -> Engine:
    """Todo teste que usa este fixture roda uma vez em cada motor."""
    return get_engine(request.param)


@pytest.fixture
def write_csv(tmp_path: Path) -> Callable[[str, str], Path]:
    def write(name: str, content: str) -> Path:
        path = tmp_path / name
        path.write_bytes(content.encode("utf-8"))  # bytes: nada de tradução de "\n"
        return path

    return write


@pytest.fixture
def run(engine: Engine, write_csv: Callable[[str, str], Path]) -> Run:
    """Grava os dois CSVs (texto completo, com cabeçalho) e concilia."""

    def run_(erp: str, crm: str) -> ReconciliationResult:
        return engine(write_csv("erp.csv", erp), write_csv("crm.csv", crm))

    return run_
```

- [ ] **Step 3: Escrever os testes de casamento**

`tests/test_matching.py`:

```python
"""Casamento por order_id em arquivos sem nenhuma linha rejeitada."""

from __future__ import annotations

from decimal import Decimal

from conftest import HEADER, Run

from reconcile.contract import Order, Pair


def test_groups_orders_by_presence_and_amount(run: Run) -> None:
    result = run(
        HEADER + "A,10.00,Ana,2024-01-01\nB,20.00,Bia,2024-01-02\nC,30.00,Caio,2024-01-03\n",
        HEADER + "B,20.01,Bia,2024-01-02\nA,10,Ana,2024-01-01\nD,40.00,Duda,2024-01-04\n",
    )
    assert result.matched == (
        Pair(
            erp=Order("A", Decimal("10.00"), "Ana", "2024-01-01", line=2),
            crm=Order("A", Decimal("10"), "Ana", "2024-01-01", line=3),
        ),
    )
    assert [p.erp.order_id for p in result.amount_mismatch] == ["B"]
    assert result.amount_mismatch[0].crm.amount - result.amount_mismatch[0].erp.amount == Decimal(
        "0.01"
    )
    assert result.missing_in_erp == (Order("D", Decimal("40.00"), "Duda", "2024-01-04", line=4),)
    assert result.missing_in_crm == (Order("C", Decimal("30.00"), "Caio", "2024-01-03", line=4),)
    assert result.rejected == ()
    assert (result.erp_rows_read, result.crm_rows_read) == (3, 3)


def test_ids_are_compared_exactly_and_case_sensitive(run: Run) -> None:
    result = run(HEADER + "ped-1,1,a,d\n", HEADER + "PED-1,1,a,d\n")
    assert [o.order_id for o in result.missing_in_crm] == ["ped-1"]
    assert [o.order_id for o in result.missing_in_erp] == ["PED-1"]


def test_amounts_compared_by_value_not_text(run: Run) -> None:
    result = run(HEADER + "A,-0,a,d\nB,00100,b,d\n", HEADER + "A,0.00,a,d\nB,100,b,d\n")
    assert [p.erp.order_id for p in result.matched] == ["A", "B"]


def test_output_groups_are_sorted_by_order_id_code_point(run: Run) -> None:
    ids = ["b", "B", "a10", "a2", "Á"]
    erp = HEADER + "".join(f"{i},1,c,d\n" for i in ids)
    result = run(erp, HEADER)
    assert [o.order_id for o in result.missing_in_crm] == sorted(ids)  # B < a10 < a2 < b < Á


def test_context_columns_pass_through_untouched(run: Run) -> None:
    result = run(
        HEADER + '007,1,00123,01/02/2024\n"N\nL",2,"Silva, Ana",ontem\n',
        HEADER + "007,1,00123,2024-02-01\n",
    )
    pair = result.matched[0]
    assert (pair.erp.order_id, pair.erp.customer, pair.erp.order_date) == (
        "007",
        "00123",
        "01/02/2024",
    )
    assert pair.crm.order_date == "2024-02-01"
    multiline = result.missing_in_crm[0]
    assert (multiline.order_id, multiline.customer, multiline.order_date) == (
        "N\nL",
        "Silva, Ana",
        "ontem",
    )


def test_line_is_record_position_not_physical_line(run: Run) -> None:
    result = run(HEADER + 'A,1,"duas\nlinhas",d\nB,1,c,d\n', HEADER)
    assert [o.line for o in result.missing_in_crm] == [2, 3]


def test_extra_columns_are_ignored(run: Run) -> None:
    result = run(
        "region,order_date,order_id,notes,customer,amount\nSul,d,A,x,c,5\n",
        HEADER + "A,5.0,c,d\n",
    )
    assert result.matched[0].erp == Order("A", Decimal("5"), "c", "d", line=2)


def test_header_only_files_reconcile_to_nothing(run: Run) -> None:
    result = run(HEADER, HEADER.rstrip("\n"))
    assert result.matched == result.amount_mismatch == ()
    assert result.missing_in_erp == result.missing_in_crm == ()
    assert result.rejected == ()
    assert (result.erp_rows_read, result.crm_rows_read) == (0, 0)


def test_bom_and_crlf_are_accepted(run: Run) -> None:
    crlf = HEADER.replace("\n", "\r\n") + "A,1,c,d\r\n"
    result = run("\N{BYTE ORDER MARK}" + crlf, HEADER + "A,1,c,d\n")
    assert [p.erp.order_id for p in result.matched] == ["A"]
```

- [ ] **Step 4: Escrever os testes de rejeição**

`tests/test_rejections.py`:

```python
"""Quarentena: cada linha rejeitada recebe um único motivo, na ordem de precedência."""

from __future__ import annotations

import pytest
from conftest import HEADER, Run

from reconcile.contract import Reason, Rejected


def reasons(run: Run, erp_rows: str) -> list[tuple[int, str]]:
    result = run(HEADER + erp_rows, HEADER)
    return [(r.line, r.reason.value) for r in result.rejected]


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ("A,1,c\n", "malformed_row"),
        ("A,1,c,d,x\n", "malformed_row"),
        (",1,c,d\n", "missing_id"),
        ("   ,1,c,d\n", "missing_id"),
        ("\xa0,1,c,d\n", "missing_id"),
        (" A,1,c,d\n", "id_whitespace"),
        ("A ,1,c,d\n", "id_whitespace"),
        ("\tA,1,c,d\n", "id_whitespace"),
        ("A,,c,d\n", "invalid_amount"),
        ("A,100.005,c,d\n", "invalid_amount"),
        ('A,"1,000.00",c,d\n', "invalid_amount"),
        ("A,R$ 10,c,d\n", "invalid_amount"),
        ("A,NaN,c,d\n", "invalid_amount"),
        ("A,Infinity,c,d\n", "invalid_amount"),
        ("A,1e3,c,d\n", "invalid_amount"),
        ("A,١٠٠,c,d\n", "invalid_amount"),
        ('A,"100\n",c,d\n', "invalid_amount"),
    ],
)
def test_single_reason_per_row(run: Run, row: str, reason: str) -> None:
    assert reasons(run, row) == [(2, reason)]


def test_every_copy_of_a_duplicate_id_is_rejected(run: Run) -> None:
    assert reasons(run, "A,1,c,d\nB,2,c,d\nA,1,c,d\n") == [(2, "duplicate_id"), (4, "duplicate_id")]


def test_duplicate_wins_over_invalid_amount(run: Run) -> None:
    assert reasons(run, "A,100.00,c,d\nA,abc,c,d\n") == [(2, "duplicate_id"), (3, "duplicate_id")]


def test_missing_id_wins_over_invalid_amount(run: Run) -> None:
    assert reasons(run, ",abc,c,d\n") == [(2, "missing_id")]


def test_duplicate_check_is_per_file(run: Run) -> None:
    result = run(HEADER + "A,1,c,d\n", HEADER + "A,1,c,d\n")
    assert result.rejected == () and len(result.matched) == 1


def test_malformed_row_makes_valid_rows_with_its_probable_id_duplicates(run: Run) -> None:
    # A linha 3 tem campos a menos, mas o campo na posição do order_id é "A".
    assert reasons(run, "A,1,c,d\nA,1\n") == [(2, "duplicate_id"), (3, "malformed_row")]


def test_malformed_row_without_probable_id_does_not_count(run: Run) -> None:
    header = "customer,amount,order_date,order_id\n"
    result = run(header + "c,1,d,A\nc,1\n", HEADER)
    assert [(r.line, r.reason.value) for r in result.rejected] == [(3, "malformed_row")]
    assert [o.order_id for o in result.missing_in_crm] == ["A"]


def test_blank_line_in_the_middle_is_malformed_and_counted(run: Run) -> None:
    result = run(HEADER + "A,1,c,d\n\nB,1,c,d\n", HEADER)
    assert [(r.line, r.reason.value) for r in result.rejected] == [(3, "malformed_row")]
    assert [o.line for o in result.missing_in_crm] == [2, 4]
    assert result.erp_rows_read == 3


def test_final_newline_is_not_a_blank_line_but_an_extra_one_is(run: Run) -> None:
    assert reasons(run, "A,1,c,d\n") == []
    assert reasons(run, "A,1,c,d\n\n") == [(3, "malformed_row")]


def test_rejected_keeps_the_row_as_it_came(run: Run) -> None:
    result = run(HEADER + " A,1.5,00123,ontem\n", HEADER)
    assert result.rejected == (
        Rejected(
            source="erp",
            line=2,
            reason=Reason.ID_WHITESPACE,
            raw={"order_id": " A", "amount": "1.5", "customer": "00123", "order_date": "ontem"},
            extra_fields=(),
        ),
    )


def test_malformed_row_fills_by_position_and_keeps_extra_fields(run: Run) -> None:
    result = run(HEADER + 'A,1,c,d,x,"y,z"\nB,2\n\n', HEADER)
    long_row, short_row, blank = result.rejected
    assert long_row.raw == {"order_id": "A", "amount": "1", "customer": "c", "order_date": "d"}
    assert long_row.extra_fields == ("x", "y,z")
    assert short_row.raw == {"order_id": "B", "amount": "2", "customer": "", "order_date": ""}
    assert short_row.extra_fields == ()
    assert blank.raw == {"order_id": "", "amount": "", "customer": "", "order_date": ""}


def test_rejected_sorted_erp_first_then_by_line(run: Run) -> None:
    result = run(HEADER + "A,x,c,d\n,1,c,d\n", HEADER + ",1,c,d\nB,x,c,d\n")
    assert [(r.source, r.line) for r in result.rejected] == [
        ("erp", 2),
        ("erp", 3),
        ("crm", 2),
        ("crm", 3),
    ]
```

- [ ] **Step 5: Escrever os testes de erro de arquivo**

`tests/test_file_errors.py`:

```python
"""Problemas de arquivo interrompem; os dois motores dão o mesmo erro."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import HEADER

from reconcile.contract import InputError
from reconcile.engines import Engine

WriteCsv = Callable[[str, str], Path]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "arquivo vazio"),
        ("order_id,amount,customer\nA,1,c\n", "faltam colunas obrigatórias: order_date"),
        ("\nA,1,c,d\n", "faltam colunas obrigatórias"),
        ("order_id,amount,customer,order_date,amount\n", "coluna repetida"),
        (HEADER + 'A,"1,c,d\nB,2,c,d\n', "CSV inválido"),
        (HEADER + 'A,"1"x,c,d\n', "CSV inválido"),
    ],
)
def test_file_level_problems_raise_input_error_with_path(
    engine: Engine, write_csv: WriteCsv, content: str, message: str
) -> None:
    bad = write_csv("ruim.csv", content)
    good = write_csv("bom.csv", HEADER)
    with pytest.raises(InputError, match=message) as exc:
        engine(bad, good)
    assert "ruim.csv" in str(exc.value)


def test_non_utf8_content(engine: Engine, write_csv: WriteCsv, tmp_path: Path) -> None:
    bad = tmp_path / "latin1.csv"
    bad.write_bytes(HEADER.encode() + "A,1,José,d\n".encode("latin-1"))
    with pytest.raises(InputError, match="não é UTF-8"):
        engine(write_csv("bom.csv", HEADER), bad)


def test_missing_file(engine: Engine, write_csv: WriteCsv, tmp_path: Path) -> None:
    with pytest.raises(InputError, match="não encontrado"):
        engine(tmp_path / "sumiu.csv", write_csv("bom.csv", HEADER))
```

- [ ] **Step 6: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_matching.py tests/test_rejections.py tests/test_file_errors.py -q`
Expected: os 45 testes terminam em `ERROR` no fixture `engine`, com `ModuleNotFoundError: No module named 'reconcile.engines.stdlib_engine'`.

- [ ] **Step 7: Implementar `src/reconcile/engines/stdlib_engine.py`**

```python
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
```

Pontos que um revisor deve conferir aqui: `csv.reader(..., strict=True)` (Review Focus 1); `io.StringIO(text, newline="")` para que o `csv` trate `\r\n` e quebras dentro de aspas; a contagem de duplicidade inclui o ID provável das linhas malformadas e exclui IDs em branco.

- [ ] **Step 8: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest -q`
Expected: `73 passed` (28 do contrato + 45 desta tarefa).

- [ ] **Step 9: Lint, formatação e tipos**

```bash
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m ruff format --check src tests
.venv/Scripts/python -m mypy
```

Expected: tudo limpo.

- [ ] **Step 10: Commit**

```bash
git add src tests
git commit -m "feat: motor stdlib com quarentena e casamento por order_id" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Motor pandas

**Files:**
- Create: `src/reconcile/engines/pandas_engine.py`
- Modify: `src/reconcile/engines/__init__.py` (a linha `ENGINE_NAMES`)

**Interfaces:**
- Consumes: `reconcile.contract` (Tarefa 1); a bateria de testes da Tarefa 2.
- Produces: `reconcile.engines.pandas_engine.reconcile(erp_path: Path, crm_path: Path) -> ReconciliationResult`; `ENGINE_NAMES == ("stdlib", "pandas")`.

Esta tarefa não escreve testes novos: o TDD aqui é ligar o motor na bateria existente e vê-la falhar.

- [ ] **Step 1: Ligar o motor pandas na bateria**

Em `src/reconcile/engines/__init__.py`, trocar:

```python
ENGINE_NAMES = ("stdlib",)
```

por:

```python
ENGINE_NAMES = ("stdlib", "pandas")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest -q`
Expected: os 45 testes `[pandas]` falham com `ModuleNotFoundError: No module named 'reconcile.engines.pandas_engine'`; os 73 restantes passam.

- [ ] **Step 3: Implementar `src/reconcile/engines/pandas_engine.py`**

```python
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
```

Pontos que um revisor deve conferir aqui: nenhuma conversão passa por `float` (`Decimal` só nas linhas válidas); `np.select` recebe as condições na mesma ordem de `Reason`, e trocar uma das duas listas sem a outra rotula errado; `skip_blank_lines=False`; a segunda leitura só acontece quando alguma linha é mais larga que o cabeçalho.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest -q`
Expected: `118 passed`.

- [ ] **Step 5: Conferir que a bateria realmente pega o motor pandas**

Mutação temporária: em `pandas_engine.py`, troque `ids.duplicated(keep=False) & filled` por `ids.duplicated(keep=False) & filled & False` e rode `.venv/Scripts/python -m pytest -q`.
Expected: 3 falhas, todas `[pandas]`, em `test_rejections.py` (as de duplicidade). **Desfaça a mutação** e confirme `118 passed` de novo.

- [ ] **Step 6: Lint, formatação e tipos**

```bash
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m ruff format --check src tests
.venv/Scripts/python -m mypy
```

Expected: tudo limpo.

- [ ] **Step 7: Commit**

```bash
git add src
git commit -m "feat: motor pandas equivalente, lendo tudo como texto" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Procedência e gravação das saídas

**Files:**
- Create: `src/reconcile/inputs.py`, `src/reconcile/writer.py`
- Test: `tests/test_writer.py`

**Interfaces:**
- Consumes: `Order`, `Pair`, `Reason`, `Rejected`, `ReconciliationResult` (Tarefa 1).
- Produces:
  - `reconcile.inputs.InputFile(name: str, sha256: str)` e `fingerprint(path: Path) -> InputFile`
  - `reconcile.writer.OUTPUT_FILES: tuple[str, ...]` (os 6 nomes)
  - `reconcile.writer.format_amount(value: Decimal) -> str`
  - `reconcile.writer.write_outputs(result, erp_input: InputFile, crm_input: InputFile, out_dir: Path) -> None`
  - `reconcile.writer.render_summary(result, erp_input, crm_input) -> str`

- [ ] **Step 1: Escrever os testes**

`tests/test_writer.py`:

```python
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from reconcile.contract import Order, Pair, Reason, ReconciliationResult, Rejected
from reconcile.inputs import InputFile, fingerprint
from reconcile.writer import OUTPUT_FILES, format_amount, write_outputs

ERP_IN = InputFile(name="erp.csv", sha256="a" * 64)
CRM_IN = InputFile(name="crm.csv", sha256="b" * 64)


def order(order_id: str, amount: str, line: int, customer: str = "c") -> Order:
    return Order(order_id, Decimal(amount), customer, "2024-01-01", line)


RESULT = ReconciliationResult(
    matched=(Pair(order("A", "10.5", 2), order("A", "10.50", 3, "Ana")),),
    amount_mismatch=(Pair(order("B", "20", 3), order("B", "19.99", 2)),),
    missing_in_erp=(order("D", "-5", 4),),
    missing_in_crm=(order("C", "7", 4, "Silva, Ana"),),
    rejected=(
        Rejected(
            "erp",
            5,
            Reason.MALFORMED_ROW,
            {"order_id": "E", "amount": "1", "customer": "c", "order_date": "d"},
            ("x", "y,z"),
        ),
        Rejected(
            "crm",
            5,
            Reason.INVALID_AMOUNT,
            {"order_id": "F", "amount": "1e3", "customer": "c", "order_date": "d"},
            (),
        ),
    ),
    erp_rows_read=4,
    crm_rows_read=4,
)


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


@pytest.mark.parametrize(
    ("value", "text"),
    [("100", "100.00"), ("100.5", "100.50"), ("-20", "-20.00"), ("0.01", "0.01")],
)
def test_format_amount_uses_two_places(value: str, text: str) -> None:
    assert format_amount(Decimal(value)) == text


def test_writes_the_six_files_with_lf_and_utf8(tmp_path: Path) -> None:
    write_outputs(RESULT, ERP_IN, CRM_IN, tmp_path / "out")
    out = tmp_path / "out"
    assert sorted(p.name for p in out.iterdir()) == sorted(OUTPUT_FILES)
    for name in OUTPUT_FILES:
        assert b"\r\n" not in (out / name).read_bytes()


def test_csv_contents(tmp_path: Path) -> None:
    write_outputs(RESULT, ERP_IN, CRM_IN, tmp_path)
    assert read(tmp_path / "matched.csv") == (
        "order_id,amount,erp_customer,erp_order_date,crm_customer,crm_order_date\n"
        "A,10.50,c,2024-01-01,Ana,2024-01-01\n"
    )
    assert read(tmp_path / "amount_mismatch.csv") == (
        "order_id,erp_amount,crm_amount,difference,erp_customer,crm_customer,erp_line,crm_line\n"
        "B,20.00,19.99,-0.01,c,c,3,2\n"
    )
    assert read(tmp_path / "missing_in_erp.csv") == (
        "order_id,amount,customer,order_date,crm_line\nD,-5.00,c,2024-01-01,4\n"
    )
    assert read(tmp_path / "missing_in_crm.csv") == (
        'order_id,amount,customer,order_date,erp_line\nC,7.00,"Silva, Ana",2024-01-01,4\n'
    )
    assert read(tmp_path / "rejected.csv") == (
        "source,line,reason,order_id,amount,customer,order_date,extra_fields\n"
        'erp,5,malformed_row,E,1,c,d,"[""x"",""y,z""]"\n'
        "crm,5,invalid_amount,F,1e3,c,d,\n"
    )


def test_summary(tmp_path: Path) -> None:
    write_outputs(RESULT, ERP_IN, CRM_IN, tmp_path)
    summary = read(tmp_path / "summary.md")
    assert "`difference = crm_amount - erp_amount`" in summary
    assert f"| ERP | erp.csv | {'a' * 64} |" in summary
    assert "| matched | 1 |" in summary
    assert "Soma das diferenças em `amount_mismatch`: -0.01" in summary
    assert "| ERP | 4 | 1 | 1 | 1 | 1 | sim |" in summary
    assert "| CRM | 4 | 1 | 1 | 1 | 1 | sim |" in summary
    assert "| malformed_row | 1 | 0 |" in summary
    assert "| invalid_amount | 0 | 1 |" in summary
    assert "| duplicate_id | 0 | 0 |" in summary  # todo motivo aparece, mesmo zerado


def test_summary_shows_when_closure_fails(tmp_path: Path) -> None:
    broken = ReconciliationResult((), (), (), (), (), erp_rows_read=1, crm_rows_read=0)
    write_outputs(broken, ERP_IN, CRM_IN, tmp_path)
    assert "| ERP | 1 | 0 | 0 | 0 | 0 | NÃO |" in read(tmp_path / "summary.md")


def test_overwrites_previous_run_and_leaves_no_staging_dir(tmp_path: Path) -> None:
    (tmp_path / "matched.csv").write_text("velho", encoding="utf-8")
    write_outputs(RESULT, ERP_IN, CRM_IN, tmp_path)
    assert read(tmp_path / "matched.csv").startswith("order_id,")
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(OUTPUT_FILES)


def test_fingerprint_uses_name_and_sha256(tmp_path: Path) -> None:
    path = tmp_path / "pedidos.csv"
    path.write_bytes(b"abc")
    assert fingerprint(path) == InputFile(
        name="pedidos.csv",
        sha256="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    )
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_writer.py -q`
Expected: erro de coleta com `ModuleNotFoundError: No module named 'reconcile.inputs'`.

- [ ] **Step 3: Implementar `src/reconcile/inputs.py`**

```python
"""Procedência das entradas: nome do arquivo e SHA-256 do conteúdo."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InputFile:
    name: str  # só o nome; o caminho varia entre máquinas e quebraria o determinismo
    sha256: str


def fingerprint(path: Path) -> InputFile:
    with path.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    return InputFile(name=path.name, sha256=digest)
```

- [ ] **Step 4: Implementar `src/reconcile/writer.py`**

```python
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
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest -q`
Expected: `128 passed`.

- [ ] **Step 6: Lint, formatação e tipos**

```bash
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m ruff format --check src tests
.venv/Scripts/python -m mypy
```

- [ ] **Step 7: Commit**

```bash
git add src tests
git commit -m "feat: gravação determinística das 6 saídas e do summary.md" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Linha de comando

**Files:**
- Create: `src/reconcile/cli.py`, `src/reconcile/__main__.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `get_engine`, `ENGINE_NAMES`, `EngineUnavailable` (Tarefas 2–3); `InputError` (Tarefa 1); `fingerprint` e `write_outputs` (Tarefa 4).
- Produces: `reconcile.cli.main(argv: Sequence[str] | None = None) -> int`; o comando `reconcile` (via `[project.scripts]`, já declarado na Tarefa 1) e `python -m reconcile`.

- [ ] **Step 1: Escrever os testes**

`tests/test_cli.py`:

```python
from __future__ import annotations

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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_cli.py -q`
Expected: erro de coleta com `ModuleNotFoundError: No module named 'reconcile.cli'`.

- [ ] **Step 3: Implementar `src/reconcile/cli.py`**

```python
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
```

- [ ] **Step 4: Implementar `src/reconcile/__main__.py`**

```python
from reconcile.cli import main

raise SystemExit(main())
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest -q`
Expected: `139 passed`.

- [ ] **Step 6: Conferir o comando instalado**

Run: `.venv/Scripts/reconcile --help`
Expected: ajuda do argparse com `--erp`, `--crm`, `--out`, `--engine {stdlib,pandas}`.

- [ ] **Step 7: Lint, formatação e tipos**

```bash
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m ruff format --check src tests
.venv/Scripts/python -m mypy
```

- [ ] **Step 8: Commit**

```bash
git add src tests
git commit -m "feat: CLI com códigos de saída 0/1/2" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Cenário de referência ponta a ponta

**Files:**
- Create: `tests/fixtures/scenario/erp_orders.csv`, `tests/fixtures/scenario/crm_orders.csv`, `tests/fixtures/scenario/expected/` (6 arquivos, gerados pela CLI e revisados)
- Test: `tests/test_scenario.py`

**Interfaces:**
- Consumes: `reconcile.cli.main`, `ENGINE_NAMES`, `OUTPUT_FILES`.
- Produces: nada consumido por outras tarefas.

O cenário cobre cada grupo e cada motivo de rejeição: valor `1e3`, ID duplicado, ID com espaço, linha curta, ID vazio, linha vazia, campo a mais, ID `007` e `customer` `00123` preservados, campo com vírgula e com quebra de linha, valor `250.5` × `250.50` casando e `80.00` × `80.01` divergindo.

- [ ] **Step 1: Criar as entradas**

`tests/fixtures/scenario/erp_orders.csv` (a linha 14 é vazia de propósito; o arquivo termina com uma única quebra de linha):

```csv
order_id,amount,customer,order_date
PED-001,100.00,Ana Souza,2024-03-01
PED-002,250.5,Bruno Lima,2024-03-02
PED-003,80.00,"Silva, Carla",2024-03-02
PED-004,-20.00,Diego Rocha,2024-03-03
PED-005,1e3,Elisa Prado,2024-03-04
PED-006,60.00,Fábio Nunes,2024-03-05
PED-006,60.00,Fábio Nunes,2024-03-05
 PED-007,45.00,Gabi Melo,2024-03-06
PED-008,30.00,Hugo Reis
,15.00,Íris Dias,2024-03-07
PED-009,10.00,Ivo Paz,2024-03-07
007,12.00,00123,07/03/2024

PED-010,99.99,Joana Cruz,2024-03-08,nota extra
```

`tests/fixtures/scenario/crm_orders.csv`:

```csv
order_id,amount,customer,order_date
PED-002,250.50,Bruno Lima,2024-03-02
PED-001,100.00,Ana Souza,2024-03-01
PED-003,80.01,Carla Silva,2024-03-02
PED-004,-20,Diego Rocha,2024-03-03
PED-011,70.00,Karen Alves,2024-03-09
007,12,00123,2024-03-07
PED-012,100.005,Leo Batista,2024-03-10
"PED-013",55.00,"Maria
Clara",2024-03-11
```

Confira que nenhum dos dois tem `\r`:

```bash
.venv/Scripts/python -c "import pathlib; print([p.name for p in pathlib.Path('tests/fixtures/scenario').glob('*.csv') if b'\r' in p.read_bytes()])"
```

Expected: `[]`.

- [ ] **Step 2: Escrever o teste**

`tests/test_scenario.py`:

```python
"""Ponta a ponta: a CLI, em cada motor, gera exatamente os bytes revisados em expected/.

Os arquivos esperados são regenerados à mão e revisados no git diff:

    python -m reconcile --erp tests/fixtures/scenario/erp_orders.csv \
        --crm tests/fixtures/scenario/crm_orders.csv --out tests/fixtures/scenario/expected

Não existe opção automática de "atualizar referências": ela convida a aprovar sem ler.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reconcile.cli import main
from reconcile.engines import ENGINE_NAMES
from reconcile.writer import OUTPUT_FILES

SCENARIO = Path(__file__).parent / "fixtures" / "scenario"


@pytest.mark.parametrize(
    "path", sorted(SCENARIO.rglob("*.*")), ids=lambda p: p.relative_to(SCENARIO).as_posix()
)
def test_fixtures_kept_lf_after_checkout(path: Path) -> None:
    # O .gitattributes marca tests/fixtures como -text. Sem isso, o checkout no Windows
    # converteria para CRLF, e o SHA-256 no summary.md e a comparação byte a byte quebrariam.
    assert b"\r" not in path.read_bytes()


@pytest.mark.parametrize("engine", ENGINE_NAMES)
@pytest.mark.parametrize("name", OUTPUT_FILES)
def test_output_matches_reviewed_file_byte_for_byte(tmp_path: Path, engine: str, name: str) -> None:
    code = main(
        [
            "--erp", str(SCENARIO / "erp_orders.csv"),
            "--crm", str(SCENARIO / "crm_orders.csv"),
            "--out", str(tmp_path),
            "--engine", engine,
        ]
    )  # fmt: skip
    assert code == 1  # o cenário tem divergências de propósito
    assert (tmp_path / name).read_bytes() == (SCENARIO / "expected" / name).read_bytes()
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_scenario.py -q`
Expected: `12 failed, 2 passed`. Os 12 testes byte a byte falham com `FileNotFoundError` (ainda não existe `expected/`); os 2 que passam são os de LF das entradas. Depois do Step 4 o teste de LF passa a cobrir também os 6 arquivos esperados.

- [ ] **Step 4: Gerar os arquivos esperados e revisar um por um**

```bash
.venv/Scripts/python -m reconcile --erp tests/fixtures/scenario/erp_orders.csv --crm tests/fixtures/scenario/crm_orders.csv --out tests/fixtures/scenario/expected
```

Expected no terminal: `matched: 4 | amount_mismatch: 1 | missing_in_erp: 2 | missing_in_crm: 1 | rejected: 9`, código de saída 1.

**Não aceite a saída por ela existir.** Compare cada arquivo com o conteúdo abaixo, que foi conferido regra por regra contra a spec. Se algum byte diferir, pare e investigue o motor, não o arquivo.

`expected/matched.csv`:

```csv
order_id,amount,erp_customer,erp_order_date,crm_customer,crm_order_date
007,12.00,00123,07/03/2024,00123,2024-03-07
PED-001,100.00,Ana Souza,2024-03-01,Ana Souza,2024-03-01
PED-002,250.50,Bruno Lima,2024-03-02,Bruno Lima,2024-03-02
PED-004,-20.00,Diego Rocha,2024-03-03,Diego Rocha,2024-03-03
```

`expected/amount_mismatch.csv`:

```csv
order_id,erp_amount,crm_amount,difference,erp_customer,crm_customer,erp_line,crm_line
PED-003,80.00,80.01,0.01,"Silva, Carla",Carla Silva,4,4
```

`expected/missing_in_erp.csv`:

```csv
order_id,amount,customer,order_date,crm_line
PED-011,70.00,Karen Alves,2024-03-09,6
PED-013,55.00,"Maria
Clara",2024-03-11,9
```

`expected/missing_in_crm.csv`:

```csv
order_id,amount,customer,order_date,erp_line
PED-009,10.00,Ivo Paz,2024-03-07,12
```

`expected/rejected.csv`:

```csv
source,line,reason,order_id,amount,customer,order_date,extra_fields
erp,6,invalid_amount,PED-005,1e3,Elisa Prado,2024-03-04,
erp,7,duplicate_id,PED-006,60.00,Fábio Nunes,2024-03-05,
erp,8,duplicate_id,PED-006,60.00,Fábio Nunes,2024-03-05,
erp,9,id_whitespace, PED-007,45.00,Gabi Melo,2024-03-06,
erp,10,malformed_row,PED-008,30.00,Hugo Reis,,
erp,11,missing_id,,15.00,Íris Dias,2024-03-07,
erp,14,malformed_row,,,,,
erp,15,malformed_row,PED-010,99.99,Joana Cruz,2024-03-08,"[""nota extra""]"
crm,8,invalid_amount,PED-012,100.005,Leo Batista,2024-03-10,
```

`expected/summary.md` (os dois SHA-256 só batem se as entradas forem idênticas byte a byte às do Step 1):

````markdown
# Resumo da conciliação

Convenção de sinal: `difference = crm_amount - erp_amount` (positivo: o CRM registrou mais que o ERP).

## Entradas

| Lado | Arquivo | SHA-256 |
|---|---|---|
| ERP | erp_orders.csv | 24804e14a3b1bde7786a44175dc75f4625bf238cf293e6f209c634a25643660d |
| CRM | crm_orders.csv | 2d3816025533492e3eb4eea659f86113c392c03942cdc8372797b8d604b08344 |

## Grupos

| Grupo | Pedidos |
|---|---|
| matched | 4 |
| amount_mismatch | 1 |
| missing_in_erp | 2 |
| missing_in_crm | 1 |
| rejected | 9 |

Soma das diferenças em `amount_mismatch`: 0.01

## Fechamento

Cada linha lida de um arquivo está em exatamente um grupo. "Só neste lado" é `missing_in_crm` para o ERP e `missing_in_erp` para o CRM.

| Lado | Linhas lidas | Rejeitadas | matched | amount_mismatch | Só neste lado | Fecha? |
|---|---|---|---|---|---|---|
| ERP | 14 | 8 | 4 | 1 | 1 | sim |
| CRM | 8 | 1 | 4 | 1 | 2 | sim |

## Rejeições por motivo

| Motivo | ERP | CRM |
|---|---|---|
| malformed_row | 3 | 0 |
| missing_id | 1 | 0 |
| id_whitespace | 1 | 0 |
| duplicate_id | 2 | 0 |
| invalid_amount | 1 | 1 |
````

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest -q`
Expected: `159 passed`.

- [ ] **Step 6: Lint, formatação e tipos**

```bash
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m ruff format --check src tests
.venv/Scripts/python -m mypy
```

- [ ] **Step 7: Commit e conferência do `-text`**

```bash
git add tests
git commit -m "test: cenário de referência comparado byte a byte nos dois motores" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git check-attr text -- tests/fixtures/scenario/erp_orders.csv
```

Expected na última linha: `tests/fixtures/scenario/erp_orders.csv: text: unset`.

---

### Task 7: Testes de propriedade

**Files:**
- Test: `tests/test_properties.py`

**Interfaces:**
- Consumes: `get_engine("stdlib")`, `get_engine("pandas")`, `ReconciliationResult`.
- Produces: nada.

- [ ] **Step 1: Escrever o teste**

`tests/test_properties.py`:

```python
"""Propriedades que valem para qualquer par de CSVs, nos dois motores ao mesmo tempo."""

from __future__ import annotations

import csv
import io
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from reconcile.contract import ReconciliationResult
from reconcile.engines import get_engine

HEADER = ["order_id", "amount", "customer", "order_date"]

# Alfabeto pequeno para forçar colisões de ID e casamentos entre os lados.
ids = st.sampled_from(["A", "B", "C", "a", " A", "A ", "", "  ", "007"])
amounts = st.sampled_from(["1", "1.0", "1.00", "2", "-1", "0", "1.005", "abc", "", "1e3", "NaN"])
texts = st.sampled_from(["c", "", "00123", "Silva, Ana", 'dito "x"', "duas\nlinhas"])

good_rows = st.tuples(ids, amounts, texts, texts).map(list)
# Linhas com campos de menos, de mais, ou vazias (lista vazia vira linha em branco).
ragged_rows = st.sampled_from([0, 1, 2, 3, 5, 6]).flatmap(
    lambda n: st.lists(texts | ids, min_size=n, max_size=n)
)
rows = st.one_of(good_rows, good_rows, good_rows, ragged_rows)
files = st.lists(rows, max_size=12)


def to_csv(records: list[list[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(records)
    return buffer.getvalue()


def reconcile_both(erp: str, crm: str) -> tuple[ReconciliationResult, ReconciliationResult]:
    with tempfile.TemporaryDirectory() as tmp:
        erp_path, crm_path = Path(tmp, "erp.csv"), Path(tmp, "crm.csv")
        erp_path.write_bytes(erp.encode("utf-8"))
        crm_path.write_bytes(crm.encode("utf-8"))
        return (
            get_engine("stdlib")(erp_path, crm_path),
            get_engine("pandas")(erp_path, crm_path),
        )


# deadline=None: o motor pandas passa com folga dos 200 ms padrão por exemplo em
# máquinas lentas de CI, e um tempo variável não pode reprovar um teste de lógica.
@settings(deadline=None, max_examples=200)
@given(erp=files, crm=files)
def test_engines_agree_and_every_row_lands_exactly_once(
    erp: list[list[str]], crm: list[list[str]]
) -> None:
    stdlib_result, pandas_result = reconcile_both(to_csv(erp), to_csv(crm))

    # 1. Diferencial: os dois motores devolvem exatamente o mesmo resultado.
    assert stdlib_result == pandas_result
    result = stdlib_result

    # 2. Partição: cada linha de dados aparece em exatamente um lugar do resultado.
    seen = [(r.source, r.line) for r in result.rejected]
    for pair in result.matched + result.amount_mismatch:
        seen += [("erp", pair.erp.line), ("crm", pair.crm.line)]
    seen += [("crm", o.line) for o in result.missing_in_erp]
    seen += [("erp", o.line) for o in result.missing_in_crm]
    expected = [("erp", n) for n in range(2, result.erp_rows_read + 2)]
    expected += [("crm", n) for n in range(2, result.crm_rows_read + 2)]
    assert sorted(seen) == sorted(expected)

    # 3. Fechamento: as duas equações do summary.md.
    matched, mismatch = len(result.matched), len(result.amount_mismatch)
    erp_rejected = sum(r.source == "erp" for r in result.rejected)
    crm_rejected = sum(r.source == "crm" for r in result.rejected)
    assert result.erp_rows_read == erp_rejected + matched + mismatch + len(result.missing_in_crm)
    assert result.crm_rows_read == crm_rejected + matched + mismatch + len(result.missing_in_erp)

    # 4. Coerência: matched tem valores iguais; amount_mismatch, diferentes.
    assert all(p.erp.amount == p.crm.amount for p in result.matched)
    assert all(p.erp.amount != p.crm.amount for p in result.amount_mismatch)
```

- [ ] **Step 2: Rodar**

Run: `.venv/Scripts/python -m pytest tests/test_properties.py -q --hypothesis-show-statistics`
Expected: `1 passed`, com `200 passing` nas estatísticas. (Este teste passa de primeira, porque o código já existe; o próximo passo prova que ele não é decorativo.)

- [ ] **Step 3: Conferir que a propriedade pega divergência entre os motores**

Mutação temporária: em `pandas_engine.py`, dentro da lista de condições do `np.select`, troque a ordem de `~filled,` e `ids != stripped,`. Rode o Step 2.
Expected: falha com um exemplo mínimo do tipo `crm=[[' A', '1', 'c', 'c']]`. **Desfaça a mutação** e confirme `1 passed`.

- [ ] **Step 4: Suíte completa, lint e tipos**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m ruff format --check src tests
.venv/Scripts/python -m mypy
```

Expected: `160 passed`; o resto limpo.

- [ ] **Step 5: Commit**

```bash
git add tests
git commit -m "test: propriedades de equivalência, partição, fechamento e coerência" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Gerador em escala e benchmark

**Files:**
- Create: `tools/generate.py`, `tools/benchmark.py`
- Modify: `pyproject.toml` (`files` do mypy)
- Test: `tests/test_generate.py`

**Interfaces:**
- Consumes: `get_engine`, `ENGINE_NAMES`, `Engine`.
- Produces: `generate(orders: int, out_dir: Path, seed: int, rates: Rates | None = None) -> tuple[Path, Path]` (ERP, CRM); `Rates` (dataclass de taxas por defeito).

- [ ] **Step 1: Escrever o teste de fumaça**

`tests/test_generate.py`:

```python
"""Teste de fumaça do gerador: a saída dele concilia, fecha as contas e os motores concordam."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from generate import generate  # noqa: E402

from reconcile.engines import get_engine  # noqa: E402


def test_generated_data_reconciles_and_closes(tmp_path: Path) -> None:
    erp, crm = generate(2_000, tmp_path, seed=7)
    result = get_engine("stdlib")(erp, crm)
    assert result == get_engine("pandas")(erp, crm)

    assert result.matched and result.amount_mismatch and result.rejected
    assert result.missing_in_erp and result.missing_in_crm
    reasons = {r.reason.value for r in result.rejected}
    assert {"invalid_amount", "duplicate_id", "malformed_row"} <= reasons

    erp_rejected = sum(r.source == "erp" for r in result.rejected)
    crm_rejected = sum(r.source == "crm" for r in result.rejected)
    both = len(result.matched) + len(result.amount_mismatch)
    assert result.erp_rows_read == erp_rejected + both + len(result.missing_in_crm)
    assert result.crm_rows_read == crm_rejected + both + len(result.missing_in_erp)


def test_same_seed_same_bytes(tmp_path: Path) -> None:
    first = generate(500, tmp_path / "a", seed=1)
    second = generate(500, tmp_path / "b", seed=1)
    assert [p.read_bytes() for p in first] == [p.read_bytes() for p in second]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_generate.py -q`
Expected: erro de coleta com `ModuleNotFoundError: No module named 'generate'`.

- [ ] **Step 3: Implementar `tools/generate.py`**

```python
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
```

- [ ] **Step 4: Implementar `tools/benchmark.py`**

```python
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
```

- [ ] **Step 5: Incluir `tools` na checagem de tipos**

Em `pyproject.toml`, na seção `[tool.mypy]`, trocar:

```toml
files = ["src", "tests"]
```

por:

```toml
files = ["src", "tests", "tools"]
```

- [ ] **Step 6: Rodar tudo**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check src tests tools
.venv/Scripts/python -m ruff format --check src tests tools
.venv/Scripts/python -m mypy
```

Expected: `162 passed`; o resto limpo.

- [ ] **Step 7: Rodar o benchmark uma vez**

Run: `.venv/Scripts/python tools/benchmark.py --orders 10000 100000 --repeat 3`
Expected: uma linha com a máquina e uma tabela Markdown com 4 linhas. Guarde a saída: ela vai para o README na Tarefa 9. (No rascunho, numa máquina Intel com Windows: stdlib 0,87 s e pandas 1,56 s para 100 mil pedidos; os seus números vão variar.)

- [ ] **Step 8: Commit**

```bash
git add tools tests pyproject.toml
git commit -m "feat: gerador de dados sintéticos e benchmark dos motores" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: CI e README

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md` (substituir o provisório)

**Interfaces:**
- Consumes: os comandos de lint, tipos e testes das tarefas anteriores; a saída do benchmark da Tarefa 8.
- Produces: nada.

As versões das actions foram conferidas no GitHub em 2026-10-02: `actions/checkout@v7` (v7.0.1) e `actions/setup-python@v7` (v7.0.0, entrada `python-version` mantida).

- [ ] **Step 1: Criar `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python-version: ["3.11", "3.14"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: ${{ matrix.python-version }}
      - name: Instalar
        run: python -m pip install -e ".[pandas,dev]"
      - name: Lint e formatação
        run: |
          python -m ruff check src tests tools
          python -m ruff format --check src tests tools
      - name: Tipos
        run: python -m mypy
      - name: Testes
        run: python -m pytest --cov=reconcile --cov-report=term-missing
```

A matriz Ubuntu × Windows é o que prova a afirmação "saída idêntica byte a byte nos dois sistemas": o mesmo `tests/fixtures/scenario/expected/` é comparado nos dois.

- [ ] **Step 2: Escrever o `README.md` final**

````markdown
# Conciliação de pedidos ERP × CRM

O ERP (financeiro) e o CRM (comercial) deveriam concordar sobre os pedidos, mas divergem.
Esta ferramenta de linha de comando compara os dois extratos CSV e separa os pedidos em
grupos, **sem deixar nenhuma linha sumir em silêncio**: cada linha lida termina em
exatamente um arquivo de saída, e o `summary.md` prova isso com as contas de fechamento.

O mesmo problema é resolvido por **dois motores independentes**, um só com a biblioteca
padrão (`csv` + `decimal`) e outro com pandas. Os dois passam pela mesma bateria de testes
e geram saídas idênticas byte a byte, no Linux e no Windows.

## Uso

```bash
pip install .            # motor stdlib, sem dependências
pip install .[pandas]    # acrescenta o motor pandas

reconcile --erp erp_orders.csv --crm crm_orders.csv --out output/ --engine stdlib
```

| Código de saída | Significado |
|---|---|
| 0 | tudo conciliado, sem divergências nem rejeições |
| 1 | executou; há divergências e/ou rejeições |
| 2 | não executou: erro de uso ou de arquivo (mensagem de uma linha em stderr) |

## Entrada

Dois CSVs UTF-8 (BOM aceito), separados por vírgula, com as colunas `order_id`, `amount`,
`customer` e `order_date`, em qualquer ordem. Colunas extras são ignoradas.

## Saída

| Arquivo | Conteúdo |
|---|---|
| `matched.csv` | pedido nos dois lados, mesmo valor |
| `amount_mismatch.csv` | pedido nos dois lados, valores diferentes; `difference = crm − erp` |
| `missing_in_erp.csv` | só no CRM |
| `missing_in_crm.csv` | só no ERP |
| `rejected.csv` | quarentena, com o motivo e a linha como veio |
| `summary.md` | contagens, prova de fechamento, rejeições por motivo e SHA-256 das entradas |

## Princípio: a ferramenta nunca altera o dado antes de comparar

Ela não tira espaços nem arredonda valores. O que não está no formato esperado vai para a
quarentena com um motivo explícito, e o analista decide. Cada linha rejeitada recebe um
único motivo, o primeiro que falhar nesta ordem:

| Motivo | Condição |
|---|---|
| `malformed_row` | número de campos diferente do cabeçalho (inclui linha vazia) |
| `missing_id` | `order_id` vazio ou só com espaços |
| `id_whitespace` | espaço no início ou no fim do ID |
| `duplicate_id` | o mesmo ID mais de uma vez no mesmo arquivo: **todas** as cópias saem |
| `invalid_amount` | valor fora de `-?[0-9]+(\.[0-9]{1,2})?` (`1e3`, `NaN`, `100.005`, `1,000.00`…) |

A expressão regular vem antes do `Decimal` porque o `Decimal` aceita `1e3`, `NaN` e
`Infinity`; e usa `[0-9]` em vez de `\d`, que em Python aceita dígitos de qualquer alfabeto.

## Os dois motores

A fronteira entre eles é: **caminhos dos arquivos entram, um resultado canônico sai**
(dataclasses imutáveis, sem nenhum tipo do pandas). Leitura, validação e casamento ficam
dentro de cada motor, porque é ali que o pandas se comporta diferente: inferência de
tipos, `float`, zeros à esquerda, linhas em branco puladas e linhas curtas completadas com
`NaN`. O motor pandas lê tudo como texto (`dtype=str`, `na_filter=False`) e usa o `NaN` de
preenchimento, o único que sobra, para contar os campos de cada linha.

## Testes

```bash
pip install -e .[pandas,dev]
pytest
```

- **Casos de exemplo:** um teste por regra, com o CSV escrito dentro do próprio teste.
- **Cenário de referência:** a CLI gera, nos dois motores, exatamente os bytes revisados em
  `tests/fixtures/scenario/expected/`.
- **Propriedades (`hypothesis`):** para CSVs gerados com IDs colidindo, espaços, linhas
  tortas e valores inválidos, os motores concordam, cada linha aparece exatamente uma vez
  no resultado e as contas fecham.
- CI no GitHub Actions com Ubuntu e Windows, `ruff` e `mypy --strict`.

## Desempenho

Gerado com `python tools/benchmark.py --orders 10000 100000 --repeat 3`:

<!-- tabela do benchmark -->

O motor pandas não é mais rápido aqui, e isso é esperado: para não perder linhas, ele usa
o leitor `engine="python"` (o único que aceita uma função em `on_bad_lines`) e converte
cada valor válido para `Decimal`, em vez de usar `float`. A comparação mostra o custo de
exigir exatidão de uma ferramenta feita para velocidade.
````

- [ ] **Step 3: Colar a tabela do benchmark**

No `README.md`, substituir a linha `<!-- tabela do benchmark -->` pelas linhas que o benchmark imprimiu na Tarefa 8, Step 7 (a linha da máquina e a tabela).

- [ ] **Step 4: Verificação final local**

```bash
.venv/Scripts/python -m pytest -q --cov=reconcile --cov-report=term-missing
.venv/Scripts/python -m ruff check src tests tools
.venv/Scripts/python -m ruff format --check src tests tools
.venv/Scripts/python -m mypy
git status --short
```

Expected: `162 passed` e a tabela de cobertura; lint e tipos limpos; `git status` mostra só `README.md` e `.github/`.

- [ ] **Step 5: Commit**

```bash
git add README.md .github
git commit -m "docs: README e CI com Ubuntu e Windows" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

A publicação no GitHub (criar o repositório remoto e fazer o push) **não faz parte deste plano**: é uma ação externa e precisa da confirmação do usuário. A CI só roda depois dela.
