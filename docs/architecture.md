# Fundação arquitetural
Frontend e API compartilham origem no ambiente Compose por proxy reverso. PostgreSQL fica na rede interna. A API tem liveness independente e readiness com consulta ao banco e verificação da revisão de schema. WebSocket nativo utiliza protocolo JSON versionado e heartbeat de aplicação. Nenhum motor de inferência está carregado na fundação.

Pipeline futuro: fonte autorizada -> ingestão -> inferência -> tracking -> agregação -> simulação/recomendação -> auditoria -> interface. Cada estágio será isolável, com limites de recursos, timestamps UTC e origem explícita. Ausência de evidência ou falha implica abstenção, nunca comando real. As recomendações não são autorização de engenharia de tráfego.

A implantação nesta fase é local de desenvolvimento. Autenticação, autorização, TLS e endurecimento de produção ainda são gates futuros. Não expor a internet.
