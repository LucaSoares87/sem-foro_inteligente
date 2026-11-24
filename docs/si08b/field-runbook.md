# Runbook de campo SI-08B

## Pré-condições
- autorização para filmagem/captura;
- cruzamento e câmera identificados sem placas/rostos/biometria como requisito do produto;
- modelo ONNX autorizado, licença/proveniência registradas e SHA-256 confirmado;
- thresholds de aceite aprovados antes do ensaio;
- armazenamento seguro para vídeo e anotações;
- operador responsável pelo ensaio;
- nenhuma conexão com controlador físico.

## Sequência única
1. Registrar o cruzamento e a fonte autorizada.
2. Fixar câmera, resolução, FPS e relógio; não mover a câmera durante o caso de avaliação.
3. Revisar ROI, linhas de contagem, sentidos e oclusões.
4. Preencher o checklist de calibração e executar `python -m src.validation.cli calibration --input calibration.json`.
5. Capturar o vídeo de avaliação sem publicar o arquivo no Git.
6. Gerar manifesto e SHA-256.
7. Produzir ground truth por anotação independente.
8. Executar o sistema no vídeo/câmera usando o modelo candidato.
9. Exportar predições no contrato SI-08B.
10. Executar o avaliador offline com os thresholds previamente aprovados.
11. Executar `ops/pilot_probe.py --require-workload` durante workload real.
12. Executar recovery drill no hardware-alvo.
13. Revisar erros, limitações, classes e cenários de falha.
14. Registrar evidências externas em `VALIDATION_EVIDENCE_JSON`.
15. Executar o checklist humano.
16. Somente se todos os gates obrigatórios estiverem `ready`, o scorecard poderá indicar `ready_for_supervised_pilot`.

## Falhas
- câmera indisponível: BLOCKED;
- modelo sem licença/proveniência: BLOCKED;
- ground truth ausente: BLOCKED;
- threshold não aprovado antes da execução: NOT_RUN;
- benchmark sem workload: NOT_RUN;
- recovery acima do limite aprovado: FAILED;
- aceite humano ausente: PENDING_HUMAN.

Nenhuma dessas situações deve ser convertida em aprovação por conveniência comercial.
