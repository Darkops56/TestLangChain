# CM Platform — AI Prompt Pack

Este directorio contiene el **proposal, diseño, specs y progreso** del proyecto de separación del monorepo TestLangChain en dos proyectos independientes (chatbot-service + cm-platform), con frontend Blazor + MudBlazor.

## Contenido

| Archivo | Propósito |
|---------|-----------|
| `proposal.md` | Por qué y qué cambiar (visión general) |
| `design.md` | Decisiones arquitectónicas, contexto, sistema + decisiones de implementación del chat |
| `tasks.md` | Plan de ejecución detallado con checkboxes y progreso marcado |
| `inventario-compartido.md` | Inventario de código compartido entre chatbot y CM |
| `extracted-http-bridge.md` | Protocolo HTTP entre agente Python y backend .NET |
| `extracted-logica-duplicada.md` | Lógica duplicada Python/C# por proyecto |
| `extracted-env-chatbot.txt` | Variables de entorno del chatbot |
| `extracted-env-cm-platform.txt` | Variables de entorno de CM Platform |
| `specs/` | 8 specs con requisitos formales (formato Gherkin) |

## Cómo usar con otra IA

Entrega estos archivos como contexto a la IA. El flujo recomendado:

1. La IA lee `proposal.md` para entender el QUÉ y POR QUÉ
2. Lee `design.md` para entender el CÓMO (arquitectura + decisiones de implementación)
3. Usa `tasks.md` como hoja de ruta con progreso marcado
4. Consulta `specs/*/spec.md` para requisitos detallados de cada capability
5. Usa los `extracted-*` para entender la separación de código compartido

## Progreso actual

Tareas completadas hasta el momento:
- **Sección 0** (Análisis código compartido): 5/5 ✓
- **Sección 1** (Chatbot migración): 5/6 ✓ (pendiente 1.4: usuario mueve repo)
- **Sección 2** (CM estructura): 3/3 ✓
- **Sección 3** (CM Backend API): 9/9 ✓ — .NET 10, EF Core, JWT, PostgreSQL/InMemory, controllers CRUD, InternalController, MockAgentClient
- **Sección 4** (CM Frontend Blazor): 10/10 ✓ — MudBlazor 9.5, Dashboard, Clients CRUD, Timeline (visual+tabla), Billing, Settings, Auth
- **Sección 5** (CM Agent mock): 4/4 ✓ — mock_agent.py, Dockerfile.mock, MockAgentClient C#
- **Sección 6** (Integración): 4/4 ✓ — Internal publications endpoint, Approve/reject UI, SignalR real-time, tests pasan

## Elecciones vitales (Key Decisions)

Decisiones concretas que surgieron durante el desarrollo y que una IA debe conocer antes de continuar:

1. **Auth simplificada**: login por email sin password devuelve JWT de 30 días. Sin refresh tokens en v1.
2. **MockAgentClient**: cuando `AgentBaseUrl` no está configurado, se usa un mock C# (sin IA) con delay simulado de 7s.
3. **InMemoryDatabase**: fallback automático si no hay PostgreSQL configurado — ideal para desarrollo local.
4. **Dos entidades de publicación coexisten**: `PublicationEntity` (frontend) y `CommunityPublicationEntity` (agente). La integración 6.1 debe crear ambas.
5. **SignalR** vía `NotificationHub` con JWT como AccessToken. Grupos por cliente (`client-{id}`).
6. **ApiClient** wrapper en lugar de `IHttpClientFactory` en Blazor WASM (evita dependencia extra).
7. **MudBadge** en vez de `MudChip` en tablas (evita problemas de genéricos en Razor).
8. **Visual + tabla** en Timeline: toggle con MudIconButton entre vista de calendario y tabla.
9. **mock_agent.py independiente**: no comparte código con el agente real. Dockerfile liviano.
10. **38 tests unitarios** con InMemoryDatabase + NullMailService. Todos pasan.

## Formato

Usa el schema **spec-driven** de OpenSpec:
- `proposal.md` → visión y alcance
- `design.md` → arquitectura y decisiones
- `specs/<capability>/spec.md` → requisitos en estilo "SHALL" con escenarios Given/When/Then
- `tasks.md` → tareas con estimaciones y checkboxes
