# Plano de entrega
Reconstrução operacional proposta a partir das decisões já discutidas. A especificação original de 30 fases ainda precisa ser reconciliada; estes agrupamentos não substituem sua numeração.

| Missão | Escopo | Gate mínimo |
|---|---|---|
| SI-01 | Fundação, configuração, FastAPI, PostgreSQL, Alembic, WebSocket nativo, React/Vite/Tailwind e Compose | migração real, health verdadeiro, testes e build |
| SI-02 | Contratos de eventos, pipelines desacoplados, filas limitadas e replay sintético | testes de isolamento, cancelamento, backpressure e proveniência |
| SI-03 | Ingestão de vídeo local autorizado, webcam e RTSP registrado | falhas, reconexão, latência real, política de fontes |
| SI-04 | Detecção YOLO e tracking | dataset autorizado, métricas por classe, licenças e testes |
| SI-05 | ROIs, contagem, filas, ocupação, congestionamento e previsão | calibração, ground truth e limites de confiança |
| SI-06 | Simulação e recomendações explicáveis | restrições, abstenção, fallback consultivo, comparação com baseline |
| SI-07 | Painel operacional e executivo, múltiplos cruzamentos e histórico | contratos, filtros, acessibilidade, testes de ponta a ponta |
| SI-08 | Auditoria, segurança, observabilidade, implantação e demonstração | ameaças, dependências, backup/restore, cargas, ensaio humano |

O avanço depende de evidência registrada, não de pontuações estimadas. Sem controle físico em todas as missões.
