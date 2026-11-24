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


## Homologação SI-08B
A rota `/homologacao` apresenta o scorecard do piloto. `/api/v1/validation/status` expõe os mesmos gates por API. O framework não promove automaticamente um ambiente a piloto: modelo, câmera, calibração, ground truth, hardware e aceite humano exigem evidência externa registrada em `VALIDATION_EVIDENCE_JSON`.

O avaliador offline é executado a partir de `backend/`:

```sh
python -m src.validation.cli evaluate \
  --manifest manifest.json \
  --ground-truth ground-truth.json \
  --predictions predictions.json \
  --thresholds thresholds.json \
  --video video.mp4 \
  --output evaluation-report.json
```

Os thresholds não possuem defaults comerciais ou municipais; devem ser aprovados antes do ensaio. Para hardware e recuperação:

```sh
python3 ops/pilot_probe.py --base-url http://127.0.0.1:5173 --samples 30 --interval 1 --require-workload --output pilot-probe.json
python3 ops/recovery_drill.py --base-url http://127.0.0.1:5173 --component backend --output recovery.json
```

Consulte `docs/si08b/` antes de produzir os vídeos de demonstração ou executar captura de campo.


## SI-09 — Queue Intelligence & Dynamic Clear-First Optimization
A SI-09 adiciona uma camada observacional de filas sem substituir SI-06. O pipeline permanece:

```text
vídeo -> YOLO -> tracking -> analytics -> queue intelligence -> optimization
```

A geometria de cada fonte pode declarar `approaches` vinculados a uma ROI, linha de descarga e grupo de serviço. O estimador calcula fila observada, chegada, descarga, espera, ocupação de armazenamento e confiança. A velocidade usada para detectar parada é somente movimento normalizado na imagem; velocidade física em m/s continua indisponível sem calibração métrica.

O otimizador compara, em simulação, duas sequências de serviço para exatamente dois grupos explícitos:
- fila menor -> fluxo dominante;
- fluxo dominante -> fila menor.

`dynamic_x_safe_vehicles` é um gate de segurança: representa o maior tamanho estimado da fila menor que pode ser considerado para limpeza prioritária sem levar o grupo dominante à faixa crítica de armazenamento no modelo. Mesmo quando existe preferência simulada, `operational_decision` permanece `abstain` e `physical_actuation=false`.

APIs:
- `/api/v1/queue/status`;
- `/api/v1/queue/sources/{source}/latest`;
- `/api/v1/queue/sources/{source}/history`;
- `/api/v1/optimization/status`;
- `/api/v1/optimization/sources/{source}/latest`;
- `/api/v1/optimization/sources/{source}/history`.

Consulte `docs/si09/` para o modelo matemático, protocolo Bellevue e limites de interpretação.


### Benchmark Bellevue e YOLOX-S
A CLI possui `prepare-bellevue` e `fps-sweep` para replay externo com proveniência e comparação de estabilidade do SI-09. Arquivos Bellevue reais já foram inspecionados e o projeto não assume que o FPS efetivo seja 30 apenas porque o dataset é nominalmente 30 Hz.

O detector agora aceita duas arquiteturas explicitamente versionadas no `ModelSpec`: `ultralytics_yolo` (contrato existente) e `yolox`. O YOLOX-S oficial foi selecionado como candidato de engenharia por sua licença Apache-2.0. A aquisição é administrativa e pinada:

```sh
cd backend
python -m src.vision.model_artifacts --output /caminho/yolox_s.onnx --spec-output /caminho/yolox_s.model-spec.json
```

O worker de inferência permanece offline. Veja `docs/si09/yolox-s.md` e `docs/si09/bellevue-fps-benchmark.md`.
