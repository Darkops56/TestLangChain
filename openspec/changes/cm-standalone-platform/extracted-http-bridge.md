# Extracción del Protocolo HTTP Bridge

## Origen: AgentClient.cs (actual, en monorepo)
**Ruta:** `src/backend/Novit.Web.Api/Services/AgentClient.cs`

| Método | chatbot-service | cm-platform | Acción |
|---|---|---|---|
| `ForwardWebhookMessageAsync` | ✓ | ✗ | Se queda en chatbot (webhook Meta/IG → agente) |
| `GenerateNewsletterAsync` | ✓ | ✗ | Se queda en chatbot |
| `ReviseNewsletterAsync` | ✓ | ✗ | Se queda en chatbot |
| `GenerateReplyAsync` | ✓ | ✗ | Se queda en chatbot |
| `GenerateClosingAsync` | ✓ | ✗ | Se queda en chatbot |
| `WrapEmailAsync` | ✓ | ✗ | Se queda en chatbot |
| `GetStatusAsync` | ✓ | ✗ | Se queda en chatbot |
| `ReviseCommunityDraftAsync` | ✗ | ✓→cm-backend\AgentClient.cs | CM: renovar para su agente |
| `GenerateCommunityDraftAsync` | ✗ | ✓→cm-backend\AgentClient.cs | CM: renovar para su agente |
| `KickCommunityDraftAsync` | ✗ | ✓→cm-backend\AgentClient.cs | CM |
| `GetCommunityDraftJobStatusAsync` | ✗ | ✓→cm-backend\AgentClient.cs | CM |
| `DeleteCommunityDraftMediaAsync` | ✗ | ✓→cm-backend\AgentClient.cs | CM |
| `MaterializeCommunityDraftMediaAsync` | ✗ | ✓→cm-backend\AgentClient.cs | CM |
| `PublishCommunityDraftAsync` | ✗ | ✓→cm-backend\AgentClient.cs | CM |
| `PublishCommunityNowAsync` | ✗ | ✓→cm-backend\AgentClient.cs | CM |

**chatbot-service:** Conserva solo métodos de nurturing. Elimina:
- `ReviseCommunityDraftAsync`, `GenerateCommunityDraftAsync`, `KickCommunityDraftAsync`
- `GetCommunityDraftJobStatusAsync`, `DeleteCommunityDraftMediaAsync`
- `MaterializeCommunityDraftMediaAsync`, `PublishCommunityDraftAsync`
- `PublishCommunityNowAsync`
- Tipos `CommunityDraftPayload`, `AgentCommunityDraftKickResult`, `AgentCommunityDraftJobStatusResult`, `AgentCommunityPublishResult`

**cm-platform:** Crea cm-backend\Services\AgentClient.cs con SOLO métodos de community draft (para cm-backend → cm-agent). El namespace cambia a `CmPlatform.Services`.

## Origen: DotNetClient.py (actual, en monorepo)
**Ruta:** `src/agent/community_manager/tools/dotnet_client.py`

| Método | cm-platform | chatbot-service | Acción |
|---|---|---|---|
| `get_nurturing_recipients` | ✓ | ✗ | Se queda en cm-agent |
| `get_newsletter` / `save_newsletter` / `mark_newsletter_sent` | ✓ | ✗ | Se queda en cm-agent |
| `get_previous_conclusions` | ✓ | ✗ | Se queda en cm-agent |
| `get_community_reviewer_memory` | ✓ | ✗ | Se queda en cm-agent |
| `get_recent_community_publication_history` | ✓ | ✗ | Se queda en cm-agent |
| `get_recent_published_image_references` | ✓ | ✗ | Se queda en cm-agent |
| `create_community_draft` | ✓ | ✗ | Se queda en cm-agent |
| `generate_dm_reply` | ✓ | ✗ | Se queda en cm-agent |
| `send_email` / `send_reply` / `get_unanswered_replies` | ✓ | ✗ | Se queda en cm-agent |
| `get_deal_notes` / `add_deal_note` | ✓ | ✗ | Se queda en cm-agent |

**cm-platform:** Conserva todo, renombrado como `cm_agent_backend_client.py`. Cambia import de `community_manager.config.settings` → `cm_agent.config.settings`, update de `community_manager.models.schemas` → `cm_agent.models.schemas`.

**chatbot-service:** No usa DotNetClient — se elimina.

## Origen: RequireInternalKeyAttribute.cs
**Ruta:** `src/backend/Novit.Web.Api/Filters/RequireInternalKeyAttribute.cs`

Ambos proyectos necesitan auth interna. Copia idéntica en cada uno:
- `chatbot-service/.../Filters/RequireInternalKeyAttribute.cs`
- `cm-platform/cm-backend/.../Filters/RequireInternalKeyAttribute.cs`
