# Bellevue — benchmark externo real para SI-09

## Fontes
Repositório oficial:
https://github.com/City-of-Bellevue/TrafficVideoDataset

Relatório City of Bellevue / Microsoft, dezembro de 2019:
https://bellevuewa.gov/sites/default/files/media/pdf_document/2020/Video%20Analytics%20Towards%20Vision%20Zero-Traffic%20Video%20Analytics-12262019.pdf

Termos de uso da City of Bellevue:
https://bellevuewa.gov/terms-of-use

## O que as fontes suportam
O README oficial descreve aproximadamente 101 horas de vídeos 1280x720/30 Hz, obtidos em setembro de 2017 em cinco cruzamentos reais com câmeras montadas em postes. O README declara disponibilidade para research purposes.

O relatório Bellevue/Microsoft mostra:
- uso de vídeo pré-gravado e streams ao vivo;
- classificação por movimento, direção e modo;
- ground truth manual/crowdsourcing e loops indutivos;
- pipeline decoder -> detector -> tracker;
- contagem baseada em linhas;
- dashboards históricos e em tempo real;
- acurácia de contagem direcional reportada entre 89% e 96% nos cinco cruzamentos;
- degradação por oclusão, poucos pixels, posicionamento de câmera, resolução e frame rate;
- recomendação de ao menos duas câmeras em cruzamentos grandes quando possível;
- cascata de operadores baratos/caros para reduzir custo computacional.

A SI-09 aproveita esses princípios, não o código Rocket.

## O que as fontes NÃO suportam diretamente
O relatório não valida nosso `Dynamic X`, nossa função de custo, nossa definição de fila, nem nossa política minor-first. Esses elementos são engenharia própria e precisam de experimentação independente.

Também não tratamos Bellevue como homologação de Recife.

## Licenciamento e demonstração comercial
O repositório não declara licença padrão e seu README enquadra o material para pesquisa. Os termos atuais da City of Bellevue proíbem uso comercial sem permissão expressa por escrito.

Por isso, uma fonte Bellevue deve entrar como:

```json
{
  "data_origin": "external_real_replay",
  "commercial_demo_authorized": false
}
```

Somente após autorização escrita deve-se definir `commercial_demo_authorized:true`, com `authorization_ref` na configuração privada. A referência não é exposta no health público.

## Estratégia de custo
Não processar 101 horas inicialmente.

Plano recomendado:
1. selecionar 3–5 cruzamentos/condições;
2. trabalhar com trechos de 5–15 minutos;
3. executar replay em 30/15/10/5 FPS;
4. comparar tracking, fila, contagem e X;
5. escolher o menor FPS que preserve os thresholds previamente aprovados.

Essa abordagem usa `target_fps` e os motores existentes em vez de introduzir uma segunda stack de vídeo.

## Multi-câmera
A recomendação de duas câmeras de Bellevue é tratada como alerta de cobertura, não como autorização para somar contagens de câmeras. A SI-09 v1 não faz fusão multi-câmera. Cada fonte produz seu próprio estado; baixa confiança leva à abstenção.
