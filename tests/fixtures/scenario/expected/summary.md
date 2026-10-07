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
