# SI-12 — Pilot Product Readiness

Base a3eeb8e8a476b913a9c9e5959dc6bd2f4832b668, PR #28; CI pós-merge 45521738938 aprovado. Mantidos os motores, APIs, critérios SI-08B, SI-09 e SI-11. Nenhum candidato promovido.

## Auditoria e alterações
As seis rotas SI-07 já existiam. Reutilizamos shell, mapa, histórico, laboratório SI-06, filas SI-09, videowall e scorecard SI-08B. Adicionamos prontidão e timestamp UTC, sem confundir health com evidência de campo. Falha do scorecard não pode exibir leitura antiga como aceite atual. No painel de filas, uma preferência precisa corresponder à mesma fonte, cruzamento e frame; ausência não implica causa específica de abstenção. Nenhuma câmera, localização ou telemetria artificial inserida. Videowall mantém layout original e área de conteúdo rolável. A apresentação ganha evidências e homologação. Extrato JSON de médias SI-11A/B/C/D com SHA-256 originais e links de execução; números extraídos dos ZIPs originais, não dados em tempo real, nem recomputação de métricas de campo. Os protocolos de 60s e 240s e a métrica SUMO são distintos; comparar apenas dentro de cada estudo. Artefatos do Actions expiram; preserve ZIPs completos externamente. O extrato não substitui os originais. SI-11B/C/D não passaram todos os gates científicos; sem promoção.

## Ensaio local (sem câmera e sem modelo)
Pré-requisito Docker Compose v2. Em uma cópia de desenvolvimento, copie .env.example para .env, configure senha forte exclusiva de desenvolvimento, APP_ENV=development, AUTH_MODE=disabled, VIDEO_SOURCES_JSON=[], VISION_MODEL_JSON vazio, TRAFFIC_GEOMETRY_JSON=[], INTERSECTION_REGISTRY_JSON=[], VALIDATION_EVIDENCE_JSON=[]. Não use esta configuração sobre um ambiente real ou publicado. Não altere segredos existentes. Não abra porta pública.
1. docker compose config --quiet
2. docker compose up --build --wait --wait-timeout 180
3. Abra http://127.0.0.1:5173/executivo. Health em /api/v1/health; estado de campo em /api/v1/validation/status. Se health falhar, consulte docker compose ps e docker compose logs --tail=80. Não registre segredos.
4. /videowall: observe estados, falta de dados, data/hora e gates. Use zoom normal; sem geografia configurada não há pontos.
5. /operacional: selecione contexto disponível; neste ensaio não há fontes. Ausência de fila não significa fila zero.
6. /laboratorio: alterne SI-11A/B/C/D, exporte extrato, execute cenário assimétrico SI-06, confira hash reprodutível. As comparações são exclusivamente sintéticas; não há replay de Bellevue autorizado para uso comercial.
7. /apresentacao: sete passos, manual ou automático; simulação e evidências explicitamente sintéticas. Homologação deve indicar bloqueio.
8. /homologacao: confira gates. Não preencha evidência fictícia. /api/v1/operations/status e /api/v1/operations/metrics são as fontes existentes de observabilidade; X-Request-ID para correlacionar logs. Nunca use headers de identidade falsos para contornar proxy de produção.
9. Para finalizar ambiente de desenvolvimento: docker compose stop. Não apague volumes do usuário. O CI usa down -v apenas no runner descartável.

## Gate da demonstração
Workflow SI-12 usa Compose real, Playwright 1.51.1 apenas no runner (sem dependência de produção), Chromium, frontend test/build e sete verificações de navegador, incluindo 1920x1080, mobile 390px, exportação JSON, repetição do hash da demo e falha do endpoint de homologação. Screenshot é evidência visual do ambiente sintético, não homologação. Se teste não completar, registrar pendente/falha. Foundation CI continua obrigatório. Sem alteração operacional, sem atuação física, sem promoção. Não chamar resultado de piloto municipal homologado. SI-13 requer sete gates de campo reais, participação humana, calibração e hardware; nenhuma evidência deste ensaio os substitui.
