# Plan de Migración .NET → Python/FastAPI

## Contexto

El sistema actual tiene una arquitectura dual:
- **Backend .NET** (C#, ASP.NET Core): API principal, web chat, voice, Pipedrive, Cal.com, email, DB
- **Python Agent** (FastAPI + LangGraph): Newsletter AI, Community content AI, Reply AI

El objetivo es migrar incrementalmente el .NET backend a Python/FastAPI para eliminar la dependencia de .NET y tener un solo stack tecnológico.

## Arquitectura Actual

```
Angular Frontend → Caddy → .NET Backend (API) → Python Agent (AI)
                              ↓
                    PostgreSQL, Pipedrive, Cal.com, Azure AI, Email
```

## Arquitectura Objetivo

```
Angular Frontend → Caddy → Python/FastAPI (API + AI)
                              ↓
                    PostgreSQL, Pipedrive, Cal.com, Azure AI, Email
```

## Fases de Migración

### Fase 1: Newsletter Endpoints ✅ (En progreso)
**Objetivo:** Migrar los endpoints de newsletter de .NET a FastAPI

**Endpoints a migrar:**
- `POST /api/nurturing/test-generate` → Preview generación
- `GET /api/nurturing/test-contacts` → Listar contactos Pipedrive
- `GET /api/nurturing/test-personalization` → Preview personalización
- `POST /api/nurturing/trigger-review` → Generar + enviar a revisores
- `POST /api/nurturing/trigger-check-feedback` → Chequear feedback revisores
- `POST /api/nurturing/trigger-send` → Enviar newsletter a leads
- `GET /api/nurturing/trigger-send/status` → Estado del envío
- `POST /api/nurturing/trigger-check-replies` → Chequear y responder replies

**Servicios a migrar:**
- `NurturingMailService` → IMAP/SMTP
- `PipedriveService` (operaciones de nurturing)
- `NurturingContentRenderer` → Email HTML template
- `NurturingWorkflowSupport` → Helpers de workflow
- `NurturingSchedule` → Lógica de ciclos

**Dependencias:**
- Conexión a PostgreSQL (nurturing_emails table)
- Pipedrive API (contacts, deals, notes)
- IMAP/SMTP (MailKit → aiosmtplib)
- Python Agent (ya existe)

**Riesgos:**
- IMAP/SMTP puede tener diferencias de comportamiento
- Pipedrive pagination necesita verificación
- Background send necesita asyncio tasks

---

### Fase 2: Community Endpoints
**Objetivo:** Migrar endpoints de community content

**Endpoints a migrar:**
- `POST /api/community/trigger-publish` → Trigger draft generation
- `POST /api/community/trigger-publish-on-demand` → On-demand draft
- `GET /api/community/trigger-publish/status/{jobId}` → Poll job status
- `POST /api/community/force-publish/{draftId}` → Force publish

**Servicios a migrar:**
- `CommunityReviewService`
- `CommunityPublicationPublisher`
- `CommunityApprovalBackgroundService`

---

### Fase 3: Database Operations
**Objetivo:** Migrar EF Core a SQLAlchemy

**Tablas a migrar:**
- `conversations` → Conversaciones de chat
- `messages` → Mensajes de chat
- `leads` → Leads de formulario de contacto
- `rate_limits` → Rate limiting
- `nurturing_emails` → Newsletters
- `community_publications` → Publicaciones community

**Consideraciones:**
- JSONB columns (widgets, hashtags_json, strategy_json, etc.)
- Cascade deletes (Conversation → Messages)
- Auto-migration on startup

---

### Fase 4: Chat + Voice
**Objetivo:** Migrar web chat y voice services

**Endpoints a migrar:**
- `POST /api/chat/conversations` → Crear conversación
- `GET /api/chat/conversations/{id}` → Obtener conversación
- `DELETE /api/chat/conversations/{id}` → Eliminar conversación
- `POST /api/chat/conversations/{id}/messages` → Enviar mensaje
- `POST /api/voice/transcribe` → STT
- `POST /api/voice/synthesize` → TTS streaming
- `GET /api/voice/token` → Token Azure Speech

**Servicios a migrar:**
- `AzureAIChatService` → Azure OpenAI completions (streaming + tool calling)
- `AzureSpeechService` → STT + TTS
- `ChatToolDefinitions` → Function calling tools
- `ChatToolHandler` → Tool execution

**Tecnologías:**
- SignalR → FastAPI WebSockets o SSE
- Azure OpenAI streaming → httpx streaming
- Azure Speech streaming → httpx streaming

**Riesgos:**
- SignalR streaming es complejo de replicar
- Function calling / tool use necesita implementación cuidadosa
- Audio streaming requiere manejo de buffers

---

### Fase 5: Eliminar .NET
**Objetivo:** Eliminar completamente el backend .NET

**Pasos:**
1. Verificar que todos los endpoints funcionan en FastAPI
2. Actualizar Caddyfile para routing a FastAPI
3. Eliminar docker-compose service de .NET
4. Eliminar código .NET del repositorio
5. Actualizar CI/CD pipeline

---

## Dependencias Externas

| Servicio | Uso | Python Equivalent |
|----------|-----|-------------------|
| Azure AI Foundry | Web chatbot AI | `openai` o `httpx` |
| Azure Speech | STT + TTS | `httpx` |
| Pipedrive | CRM | `httpx` |
| Cal.com | Scheduling | `httpx` |
| Meta Webhooks | Instagram/Facebook | `httpx` + HMAC |
| IMAP/SMTP | Email | `aiosmtplib` + `imaplib2` |
| PostgreSQL | Database | `sqlalchemy` + `asyncpg` |
| Google OAuth2 | Google Docs/Drive | `google-auth` |

---

## Seguridad

| Mecanismo | .NET | Python Equivalent |
|-----------|------|-------------------|
| API Key (`X-Api-Key`) | `RequireApiKeyAttribute` | FastAPI Dependency |
| Internal Key (`X-Internal-Key`) | `RequireInternalKeyAttribute` | FastAPI Dependency |
| IP Whitelist | `AdminApiAllowedIps` | FastAPI Dependency |
| Meta HMAC-SHA256 | `CryptographicOperations.FixedTimeEquals` | `hmac.compare_digest` |
| Rate Limiting | PostgreSQL + in-memory | PostgreSQL + in-memory |

---

## Testing Strategy

1. **Unit tests:** Cada servicio migrado tiene tests
2. **Integration tests:** Endpoints con DB real
3. **E2E tests:** Flujo completo newsletter, chat, voice
4. **Shadow mode:** Ejecutar .NET y FastAPI en paralelo, comparar respuestas
5. **Gradual rollout:** Migrar un endpoint a la vez

---

## Timeline Estimado

| Fase | Duración | Dependencias |
|------|----------|--------------|
| Fase 1: Newsletter | 1-2 días | Ninguna |
| Fase 2: Community | 1-2 días | Fase 1 |
| Fase 3: Database | 2-3 días | Fase 2 |
| Fase 4: Chat + Voice | 3-5 días | Fase 3 |
| Fase 5: Eliminar .NET | 1 día | Fase 4 |
| **Total** | **8-13 días** | |

---

## Estado Actual

- [x] Análisis completo del .NET backend
- [x] Plan de migración documentado
- [ ] Fase 1: Newsletter endpoints (en progreso)
- [ ] Fase 2: Community endpoints
- [ ] Fase 3: Database operations
- [ ] Fase 4: Chat + Voice
- [ ] Fase 5: Eliminar .NET
