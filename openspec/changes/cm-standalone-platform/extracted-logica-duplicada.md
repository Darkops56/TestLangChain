# Extracción de Lógica Duplicada Python vs C#

Toda la lógica duplicada existe porque el chatbot tiene implementaciones en .NET y el CM agent en Python. Al separar, **cada proyecto conserva solo las copias que realmente usa**.

| Concepto | Python (origen) | C# (origen) | chatbot-service | cm-platform |
|---|---|---|---|---|
| **Email HTML wrapping** | `services/nurturing_content_renderer.py` | `Services/NurturingContentRenderer.cs` | ✓ (ambos) | ✗ |
| **Newsletter summary stripping** | (mismo archivo) | (mismo archivo) | ✓ (ambos) | ✗ |
| **Pipedrive API client** | `services/pipedrive_service.py` | `Services/PipedriveService.cs` | ✓ (ambos) | ✗ |
| **Nurturing schedule** | `services/nurturing_schedule.py` | `Services/NurturingSchedule.cs` | ✓ (ambos) | ✗ |
| **Nurturing mail (IMAP/SMTP)** | `services/nurturing_mail_service.py` | `Services/NurturingMailService.cs` | ✓ (ambos) | ✗ |
| **Nurturing workflow (keywords)** | `services/nurturing_workflow_support.py` | `Services/NurturingWorkflowSupport.cs` | ✓ (ambos) | ✗ |
| **AI Foundry LLM factory** | `tools/llm.py` | `Services/AzureAIChatService.cs` | ✓ (ambos) | ✓ solo Python (cm-agent/tools/llm.py) |
| **Community draft models** | `models/schemas.py` (parcial) | `Models/CommunityDraftModels.cs` | ✗ | ✓ (ambos) |

## chatbot-service
**Conserva** (del backend .NET actual):
- `Services/NurturingContentRenderer.cs`
- `Services/PipedriveService.cs` + `Models/PipedriveOptions.cs`
- `Services/NurturingSchedule.cs`
- `Services/NurturingMailService.cs` + `INurturingMailService.cs`
- `Services/NurturingWorkflowSupport.cs`
- `Services/NurturingAIService.cs`
- `Services/NurturingBackgroundService.cs`
- `Services/AzureAIChatService.cs`
- `Prompts/` (system prompts del chatbot)
- `Controllers/NurturingController.cs`
- `Controllers/ChatController.cs`
- `Models/NurturingOptions.cs`, `CommunityDraftModels.cs` ✗ (solo CM)

**Elimina:**
- `Controllers/CommunityController.cs` → CM
- `Controllers/InternalController.cs` (endpoints CM) → CM
- `Models/CommunityDraftModels.cs` → CM
- `Services/AgentClient.cs` (solo métodos CM) → ya extraído en 0.4

## cm-platform
**Conserva** (del agente Python actual en `src/agent/community_manager/`):
- `tools/llm.py` → cm-agent/tools/llm.py
- `models/schemas.py` (modelos de community draft y publication) → cm-agent/models/schemas.py
- `config/settings.py` → cm-agent/config/settings.py
- `config/prompts.py` → cm-agent/config/prompts.py
- `services/` (todo lo que usa el CM agent)

**No copia** del monorepo:
- Nurturing services, Pipedrive, schedule → son del chatbot, no los necesita
- Backend .NET actual → se crea cm-backend nuevo (no hereda del chatbot backend)
