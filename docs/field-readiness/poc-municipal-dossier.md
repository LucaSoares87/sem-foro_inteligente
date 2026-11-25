# Dossiê preliminar — POC municipal CIU, um cruzamento em modo sombra
## Objetivo e limites
30 dias propostos de observação, após autorizações, com uma câmera e um cruzamento. CIU não se conecta ao controlador físico, não altera fases/tempos, não identifica placas ou pessoas; resultados experimentais não são promessa de redução de congestionamento. Aceite humano produto e campo separados.
## Infraestrutura inicial proposta (dimensionamento a verificar)
- Câmera existente autorizada, fixa, imagem suficiente para região de interesse; RTSP/RTSPS ou VMS somente após validação; referência de geometria e relógio. Uma fonte inicialmente, rede segregada, acesso somente leitura e credenciais em segredo local.
- Host Linux x86_64 dedicado, ponto de partida de avaliação: 8 vCPU ou núcleos equivalentes, 16 GB RAM, SSD 256 GB; não são mínimos certificados. Confirmar consumo medido em benchmark, GPU somente se necessária e validada. NTP, UPS/energia e espaço privado conforme retenção autorizada.
- Armazenamento: não reter vídeo contínuo por padrão. Se autorização exigir retenção, dimensionar por bitrate medido x duração/8, mais margem e política de expurgo. Acesso restrito, logs sem credenciais ou imagens, backup de relatórios agregados.
- Rede: medir bitrate e perdas da câmera; não expor portas públicas. Separar rede de pesquisa do controlador, sem rota de escrita/controle. 
- Papéis: órgão de mobilidade (autorização, engenharia de tráfego), responsável de privacidade/dados (finalidade, acesso e retenção), operador de infraestrutura, dois anotadores e terceiro revisor independente.
## Fases e entregáveis
0. Carta de autorização, local, fonte, modelo/hash, política de dados, critérios aprovados antes da coleta.
1. Homologação privada produto, revisão C3, calibração e referência independente, benchmark integrado e recuperação no alvo, ensaio de 24h de laboratório.
2. Só com autorização de observação e evidências exigidas, coleta em sombra; indicadores: cobertura, contagem/filas/velocidade somente quando validadas, qualidade por fonte e lacunas. Comparações em replay/simulação, sem alegar ganho contrafactual real.
3. Relatório agregado, limitações e decisão do responsável, plano de retenção e encerramento. Parar diante de revogação, perda de privacidade, câmera deslocada, dados inválidos, tentativa de atuação ou risco operacional.
## Critérios e custos
Sete gates SI08B originais permanecem obrigatórios, nenhum atendido nesta fase. Limites de erro/FPS/latência/recuperação de campo definidos pelos responsáveis antes da medição; não inventar números de aprovação. Custo deve ser cotado a partir de câmera existente, host/energia, conectividade, instalação, operação e anotação. Sem orçamento autorizado ou contratação nesta rodada. Usar host já disponível se autorizado e suficiente. Nenhum teste contínuo iniciado.
