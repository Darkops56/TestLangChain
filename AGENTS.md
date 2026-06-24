## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Project Status: CM Platform (cm-platform/)

Monorepo dividido en chatbot-service/ y cm-platform/. Lo implementado en cm-platform/:

### Backend (cm-backend/ — .NET 10, EF Core, JWT, PostgreSQL/InMemory)
- Controllers: ClientsController (CRUD + register + social accounts), PublicationsController (CRUD + PUT status + delete), BillingController (invoices), AuthController (login + /me + register), InternalController (community/ drafts + publications endpoints protected con X-Internal-Key)
- SignalR Hub: NotificationHub emite "PublicationStatusChanged" en tiempo real
- Servicios: MockAgentClient (fake si no hay agent URL), CommunityReviewService, CommunityPublicationPublisher, CommunityApprovalBackgroundService
- Auth: JWT Bearer, login por email (sin password), token 30 días

### Frontend (cm-frontend/ — Blazor WASM + MudBlazor 9.5)
- Pages: Dashboard, Clients (búsqueda + navegación), ClientDetail (redes, pubs, facturas), ClientForm (crear/editar), Timeline (visual + tabla, approve/reject), Billing (lista + pay), Login, Register, Settings
- Services: ApiClient (wrapper HTTP con Bearer token), AuthService, NotificationService (SignalR)
- Build 0 errores, warnings MudBlazor analyzer (26, existentes)

### CM Agent (cm-agent/ — Python mock)
- mock_agent.py: FastAPI standalone con 19 endpoints mock (sin IA)
- Dockerfile.mock (fastapi+uvicorn), docker-compose.yml independiente
- MockAgentClient C#: implementa IAgentClient con delay simulado 7s

### Tests
- 38/38 tests unitarios pasan (InMemoryDatabase, NullMailService)

### Próximos pasos
- Tasks 7.x: Stripe/pagos, dashboard facturación global
- Tasks 8.x: Roles y permisos
- Tasks 9.x: Docker Compose global, CI/CD

### Key Decisions para el próximo AI session
1. Auth: login por email sin password, JWT 30 días, sin refresh tokens v1
2. MockAgentClient reemplaza agente real cuando AgentBaseUrl no está configurado
3. InMemoryDatabase fallback si no hay PostgreSQL
4. PublicationEntity (frontend) + CommunityPublicationEntity (agente) coexisten
5. SignalR con JWT AccessToken, grupos por cliente
6. ApiClient wrapper en lugar de IHttpClientFactory en Blazor
7. MudBadge en vez de MudChip en tablas
8. visual+table toggle en Timeline
9. mock_agent.py independiente, no comparte código con agente real
10. 38 tests con InMemoryDatabase + NullMailService
