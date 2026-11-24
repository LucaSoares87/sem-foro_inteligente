# Protocolo experimental Bellevue

## Objetivo
Usar trânsito real externo para descobrir regiões de estado em que minor-first ou major-first produz menor custo simulado, sem promover o dataset a evidência de campo Recife.

## Seleção inicial
Escolher amostras que cubram:
- baixo, médio e alto volume;
- fila assimétrica e equilibrada;
- dia/noite quando disponível;
- condições com oclusão;
- mix de classes diferente.

Não selecionar resultados com base no desempenho do algoritmo.

## Geometria
Para cada câmera:
1. definir ROIs de aproximação;
2. definir linhas de descarga;
3. declarar grupos de serviço A/B;
4. estimar capacidade de armazenamento em veículos para fins experimentais;
5. revisar visibilidade e registrar `visibility_score`;
6. marcar `visibility_calibrated=true` somente após revisão humana da cena.

Essa calibração é experimental, não homologação municipal.

## Replay
Executar o mesmo trecho em vários `target_fps`:
- 30;
- 15;
- 10;
- 5.

Comparar:
- contagem;
- estabilidade de track IDs;
- queue_length;
- arrival/discharge;
- wait;
- observation_confidence;
- preferência SI-09.

Não reduzir FPS de produção apenas por ganho computacional; primeiro demonstrar que as métricas relevantes permanecem dentro dos thresholds escolhidos antes do ensaio.

## Descoberta do X
Para cada snapshot válido:
1. registrar estado dos dois grupos;
2. calcular `X_safe`;
3. executar minor-first e major-first;
4. armazenar custos e vencedor;
5. estratificar por volume, assimetria, confiança e margem de spillback.

Após volume suficiente, analisar se `X*` pode ser aproximado por modelo leve. Não treinar uma rede neural decisória antes de existir baseline determinístico e dados suficientes.

## Proveniência
Todo resultado Bellevue deve preservar:
- source_id;
- data_origin=external_real_replay;
- SHA/manifesto do vídeo quando disponível no fluxo SI-08B;
- geometry hash;
- model hash;
- queue epoch;
- state/result hashes.

Sem autorização comercial escrita, não usar frames Bellevue em pitch de venda.
