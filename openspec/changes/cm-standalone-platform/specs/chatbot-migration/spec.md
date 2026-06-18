## ADDED Requirements

### Requirement: Chatbot migrado a su propio repositorio

El sistema SHALL migrar todo el código del chatbot con IA a un repositorio independiente `chatbot-service/`, sin dependencias con el proyecto CM.

#### Scenario: Chatbot funcionando en repositorio propio
- **WHEN** se clona `chatbot-service/` y se ejecuta `docker-compose up`
- **THEN** el chatbot responde exactamente igual que antes de la migración

#### Scenario: Chatbot sin importar código del CM
- **WHEN** se analizan las importaciones del chatbot
- **THEN** ninguna importación referencia archivos del CM

### Requirement: Renombrar repositorio actual

El proyecto `TestLangChain` SHALL renombrarse a `chatbot-service/` para reflejar su propósito.

#### Scenario: Renombrado correcto
- **WHEN** se migra el código
- **THEN** el repositorio destino se llama `chatbot-service` y contiene solo el chatbot
