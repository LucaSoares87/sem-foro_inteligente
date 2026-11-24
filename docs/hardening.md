# SI-08A — Hardening corporativo e operacional

## Escopo e ameaça
A SI-08A endurece a plataforma sem mudar sua finalidade: advisory e simulation. Não cria atuação física, não adiciona captura de credenciais e não muda os contratos de visão, tracking, analytics, previsão ou decisão.

A fronteira considerada é: navegador/operador -> proxy ou IdP corporativo -> Nginx da aplicação -> FastAPI -> PostgreSQL interno. O PostgreSQL permanece sem porta pública. Em produção, o Nginx da aplicação não deve ser exposto diretamente a clientes sem um proxy corporativo que autentique o usuário e sanitize headers de identidade.

## Identidade e RBAC
`AUTH_MODE=proxy_headers` usa claims fornecidos externamente:
- `X-SI-User`: identidade corporativa já autenticada;
- `X-SI-Roles`: lista de `viewer`, `operator` e/ou `admin`.

O sistema não recebe senha, token de login, biometria ou segredo do usuário. O backend apenas aplica autorização. `APP_ENV=production` falha na inicialização se a autenticação estiver desabilitada, se auditoria estiver desligada ou se `ALLOWED_ORIGINS` não for explícito.

GET/HEAD/OPTIONS exigem `viewer`, ações mutáveis exigem `operator`, e o journal de auditoria exige `admin`. Health/readiness permanece público para probes. WebSocket obedece à mesma fronteira de leitura e ao allowlist de Origin.

## Auditoria
A migração `0005_operational_hardening` cria `operational_audit_events`. O journal registra request ID, ator, papéis, método, rota, status, desfecho e timestamp. Não persiste corpo da requisição, imagem, vídeo, placa, face ou credencial.

Em modo autenticado, ações mutáveis fazem preflight do armazenamento de auditoria e falham fechadas com `503 audit_unavailable` se o journal não estiver disponível. Falhas de escrita pós-resposta são contabilizadas em observabilidade e registradas sem payload.

## Observabilidade
Cada requisição recebe `X-Request-ID`. Logs do namespace `si.operations` são JSON e incluem apenas metadados operacionais mínimos. `/api/v1/operations/metrics` expõe contadores agregados de requests, erros 5xx, negações, requests em voo, falhas de auditoria, uptime e latência média. Não há labels de usuário ou rota dinâmica em métricas para evitar cardinalidade e exposição desnecessária.

## HTTP e containers
Nginx adiciona CSP restritiva, Permissions-Policy, proteção contra framing, no-sniff, referrer policy e cache no-store. O limite de corpo é 1 MiB. Backend e serviço de migração usam filesystem somente leitura com `/tmp` em tmpfs, `no-new-privileges`, PID limit e recursos configuráveis. Backend e frontend executam não-root; o CI verifica isso.

Os limites são defaults de proteção e podem ser ajustados por variáveis de ambiente após medição no hardware-alvo. Não representam dimensionamento homologado.

## Backup e restore
`ops/backup.sh` usa `pg_dump -Fc`, escrita atômica, `umask 077` e checksum SHA-256. `ops/restore.sh` verifica checksum quando presente e restaura para banco alternativo por padrão. Sobreposição do banco ativo é recusada sem opt-in explícito. O CI executa backup real do PostgreSQL do Compose, restaura em outro banco, confirma a revisão Alembic e remove o banco de ensaio.

Isto prova o mecanismo, não define sozinho RPO/RTO municipal. Frequência, retenção, criptografia em repouso fora do host e armazenamento off-site dependem da infraestrutura contratante.

## Carga
`ops/smoke_load.py` é um gate leve e determinístico, não um benchmark de capacidade. O CI dispara requisições concorrentes ao health endpoint e exige zero erros e p95 abaixo de um teto amplo de regressão. Dimensionamento de produção será parte da SI-08B no hardware-alvo.

## Itens deliberadamente fora da SI-08A
- login próprio ou armazenamento de senhas;
- integração específica com um IdP municipal ainda não fornecido;
- TLS/certificados geridos pela aplicação;
- SIEM externo, storage off-site e alertmanager;
- pentest independente;
- homologação de câmera/modelo/hardware de campo;
- qualquer interface de atuação semafórica.

Esses itens dependem da infraestrutura real ou de autorização humana e não são simulados como concluídos.
