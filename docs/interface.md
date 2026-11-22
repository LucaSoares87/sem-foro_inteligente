# SI-07A — arquitetura da interface

A interface foi dividida em três ambientes sobre os contratos existentes, sem mudança incompatível no backend e sem nova dependência de frontend.

- `/executivo`: síntese para videowall e gestão. Exibe somente métricas derivadas do health atual. Valores ausentes aparecem como indisponíveis, não como zero. O espaço de mapa é deliberadamente vazio até a SI-07B; nenhuma coordenada fictícia é criada.
- `/operacional`: saúde, fontes, inferência, tracking, analytics e previsão. Mantém as ressalvas de cada motor e reutiliza os endpoints existentes.
- `/laboratorio`: isola o simulador sintético SI-06 dos dados operacionais. Não recebe nem produz comando físico.

O shell compartilhado possui navegação por URL usando History API nativa, fallback SPA já fornecido pelo Nginx, navegação responsiva, skip-link, foco visível, `aria-current`, tabelas semânticas e estados explícitos. Links modificados preservam o comportamento normal do navegador. Não foi adicionado React Router.

A derivação de métricas executivas fica em funções puras testadas. Cruzamentos são identificadores já presentes nas fontes; passagens são somente o acumulado exposto na sessão analítica atual; tracks são snapshot visível; janelas são as persistidas na execução atual. O painel não transforma ausência de informação em zero.

Esta etapa não adiciona mapa real, cadastro de cruzamento, RBAC, autenticação, streaming de imagem no navegador ou persistência de preferências. SI-07B deverá adicionar cadastro geográfico explícito e múltiplos cruzamentos sem alterar os contratos dos motores. SI-07C consolidará histórico visual e o laboratório para demonstração.

Gate: testes Node existentes + testes de navegação/view-model, build Vite, regressão integral de backend e Compose no CI. Não reduzir os gates anteriores.
