## 0. Análisis de Código Compartido (Est: 1 día ⚡)

- [x] 0.1 Auditar el monorepo actual e identificar TODO el código/contratos compartidos entre chatbot y CM: `.env`, protocolo HTTP (requests/responses JSON), API key interna, lógica duplicada Python/C# (email wrapping, Pipedrive, scheduling, AI Foundry, modelos) (3h ⚡⚡)
- [x] 0.2 Para cada elemento compartido, determinar qué necesita el chatbot y qué necesita CM. Crear inventario por proyecto (2h ⚡)
- [x] 0.3 Extraer `.env` compartido en dos archivos: `chatbot-service/.env` con solo vars del chatbot, `cm-platform/.env` con solo vars del CM (1h ⚡)
- [x] 0.4 Extraer protocolo HTTP: `chatbot-service/` conserva `AgentClient.cs` (C# → Python) y elimina `DotNetClient`; `cm-platform/` conserva `DotNetClient` (Python → .NET) renombrado para su contexto (2h ⚡)
- [x] 0.5 Extraer lógica duplicada (email, Pipedrive, scheduling, AI Foundry, modelos): cada proyecto conserva **solo** las copias que realmente usa. No se copia nada que no se necesite (2h ⚡)

## 1. Chatbot — Migración a Repositorio Propio (Est: 2-3 días ⚡⚡)

- [x] 1.1 Crear estructura local `chatbot-service/` con directorios backend, frontend, .github, docs (30min ⚡)
- [x] 1.2 Copiar a `chatbot-service/` **solo** el código que corresponde al chatbot según el inventario de la tarea 0: backend .NET, frontend Angular, configs de chatbot, tests. Excluir `src/agent/community_manager/`, `graphify-out/`, y cualquier archivo identificado como solo-CM (1h ⚡)
- [x] 1.3 Renombrar solución: `web-novit-ai.sln` → `chatbot-service.sln`. Namespaces de .NET se conservan como `Novit.Web.Api` (identidad del chatbot) (2h ⚡)
- [ ] 1.4 El usuario moverá `chatbot-service/` a su propio repo y verificará compilación (2h ⚡)
- [x] 1.5 Limpiar referencias al CM en `chatbot-service/`: remover `CommunityController.cs`, `InternalController.cs`, `CommunityReviewService.cs`, `CommunityPublicationPublisher.cs`, `CommunityApprovalBackgroundService.cs`, `CommunityDraftModels.cs`, `CommunityPublicationEntity.cs`, migraciones CM, métodos community de `AgentClient.cs`. Aplicar `.env` extraído en 0.3 (2h ⚡)
- [x] 1.6 Confirmar que `chatbot-service` NO importa nada del CM (grep verifica 0 referencias a Community* fuera de docs/MIGRATION_PLAN.md) (1h ⚡)

## 2. CM Platform — Repositorio y Estructura (Est: 2 días ⚡)

- [x] 2.1 Crear estructura local `cm-platform/` con `cm-backend/CmPlatform.Api`, `cm-backend/CmPlatform.Api.Tests`, `cm-agent/src/community_manager`, `cm-agent/tests`, `cm-frontend`, `.github/workflows` (30min ⚡)
- [x] 2.2 Copiar a `cm-platform/` **solo** el código del CM según inventario de tarea 0: agente Python (`src/agent/community_manager/` → `cm-agent/src/community_manager/`), pyproject.toml, Dockerfile, tests, más `.env` de 0.3 (2h ⚡)
- [x] 2.3 Ajustar Dockerfile de cm-agent (path de copia `src/`) y crear `docker-compose.yml`, `.gitignore`. Los imports `community_manager.*` funcionan porque el package conserva el mismo nombre (2h ⚡)

## 3. CM Backend — API REST .NET (Est: 5-6 días ⚡⚡⚡)

- [x] 3.1 Crear proyecto `cm-backend/` con .NET 10, WebAPI, EF Core + PostgreSQL (2h ⚡)
- [x] 3.2 Diseñar y crear migraciones iniciales: tablas `Clients`, `SocialAccounts`, `Subscriptions`, `Publications`, `Invoices` (4h ⚡⚡)
- [x] 3.3 Implementar endpoints CRUD de clientes (`/api/clients`) (3h ⚡⚡)
- [x] 3.4 Implementar endpoints de redes sociales vinculadas (`/api/clients/{id}/social-accounts`) (2h ⚡)
- [x] 3.5 Implementar endpoints de timeline/publicaciones (`/api/publications`) (3h ⚡⚡)
- [x] 3.6 Implementar endpoints de facturación (`/api/billing/invoices`) (3h ⚡⚡)
- [x] 3.7 Implementar endpoints de autenticación (`/api/auth/login`, `/api/auth/register`, `/api/auth/me`) (3h ⚡⚡)
- [x] 3.8 Agregar middleware de JWT, roles y autorización por endpoint (2h ⚡)
- [x] 3.9 Integrar `cm-backend/` con el agente CM (InternalController + MockAgentClient) (4h ⚡⚡)

## 4. CM Frontend — Dashboard Blazor WebAssembly (Est: 6-8 días ⚡⚡⚡)

- [x] 4.1 Inicializar proyecto Blazor WebAssembly con .NET 10, MudBlazor 9.5 para componentes UI (1h ⚡)
- [x] 4.2 Implementar layout base: sidebar navigation, header con MudLayout (2h ⚡)
- [x] 4.3 Implementar pantalla de login con JWT + localStorage (3h ⚡⚡)
- [x] 4.4 Implementar dashboard principal con tarjetas resumen (clientes, pubs hoy, ingresos, alertas) (3h ⚡⚡)
- [x] 4.5 Implementar página de lista de clientes con búsqueda y filtros (3h ⚡⚡)
- [x] 4.6 Implementar página de detalle de cliente: datos, redes sociales vinculadas, timeline, facturas (4h ⚡⚡)
- [x] 4.7 Implementar formulario de creación/edición de cliente con Blazor EditForm + validación (2h ⚡)
- [x] 4.8 Implementar vista de timeline visual con MudDatePicker + filtros + agrupación por mes + toggle tabla (4h ⚡⚡)
- [x] 4.9 Implementar sección de facturación: lista de facturas, pay (3h ⚡⚡)
- [x] 4.10 Implementar sección de configuración: perfil del gestor, plan de suscripción, notificaciones (2h ⚡)

## 5. CM Agent — Mock Independiente (Est: 2-3 días ⚡⚡)

- [x] 5.1 Configurar `cm-agent/` con su propio `Dockerfile.mock` y `docker-compose.yml` (1h ⚡)
- [x] 5.2 Crear `mock_agent.py` — servidor FastAPI standalone con 19 endpoints mock sin IA (3h ⚡⚡)
- [x] 5.3 Configurar variables de entorno mock (`.env.mock`) y `requirements-mock.txt` (1h ⚡)
- [x] 5.4 Implementar `MockAgentClient` en C# para desarrollo local sin agente real (3h ⚡⚡)

## 6. Integración CM: Agente ↔ Backend ↔ Frontend (Est: 3-4 días ⚡⚡)

- [x] 6.1 Notificar publicaciones del agente a `cm-backend` via `POST /api/internal/publications` + `PUT /api/internal/publications/{id}/status` (3h ⚡⚡)
- [x] 6.2 Botones approve/reject en frontend (Timeline + ClientDetail) llamando a `PUT /api/publications/{id}/status` (2h ⚡)
- [x] 6.3 SignalR para notificaciones en tiempo real al frontend (`NotificationHub` + `NotificationService`) (3h ⚡⚡)
- [x] 6.4 Prueba de compilación: 0 errores backend/frontend, 38/38 tests pasan (2h ⚡)

## 7. Sistema de Facturación (Est: 3-4 días ⚡⚡)

- [ ] 7.1 Implementar lógica de ciclo de facturación mensual en `cm-backend/` (2h ⚡)
- [ ] 7.2 Integrar gateway de pago (Stripe o Mercado Pago) (4h ⚡⚡)
- [ ] 7.3 Implementar notificaciones de vencimiento (email + in-app) (2h ⚡)
- [ ] 7.4 Implementar dashboard de facturación global (ingresos totales, clientes morosos, proyección) (3h ⚡⚡)

## 8. Autenticación y Seguridad (Est: 2 días ⚡)

- [ ] 8.1 Implementar registro de gestores (admin crea usuarios) (1h ⚡)
- [ ] 8.2 Implementar roles y permisos en frontend (rutas protegidas por rol) (2h ⚡)
- [ ] 8.3 Implementar recuperación de contraseña vía email (2h ⚡)
- [ ] 8.4 Agregar rate limiting y protección de endpoints críticos (1h ⚡)

## 9. Puesta en Marcha (Est: 3-4 días ⚡⚡⚡)

- [ ] 9.1 Crear script de migración de datos del monorepo antiguo a `cm-backend/` (3h ⚡⚡)
- [ ] 9.2 Configurar Docker Compose global de `cm-platform/` (cm-backend, cm-agent, cm-frontend, postgres, redis) (2h ⚡)
- [ ] 9.3 Configurar CI/CD para `chatbot-service/` y `cm-platform/` (GitHub Actions, dos pipelines separados) (3h ⚡⚡)
- [ ] 9.4 Ejecutar migración de datos de prueba y validar integridad (3h ⚡⚡)
- [ ] 9.5 Desplegar `chatbot-service/` en su propio entorno y verificar funcionamiento (2h ⚡)
- [ ] 9.6 Desplegar `cm-platform/` en staging, validar flujo completo, corregir issues (4h ⚡⚡)
- [ ] 9.7 Desplegar `cm-platform/` en producción y monitorear (2h ⚡)
- [ ] 9.8 Desactivar funcionalidades del CM en el monorepo antiguo (1h ⚡)

## 10. Testing Integral (Est: 3-4 días — paralelo)

- [ ] 10.1 Tests del chatbot migrado: verificar que todo funciona igual que antes (2h ⚡)
- [ ] 10.2 Tests unitarios e integración para `cm-backend` (API endpoints + DB) (4h ⚡⚡)
- [ ] 10.3 Tests de componentes frontend (bUnit) (3h ⚡⚡)
- [ ] 10.4 Tests end-to-end del flujo completo CM: login → crear cliente → configurar redes → generar contenido → publicar → facturar (4h ⚡⚡⚡)
- [ ] 10.5 Tests de seguridad: autenticación, roles, rate limiting (2h ⚡)
- [ ] 10.6 Verificar que cambios en `chatbot-service/` NO afectan a `cm-platform/` y viceversa (1h ⚡)
