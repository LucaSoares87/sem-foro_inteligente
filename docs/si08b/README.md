# SI-08B — Homologação integrada de campo e preparação do piloto

Esta missão é executada como um único programa com um gate final. Os componentes internos existem para impedir que uma demonstração, um benchmark isolado ou um relatório sintético sejam confundidos com homologação municipal.

## Estado atual
O framework de software está pronto para receber evidências. Como os vídeos e os ativos de campo ainda não foram fornecidos, o resultado correto do gate final é `blocked_by_field_evidence`.

Isto não é uma falha. É a condição de segurança definida em `AGENTS.md`: infraestrutura ou dados ausentes são `BLOCKED/NOT_RUN`, nunca homologados artificialmente.

## Gates
| Gate | Pode ser sintético? | Bloqueia piloto? | Evidência mínima |
|---|---:|---:|---|
| synthetic_demo_dataset | sim | não | manifesto + vídeo + ground truth sintético |
| authorized_model | não | sim | relatório métrico + SHA do artefato/modelo |
| physical_camera | não | sim | captura autorizada e evidência de execução |
| calibration | não | sim | checklist completo + geometria revisada |
| field_ground_truth | não | sim | anotação humana/externa vinculada ao vídeo |
| hardware_benchmark | não | sim | probe com workload real no hardware-alvo |
| recovery_drill | CI prepara; campo confirma | sim | drill no hardware-alvo |
| human_acceptance | não | sim | autorização humana explícita |

## Princípios
1. Nenhum relatório de avaliação aciona semáforo físico.
2. `meets_supplied_thresholds=true` não significa `pilot_ready=true`.
3. Evidência sintética nunca satisfaz gate de campo.
4. O aceite humano não é automatizado.
5. Todo artefato relevante deve ter SHA-256 e origem conhecida.
6. Vídeos reais não devem ser publicados no repositório público.

Veja também `dataset-and-evaluation.md`, `field-runbook.md`, `acceptance.md` e `human-acceptance.md`.
