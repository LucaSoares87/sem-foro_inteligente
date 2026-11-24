# SI-09D — ensaio real preliminar Bellevue

Base: eab3d3caa387a1dc5de9122f2dc5f5aac15c5d99; SI-09C integrada. Nenhum motor de decisão ou runtime alterado.

## Protocolo
- Fonte pública oficial: Bellevue_116th_NE12th__2017-09-11_12-08-33.mp4, 1280x720, SHA-256 f53d6b706080e0d9bb587e9d254e57a3539ae22f04e54ce503f1572e894cc4a5.
- A média de FPS não é suficiente: o arquivo tem um intervalo inicial irregular. A rotina SI-09D seleciona o primeiro trecho de 32 s com 960 frames reais consecutivos, tolerância máxima de 2 ms na cadência e no desvio acumulado. Não seleciona por resultado de tráfego.
- Derivação FFV1 lossless, 30 FPS, hash dos pixels decodificados comparado antes/depois, nenhuma interpolação, duplicação inserida ou descarte dentro do trecho. Timestamp de início corrigido pela posição temporal original. Original intacto.
- Pipeline inalterado: prepare-bellevue, fps-sweep e critérios v1 congelados. 30/15/10/5 FPS. Todas as taxas usam o mesmo clipe derivado e mesma geometria.
- ROI retangular aproximada de duas regiões visíveis na imagem, linhas de passagem preliminares, dois grupos experimentais (não fases reais), capacidade 12 como placeholder por grupo, visibilidade 0,5 e visibility_calibrated=false. Não representa armazenamento ou fases semafóricas medidos. Confiança limitada; abstenção esperada. Não desativar essa salvaguarda.
- A saída bruta do runner v1 usa referência 30 como fallback quando nenhuma redução passa. Não interpretar como recomendação validada. O artefato interpretation.json declara recomendação nula e bloqueio por confiança geométrica.
- Métricas de contagem, fila e custo computacional são exploratórias, não acurácia absoluta; sem ground truth. Não há validação de X nem eficácia da política. O ensaio principal de 5–15 minutos permanece pendente.
- A execução isolada não usa segredos, não publica frames/vídeos/modelos nos artefatos de pesquisa e não promove homologação SI-08B. Somente JSON agregado, proveniência e hashes. O download público ocorre apenas no workflow experimental.
- Modelo YOLOX-S oficial com hash pinado, validation_only; dataset external_real_replay; commercial_demo_authorized=false, operationally_validated=false, physical_actuation=false.

## Próximo gate
Confirmar CI da branch e execução real; registrar falhas sem fabricar métricas. Para avançar além do ensaio preliminar: revisão geométrica com direção, capacidade e visibilidade comprovadas; clipe longo temporalmente adequado; ground truth independente; comparação contrafactual e validação de X com critérios pré-registrados. Não alterar critérios v1 depois de observar resultados.

## Auditoria de tempo na origem
Amostras analisadas por timestamps de pacotes, tolerância 2 ms local:
- 22-08-50: 13068 frames, 15 desvios, maior intervalo ~145,6 s.
- 05-08-39: 11977 frames, 28 desvios, maior intervalo ~136,3 s.
- 07-08-32: 11824 frames, 5 desvios, maior intervalo ~212,8 s.
- 11-08-33: 9414 frames, 28 desvios, maior intervalo ~99,6 s.
- 12-08-33: 3262 frames, 1 desvio, maior intervalo ~108,7 s.
Os intervalos são exploratórios; a preparação revalida timestamps decodificados e desvio acumulado.
