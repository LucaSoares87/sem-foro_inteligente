# SI-09 — Queue Intelligence & Dynamic Clear-First Optimization

## Objetivo
Reduzir retenção, paradas e instabilidade de fluxo sem cair na regra simplista “mais carros = mais verde”. A hipótese central é avaliar se uma fila menor pode ser eliminada rapidamente antes de conceder uma janela de serviço mais longa ao fluxo dominante.

A SI-09 é exclusivamente observacional, analítica e simulada. Não existe interface com controlador físico.

## Arquitetura
```text
Video
  -> YOLO/ONNX
  -> ByteTrackInspired
  -> ROI + line analytics
  -> QueueEstimator
       queue_length
       arrival_rate
       discharge_rate
       wait
       storage occupancy
       confidence
  -> Dynamic Clear-First
       X_safe
       minor-first counterfactual
       major-first counterfactual
       continuity/queue cost
  -> explainable simulation preference
  -> operational abstention
```

Nada na SI-09 reimplementa detecção, tracking ou contagem. O estimador consome os mesmos `TrackBatch` e `TrafficSnapshot` já consolidados.

## Duas fases explícitas
O otimizador v1 exige exatamente dois `service_group`. Várias aproximações podem pertencer ao mesmo grupo se forem explicitamente configuradas como simultaneamente atendíveis. O sistema não infere conflitos de movimento.

Mais ou menos de dois grupos => `abstain/requires_two_service_groups`.

Isso preserva o modelo de duas filas da SI-06 sem fingir suporte a um controlador multifásico completo.

## Continuidade, não “velocidade constante” literal
Sem calibração de perspectiva/distância, a câmera não fornece velocidade física confiável. Por isso a SI-09 não afirma manter km/h constante. Ela tenta preservar continuidade por proxies mensuráveis:
- área acumulada de fila;
- espera máxima estimada;
- chegadas durante períodos sem serviço;
- exposição a spillback;
- custo de transição.

O objetivo futuro é reduzir a probabilidade de parada e o tempo retido. Velocidade física ficará fora até calibração de campo.

## Segurança
- `physical_actuation=false`;
- `operational_decision=abstain`;
- confiança visual abaixo de 0,65 => abstenção;
- visibilidade não calibrada tem confiança limitada a 0,60;
- fila menor acima de `X_safe` nunca recebe preferência minor-first;
- pesos da função de custo permanecem `engineering_weights_validated=false`.
