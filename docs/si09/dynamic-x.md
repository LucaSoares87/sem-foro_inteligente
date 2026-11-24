# Dynamic X — modelo matemático v1

Considere dois grupos concorrentes: `M` (fila dominante) e `m` (fila menor).

Para cada grupo:
- `q`: fila observada;
- `lambda`: taxa de chegada observada (veh/s);
- `mu`: taxa de descarga observada (veh/s);
- `C`: capacidade calibrada de armazenamento em veículos.

## Tempo de limpeza
Quando `mu_m > lambda_m`:

```text
T_clear,m = q_m / (mu_m - lambda_m)
```

Se `mu_m <= lambda_m`, não existe capacidade líquida de esvaziamento no estado observado e o minor-first é bloqueado.

## X seguro
O modelo define a região crítica da fila dominante como:

```text
Qcrit,M = 0.85 * C_M
```

O tempo disponível antes de a chegada observada consumir a margem é aproximadamente:

```text
Tbudget,M = (Qcrit,M - q_M) / lambda_M - transition_overhead
```

Para `lambda_M=0`, usa-se apenas o horizonte analítico restante.

Então:

```text
X_safe = floor((mu_m - lambda_m) * max(0, Tbudget,M))
```

limitado também a 85% da capacidade de armazenamento da fila menor.

`X_safe` não é uma ordem. Ele é um gate: `q_m <= X_safe` permite que minor-first seja comparado; `q_m > X_safe` bloqueia essa alternativa mesmo se a função de custo parecer favorável.

## Contrafactual
Para o mesmo estado são simuladas duas sequências:
- minor-first;
- major-first.

As duas usam o mesmo horizonte e a mesma primeira janela analítica, derivada de `T_clear,m` e limitada a 30 s. Isso compara ordem de atendimento sem transformar o resultado em plano físico de temporização.

## Função de custo
```text
J =
  1.0 * queue_area
+ 2.0 * max_wait_proxy
+ 25.0 * spillback_exposure
+ 10.0 * flow_interruption_proxy
+ 5.0 * transition_overhead
```

Os coeficientes são `engineering defaults`, versionados como `continuity_queue_cost_v1`. Eles não são parâmetros homologados de Recife.

Uma preferência só é material se a redução relativa for >= 5%. Caso contrário o resultado é `no_material_advantage`.

## Interpretação
O objetivo não é “abrir sempre a menor fila”. O minor-first só é candidato quando:
1. há capacidade líquida de descarga;
2. a observação tem confiança suficiente;
3. a fila menor cabe dentro do X dinâmico;
4. o contrafactual produz ganho material.

Mesmo assim o resultado permanece simulativo.
