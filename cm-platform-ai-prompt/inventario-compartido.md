## Inventario de Código Compartido — Separación chatbot-service / cm-platform

### 1. `.env` — Variables de entorno

| Variable | chatbot-service | cm-platform | Notas |
|---|---|---|---|
| `AIFoundryDeployment`, `AIFoundryKey` | ✓ | ✓ | Ambos llaman a Azure AI Foundry |
| `Nurturing__*` | ✓ | ✗ | Solo chatbot (nurturing flow) |
| `PipedriveKey`, `PipedriveBaseUrl` | ✓ | ✗ | Solo chatbot (CRM) |
| `Google__*` | ✓ | ✗ | Solo chatbot (Google Docs/Drive) |
| `AzureAISpeech*`, `STTUrl` | ✓ | ✗ | Solo chatbot (speech) |
| `INTERNAL_API_KEY` | ✓ | ✓ | Autenticación interna HTTP |
| `ConnectionStrings__Default` | ✓ | ✓ | DB connection (cada uno su propia DB) |
| `CM__*` | ✗ | ✓ | Solo CM (config del gestor) |

### 2. Protocolo HTTP Bridge

| Componente | chatbot-service | cm-platform | Acción |
|---|---|---|---|
| `DotNetClient.py` (Python → .NET) | ✗ (no usa) | ✓ (conservar renombrado) | Se queda en cm-agent/ |
| `AgentClient.cs` (C# → Python) | ✓ (conservar) | ✗ (no usa) | Se queda en chatbot |
| `RequireInternalKeyAttribute.cs` | ✓ (copia) | ✓ (copia) | Ambos necesitan auth interna |
| `InternalController.cs` | ✗ (endpoints CM) | ✓ (endpoints CM) | Migrar a cm-backend |
| `CommunityController.cs` | ✗ | ✓ | Migrar a cm-backend |

### 3. Lógica Duplicada Python/C#

| Concepto | Archivo Python | Archivo C# | chatbot-service | cm-platform |
|---|---|---|---|---|
| Email HTML wrapping | `services/nurturing_content_renderer.py` | `Services/NurturingContentRenderer.cs` | ✓ (ambos lenguajes) | ✗ (solo agente usará su propio render) |
| Newsletter summary stripping | (mismo archivo) | (mismo archivo) | ✓ | ✗ |
| Pipedrive API client | `services/pipedrive_service.py` | `Services/PipedriveService.cs` | ✓ (ambos lenguajes) | ✗ (no CRM) |
| Nurturing schedule | `services/nurturing_schedule.py` | `Services/NurturingSchedule.cs` | ✓ | ✗ (CM tiene su propio scheduling) |
| Nurturing mail (IMAP/SMTP) | `services/nurturing_mail_service.py` | `Services/NurturingMailService.cs` | ✓ | ✗ |
| AI Foundry LLM factory | `tools/llm.py` | `Services/AzureAIChatService.cs` | ✓ | ✓ (solo Python agent) |
| Community draft models | `models/schemas.py` | `Models/CommunityDraftModels.cs` | ✗ (solo CM) | ✓ |
| Keyword matching helpers | `services/nurturing_workflow_support.py` | `Services/NurturingWorkflowSupport.cs` | ✓ | ✗ |

### 4. Archivos exclusivos de cada proyecto

| chatbot-service (excluir de cm-platform) | cm-platform (excluir de chatbot-service) |
|---|---|
| `src/agent/community_manager/` (todo) | — (es el agente CM) |
| `src/frontend/` (Angular) | — (cm-frontend es Blazor nuevo) |
| `graphify-out/` | — |
| Nurturing services, Pipedrive, Google, Speech | — |
| Chatbot controllers, prompts, services | Community controllers |
