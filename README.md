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

Python 3.14.6 | Windows-11-10.0.26200-SP0 | Intel64 Family 6 Model 191 Stepping 2, GenuineIntel

| Pedidos | Motor | Melhor de N (s) |
|---|---|---|
| 10,000 | stdlib | 0.06 |
| 10,000 | pandas | 0.12 |
| 100,000 | stdlib | 0.99 |
| 100,000 | pandas | 2.41 |

O motor pandas não é mais rápido aqui, e isso é esperado: para não perder linhas, ele usa
o leitor `engine="python"` (o único que aceita uma função em `on_bad_lines`) e converte
cada valor válido para `Decimal`, em vez de usar `float`. A comparação mostra o custo de
exigir exatidão de uma ferramenta feita para velocidade.
