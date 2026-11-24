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
| SI-08A | Hardening corporativo: RBAC externo, auditoria, observabilidade, backup/restore, limites e carga | ameaças, migração, testes negativos, restore real e CI integrado |
| SI-08B | Homologação de campo: modelo/câmera reais autorizados, calibração, ground truth, hardware-alvo e aceite humano | evidência de campo, métricas por classe, recuperação e autorização humana |
| SI-09 | Queue Intelligence e Dynamic Clear-First Optimization | fila/chegada/descarga/espera com confiança, X dinâmico seguro, contrafactual menor→maior vs maior→menor, persistência e abstenção |

O avanço depende de evidência registrada, não de pontuações estimadas. Sem controle físico em todas as missões.


## Estado da SI-08B
O framework integrado de homologação, avaliação, benchmark, recovery e aceite está implementado. O gate final permanece `blocked_by_field_evidence` até existirem modelo candidato autorizado, câmera física autorizada, calibração, ground truth real, benchmark no hardware-alvo, recovery no hardware-alvo e aceite humano. Os vídeos sintéticos de demonstração serão incorporados posteriormente ao mesmo contrato, sem substituir os gates de campo.


## Estado da SI-09
A SI-09 é uma evolução experimental e consultiva sobre os motores já consolidados. Ela não substitui a SI-06: a SI-06 permanece baseline sintético isolado, enquanto a SI-09 transforma estados observados de fila em experimentos contrafactuais. Os pesos da função de custo são defaults de engenharia ainda não homologados; por isso nenhuma preferência simulada pode ser convertida automaticamente em comando semafórico.

Bellevue entra somente como `external_real_replay`. O dataset pode acelerar desenvolvimento e robustez, mas não satisfaz os gates de campo de Recife e não está autorizado para demonstração comercial pela configuração enquanto não existir autorização escrita.
