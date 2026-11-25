# FINAL-ACCEPTANCE — Aceite humano do produto

Base SI-13: 3fa80d07bf91a363f3e7fd043857df47ff65af2d; CI pós-merge 45525137164, três jobs aprovados. Ensaio integrado SI-13 45524591138, artefato 14981962501, ZIP SHA-256 7174edd3a2df4466f666a90907d66692d44222f87e687fcca228da3b8567690b. Preservar acervo SI-13 e resultados anteriores. Não é SI-14, nem homologação municipal. Nenhuma configuração de produção, motor ou gate alterado.

## Instalação no Codespaces (Linux)
Depois do merge e CI, abrir Code > Codespaces > Create codespace on main (preferir nova instância, não alterar ambiente corporativo). Dev container Ubuntu 24.04, Docker-in-Docker, Python 3.12, porta 5173 encaminhada. Escolher máquina de 4 cores/8 GB se disponível; 2 cores pode ser mais lento. Consumo depende da franquia; parar Codespace ao terminar. Não há inicialização automática de serviços. No terminal:

```bash
git rev-parse HEAD
git status --short
python ops/final_acceptance.py start
python ops/final_acceptance.py test
```

Na aba Ports, confirmar **Private** na porta 5173; não abrir como Public. O Compose original publica somente loopback. Auth desabilitada apenas na demonstração privada. Abra o endereço encaminhado (em nova aba, não iframe). Comece em /executivo. Não compartilhar URL nem cadastrar fontes reais. A ferramenta usa projeto Compose dedicado por diretório, senha local aleatória persistida fora do Git (permissão 0600), ignora .env e variáveis de campo, usa daemon Linux local e recusa configuração que publique backend, monte fontes ou registre evidências de campo. Não modifica .env, não apaga volumes, não baixa modelo nem vídeo. Se 5173 já estiver ocupado, não mate o processo: escolha Codespace novo. Não use este roteiro em servidor público ou ambiente municipal.

## Roteiro de aceite (manual)
| Ambiente | Ação | Resultado esperado |
| --- | --- | --- |
| /executivo | Conferir painel, saúde, disponibilidade e prontidão | UI legível; sem cruzamentos cadastrados; piloto não homologado |
| /videowall | Entrar em tela cheia, conferir 1920x1080 se disponível, sair | Navegação e indicadores sem corte crítico; sem dados fictícios |
| /operacional | Testar contexto inexistente; conferir ausência de fontes | Não exibir preferência atual ou fila inventada; aviso explícito |
| /laboratorio | Testar os cinco cenários; repetir assimétrico, abrir detalhes e exportar extrato SI-11 | Resultado sintético, hash estável, comparações e limitações explícitas |
| /apresentacao | Percorrer sete passos; testar iniciar automático, pausar, anterior, próximo, encerrar | Navegação e indicadores de origem; simulação e acervo identificados |
| /homologacao | Conferir status e 7 gates | Piloto bloqueado, nenhuma autorização fictícia, sem atuação física |

A demo é a simulação determinística SI-06 existente, mais o acervo científico SI-11. Não existe reprodução de câmera nem detector ativo neste perfil. O replay de pesquisa integrado foi executado separadamente na SI-13; a exibição de vídeo real não foi autorizada comercialmente. A ausência de fonte não é fila zero. O teste HTTP não garante renderização; o workflow usa também o navegador Playwright previamente aprovado em Ubuntu 24.04, executando os sete checks SI-12 sobre a mesma instalação. Codespace efetivo, visibilidade privada e experiência humana não são certificados por CI.

## Evidência local e decisão
```bash
python ops/final_acceptance.py status
python ops/final_acceptance.py test --output /tmp/final-acceptance-local.json
```
Preencher checklist.md privadamente, incluir commit, ambiente, capturas de falhas (sem segredos), resultado por ambiente, decisão aprovado/reprovado/pendente. Não registrar este aceite como human_acceptance de campo no VALIDATION_EVIDENCE_JSON. Se houver falha, interromper aceite e informar comando/rota e mensagem, não alterar critérios. Para parar: `python ops/final_acceptance.py stop`; depois Stop codespace. Preservar volumes. Os checks do CI e os testes do usuário são evidências diferentes.

## Limites
Mesmo com CI e demonstração aprovados, POC municipal exige autorização, câmera física, calibração, ground truth independente, desempenho e recuperação no hardware-alvo e aceite formal de campo. Nenhuma promoção automática; sem comandos para semáforos. Próxima etapa após aceite de produto: preparar POC em modo sombra, dentro dos requisitos já definidos.

## Complemento PIMCAT G
Depois de F e G integrados e CI aprovado, o mesmo comando demonstra os novos painéis. No executivo e operacional, relatório diário deve indicar ausência de cruzamento/fonte no ambiente vazio, nunca zero fabricado. No laboratório, selecionar C3 (replay externo, precisão bloqueada), D/E (gates negativos), selecionar 175/240/305s da rede E (18 segmentos desconhecidos em 240s), exportar acervo PIMCAT e confirmar propostas não aplicadas. Ver [dossiê G](../pimcat/g-pilot-dossier.md). O navegador agora executa oito verificações nomeadas, preservando as sete anteriores. Não há motor multimodal ligado à operação: as estratégias permanecem offline.
