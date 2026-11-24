# Bellevue FPS benchmark — execução e estado

## Estado atual
`BLOCKED_BY_VIDEO_BYTES`.

A infraestrutura de benchmark está implementada, mas nenhum resultado 30/15/10/5 é registrado como Bellevue enquanto um clipe real não estiver disponível localmente. O repositório oficial referencia pastas do Google Drive; não há MP4 pequeno versionado no GitHub oficial. Um espelho acadêmico AVA-100 foi localizado, porém o arquivo de tráfego observado tem aproximadamente 2,62 GB. Baixar esse volume para obter poucos minutos não é uma estratégia de custo aceitável para o primeiro ensaio.

Dados derivados encontrados em repositórios acadêmicos não são importados quando a licença não está clara e nunca substituem vídeo + ground truth.

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
