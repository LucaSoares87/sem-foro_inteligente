# YOLOX-S — adapter e cadeia de suprimento

## Decisão
YOLOX-S é o candidato de engenharia para replay Bellevue. Ele não substitui automaticamente modelos já configurados e permanece `validation_only` até os gates de SI-08B.

Motivos:
- Apache-2.0 no upstream YOLOX;
- COCO-80 inclui bicycle, car, motorcycle, bus e truck;
- 640x640 oferece mais margem para veículos pequenos do que Nano/Tiny;
- aproximadamente 35.9 MB, dentro do limite atual de artefato;
- contrato ONNX publicamente verificável: `[1,3,640,640] -> [1,8400,85]`.

## Isolamento arquitetural
`ModelSpec.architecture` aceita:
- `ultralytics_yolo`: comportamento consolidado anterior, default para compatibilidade;
- `yolox`: novo caminho.

O adapter YOLOX usa o pré-processamento do upstream:
- BGR do OpenCV;
- sem divisão por 255;
- padding 114 no canto superior esquerdo;
- CHW float32.

A saída raw é decodificada com grids e strides 8/16/32. Score final = objectness × probabilidade de classe. O NMS mantém a política class-aware já usada pelo projeto.

## Supply chain
URL oficial pinada:
`https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx`

SHA-256:
`c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063`

Licença:
Apache-2.0 — `Megvii-BaseDetection/YOLOX/LICENSE`.

O módulo `src.vision.model_artifacts`:
1. usa somente a URL pinada;
2. aplica limite de 64 MiB;
3. faz streaming para `.part`;
4. calcula SHA-256 durante o download;
5. remove o parcial em falha;
6. promove atomicamente o arquivo apenas quando o hash coincide;
7. gera `ModelSpec` com `architecture=yolox` e `purpose=validation_only`.

O worker continua sem acesso de rede e não baixa modelos.

## Gate CI
O CI baixa o artefato oficial, verifica o SHA e executa um forward real via OpenCV DNN usando o adapter YOLOX. Fixtures unitários continuam testando a matemática separadamente.

Uma falha de rede, hash ou formato torna o gate vermelho; o CI não troca de mirror silenciosamente.
