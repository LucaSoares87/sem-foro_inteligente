# Semáforos Inteligentes

Plataforma de inteligência semafórica urbana exclusivamente consultiva e de simulação, em desenvolvimento. Não controla semáforos físicos.

## Desenvolvimento local
Requisitos: Docker Compose v2. Copie .env.example para .env e preencha POSTGRES_PASSWORD com uma senha forte de desenvolvimento. Não publique esse arquivo.
Execute:
```sh
docker compose up --build -d
docker compose ps
```
Dashboard: http://localhost:5173. Health: http://localhost:5173/api/v1/health.
A migração é executada por serviço separado antes da API. O banco não publica portas. A interface é vinculada a loopback por padrão. Não disponibilizar na internet: autenticação e TLS não fazem parte deste primeiro incremento.
Para Codespaces, mantenha a porta privada e configure a origem autorizada conforme o endereço real antes de testar WebSocket.

## Verificação
```sh
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
```
O CI também deve testar PostgreSQL, migração, frontend e Compose. Consulte docs/roadmap.md e AGENTS.md. Não há detecção ou controle real nesta entrega.
