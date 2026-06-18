## ADDED Requirements

### Requirement: Backend API para el agente CM

El sistema SHALL tener un backend .NET 10 (`cm-backend/`) que exponga APIs REST para que el agente Python del CM consuma.

#### Scenario: Agente se comunica con backend
- **WHEN** el agente Python completa una publicación
- **THEN** envía una solicitud HTTP a `cm-backend` para actualizar el timeline

### Requirement: Endpoints de clientes

El backend SHALL exponer endpoints CRUD para clientes y sus redes sociales.

#### Scenario: Listar clientes
- **WHEN** el frontend solicita `GET /api/clients`
- **THEN** el backend retorna la lista paginada de clientes del gestor autenticado
