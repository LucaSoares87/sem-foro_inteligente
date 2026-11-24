# Critério de aceite e gate final

O gate final SI-08B é deliberadamente composto. A plataforma só expõe `ready_for_supervised_pilot` quando todos os gates obrigatórios têm evidência `ready`.

## O que o software pode provar sozinho
- contratos e validações funcionam;
- avaliador é determinístico;
- SHA-256 vincula arquivos e relatórios;
- regressões são detectadas pelo CI;
- backup/restore e recovery harness funcionam;
- scorecard não promove evidência sintética a campo;
- nenhuma atuação física foi introduzida.

## O que exige mundo real
- qualidade do modelo na cena escolhida;
- estabilidade da câmera;
- geometria e oclusões reais;
- ground truth independente;
- desempenho do hardware-alvo sob workload;
- tempo de recuperação aceito no ambiente-alvo;
- aprovação humana.

## Registro de evidência
`VALIDATION_EVIDENCE_JSON` aceita no máximo um registro por gate. Um gate `ready` exige SHA-256 + timestamp; aceite humano exige referência, timestamp e `human_authorized:true`. Evidência com `origin:synthetic` não pode satisfazer gate obrigatório de piloto.

O JSON é configuração operacional externa. Não embutir dados pessoais, segredos, vídeos ou credenciais nele.
