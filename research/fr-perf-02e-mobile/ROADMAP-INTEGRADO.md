# Roadmap integrado — auditoria 25/11/2026

Base main 366c30c2d059be1f7125ebc42de91568f86d4d7d. O roadmap existente é agrupamento da especificação original de 30 fases, ainda não reconciliada. Não renumerar fases nem confundir indicadores de maturidade estimados com aprovação de gates. Preservar referência de 83% estimada, sem aumento automático por novas fixtures. As quatro frentes podem avançar em paralelo por evidência, não por promoção.

| Frente / prioridade | Evidência existente | Próxima entrega independente | Critério de conclusão / bloqueio |
|---|---|---|---|
| A1 desempenho (P0) | FR01A 9 ensaios falharam gate absoluto; 02C ORT2 ganho 42.57% Bellevue e 34.38% CPU, falha equivalência funcional; nenhum candidato | OBS-MOBILE privado único, depois auditoria de pares e diagnósticos | 96 entradas, 384 medidas, original e semântico separados; sem 02D enquanto não houver candidato elegível segundo protocolo autorizado |
| B1 visão (P1) | PIMCAT I2C C3 bloqueado por falta de anotação independente; fonte câmera fixa CC0 proposta não tem ground truth | projetar formulário cego e contrato de anotação independente + avaliador de classes/oclusão, métricas precision/recall, sem nova aquisição | prova independente da mesma mídia e revisão humana; não reutilizar detecção como verdade, não substituir C3 por vídeo diferente; sem extrapolar pedestres |
| C1 inteligência (P1) | I1 632 trajetórias: avanço marginal I1A, ganhos de cobertura ETA/storage I1B mas gates controle negativos; I1C redução exposição com custo; I1D nulo/negativo | analisar contrafactuais existentes por estratos e riscos; especificar experimentos prospectivos com orçamento, sem tuning nos holdouts | separar menor-primeiro vs maior-primeiro, espera máxima, spillback, equidade, abstenção e fallback X_safe; preservar resultados negativos; sem promoção |
| D1 produto (P0 comercial) | FINAL-ACCEPTANCE automatizado, PENDING_HUMAN | sessão de demonstração privada existente porta 5173, checklist e roteiro municipal em modo sombra, sem mídia externa | aceite humano real; não satisfaz SI08B; usar apenas fonte sintética autorizada |
| D2 integração (P1) | FR-A/B/C/D concluídas tecnicamente; D recuperação laboratório, não hardware-alvo | contrato de inventário câmera/RTSP/VMS, checklist de autorização, segregação de rede, dados/calibração e orçamento POC | documentação pode avançar localmente; testes físicos e implantação só com autorização e evidência no alvo |
| A2 confirmação (dependente) | 02D >=475/500 e P95 idade<=200ms por repetição, Phase B DEFERRED | só depois de elegibilidade científica e aprovação | preservar protocolo, sem execução agora |

Sequência de maior retorno: concluir entrega MOBILE e preparar aceite humano da demonstração em paralelo; depois anotação independente e auditoria contrafactual já registrada. Sem novas campanhas remotas ou mídia nas frentes B/C/D nesta rodada. A avaliação do benefício de X ou priorização de filas menores continua dependente de cenários e evidência; não há promessa de redução de congestionamento. Os sete gates de campo exigem modelo/câmera autorizados, calibração, ground truth, benchmark e recovery no hardware-alvo, aceite humano. POC proposta de 30 dias em modo sombra, sem controlador físico, não é implantação.

## Fontes originais auditadas (Git blob, main)
- docs/roadmap.md — 13cca131f6f663b2131f044eec74f33941875149
- docs/si08b/acceptance.md — 52b33e63e57e1ba0c02e0650ba4e89c82b7b8484
- docs/field-readiness/d-technical-recovery.md — c4f397542c4ab5bffcc6dcf1918b98f331779050
- docs/pimcat/i1-synthesis.md — bc7c44089a6d7a5d8598417c9434888b6f593ce3
- docs/pimcat/i2c-independent-sources.md — 43dc756bf39970efa673410a3c72b48d458f7f9b
- docs/final-acceptance/checklist.md — c4571d01745f0b96732fac7bfb3ec6368b01018f
- docs/field-readiness/poc-municipal-dossier.md — d6ca757bd9b089716e186a360ec93acedfda41f1

Sem alteração dos documentos ou defaults originais. X_safe/RP07/RP08, sete SI08B, PENDING_HUMAN, physical_actuation=false, NO_ELIGIBLE_CANDIDATE, Phase B DEFERRED e FIELD_BLOCKED preservados. Orçamento Actions 25 job-min não consumido. Preparação de documentação/fixtures não equivale a execução em campo.
