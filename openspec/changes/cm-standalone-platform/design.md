## Context

Actualmente el Community Manager agent y el Chatbot con IA coexisten en un mismo proyecto Python con un backend .NET compartido. El código del CM (`src/agent/community_manager/`) comparte tools, modelos y configuraciones con el chatbot. Esto hace que un deploy del CM requiera validar todo el proyecto, y cualquier cambio en el chatbot puede afectar al CM.

El CM es el producto prioritario y necesita una plataforma completa con frontend para que un gestor de comunidades pueda administrar múltiples clientes, cada uno con sus redes sociales, publicaciones programadas y facturación.

## Goals / Non-Goals

**Goals:**
- Renombrar `TestLangChain` → `chatbot-service/` y moverlo a su propio repositorio (aislamiento total)
- Crear `cm-platform/` como nuevo repositorio con: `cm-agent/` (worker Python), `cm-backend/` (API .NET), `cm-frontend/` (Blazor WebAssembly)
- NO existe código compartido entre repositorios — cada uno tiene su propia copia de lo que necesita
- Crear `cm-backend/` con endpoints para clientes, redes sociales, timeline y facturación
- Crear `cm-frontend/` con dashboard del gestor, vista de clientes, timeline, aprobaciones y facturación
- Migrar la base de datos actual al esquema multitenant del CM

**Non-Goals:**
- No se modifica el chatbot existente (se migra tal cual a su propio repositorio)
- No se implementa un frontend para el chatbot
- No se migran datos de producción hasta la fase 3 del migration plan

## Decisions

1. **Repositorios independientes** sobre monorepo — `chatbot-service/` y `cm-platform/` son repos separados, sin submódulos, sin dependencias compartidas. Cada uno tiene su propio `package.json`, `requirements.txt`, `Dockerfile` y CI/CD.
2. **Extracción de código compartido por proyecto** — No existe código fuente compartido entre Python y C#, pero sí contratos compartidos (`.env`, protocolo HTTP, API key). En lugar de duplicar ciegamente, se extrae un archivo por proyecto conteniendo **exclusivamente lo que ese proyecto necesita**:

   ```
   Compartido actual                     chatbot-service/           cm-platform/
   ─────────────                         ──────────────            ────────────
   .env (todo)                           .env (solo chatbot)       .env (solo CM)
   dotnet_client.py (Python→NET)         —                         cm-agent/... (copia)
   AgentClient.cs (NET→Python)           AgentClient.cs (copia)    —
   RequireInternalKeyAttribute.cs        ──────────                 ──────────
   ────────── quedan en cada uno         filtro auth (copia)        filtro auth (copia)
   Lógica duplicada (email, Pipedrive,   cada proyecto conserva     cada proyecto conserva
   scheduling, AI Foundry, modelos)      solo las copias que usa   solo las copias que usa
   ```
   
   No se crea shared-core. Cada proyecto tiene su propia copia **exacta de lo que necesita**, ni más ni menos.
3. **Blazor WebAssembly** para el frontend del CM. Alternativa considerada: React — se descarta para mantener el stack unificado (.NET en backend y frontend), compartir tipos y reducir la cantidad de lenguajes en el proyecto.
4. **API .NET 10** para `cm-backend/` — consistente con el backend actual del chatbot. Alternativa considerada: FastAPI (Python) — se descarta para evitar dos runtimes distintos.
5. **PostgreSQL** como base de datos única con esquema multitenant. Alternativa considerada: base de datos por cliente — se descarta por complejidad operativa.
6. **JWT + refresh tokens** para autenticación del gestor en el frontend del CM.
7. **Mercado Pago / Stripe** para facturación (depende del país del cliente). Se implementa como plugin intercambiable.

## Risks / Trade-offs

- [Ruptura del chatbot existente] → Mitigación: el chatbot se migra a `chatbot-service/` con su test suite completa. No se toca su lógica interna, solo se mueve a su propio repositorio.
- [Pérdida de cambios en CM durante migración] → Mitigación: se congela el desarrollo del CM en el monorepo durante la migración. Todos los cambios nuevos van directo a `cm-platform/`.
- [Migración de datos compleja] → Mitigación: migración en 3 fases (schema, datos de prueba, datos reales) con rollback en cada fase.
- [Curva de aprendizaje Blazor] → Mitigación: el equipo ya conoce C# y .NET; solo deben aprender el modelo de componentes de Blazor (Razor). Usar MudBlazor o Radzen para componentes UI listos.
- [Código compartido mal particionado] → Mitigación: la tarea 0 audita todo el código compartido antes de mover nada. Cada proyecto recibe solo lo que usa. Si algo se omite, se agrega después sin riesgo de acoplamiento.

## Migration Plan

**Fase 0 — Análisis de código compartido (semana 1):**
1. Auditar el monorepo e inventariar todo el código/contratos compartidos
2. Extraer por proyecto solo lo que cada uno necesita (`.env`, HTTP bridge, API key, lógica duplicada)

**Fase 1 — Migración del chatbot (semanas 1-2):**
3. Crear repositorio `chatbot-service/` y migrar solo el código del chatbot según inventario de Fase 0
4. Verificar que chatbot funciona independientemente
5. Congelar desarrollo de CM en monorepo

**Fase 2 — CM Platform setup (semanas 2-4):**
6. Crear repositorio `cm-platform/` con estructura inicial
7. Migrar a `cm-platform/` solo el código del CM según inventario de Fase 0
6. Crear `cm-backend/` con API de clientes y autenticación
7. Crear `cm-frontend/` con dashboard y gestión de clientes

**Fase 3 — Timeline + Facturación (semanas 5-8):**
8. Implementar timeline de publicaciones
9. Implementar módulo de facturación
10. Integrar frontend con backend y agente

**Fase 4 — Go Live (semanas 9-10):**
11. Migrar datos de producción al nuevo sistema
12. Desactivar funcionalidades del CM en chatbot-service/
13. Monitorear y corregir

## Open Questions

- ¿Stripe o Mercado Pago para facturación (clientes LATAM vs global)?
- ¿El frontend debe ser mobile-first o desktop-first (el gestor trabaja desde PC)?
- ¿Chatbot-service necesita endpoint propio o puede consumir directo el LLM?
