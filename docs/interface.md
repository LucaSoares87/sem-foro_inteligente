# SI-07A — arquitetura da interface

A interface foi dividida em três ambientes sobre os contratos existentes, sem mudança incompatível no backend e sem nova dependência de frontend.

- `/executivo`: síntese para videowall e gestão. Exibe somente métricas derivadas do health atual. Valores ausentes aparecem como indisponíveis, não como zero. O espaço de mapa é deliberadamente vazio até a SI-07B; nenhuma coordenada fictícia é criada.
- `/operacional`: saúde, fontes, inferência, tracking, analytics e previsão. Mantém as ressalvas de cada motor e reutiliza os endpoints existentes.
- `/laboratorio`: isola o simulador sintético SI-06 dos dados operacionais. Não recebe nem produz comando físico.

O shell compartilhado possui navegação por URL usando History API nativa, fallback SPA já fornecido pelo Nginx, navegação responsiva, skip-link, foco visível, `aria-current`, tabelas semânticas e estados explícitos. Links modificados preservam o comportamento normal do navegador. Não foi adicionado React Router.

A derivação de métricas executivas fica em funções puras testadas. Cruzamentos são identificadores já presentes nas fontes; passagens são somente o acumulado exposto na sessão analítica atual; tracks são snapshot visível; janelas são as persistidas na execução atual. O painel não transforma ausência de informação em zero.

Esta etapa não adiciona mapa real, cadastro de cruzamento, RBAC, autenticação, streaming de imagem no navegador ou persistência de preferências. SI-07B deverá adicionar cadastro geográfico explícito e múltiplos cruzamentos sem alterar os contratos dos motores. SI-07C consolidará histórico visual e o laboratório para demonstração.

Gate: testes Node existentes + testes de navegação/view-model, build Vite, regressão integral de backend e Compose no CI. Não reduzir os gates anteriores.


## SI-07C — histórico visual, videowall e demonstração integrada

O histórico visual reutiliza exclusivamente `traffic_windows`, já persistido pelo motor SI-05B. O novo endpoint `GET /api/v1/predictive/intersections/{intersection}/history` consulta somente fontes atualmente registradas para o cruzamento e devolve séries separadas por fonte, linha e sentido. Não existe soma entre câmeras. Cada ponto preserva `analytics_epoch`, qualidade da janela, duração, finalidade do modelo e quantidade observada de passagens. Mudanças de epoch e janelas limitadas interrompem visualmente a linha, evitando representar descontinuidade como série contínua.

O Painel Operacional passa a exibir gráfico SVG nativo, sem biblioteca de gráficos ou dependência externa. A métrica é passagens observadas por janela de aproximadamente 60 segundos; não é demanda latente, fila física ou fluxo municipal consolidado.

`/videowall` é uma visão imersiva de leitura contínua. Consolida quantidade de cruzamentos cadastrados, fontes, tracks visíveis, passagens da sessão atual, janelas persistidas, mapa WGS84, cruzamentos em atenção e alertas. Ele não soma históricos de múltiplas câmeras e não apresenta ausência de dado como zero.

`/apresentacao` é um roteiro guiado em cinco etapas: visão municipal, cruzamento, histórico, cadeia de inteligência e simulação. O avanço pode ser manual ou automático. A etapa de simulação é explicitamente marcada como sintética e continua usando o motor SI-06 sem atuação física. As etapas anteriores exibem apenas dados observados/estado corrente quando disponíveis.

A SI-07C não adiciona vídeo ao vivo no navegador, nova telemetria física, geocodificação, controle de semáforo, RBAC ou serviços externos. A próxima missão deve ser SI-08A: segurança, observabilidade, auditoria, backup/restore, carga e implantação reproduzível.
