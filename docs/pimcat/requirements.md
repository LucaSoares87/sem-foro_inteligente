# Matriz de rastreabilidade PIMCAT
Estados: EXISTENTE, PARCIAL, PLANEJADO, BLOCKED/NOT_RUN. Aceite técnico != autorização física. O relatório de execução B/C1 deve dizer quais testes efetivamente passaram; esta matriz é plano de evidências.

| Requisito | Componente/entrega | Gate e dependência |
|---|---|---|
| RV-01/02/03 | B/C1 regra local, triestado, memória | demanda única, vazio confirmado, surgimento; unknown abstém |
| RV-04 | SI-09/SI-11 preservados + B/C1 ablação | comparar original X_safe, proporcional, fairness; não promover |
| RP-01/02/03/04 | B/C1 Xp e baselines | sem limiar mínimo, relógio oldest, prazo 120 configurável, oportunidade protegida |
| RP-05 | B/C1 invariantes + C2/C3 | proteção planejada e ocupação, acessibilidade real bloqueada |
| RP-06 | B/C1 proxy Xp e custo pessoa | análise por coortes, sensibilidade e validação independente |
| RC-01/02 | D | previsão agregada com relógio/intervalo, não liberar se destino cheio |
| RC-03 | D | tempo viagem, paradas, regularidade, limite legal e erro |
| RC-04 | C3/D | sem identificação pessoal, autorização e calibração |
| RG-01/02 | E | grafo, calor baseado em criticidade e dados ausentes cinza |
| RG-03/04 | E | armazenamento finito, conservação, backpressure, comparação rede |
| Arbitragem P0–P6 | B/C1 parcial, E | admissibilidade antes de custo; emergência NOT_RUN; conflitos de prazo logados |
| Relatório/retroalimentação | F (B/C1 agregado sintético inicial) | denominadores/cobertura, origens, P95, comparação pareada, ajustes apenas propostas |
| Resiliência | SI-13 existente, B/C1 unknown, C3/D/E/G | falhas físicas e energia NOT_RUN, fallback consultivo, perda central testada futura |
| Governança | todos | branch isolada, CI, hashes, gates SI-08B, sem atuação |

## 25 cenários obrigatórios e critério de evidência
| # | Cenário | Gate objetivo | Escopo/estado previsto |
|---|---|---|---|
| 1 | ambos vazios | manter último sem troca sem demanda | B/C1 |
| 2 | único fluxo | priorizar conhecido demand/empty | B/C1 |
| 3 | chegada no fechado | escolher na próxima oportunidade sintética | B/C1 |
| 4 | filas equivalentes | comparar sem viés de desempate declarado | B/C1 |
| 5 | assimétricas | ablação, custo/esperas por coorte | B/C1 |
| 6 | dominante contínuo | medir filas e espera de ambos | B/C1 |
| 7 | menor privação | contabilizar cada espera >180 experimental | B/C1 |
| 8 | pessoa isolada | atender sem número mínimo | B/C1 |
| 9 | grupo progressivo | timestamp original preservado | B/C1 |
| 10 | veículos intensos 120s | antecipar prazo ou registrar violação | B/C1 |
| 11 | oportunidade antecipada | carona só matriz compatível | B/C1 |
| 12 | mobilidade reduzida | intervalo conservador, extensão, sem conflito | B/C1; campo BLOCKED |
| 13 | faixa ocupada | veto de conflito inclusive pós-bloco | B/C1 |
| 14 | pelotão anterior | erro de ETA e paradas comparados | D NOT_RUN |
| 15 | destino saturado | nenhuma liberação sem espaço | E NOT_RUN |
| 16 | propagação 3+ | conservação rede e exposição | E NOT_RUN |
| 17 | prazos simultâneos | arbitrar prazo e registrar inviabilidade | B/C1 |
| 18 | câmera falha | unknown nunca zero; abstain | B/C1 regra; C3 replay NOT_RUN |
| 19 | comunicação falha | validade temporal, abstain em dado expirado | D/E NOT_RUN |
| 20 | perda central | local consultivo sem dependência central | E NOT_RUN |
| 21 | baixa confiança | abstain sem reset de pedido | B/C1 regra; C3 NOT_RUN |
| 22 | oclusão | unknown, referência independente | B/C1 regra; C3 NOT_RUN |
| 23 | alternância excessiva | mínimo bloco, contar mudanças | B/C1 |
| 24 | reinício | preservar estado validado ou desconhecido, requests; recuperação SI-13 anterior não prova multimodal | E/G NOT_RUN |
| 25 | FPS | comparar 30/15/10/5 com GT e perdas | veicular SI-09 preliminar; C3 BLOCKED |

## Complemento RP-07 — topologia isolada
| Requisito | Componente | Gate |
|---|---|---|
| RP-07 | pimcat_midblock.py (pesquisa) | 86400 amostras sem pedido mantêm preferência veicular; pedido individual registrado; prazo não reinicia; ocupação/clearance, incerteza e obrigações vetam retorno |
| 26 | travessia isolada sem demanda | ausência confirmada em espera/faixa; sem alternância periódica; C2 SUMO NOT_RUN |
| 27 | travessia isolada com pedido único e retomada | botoeira/observação, proteção e confirmação de atendimento; C2 SUMO/C3 campo NOT_RUN |

## Complemento RP-08 — brechas veiculares
| Requisito | Componente | Gate |
|---|---|---|
| RP-08 | pimcat_h2_gap.py (pesquisa isolada) | Aproveitar brechas somente para serviço protegido, preservar RP-07, prazos e proteção. 96 trajetórias SUMO executadas; redução de paradas observada, aumento da espera de pedestres; candidato reprovado. C3 independente e calibração de brechas reais bloqueadas. |
| 28 (complementar, fora da matriz G original) | baixo fluxo e pelotões | comparar paradas, espera, episódios protegidos, censura e perda da previsão; nunca travessia vermelha. |
