## Context

Actualmente el Community Manager agent y el Chatbot con IA coexisten en un mismo proyecto Python con un backend .NET compartido. El código del CM (`src/agent/community_manager/`) comparte tools, modelos y configuraciones con el chatbot. Esto hace que un deploy del CM requiera validar todo el proyecto, y cualquier cambio en el chatbot puede afectar al CM.

El CM es el producto prioritario y necesita una plataforma completa con frontend para que un gestor de comunidades pueda administrar múltiples clientes, cada uno con sus redes sociales, publicaciones programadas y facturación.

## Goals / Non-Goals

**Goals:**
- Renombrar `TestLangChain` → `chatbot-service/` y moverlo a su propio repositorio (aislamiento total)
- Crear `cm-platform/` como nuevo repositorio con: `cm-agent/` (worker Python), `cm-backend/` (API .NET), `cm-frontend/` (SPA React)
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
2. **Duplicación aceptable** de código de ruteo a LLMs, helpers y configuraciones. Ambos proyectos pueden tener código similar pero en entornos diferentes. No se crea una librería compartida.
3. **React + TypeScript** para el frontend del CM. Alternativa considerada: Angular — se descarta porque el equipo no lo conoce y React es más ágil para dashboards.
4. **API .NET 10** para `cm-backend/` — consistente con el backend actual del chatbot. Alternativa considerada: FastAPI (Python) — se descarta para evitar dos runtimes distintos.
5. **PostgreSQL** como base de datos única con esquema multitenant. Alternativa considerada: base de datos por cliente — se descarta por complejidad operativa.
6. **JWT + refresh tokens** para autenticación del gestor en el frontend del CM.
7. **Mercado Pago / Stripe** para facturación (depende del país del cliente). Se implementa como plugin intercambiable.

## Risks / Trade-offs

- [Ruptura del chatbot existente] → Mitigación: el chatbot se migra a `chatbot-service/` con su test suite completa. No se toca su lógica interna, solo se mueve a su propio repositorio.
- [Pérdida de cambios en CM durante migración] → Mitigación: se congela el desarrollo del CM en el monorepo durante la migración. Todos los cambios nuevos van directo a `cm-platform/`.
- [Migración de datos compleja] → Mitigación: migración en 3 fases (schema, datos de prueba, datos reales) con rollback en cada fase.
- [Curva de aprendizaje React] → Mitigación: usar Vite + shadcn/ui para componentes listos, enfocar en lógica de negocio.
- [Duplicación de código] → Trade-off aceptado. La duplicación de ruteo a endpoints de LLM y helpers es mínima y prefierible al acoplamiento.

## Migration Plan

**Fase 1 — Migración del chatbot (semana 1-2):**
1. Crear repositorio `chatbot-service/` y migrar todo el código del monorepo actual
2. Verificar que chatbot funciona independientemente
3. Congelar desarrollo de CM en monorepo

**Fase 2 — CM Platform setup (semanas 2-4):**
4. Crear repositorio `cm-platform/` con estructura inicial
5. Migrar agente Python del CM a `cm-platform/cm-agent/`
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
