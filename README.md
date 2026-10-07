# Conciliação de pedidos ERP × CRM

[![CI](https://github.com/RPdatascience819/conciliacao-erp-crm/actions/workflows/ci.yml/badge.svg)](https://github.com/RPdatascience819/conciliacao-erp-crm/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
[![Licença MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green)](LICENSE)

O ERP (financeiro) e o CRM (comercial) deveriam concordar sobre os pedidos, mas divergem.
Esta ferramenta de linha de comando compara os dois extratos CSV e separa os pedidos em
grupos, **sem deixar nenhuma linha sumir em silêncio**: cada linha lida termina em
exatamente um arquivo de saída, e o `summary.md` prova isso com as contas de fechamento.

O mesmo problema é resolvido por **dois motores independentes**, um só com a biblioteca
padrão (`csv` + `decimal`) e outro com pandas. Os dois passam pela mesma bateria de testes
e geram saídas idênticas byte a byte, no Linux e no Windows.

## O que este projeto demonstra

- **Exatidão antes de conveniência.** Valores em `Decimal`, nunca `float`; nada é
  arredondado, aparado ou corrigido antes de comparar. O que foge do formato vai para a
  quarentena com o motivo.
- **Prova, não promessa.** Cada linha lida termina em exatamente um arquivo, e o
  `summary.md` fecha as contas. Testes de propriedade (`hypothesis`) verificam isso em
  entradas geradas, além dos casos escritos à mão.
- **Dois motores, um contrato.** A mesma especificação implementada com a biblioteca
  padrão e com pandas, com saídas idênticas byte a byte. Os pontos em que o pandas
  "ajuda" demais (inferência de tipos, `NaN`, linhas puladas) estão neutralizados.
- **Falha segura.** As 6 saídas são trocadas de uma vez: um arquivo travado no Windows não
  deixa a pasta com metade de uma execução e metade de outra.
- **Dados reais com honestidade.** O estudo de caso com o Olist separa o que os números
  mostram do que é hipótese.
- **Design antes do código.** A [spec](docs/superpowers/specs/2026-09-29-conciliacao-erp-crm-design.md)
  e o [plano de implementação](docs/superpowers/plans/2026-10-02-conciliacao-erp-crm.md)
  registram as decisões e as alternativas descartadas.

## Uso

```bash
git clone https://github.com/RPdatascience819/conciliacao-erp-crm.git
cd conciliacao-erp-crm
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

## Estudo de caso: dados públicos do Olist

Os testes usam dados sintéticos porque precisam de gabarito: cada defeito é plantado e a
resposta certa é conhecida. Para ver a ferramenta diante de dados reais, `tools/olist.py`
monta um par ERP × CRM a partir do
[Brazilian E-commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
(licença CC BY-NC-SA 4.0): "ERP" é a soma dos pagamentos de cada pedido e "CRM" é a soma de
preço + frete dos itens. Os dados não ficam no repositório; o script baixa o arquivo.

```bash
python tools/olist.py
python -m reconcile --erp data/olist/erp_orders.csv --crm data/olist/crm_orders.csv --out output/olist
```

Resultado com o arquivo de SHA-256 `967e41e04fc306fe604e2a693f488995a8b41e5047418f8a5c8e4abd6deca784`
(os dois motores geram saídas idênticas byte a byte):

| Grupo | Pedidos |
|---|---|
| matched | 98.089 |
| amount_mismatch | 576 |
| missing_in_erp | 1 |
| missing_in_crm | 775 |
| rejected | 0 |

O que os números dizem, e o que não dizem:

- **576 pedidos** (0,58% dos que existem nos dois lados) têm pagamento diferente de preço +
  frete. A soma das diferenças é −2.870,39: no saldo, os pagamentos superam os itens.
  76,7% desses pedidos foram parcelados no cartão, contra 51,5% de todos os pedidos, o que
  sugere juros de parcelamento. É uma hipótese: os dados não trazem a taxa de juros.
- **775 pedidos** têm pagamento e nenhum item; 603 estão com status `unavailable` e 164
  com `canceled`. **1 pedido** tem item e nenhum pagamento.
- **Nenhuma linha foi rejeitada.** O Olist vem limpo e os extratos são somas por pedido, então
  este estudo não exercita a quarentena; quem faz isso são os dados sintéticos.

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

## Estrutura

```text
src/reconcile/
  cli.py            linha de comando e códigos de saída
  contract.py       regras de formato, motivos de rejeição, resultado canônico e leitura do texto
  inputs.py         procedência das entradas: nome do arquivo e SHA-256
  engines/          motor stdlib e motor pandas, atrás da mesma interface
  writer.py         as 6 saídas, gravadas de uma vez
tests/              exemplos, cenário de referência e propriedades
tools/
  generate.py       gerador de dados sintéticos com defeitos plantados
  benchmark.py      comparação de desempenho entre os motores
  olist.py          extração do estudo de caso com dados públicos
docs/superpowers/   spec e plano de implementação
```

## Licença

Código sob a licença [MIT](LICENSE). Os dados do Olist não fazem parte do repositório e
seguem a licença deles (CC BY-NC-SA 4.0).
