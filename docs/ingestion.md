# SI-02A — motor de ingestão

O motor aceita observações sintéticas estruturadas; não captura vídeo nem executa inferência. Cada evento possui identificador UUID, cruzamento, fonte lógica, sequência, data UTC e origem. A passagem pelo processador padrão somente valida um handoff que se abstém de decidir. Estado processed significa ingestão concluída, não análise visual concluída.

Fila FIFO limitada a 32 itens aguardando mais um em processamento; histórico de 128 recibos terminais. Memória por processo. Reenvio do mesmo ID/payload retorna recibo enquanto retido; conflito retorna 409. Após expiração por capacidade ou reinício não há garantia de deduplicação. Sobrecarga responde 503, Retry-After 1. Timeout e exceção são registrados com códigos sanitizados; o consumidor segue para o próximo evento. Encerramento drena por até 3 segundos e cancela o restante; adaptadores assíncronos devem cooperar com cancelamento e nunca bloquear o event loop. Sem retry automático (evita duplicar efeitos). A latência medida é tempo do processador local, não latência de câmera.

API local de desenvolvimento, sem exposição pública: POST /api/v1/ingestion/observations (202 novo, 200 repetido, 409 conflito, 422 contrato inválido, 503 indisponível), GET /api/v1/ingestion/observations/{event_id}, GET /api/v1/ingestion/status. Health existente mantém contrato e acrescenta ingestion; readiness continua refletindo a fundação. WebSocket, banco e frontend não foram substituídos.

Exemplo:
```json
{"event_id":"b959a21f-dc55-4131-8632-1c7cc16f702e","intersection_code":"CR_01","source_id":"CAM_01","sequence":1,"captured_at":"2026-01-01T12:00:00Z","origin":"synthetic","vehicle_count":3}
```

Pendências: SI-02B (orquestração de múltiplos estágios, replay e auditoria persistente); SI-03 (adaptadores reais de vídeo e reconexão). Autenticação e limites de requisição em gateway são obrigatórios antes de uso fora do ambiente local. Nenhuma atuação física.
