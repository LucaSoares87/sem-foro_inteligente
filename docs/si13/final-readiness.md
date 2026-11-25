# SI-13 — Homologação integrada final

Revisão inicial 1264056534d2c11fb1d6f43f789d7b29bac71f91, PR #29 e CI pós-merge 45523395109. Uma única missão/PR: preparação técnica, instrumentos de campo e roteiro de aceite. Não substituir nenhum gate SI-08B. Nenhum candidato promovido; nenhuma atuação física. Esta entrega não promete homologação real por CI.

## Evidências históricas
Pacote SI13-acervo-historico-verificado.zip: 14 ZIPs originais, sem vídeos brutos, inclui modelo de pesquisa e licença. SHA-256 e IDs em evidence-index.json. Arquivo preservado fora do Git público na Biblioteca pessoal do usuário; original dos Actions pode expirar. Verificar localmente com `python ops/verify_si13_archive.py /caminho/SI13-acervo-historico-verificado.zip`. Preservar também as evidências SI-13 após CI. Não publicar frames ou credenciais. SI-09F ainda não tem anotação independente submetida; SI-10B não sustentou 5 FPS; SI-11B/C/D não passaram todos os critérios científicos. SI-12 passou sete testes de navegador em ambiente vazio, não homologação de câmera.

## Ensaio técnico integrado (gates de engenharia, não de campo)
Workflow em Ubuntu 24.04, Python 3.12, Node 22, Playwright 1.51.1. Compose real, PostgreSQL e migrações, backend não-root, interface e sete verificações SI-12. Modelo oficial YOLOX-S SHA fixado, purpose=validation_only. Preparar trecho Bellevue de 32s/960 frames por preflight SI-09D, sem alterar fonte, verificar pixels congelados. Montagem somente leitura, uma fonte tipo file, data_origin=external_real_replay, comercial não autorizado, geometria anterior não calibrada. Taxa de oferta 5 FPS é teste de pressão sobre a cadeia, não recomendação de percepção; decoder atual paceia os frames sequencialmente, portanto não é replay em tempo nativo. Nenhum resultado científico anterior alterado.

Antes de executar: verificar sete gates bloqueados, modelo de pesquisa, nenhuma fonte física. Iniciar apenas arquivo registrado no loopback do runner; exigir progressão de inferência, tracking, analytics e filas, persistência real, otimização em abstenção e X nulo. Medir 20 amostras de health a cada .5s junto com 120 requisições HTTP concorrentes (8), p95 HTTP <=5000ms, zero erros, delta positivo de estágios; esses limites são de ensaio de integração, não de hardware municipal. Repetir probe com --require-workload e exigir código 5: replay não é workload de campo. Reiniciar backend enquanto replay ativo, medir retorno de health em até 60s e separadamente esperar modelo carregar e novo processamento com session_id distinto. Parar fonte, verificar que fila e preferência atual desaparecem; preservar histórico. Reiniciar PostgreSQL com fonte parada (<=60s), conferir persistência; backup e restauração em banco alternativo descartável, comparar contagem de registros reais da fila. Não enviar backup, vídeo ou modelo binário no artefato SI-13. Revalidar abstenção, ausência de fonte física e sete gates pendentes. Publicar métricas agregadas, hashes e capturas da demo sem vídeo.

Auditoria de leitura: optimization.latest/status anteriormente podiam expor resultado em cache após término/parada ou mudança de sessão. A API agora exige vínculo ao snapshot atual da fila por hash do estado (inclui queue_epoch, frame, geometria, modelo e approaches). Motor de otimização, histórico e regras originais preservados; health agregado pode indicar existência de cache interno e não substitui a leitura atual do endpoint específico. Testes de ausência e epoch/frame diferentes. O pipeline nunca gera decisão operacional.

## Preparação e execução privada de campo
Siga primeiro docs/si08b/field-runbook.md e human-acceptance.md. Prepare um diretório novo fora do Git público:

```sh
cd backend
python -m src.validation.si13_field_packet prepare --directory /caminho/privado/si13-field
```

Contém JSON Schemas dos contratos existentes, rascunho de dossier com campos nulos e plano de gates pendentes. NÃO é ground truth, aprovação, calibração ou registro de aceite. Obter autorização de filmagem e do modelo, escolher câmera fixa, resolução <=1280x720/FPS<=30, relógio, geometrias, direção, visibilidade/oclusões, privacidade, hardware e operador. Thresholds de precisão/contagem e limites de desempenho/recuperação devem ser aprovados antes do ensaio. Nenhum default municipal inventado.

Produzir manifest.json, ground-truth.json, thresholds.json, calibration.json, geometry.json, model-spec.json reais. Dossier deve ser SUBMITTED_FOR_REVIEW, referências distintas de operador, anotador e revisor independente, autorização de captura igual ao manifesto, referência de thresholds igual à aprovação, hash de vídeo/modelo/ground truth/geometria/thresholds, reviewed_frames com todos os frames explicitamente revisados (inclui vazios). O preflight exige caso representativo com pelo menos uma anotação, contagens agregadas por toda linha/sentido, sem transformar desconhecido em zero. Não autentica identidade ou autorizações; o humano deve verificá-las. A aprovação de thresholds é anterior à gravação. Executar:

```sh
python -m src.validation.si13_field_packet inspect --directory /caminho/privado/si13-field --video /caminho/privado/video.mp4 --model-root /caminho/privado/modelos --output /caminho/privado/input-consistency.json
```

Depois executar calibration, inspect-video, run-case e evaluate conforme docs/si08b; não alterar predições. Aplicar protocolo de fila SI-09F com anotações independentes e revisão, além do ground truth SI-08B. Executar ops/pilot_probe.py --require-workload no hardware-alvo durante fonte física autorizada e modelo autorizado; avaliar deltas realmente positivos, FPS/latência, perdas, CPU/RAM e estabilidade conforme limites previamente aprovados. Recovery drill no ambiente definitivo somente mediante autorização, não na via ativa. Consolidar falhas e limitações. Preencher checklist humano; nunca promover sem referências verificáveis. Registrar VALIDATION_EVIDENCE_JSON externamente somente após análise de cada evidência; a missão não assina, gera ou instala autorização.

## Scorecard e conclusão
| Gate obrigatório | Estado inicial deste ensaio | Requisito de encerramento real |
| --- | --- | --- |
| authorized_model | BLOCKED | licença, aprovação externa e SHA carregado |
| physical_camera | BLOCKED | captura física autorizada e fonte configurada |
| calibration | BLOCKED | geometria real revisada e checklist completo |
| field_ground_truth | BLOCKED | anotação independente, revisão e métricas |
| hardware_benchmark | NOT_RUN | carga física real e limites aprovados |
| recovery_drill | NOT_RUN | recuperação no hardware-alvo autorizada |
| human_acceptance | PENDING_HUMAN | assinatura/referência externa formal |

CI verde e ensaio replay concluído permitem declarar somente TECHNICAL_REHEARSAL_PASSED_FIELD_BLOCKED. CI incompleto/falho permanece pendente/falho. Não gerar nova "missão" para ocultar dependências físicas; continuar no mesmo SI-13 até obter evidências reais. Se e somente se gates legítimos do scorecard SI-08B estiverem ready, poderá haver piloto supervisionado consultivo. Não aprovar controlador, segurança viária ou atuação física. Nenhum algoritmo candidato promovido.
