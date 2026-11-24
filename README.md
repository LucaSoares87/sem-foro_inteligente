# Semáforos Inteligentes

Plataforma de inteligência semafórica urbana exclusivamente consultiva e de simulação. Não controla semáforos físicos.

## Desenvolvimento local
Requisitos: Docker Compose v2. Copie `.env.example` para `.env` e preencha `POSTGRES_PASSWORD` com uma senha forte de desenvolvimento. Não publique esse arquivo.

```sh
docker compose up --build -d
docker compose ps
```

Dashboard: http://localhost:5173. Health: http://localhost:5173/api/v1/health.

A migração é executada por serviço separado antes da API. O PostgreSQL não publica portas e a interface é vinculada a loopback por padrão. O backend executa como usuário não-root, filesystem somente leitura e limites de recursos configuráveis.

## Fronteira corporativa
O projeto não coleta nem armazena senhas de usuários. Em desenvolvimento, `AUTH_MODE=disabled` mantém compatibilidade local. Em produção, `APP_ENV=production` exige `AUTH_MODE=proxy_headers`, auditoria habilitada e origens explícitas.

O modo `proxy_headers` confia em identidade já autenticada por um proxy/IdP corporativo. Esse proxy externo deve remover qualquer `X-SI-User` e `X-SI-Roles` enviado pelo cliente e injetar seus próprios valores autenticados. Nunca exponha o Nginx da aplicação diretamente à internet nesse modo.

Papéis:
- `viewer`: leitura de painéis, APIs e métricas;
- `operator`: leitura + operações mutáveis já existentes;
- `admin`: acesso adicional ao journal de auditoria.

Ações mutáveis em modo autenticado falham com `503 audit_unavailable` se o journal não puder ser verificado antes da execução.

## Backup e recuperação
Backup PostgreSQL em formato custom com checksum:

```sh
./ops/backup.sh
```

Restauração segura exige arquivo e banco destino. Por padrão, o script recusa sobrescrever o banco ativo e recusa substituir um banco já existente.

```sh
./ops/restore.sh backups/traffic-AAAAmmddTHHMMSSZ.dump traffic_restore
```

Use `RESTORE_REPLACE=YES` somente para substituir um banco alternativo existente. Restaurar sobre o banco ativo exige também `ALLOW_DESTRUCTIVE_RESTORE=YES` e deve ocorrer apenas sob procedimento operacional aprovado.

## Observabilidade
- `/api/v1/operations/status`: postura de segurança, auditoria e métricas agregadas;
- `/api/v1/operations/metrics`: métricas Prometheus-text sem dependência externa;
- `/api/v1/operations/audit`: journal administrativo de ações mutáveis e negações;
- cada resposta HTTP recebe `X-Request-ID`;
- logs operacionais são estruturados em JSON e não registram payloads de requisição.

## Verificação
```sh
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

O CI valida Python, PostgreSQL, migrações, frontend, Compose, headers, usuário não-root, smoke de carga e ciclo real de backup/restore. Consulte `docs/hardening.md`, `docs/roadmap.md` e `AGENTS.md`.
