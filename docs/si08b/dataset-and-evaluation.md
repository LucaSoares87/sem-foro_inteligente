# Dataset e avaliação

## Vídeos a serem produzidos depois
Os vídeos sintéticos deverão usar o mesmo contrato dos vídeos de campo, mas com `origin: synthetic`. Isso permite testar o pipeline sem criar um segundo sistema de demonstração.

Cada caso deve possuir, fora do repositório público quando o arquivo for grande ou sensível. Para manter paridade com o pipeline atual, use no máximo 1280×720 e 30 FPS:

- vídeo autorizado;
- `manifest.json`;
- `ground-truth.json`;
- `predictions.json`, produzido pelo ensaio;
- `thresholds.json`, aprovado antes do ensaio;
- `evaluation-report.json`, gerado pelo CLI;
- SHA-256 dos artefatos relevantes.

## Manifesto
O manifesto fixa dataset, origem, fonte, cruzamento, nome e SHA-256 do vídeo, proveniência, referência de licença/autorização, FPS, resolução, frame count e classes.

A ferramenta verifica nome, SHA-256, capacidade de abertura pelo OpenCV, resolução, FPS e frame count antes de calcular métricas.

## Ground truth
Cada objeto contém frame, ID humano/verdadeiro, classe e bounding box normalizada. Contagens esperadas são vinculadas a linha, direção e opcionalmente classe. Duplicações incompatíveis são rejeitadas.

## Predições
Não editar manualmente as predições para um ensaio de aceite. Gere-as com o runner offline, que reutiliza o mesmo worker YOLO, o mesmo ByteTrackInspired e o mesmo TrafficEngine do produto:

```sh
cd backend
python -m src.validation.cli run-case \
  --manifest manifest.json \
  --video video.mp4 \
  --model-spec model-spec.json \
  --model-root /caminho/autorizado/modelos \
  --geometry geometry.json \
  --output predictions.json
```

`predictions.json` separa `detections` de `tracks`, registra SHA-256 do modelo e da geometria e contém as contagens finais por linha/sentido. O runner emite contagens agregadas (`label:null`); enquanto não houver contagem por classe no motor analítico, o ground truth de contagem usado para aceite também deve ser agregado.

## Métricas
O avaliador calcula:
- TP/FP/FN, precisão, recall e F1 por classe;
- macro F1 de detecção;
- recall de observações com tracking;
- trocas de identidade e taxa de troca;
- erro absoluto médio de contagem;
- acurácia ponderada de contagem.

O matching usa IoU configurável e greedy matching por classe dentro do mesmo frame. Não chamar essas métricas de mAP/MOTA, pois o algoritmo não implementa integralmente esses padrões.

## Thresholds
Não existe threshold municipal default no código. `thresholds.json` deve informar:
- `detection_macro_f1`;
- `tracking_match_recall`;
- `max_identity_switch_rate`;
- `count_accuracy`.

Esses valores devem ser aprovados antes da coleta que valerá como aceite. Alterar thresholds depois de ver o resultado invalida a imparcialidade do gate.

## Exemplo conceitual
```json
{
  "detection_macro_f1": "<valor aprovado 0..1>",
  "tracking_match_recall": "<valor aprovado 0..1>",
  "max_identity_switch_rate": "<valor aprovado 0..1>",
  "count_accuracy": "<valor aprovado 0..1>"
}
```

Os placeholders acima são deliberadamente inválidos para impedir uso acidental como critério real.
