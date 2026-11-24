# Bellevue FPS benchmark — execução e estado

## Estado atual
`MODEL_ADAPTER_IN_VALIDATION`.

O conector autorizado do Google Drive permitiu acessar diretamente a pasta pública oficial de Bellevue, eliminando a dependência do espelho AVA-100. Arquivos reais do cruzamento `Bellevue_116th_NE12th` foram inspecionados e uma amostra de 7m06s foi preservada como replay secundário.

A inspeção dos bytes mostrou que o FPS efetivo varia entre arquivos apesar do dataset ser descrito nominalmente como 30 Hz. Exemplos observados:
- `2017-09-11_17-08-39`: 426.58 s, 17.39 FPS — replay real útil, mas não baseline 30 FPS;
- `2017-09-11_07-08-32`: 408.54 s, 28.94 FPS — próximo de 30, porém não será rotulado como 30;
- `2017-09-11_12-08-33`: 108.67 s, 30.02 FPS — válido para sanity-check 30 FPS, curto demais para o ensaio principal;
- `2017-09-11_08-08-50`: 602.78 s, 27.65 FPS;
- `2017-09-11_14-08-35`: 730.52 s, 21.96 FPS.

Portanto o protocolo continua estrito: um ensaio `30/15/10/5` só poderá usar como referência um clipe cujo FPS efetivo realmente suporte 30 FPS. Se isso não ocorrer em um trecho de 5–15 minutos, será criado um protocolo versionado de referência nativa; não haverá arredondamento silencioso.

O modelo escolhido é o YOLOX-S oficial, Apache-2.0. O worker continua sem downloads de rede, mas existe uma etapa administrativa separada, pinada por URL e SHA-256, para materializar o modelo. O adapter YOLOX é isolado do parser original e precisa passar CI com o ONNX oficial antes do benchmark real.

## Por que o benchmark existe
O estudo Bellevue/Microsoft mostra que frame rate, resolução, oclusão e posição de câmera afetam videoanalytics. Em vez de copiar uma stack de cascata externa, este projeto mede diretamente a relação custo/estabilidade no nosso próprio pipeline.

O mesmo clipe é processado em:
- 30 FPS: referência de engenharia;
- 15 FPS;
- 10 FPS;
- 5 FPS.

Cada replay executa o mesmo caminho:

```text
InferenceWorker
  -> ByteTrackInspired
  -> TrafficEngine
  -> QueueEstimator
  -> Dynamic Clear-First / X
```

## Métricas
Cada FPS registra:
- frames processados;
- inferência média/p95;
- tracking médio;
- detecções e observações confirmadas;
- contagens finais;
- fila por aproximação;
- arrival/discharge rates;
- confiança;
- X dinâmico;
- preferência minor-first / major-first / no-material-advantage / abstain.

A comparação contra 30 FPS calcula:
- MAE de fila;
- MAE de arrival/discharge;
- erro relativo de contagem;
- MAE de X;
- concordância da preferência simulada.

O menor FPS só é marcado como candidato de engenharia quando há duração comum, decisões comparáveis e observações de X suficientes. Ausência de decisão não é convertida em concordância artificial.

## Critérios v1 congelados antes do vídeo
`bellevue-benchmark-criteria-v1.json` foi definido antes da execução real. Ele não é critério municipal e não é homologação:
- queue MAE <= 1 veículo;
- count relative error <= 5%;
- X MAE <= 1 veículo;
- preferência simulada >= 95%;
- >= 30 segundos comuns;
- >= 10 segundos com preferência comparável;
- >= 5 segundos com X comparável.

Os critérios podem ser versionados no futuro, mas qualquer alteração depois de observar um resultado precisa gerar uma nova versão, nunca reescrever v1.

## Preparação do clipe
Coloque o clipe em uma pasta ignorada pelo Git, por exemplo `external-data/bellevue/`.

Para um arquivo oficial cujo nome contenha `__YYYY-MM-DD_HH-MM-SS`:

```sh
cd backend
python -m src.validation.cli prepare-bellevue \
  --video ../external-data/bellevue/Bellevue_116th_NE12th__2017-09-11_09-08-31.mp4 \
  --dataset-id bellevue-116th-ne12th-case01 \
  --source-id BELLEVUE_116TH_NE12TH \
  --intersection-code BELLEVUE_116TH_NE12TH \
  --output ../benchmark-results/bellevue-case01-manifest.json
```

Se o clipe foi recortado/renomeado, forneça `--recorded-at` com timestamp timezone-aware referente ao início real do clipe.

O manifesto sempre nasce com:
- `origin=external_real_replay`;
- `commercial_demo_authorized=false`;
- SHA-256 do clipe;
- proveniência do repositório oficial;
- referência de pesquisa, não de licença comercial.

## Execução
Depois de revisar manualmente ROIs, linhas, grupos e visibilidade na geometria:

```sh
python -m src.validation.cli fps-sweep \
  --manifest ../benchmark-results/bellevue-case01-manifest.json \
  --video ../external-data/bellevue/<arquivo>.mp4 \
  --model-spec model-spec.json \
  --model-root /caminho/modelos \
  --geometry bellevue-geometry.json \
  --criteria ../docs/si09/bellevue-benchmark-criteria-v1.json \
  --output ../benchmark-results/bellevue-case01-fps.json
```

## Interpretação
`engineering_recommended_min_fps` é somente um candidato técnico para reduzir custo computacional. Não altera automaticamente `target_fps` de produção, não satisfaz SI-08B e não autoriza atuação física.

Sem autorização escrita de Bellevue, frames e vídeos não devem ser usados em apresentação comercial.


## YOLOX-S selecionado
Artefato: `yolox_s.onnx` da release oficial YOLOX `0.1.1rc0`.

Contrato:
- arquitetura: `yolox`;
- input: `images[1,3,640,640]`;
- output: `output[1,8400,85]`;
- classes: COCO-80, mantendo somente bicycle/car/motorcycle/bus/truck;
- SHA-256 esperado: `c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063`;
- licença: Apache-2.0;
- purpose inicial: `validation_only`.

Aquisição administrativa:

```sh
cd backend
python -m src.vision.model_artifacts \
  --output /caminho/modelos/yolox_s.onnx \
  --spec-output /caminho/modelos/yolox_s.model-spec.json
```

O comando baixa somente a URL oficial pinada, impõe limite de tamanho, calcula SHA-256 durante streaming e só faz rename atômico do `.part` após a verificação. O subprocesso de inferência não realiza downloads.
