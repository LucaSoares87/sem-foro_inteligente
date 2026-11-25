# Dossiê G — prontidão para ensaio e futuro piloto municipal
**PENDING_HUMAN / BLOCKED_BY_FIELD_EVIDENCE**. Não é autorização. A matriz g-scenarios.json contém 27 cenários com escopos e limitações; o CI produz scorecard com regressões realmente executadas. PR39 dependência aprovada porém não integrada na auditoria inicial. Revisão G/CI efetivo deve ser anexada após revisão, não presumida.
## Aceite de produto (privado)
Após integrar F e G, conferir main/CI e abrir Codespace privado on main, conforme docs/final-acceptance/README.md. Executar `git rev-parse HEAD`, `git status --short`, `python ops/final_acceptance.py start`, `python ops/final_acceptance.py test --output /tmp/pimcat-g-local.json`. Porta 5173 Private. Não expor fontes, não abrir porta pública. Percorrer seis ambientes:
- Executivo: saúde e relatório diário sem contexto; acervo separado, não dado atual.
- Operacional: contexto inexistente, nenhuma preferência ou métrica inventada; fonte ausente não equivale a vazio.
- Laboratório: cinco presets, comparar X_safe e estratégias antigas, C1/C2/RP07, C3 replay e precisão bloqueada, D/E gates negativos, mapa t=175/240/305 (18 unknown durante perda); exportar e verificar seis propostas não aplicadas.
- Videowall: legibilidade 1920x1080, sair corretamente.
- Apresentação: sete etapas; ver acervo original; não alegar benefícios de campo.
- Homologação: sete gates ausentes; decisão abstain; erro 503 não equivale a pronto.
Preencher checklist privado original e complemento com data, SHA, resultado por rota, screenshots sem dados privados, falhas e decisão humana. Não marcar automaticamente. Parar com `python ops/final_acceptance.py stop` e Stop Codespace. CI é ensaio, não aceite humano.
## Estado técnico e científico
X_safe/SI09 permanece original; C1/C2/D/E candidatos não aprovados. C3 precisão independente e intenção/ocupação real bloqueadas. RP07 no modelo, não autorização de verde real indefinido. E capacidade proxy e contingência local idealizada, entradas críticas residuais; D ETA cobertura insuficiente. G não executa nova campanha de eficácia; seleciona casos registrados e testa integração lógica, não integra controlador físico. Reinício C3 perde relógio e volta desconhecido; restauração de pedidos multimodais NOT_RUN. F diária sob demanda, 20 mil janelas no máximo, origem física histórica não verificada, sem totais de rede e sem agendamento. Xp/Xg não são motores runtime; só pesquisa/relatórios.
## Sete gates SI-08B (todos pendentes até evidência real)
| Gate | Evidência a obter antes de solicitar revisão |
|---|---|
| authorized_model | Autorização escrita e hash do modelo exato carregado |
| physical_camera | Local/câmera autorizados, configuração e amostra controlada |
| calibration | Geometria, oclusões, sincronismo, velocidades e revisão técnica |
| field_ground_truth | Anotadores independentes, revisão, dados representativos e limiares pré-registrados |
| hardware_benchmark | Carga autorizada, FPS processado/perdas, latência, CPU/RAM, critérios anteriores ao teste |
| recovery_drill | Recuperação em ambiente-alvo autorizado, energia/comunicação e persistência de pedidos; não testar em via ativa |
| human_acceptance | Aprovação formal documentada por responsável autorizado; diferente do aceite de produto |
Referenciar docs/si08b/acceptance.md, docs/si13/final-readiness.md e preparar dossier privado via si13_field_packet prepare. Não criar VALIDATION_EVIDENCE_JSON fictício. Autoridade municipal decide plano de piloto em shadow mode; validação de acessibilidade, dispositivos de solicitação, controlador e normas vigentes por especialista. Sem comandos reais, sem dados identificáveis. Definir critérios e responsabilidades antes da coleta; autorização não presumida.
## Próximas decisões
1. Integrar PR39 e G apenas com checks verdes e revisão de diff. PR36 é workflow independente.
2. Aceite humano do produto; registrar problemas e correções.
3. POC autorizada somente de observação/sombra, com sete gates e dados independentes. Resolver C3, FPS e calibração; reavaliar candidatos com comparadores fortes e coortes novas.
4. Piloto supervisionado somente se órgãos e especialistas aprovarem. Comercialização não é gate automático.

## Complemento H-CLOSE (2026-11-25)
F/G já integrados, H2 PR44 integrado com gate negativo; PR36 integrado para reforçar a verificação D. H1 e o ensaio integrado devem ser reconciliados e aprovados no CI antes do aceite humano privado. Ver [registro H](h-integrated-demo.md) e [roteiro FINAL-ACCEPTANCE](../final-acceptance/README.md). H1 loopback sintético não prova soak 24h, RTSPS real ou VMS municipal. RP08 não promovida; C3 e os sete gates SI-08B continuam bloqueados. O roadmap de pesquisa após aceite de produto deve separar melhoria matemática, percepção/resiliência e relatório diário automatizado; não confundir validação laboratorial com autorização de campo.
