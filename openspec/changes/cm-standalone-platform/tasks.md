## 1. Chatbot — Migración a Repositorio Propio (Est: 2-3 días ⚡⚡)

- [ ] 1.1 Crear repositorio `chatbot-service/` en GitHub/GitLab y clonarlo localmente (30min ⚡)
- [ ] 1.2 Copiar todo el código de `TestLangChain` (excepto `src/agent/community_manager/` y `graphify-out/`) a `chatbot-service/` (1h ⚡)
- [ ] 1.3 Renombrar proyecto: archivos de solución, csproj, carpetas, namespaces de .NET (2h ⚡)
- [ ] 1.4 Verificar que el chatbot compila, los tests pasan y `docker-compose up` funciona en el nuevo repo (2h ⚡)
- [ ] 1.5 Eliminar referencias al CM del chatbot: remover `src/agent/community_manager/`, limpiar imports y configs (2h ⚡)
- [ ] 1.6 Confirmar que chatbot-service NO importa nada del CM (revisión manual + grep) (1h ⚡)

## 2. CM Platform — Repositorio y Estructura (Est: 2 días ⚡)

- [ ] 2.1 Crear repositorio `cm-platform/` con estructura: `cm-backend/`, `cm-agent/`, `cm-frontend/` (30min ⚡)
- [ ] 2.2 Copiar código del CM agent (`src/agent/community_manager/`) a `cm-platform/cm-agent/` con su propio `pyproject.toml` y dependencias (2h ⚡)
- [ ] 2.3 Verificar que `cm-agent/` compila e importa todo correctamente (2h ⚡)

## 3. CM Backend — API REST .NET (Est: 5-6 días ⚡⚡⚡)

- [ ] 3.1 Crear proyecto `cm-backend/` con .NET 10, WebAPI, EF Core + PostgreSQL (2h ⚡)
- [ ] 3.2 Diseñar y crear migraciones iniciales: tablas `Clients`, `SocialAccounts`, `Subscriptions`, `Publications`, `Invoices` (4h ⚡⚡)
- [ ] 3.3 Implementar endpoints CRUD de clientes (`/api/clients`) (3h ⚡⚡)
- [ ] 3.4 Implementar endpoints de redes sociales vinculadas (`/api/clients/{id}/social-accounts`) (2h ⚡)
- [ ] 3.5 Implementar endpoints de timeline/publicaciones (`/api/clients/{id}/publications`) (3h ⚡⚡)
- [ ] 3.6 Implementar endpoints de facturación (`/api/clients/{id}/invoices`, `/api/billing`) (3h ⚡⚡)
- [ ] 3.7 Implementar endpoints de autenticación (`/api/auth/login`, `/api/auth/refresh`, `/api/auth/register`) (3h ⚡⚡)
- [ ] 3.8 Agregar middleware de JWT, roles y autorización por endpoint (2h ⚡)
- [ ] 3.9 Integrar `cm-backend/` con el agente CM (comunicación vía HTTP) (4h ⚡⚡)

## 4. CM Frontend — Dashboard React (Est: 6-8 días ⚡⚡⚡)

- [ ] 4.1 Inicializar proyecto con Vite + React + TypeScript + shadcn/ui + Tailwind (1h ⚡)
- [ ] 4.2 Implementar layout base: sidebar navigation, header, breadcrumbs (2h ⚡)
- [ ] 4.3 Implementar pantalla de login con JWT (3h ⚡⚡)
- [ ] 4.4 Implementar dashboard principal con tarjetas resumen (clientes, pubs hoy, ingresos, alertas) (3h ⚡⚡)
- [ ] 4.5 Implementar página de lista de clientes con búsqueda y filtros (3h ⚡⚡)
- [ ] 4.6 Implementar página de detalle de cliente: datos, redes sociales vinculadas, timeline, facturas (4h ⚡⚡)
- [ ] 4.7 Implementar formulario de creación/edición de cliente (2h ⚡)
- [ ] 4.8 Implementar vista de timeline visual con componentes de calendario/chrono (4h ⚡⚡)
- [ ] 4.9 Implementar sección de facturación: lista de facturas, crear factura, estado de pagos (3h ⚡⚡)
- [ ] 4.10 Implementar sección de configuración: perfil del gestor, plan de suscripción, notificaciones (2h ⚡)

## 5. CM Agent — Worker Independiente (Est: 2-3 días ⚡⚡)

- [ ] 5.1 Configurar `cm-agent/` con su propio `Dockerfile` y `docker-compose` (1h ⚡)
- [ ] 5.2 Duplicar en `cm-agent/` el código necesario de ruteo a LLMs (Azure OpenAI, Gemini) desde cero (sin shared-core) (3h ⚡⚡)
- [ ] 5.3 Configurar variables de entorno y secrets para el agente CM (1h ⚡)
- [ ] 5.4 Implementar comunicación HTTP entre `cm-agent/` y `cm-backend/` para reportar estado de publicaciones (3h ⚡⚡)

## 6. Integración CM: Agente ↔ Backend ↔ Frontend (Est: 3-4 días ⚡⚡)

- [ ] 6.1 Cuando el agente completa una publicación, notificar a `cm-backend` para actualizar el timeline del cliente (3h ⚡⚡)
- [ ] 6.2 Cuando el gestor aprueba/rechaza contenido desde el frontend, enviar comando al agente vía `cm-backend` (2h ⚡)
- [ ] 6.3 Implementar WebSocket/SignalR para notificaciones en tiempo real al frontend (3h ⚡⚡)
- [ ] 6.4 Probar flujo completo: login → ver clientes → seleccionar cliente → ver timeline → aprobar publicación (2h ⚡)

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
- [ ] 10.3 Tests de componentes frontend (React Testing Library) (3h ⚡⚡)
- [ ] 10.4 Tests end-to-end del flujo completo CM: login → crear cliente → configurar redes → generar contenido → publicar → facturar (4h ⚡⚡⚡)
- [ ] 10.5 Tests de seguridad: autenticación, roles, rate limiting (2h ⚡)
- [ ] 10.6 Verificar que cambios en `chatbot-service/` NO afectan a `cm-platform/` y viceversa (1h ⚡)
