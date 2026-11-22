# Regras de desenvolvimento
- Modo exclusivamente advisory e simulation. Nunca emitir comandos para controladores físicos, alterar fases reais ou integrar interfaces de atuação.
- Não coletar placas, rostos, biometria ou credenciais; não publicar vídeos reais no repositório público.
- Dados simulados devem ser identificados em cada contrato e na interface. Não apresentar métricas fictícias como medidas.
- Preservar contratos publicados; mudanças incompatíveis exigem ADR e nova versão.
- Para cada missão: inspecionar main e issues, implementar em branch isolada, testar casos positivos e negativos, abrir PR com evidências, verificar SHA e CI antes de integrar. Nunca forçar referências, desativar testes ou ignorar falhas para obter verde.
- Não introduzir serviços pagos ou dependências pesadas sem justificar necessidade. Segredos somente por variáveis externas; nunca no Git.
- Se faltar infraestrutura ou dados, registrar BLOCKED/NOT_RUN com evidência. Não afirmar homologação sem execução. Aceite de campo e implantação dependem de autorização humana.
