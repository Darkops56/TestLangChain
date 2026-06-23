# Diagramas de Arquitectura — Novit AI Agent

> **Generado desde:** Análisis estático del código fuente + grafo Graphify (4.765 nodos, 7.942 aristas, 309 comunidades)
> **Fecha:** 2026-06-23
> **Propósito:** Documentar la arquitectura completa del sistema para comprensión de nuevos desarrolladores

---

## Índice

1. [Diagrama de Flujo de la Aplicación](#1-diagrama-de-flujo-de-la-aplicación)
2. [Diagrama Entidad-Relación de la Base de Datos](#2-diagrama-entidad-relación-de-la-base-de-datos)
3. [Diagrama de Clases](#3-diagrama-de-clases)

---

## 1. Diagrama de Flujo de la Aplicación

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              NOVIT AI AGENT — FLUJO DEL SISTEMA                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

                                  ┌───────────────────────────┐
                                  │       USUARIO / CM         │
                                  │   (Frontend Angular)       │
                                  └──────────┬────────────────┘
                                             │  HTTP (REST)
                                             ▼
                            ┌────────────────────────────────────┐
                            │       .NET BACKEND API (C#)        │
                            │  ┌──────────────────────────────┐  │
                            │  │  CommunityController         │  │  ← Disparo de contenido
                            │  │  NurturingController         │  │  ← Pipeline newsletter
                            │  │  ChatController              │  │  ← Chat en vivo
                            │  │  WebhooksController          │  │  ← Meta/TikTok inbound
                            │  │  InternalController          │  │  ← API interna
                            │  │  CommunityReviewController   │  │  ← Aprobación HITL
                            │  └──────────┬───────────────────┘  │
                            └─────────────┼──────────────────────┘
                                          │
            ┌─────────────────────────────┼─────────────────────────────┐
            │                             │                             │
            ▼                             ▼                             ▼
  ┌────────────────────┐    ┌──────────────────────┐    ┌─────────────────────────┐
  │   Agent Client     │    │  AzureAIChatService   │    │   Webhook Handler       │
  │  (Python → .NET)   │    │  (Azure OpenAI)       │    │  Meta / TikTok inbound  │
  └─────────┬──────────┘    └──────────┬───────────┘    └───────────┬─────────────┘
            │                          │                            │
            │                          ▼                            │
            │                 ┌─────────────────┐                   │
            │                 │ PostgresConvers │                   │
            │                 │ ationStore      │                   │
            │                 │ (historial chat)│                   │
            │                 └─────────────────┘                   │
            ▼                                                        ▼
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │               LANGGRAPH WORKFLOW ENGINE (Python)                             │
  │                                                                              │
  │  ┌──────────────────────────────────────────────────────────────────────┐   │
  │  │            COMMUNITY MANAGER CONTENT GRAPH                            │   │
  │  │                                                                       │   │
  │  │   START ──► generador ──► corrector ──► image_generator ──► publish  │   │
  │  │        ▲          │             │               │              │      │   │
  │  │        │          └─────(max 3 reintentos)──────┘              │      │   │
  │  │        │                                                       │      │   │
  │  │   (HITL interrupt ──► CommunityReviewController)               │      │   │
  │  │                                                               │      │   │
  │  │   Output: Gmail, TikTok, Instagram, WhatsApp                   │      │   │
  │  └───────────────────────────────────────────────────────────────┘      │   │
  │                                                                              │
  │  ┌──────────────────────────────────────────────────────────────────────┐   │
  │  │            NEWSLETTER NURTURING GRAPH                                 │   │
  │  │                                                                       │   │
  │  │   Researcher ──► Writer ──► Chart Planner ──► Chart Renderer         │   │
  │  │       │                      │                                        │   │
  │  │       ▼                      ▼                                        │   │
  │  │   Content Scorer ◄────── Evaluator_Pre_Media                          │   │
  │  │       │                                                              │   │
  │  │       ▼                                                              │   │
  │  │   Slides Planner ──► Image Generator ──► Slides Assembler            │   │
  │  │       │                      │                                        │   │
  │  │       ▼                      ▼                                        │   │
  │  │   Quality Review ──── Evaluator ──── Distributor                      │   │
  │  │                                       │                               │   │
  │  │                                       ├──► PPTX Publisher             │   │
  │  │                                       ├──► HTML Publisher            │   │
  │  │                                       └──► NurturingMailService      │   │
  │  └──────────────────────────────────────────────────────────────────────┘   │
  │                                                                              │
  │  ┌──────────────────────────────────────────────────────────────────────┐   │
  │  │            AI RADAR GRAPH (generación mensual)                       │   │
  │  │                                                                       │   │
  │  │   Researcher (70 consultas paralelas: Brave + Serper)                │   │
  │  │       │                                                              │   │
  │  │       ├──► BenchmarkSnapshot (benchmarks de modelos)                 │   │
  │  │       └──► RadarInsight[] (tendencias + novedades)                  │   │
  │  │                    │                                                  │   │
  │  │                    ▼                                                  │   │
  │  │              RadarReport (nodo central)                              │   │
  │  │                    │                                                  │   │
  │  │           ┌───────┼───────────┐                                      │   │
  │  │           ▼       ▼           ▼                                      │   │
  │  │      PPTX     HTML     Google Slides                                  │   │
  │  │      Pub      Pub      Pub                                           │   │
  │  └──────────────────────────────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
          ┌────────────────────────────────────────────────────┐
          │              PLATAFORMAS DE SALIDA                  │
          │                                                    │
          │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐  │
          │  │  Gmail   │ │ TikTok   │ │Instagram │ │Whats │  │
          │  │  (SMTP)  │ │ (API)    │ │(Meta API)│ │App   │  │
          │  └──────────┘ └──────────┘ └──────────┘ └──────┘  │
          │                                                    │
          │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
          │  │  PPTX    │ │  HTML    │ │  Google Slides   │   │
          │  └──────────┘ └──────────┘ └──────────────────┘   │
          └────────────────────────────────────────────────────┘
```

### 1.1 Explicación Detallada del Flujo

El sistema Novit AI Agent es una **arquitectura multi-agente orquestada por LangGraph** que se compone de cuatro pipelines principales, más un conjunto de servicios transversales. A continuación se describe cada componente y su rol en el flujo general.

---

#### 1.1.1 Capa de Entrada (Frontend + Scheduler)

| Componente | Rol | Tecnología |
|-----------|-----|-----------|
| **Frontend Angular** | Interfaz de usuario para que el gestor de comunidades (CM) dispare contenido, revise borradores, vea historial y administre clientes | Angular + TypeScript |
| **AgentScheduler** (cron) | Dispara pipelines de forma automática según calendario (newsletter mensual, AI Radar) | Python `scheduler/cron.py` |
| **CalendlyService** | Dispara flujos basados en citas agendadas por clientes | Integración Calendly API |

**Flujo de entrada:**
1. El usuario (gestor CM) interactúa con el frontend Angular
2. El frontend hace peticiones REST al backend .NET
3. El backend .NET traduce esas peticiones a comandos para el agente Python vía `AgentClient`
4. El scheduler también puede iniciar flujos automáticos según configuraciones cron

---

#### 1.1.2 Backend .NET (C#)

El backend .NET es el **orquestador central** que recibe todas las peticiones y las enruta al agente Python correspondiente. Expone los siguientes controladores:

| Controlador | Endpoint | Propósito | Flujo de salida |
|------------|---------|-----------|----------------|
| **CommunityController** | `POST /api/community/content` | Disparar pipeline de contenido para redes sociales | → AgentClient → Python CM Graph |
| **NurturingController** | `POST /api/nurturing/newsletter` | Iniciar generación de newsletter | → AgentClient → Python Newsletter Graph |
| **ChatController** | `POST /api/chat/message` | Enviar mensaje al chat con IA | → AzureAIChatService → Azure OpenAI |
| **WebhooksController** | `POST /api/webhooks/meta` | Recibir mensajes entrantes de Meta/TikTok | → AgentClient → Python Social Media Pipeline |
| **InternalController** | `GET/POST /api/internal/*` | Endpoints internos para el agente Python | Bidireccional Python ↔ .NET |
| **CommunityReviewController** | `POST /api/review/approve` | Aprobación humana (HITL) de contenido | → AgentClient → Resume workflow |

**Patrón de comunicación:**
- El backend .NET se comunica con el agente Python exclusivamente a través de `AgentClient` (`Services/AgentClient.cs`), un cliente HTTP que llama a la API interna del agente.
- El agente Python también puede llamar al backend .NET a través de `DotNetClient` (`tools/dotnet_client.py`) para operaciones como crear notas en Pipedrive, enviar facturas, o consultar datos de clientes.
- **Dirección del flujo:** Principalmente .NET → Python (para disparar trabajo), pero también Python → .NET (para consultar datos o persistir resultados).

---

#### 1.1.3 LangGraph Workflow Engine (Python)

Este es el **corazón del sistema**. Un motor de grafos de estado (`StateGraph`) que orquesta pipelines de generación de contenido usando LLMs. Los nodos del grafo son funciones Python que transforman el estado compartido.

##### Community Manager Content Graph

El pipeline principal para generación de contenido social:

```
    START
      │
      ▼
┌─────────────┐
│  generador  │  Invoca LLM con structured output (Pydantic)
│  (Gemini →  │  Genera texto para cada plataforma solicitada
│   OpenAI)   │  Usa MultiPlatformOutput como esquema de salida
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  corrector  │  Validación local SIN LLM:
│             │  - Largo máximo (150/220/500/2000 chars)
│             │  - Presencia de hashtags requeridos
│             │  - Palabra clave "IA" obligatoria
│             │  - Prohibición de HTML en WhatsApp
│             │  - Si falla → feedback + reintento (max 3)
└──────┬──────┘
       │
       ▼
┌───────────────┐
│image_generator│  Genera imágenes:
│               │  - DALL-E 3 (preferente)
│               │  - Pillow (fallback)
│               │  - Una imagen por plataforma si aplica
└───────┬───────┘
        │
        ▼
┌─────────────┐
│   publish   │  Publicación en paralelo:
│             │  - ThreadPoolExecutor
│             │  - Cada adaptador en su propio hilo
│             │  - Antes de publicar: HITL interrupt
│             │    (pausa y espera aprobación humana)
└──────┬──────┘
       │
       ▼
      END
```

**Mecanismo de reintentos:**
- El `corrector` valida localmente. Si falla, añade `platform_feedback` al estado y redirige al `generador`.
- Máximo 3 reintentos por plataforma. Si se agotan, esa plataforma se marca como fallida y se continúa con las demás.
- No se consume LLM en los reintentos de validación (el corrector es 100% reglas locales).

**HITL (Human-in-the-Loop):**
- Antes de publicar, el grafo se interrumpe vía `langgraph.checkpoint.sqlite.SqliteSaver`.
- El contenido queda en estado `PENDING_HITL` en la base de datos.
- El `CommunityReviewController` permite al gestor aprobar o rechazar.
- Si se aprueba, el grafo se reanuda desde el `publish` node.
- Si se rechaza, se reinicia desde el `generador` con feedback humano.

##### Newsletter Nurturing Graph

Pipeline más complejo para generar newsletters mensuales con investigación, análisis y diseño profesional:

```
    START
      │
      ▼
┌────────────────┐
│  Researcher    │  ≈70 consultas paralelas (Brave Search + Serper)
│                │  Recolecta noticias, tendencias, datos de IA
│                │  Estructura en RadarInsight[] y BenchmarkSnapshot
└───────┬────────┘
        │
        ▼
┌────────────────┐
│  Writer        │  Genera texto del newsletter con LLM
│                │  Aplica prompts con jerga, país, tono
│                │  Produce contenido en Markdown estructurado
└───────┬────────┘
        │
        ▼
┌────────────────────┐
│  Chart Planner     │  Planifica qué gráficos incluir
│                    │  Decide tipo: barras, radar, líneas
│                    │  Selecciona qué datos visualizar
└───────┬────────────┘
        │
        ▼
┌────────────────────┐
│  Chart Renderer    │  Renderiza gráficos con matplotlib
│                    │  Genera imágenes de charts
│                    │  Las sube a Azure Blob Storage
└───────┬────────────┘
        │
        ▼
┌────────────────────┐
│  Content Scorer    │  Puntúa y filtra insights usando LLM
│                    │  Mantiene los mejores por país
│                    │  Elimina duplicados y baja calidad
└───────┬────────────┘
        │
        ▼
┌────────────────────┐
│  Evaluator_Pre     │  Validación pre-media (sin imágenes)
│  _Media            │  Verifica: fuentes, contradicciones,
│                    │  extensión, formato
└───────┬────────────┘
        │
        ▼
┌────────────────────┐
│  Slides Planner    │  Planifica diapositivas del newsletter
│                    │  Decide layout, orden, qué va en cada slide
└───────┬────────────┘
        │
        ▼
┌────────────────────┐
│  Image Generator   │  Genera imágenes con GPT Image / DALL-E
│                    │  Una imagen por slide planificado
│                    │  Cachea para evitar regeneración
└───────┬────────────┘
        │
        ▼
┌────────────────────┐
│  Slides Assembler  │  Arma las diapositivas PPTX
│                    │  Coloca texto + imágenes en plantilla
└───────┬────────────┘
        │
        ▼
┌────────────────────┐
│  Quality Review    │  Revisión final de calidad
│                    │  Verifica coherencia visual
│                    │  Comprueba enlaces y referencias
└───────┬────────────┘
        │
        ▼
┌────────────────────┐
│  Evaluator         │  Evaluación final con LLM
│                    │  Score de calidad (0-100)
│                    │  Si < threshold → reintento
└───────┬────────────┘
        │
        ▼
┌────────────────────┐
│  Distributor       │  Distribuye a múltiples formatos:
│                    │  - PPTX Publisher → archivo .pptx
│                    │  - HTML Publisher → email template
│                    │  - NurturingMailService → envío SMTP
└────────────────────┘
```

##### AI Radar Graph

Sub-pipeline especializado que se ejecuta mensualmente:

```
    START
      │
      ▼
┌────────────────────┐
│  Researcher (70x)  │  Consultas paralelas:
│                    │  - Brave Search (noticias actualidad IA)
│                    │  - Serper (búsqueda estructurada)
│                    │  - Recopila: lanzamientos, benchmarks,
│                    │    papers, tendencias
└───────┬────────────┘
        │
        ├────────────────────────────────┐
        ▼                                ▼
┌──────────────────┐    ┌──────────────────────┐
│ BenchmarkSnapshot │    │   RadarInsight[]     │
│ - vendor/model    │    │ - título             │
│ - score/ranking   │    │ - resumen            │
│ - precio          │    │ - fuente             │
│ - categoría       │    │ - categoría          │
└────────┬─────────┘    └──────────┬───────────┘
         │                         │
         └──────────┬──────────────┘
                    ▼
          ┌──────────────────┐
          │   RadarReport    │  Nodo central que agrega todo
          │                  │  Conecta 16+ comunidades del grafo
          └────────┬─────────┘
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
    ┌────────┐ ┌──────┐ ┌──────────────┐
    │  PPTX  │ │ HTML │ │ Google Slides│
    │  Pub   │ │ Pub  │ │    Pub       │
    └────────┘ └──────┘ └──────────────┘
```

---

#### 1.1.4 Servicios Transversales

| Servicio | Rol | Comunicación |
|---------|-----|-------------|
| **MetaClient** | Publicar en Instagram/Facebook, leer mensajes entrantes | Meta Graph API (HTTP) |
| **TikTokApiClient** | Publicar videos en TikTok, obtener analíticas | TikTok API (HTTP) |
| **ImageGenClient** | Generar imágenes vía Azure AI Foundry (gpt-image-2) | Azure REST API |
| **VideoGen (Sora)** | Generar videos con Sora + avatares | OpenAI Sora API |
| **AzureBlobMediaPublisher** | Hosting temporal de media con URLs SAS | Azure Blob Storage |
| **NurturingMailService** | Envío y recepción de emails vía SMTP/IMAP | Servidor SMTP |
| **PipedriveService** | Sincronización con CRM Pipedrive (deals, notas) | Pipedrive API |
| **GoogleSlidesRadarPublisher** | Publicar reportes en Google Slides | Google Slides API |
| **AzureAIChatService** | Chat en vivo con Azure OpenAI (streaming) | Azure OpenAI API |
| **DotNetClient** | Puente Python → .NET para datos internos | HTTP a .NET Internal API |

---

#### 1.1.5 Flujo de Datos por Pipeline

**Pipeline de Newsletter (flujo completo):**
```
Frontend/Scheduler ──HTTP──► CommunityController ──► AgentClient
    ──► Researcher ──► Writer ──► Chart Planner ──► Chart Renderer
    ──► Content Scorer ──► Evaluator_Pre_Media ──► Slides Planner
    ──► Image Generator ──► Slides Assembler ──► Quality Review
    ──► Evaluator ──► Distributor ──► [PPTX | HTML | Email]
```

**Pipeline de Redes Sociales (respuesta a mensajes):**
```
Meta/TikTok ──Webhook──► WebhooksController ──► AgentClient
    ──► Strategist ──► Designer ──► [MetaClient | TikTokApiClient]
    ──► Plataforma origen
```

**Pipeline de Chat en vivo:**
```
Usuario ──► Angular ──► ChatController ──► AzureAIChatService
    ──► Azure OpenAI ──► respuesta streaming
    ──► PostgresConversationStore (persistencia)
```

---

## 2. Diagrama Entidad-Relación de la Base de Datos

### 2.1 Modelo General

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                      MODELO ENTIDAD-RELACIÓN — NOVIT AI AGENT                       │
│                          (PostgreSQL + SQLite Checkpointer)                          │
└─────────────────────────────────────────────────────────────────────────────────────┘

                                ┌─────────────────────┐
                                │       Client        │
                                │─────────────────────│
                                │ PK  ClientId        │
                                │     Name            │
                                │     Email           │
                                │     Phone           │
                                │     SubscriptionStatus │
                                │     BillingPlan     │
                                │     EditorialPrefs  │
                                │     VisualPrefs     │
                                │     IsActive        │
                                │     CreatedAt       │
                                │     UpdatedAt       │
                                └──────────┬──────────┘
                                           │
                    ┌──────────────────────┼────────────────────────┐
                    │                      │                        │
                    ▼                      ▼                        ▼
    ┌───────────────────────┐  ┌───────────────────┐  ┌────────────────────────┐
    │   SocialAccount       │  │ CommunityPublicat │  │    BillingInvoice      │
    │───────────────────────│  │ ion                │  │────────────────────────│
    │ PK  AccountId         │  │───────────────────│  │ PK  InvoiceId          │
    │ FK  ClientId          │──│ PK PublicationId  │  │ FK  ClientId           │
    │     Platform          │  │ FK ClientId       │  │     Amount             │
    │     AccessToken       │  │     Platform      │  │     Currency           │
    │     RefreshToken      │  │     ContentText   │  │     Status             │
    │     PageId            │  │     ImageUrl      │  │     PeriodStart        │
    │     PageName          │  │     Status (enum) │  │     PeriodEnd          │
    │     IsActive          │  │     ReviewStage   │  │     PaymentDate        │
    │     LastSyncedAt      │  │     ScheduledAt   │  │     PaymentMethod      │
    └───────────────────────┘  │     PublishedAt   │  │     ExternalReference  │
                               │     RetryCount    │  │     CreatedAt          │
     ┌─────────────────────┐   │     ErrorLog      │  └────────────────────────┘
     │  FeedbackHistory    │   │     CreatedAt     │
     │─────────────────────│   │     UpdatedAt     │         1
     │ PK  FeedbackId      │   └───────────────────┘          │
     │ FK  PublicationId   │             1                    N
     │ FK  ReviewerUserId  │              │          ┌────────────────────────┐
     │     Stage           │              │          │  NurturingEmail        │
     │     Decision        │              │          │────────────────────────│
     │     Notes           │              N          │ PK  EmailId            │
     │     CreatedAt       │              │          │ FK  ClientId           │
     └─────────────────────┘              │          │     Subject            │
                                          ▼          │     BodyHtml           │
                               ┌──────────────────┐  │     BodyText           │
                               │  NurturingEmail   │  │     SendStatus         │
                               │  Version          │  │     ScheduledAt        │
                               │──────────────────│  │     SentAt             │
                               │ PK  VersionId    │  │     Version            │
                               │ FK  EmailId      │  │     IsOnHold           │
                               │     BodyHtml     │  │     CreatedAt          │
                               │     CreatedAt    │  │     UpdatedAt          │
                               └──────────────────┘  └────────────────────────┘

┌──────────────────────┐      ┌──────────────────────┐
│  Conversation        │      │      Message          │
│──────────────────────│      │──────────────────────│
│ PK  ConversationId   │──1:N─│ PK  MessageId        │
│     UserId           │      │ FK  ConversationId   │
│     UserName         │      │     Role (user/assist)│
│     Status           │      │     Content           │
│     CreatedAt        │      │     TokenCount        │
│     UpdatedAt        │      │     ModelUsed         │
│                      │      │     LatencyMs         │
│                      │      │     CreatedAt         │
└──────────────────────┘      └──────────────────────┘

┌──────────────────────┐      ┌──────────────────────┐
│  RateLimit           │      │      Lead            │
│──────────────────────│      │──────────────────────│
│ PK  RuleId           │      │ PK  LeadId           │
│     EndpointPath     │      │     Name             │
│     MaxRequests      │      │     Email            │
│     WindowSeconds    │      │     Phone            │
│     IsActive         │      │     PipedriveDealId  │
└──────────────────────┘      │     Status           │
                               │     LastContactedAt  │
┌──────────────────────┐      │     Notes            │
│  AuditLog            │      │     CreatedAt        │
│──────────────────────│      │     UpdatedAt        │
│ PK  AuditId          │      └──────────────────────┘
│     EntityType       │
│     EntityId         │
│     Action           │
│     OldValues        │
│     NewValues        │
│     ChangedBy        │
│     ChangedAt        │
└──────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  SQLite (LangGraph Checkpointer)                            │
│─────────────────────────────────────────────────────────────│
│  state_db.sqlite  (checkpoints del grafo)                   │
│  Tabla interna: checkpoints (thread_id, checkpoint_id,      │
│                  state, parent_checkpoint_id, created_at)   │
│                                                             │
│  Propósito: Persistir el estado del grafo LangGraph         │
│  entre ejecuciones. Permite:                                │
│  - Reanudar workflows después de HITL interrupts           │
│  - Reintentar desde el último checkpoint válido             │
│  - Depurar ejecuciones fallidas                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Diccionario de Tablas y Atributos

#### `Client`

Almacena los clientes del gestor de comunidades. Cada cliente representa una empresa o persona para la cual se gestiona contenido.

| Atributo | Tipo | Descripción | Restricciones |
|---------|------|-------------|-------------|
| `ClientId` | GUID (PK) | Identificador único del cliente | Generado automáticamente |
| `Name` | VARCHAR(200) | Nombre del cliente o empresa | NOT NULL |
| `Email` | VARCHAR(255) | Email de contacto principal | NOT NULL, UNIQUE |
| `Phone` | VARCHAR(50) | Teléfono de contacto | NULLABLE |
| `SubscriptionStatus` | ENUM | Estado de suscripción: `Active`, `Paused`, `Cancelled`, `Trial` | NOT NULL, DEFAULT 'Trial' |
| `BillingPlan` | ENUM | Plan de facturación: `Basic`, `Professional`, `Enterprise` | NOT NULL, DEFAULT 'Basic' |
| `EditorialPrefs` | JSON | Preferencias editoriales estructuradas (tono, temas, keywords) | NULLABLE |
| `VisualPrefs` | JSON | Preferencias visuales (paleta de colores, estilo de imágenes) | NULLABLE |
| `IsActive` | BOOLEAN | Indica si el cliente está activo en el sistema | NOT NULL, DEFAULT TRUE |
| `CreatedAt` | DATETIME | Fecha de creación del registro | NOT NULL, DEFAULT NOW() |
| `UpdatedAt` | DATETIME | Fecha de última modificación | NOT NULL, AUTO-UPDATE |

**Relaciones:**
- 1:N con `SocialAccount` (un cliente puede tener múltiples cuentas de redes sociales)
- 1:N con `CommunityPublication` (un cliente tiene múltiples publicaciones)
- 1:N con `BillingInvoice` (un cliente tiene múltiples facturas)
- 1:N con `NurturingEmail` (un cliente recibe múltiples newsletters)

---

#### `SocialAccount`

Representa una cuenta de red social vinculada a un cliente.

| Atributo | Tipo | Descripción | Restricciones |
|---------|------|-------------|-------------|
| `AccountId` | GUID (PK) | Identificador único de la cuenta | Generado automáticamente |
| `ClientId` | GUID (FK) | Referencia al cliente propietario | NOT NULL, FK → Client(ClientId) ON DELETE CASCADE |
| `Platform` | ENUM | Plataforma: `Instagram`, `Facebook`, `TikTok`, `LinkedIn`, `Twitter` | NOT NULL |
| `AccessToken` | TEXT | Token de acceso a la API de la plataforma | NOT NULL, ENCRYPTED |
| `RefreshToken` | TEXT | Token para refrescar el access token | NULLABLE, ENCRYPTED |
| `PageId` | VARCHAR(100) | ID de la página/cuenta en la plataforma | NOT NULL |
| `PageName` | VARCHAR(200) | Nombre público de la cuenta | NOT NULL |
| `IsActive` | BOOLEAN | Indica si la cuenta está activa y conectada | NOT NULL, DEFAULT TRUE |
| `LastSyncedAt` | DATETIME | Última sincronización exitosa con la API | NULLABLE |

**Relaciones:**
- N:1 con `Client`
- La combinación `ClientId` + `Platform` + `PageId` tiene UNIQUE constraint

---

#### `CommunityPublication`

Registro de cada publicación generada por el sistema, su estado y resultados.

| Atributo | Tipo | Descripción | Restricciones |
|---------|------|-------------|-------------|
| `PublicationId` | GUID (PK) | Identificador único de la publicación | Generado automáticamente |
| `ClientId` | GUID (FK) | Cliente para quien se generó | NOT NULL, FK → Client(ClientId) |
| `Platform` | ENUM | Plataforma destino: `Gmail`, `TikTok`, `Instagram`, `WhatsApp`, `Blog` | NOT NULL |
| `ContentText` | TEXT | Texto del contenido generado | NOT NULL |
| `ImageUrl` | VARCHAR(500) | URL de la imagen generada (opcional) | NULLABLE |
| `Status` | ENUM | Estado: `Draft`, `PendingHitl`, `Approved`, `Published`, `Failed`, `Cancelled` | NOT NULL, DEFAULT 'Draft' |
| `ReviewStage` | ENUM | Etapa de revisión: `Pending`, `InReview`, `Approved`, `ChangesRequested` | NOT NULL, DEFAULT 'Pending' |
| `ScheduledAt` | DATETIME | Fecha programada para publicación | NULLABLE |
| `PublishedAt` | DATETIME | Fecha real de publicación | NULLABLE |
| `RetryCount` | INT | Número de reintentos realizados | NOT NULL, DEFAULT 0 |
| `ErrorLog` | TEXT | Log de errores en caso de fallo | NULLABLE |
| `CreatedAt` | DATETIME | Fecha de creación | NOT NULL, DEFAULT NOW() |
| `UpdatedAt` | DATETIME | Fecha de última modificación | NOT NULL, AUTO-UPDATE |

**Relaciones:**
- N:1 con `Client`
- 1:N con `FeedbackHistory` (una publicación puede tener múltiples revisiones)

**Enumeradores relacionados:**
- `CommunityPublicationStatus`: `Draft`, `PendingHitl`, `Approved`, `Published`, `Failed`, `Cancelled`
- `CommunityReviewStage`: `Pending`, `InReview`, `Approved`, `ChangesRequested`
- `CommunityRevisionTarget`: `Content`, `Design`, `Both`

---

#### `FeedbackHistory`

Historial de revisiones y feedback humano sobre las publicaciones.

| Atributo | Tipo | Descripción | Restricciones |
|---------|------|-------------|-------------|
| `FeedbackId` | GUID (PK) | Identificador único del feedback | Generado automáticamente |
| `PublicationId` | GUID (FK) | Publicación a la que pertenece | NOT NULL, FK → CommunityPublication(PublicationId) ON DELETE CASCADE |
| `ReviewerUserId` | GUID | ID del usuario que realizó la revisión | NOT NULL |
| `Stage` | ENUM | Etapa en la que se dio el feedback: `Content`, `Design`, `Final` | NOT NULL |
| `Decision` | ENUM | Decisión: `Approved`, `ChangesRequested`, `Rejected` | NOT NULL |
| `Notes` | TEXT | Notas y comentarios del revisor | NULLABLE |
| `CreatedAt` | DATETIME | Fecha del feedback | NOT NULL, DEFAULT NOW() |

**Relaciones:**
- N:1 con `CommunityPublication`

---

#### `NurturingEmail`

Newsletters generados por el pipeline de nurturing.

| Atributo | Tipo | Descripción | Restricciones |
|---------|------|-------------|-------------|
| `EmailId` | GUID (PK) | Identificador único del email | Generado automáticamente |
| `ClientId` | GUID (FK) | Cliente destinatario | NOT NULL, FK → Client(ClientId) |
| `Subject` | VARCHAR(500) | Asunto del newsletter | NOT NULL |
| `BodyHtml` | TEXT | Cuerpo del email en formato HTML | NOT NULL |
| `BodyText` | TEXT | Versión texto plano del cuerpo | NOT NULL |
| `SendStatus` | ENUM | Estado: `Draft`, `Scheduled`, `Sent`, `Failed`, `Opened`, `Clicked` | NOT NULL, DEFAULT 'Draft' |
| `ScheduledAt` | DATETIME | Fecha programada para envío | NULLABLE |
| `SentAt` | DATETIME | Fecha real de envío | NULLABLE |
| `Version` | INT | Versión del contenido (incremental) | NOT NULL, DEFAULT 1 |
| `IsOnHold` | BOOLEAN | Indica si el envío está en pausa | NOT NULL, DEFAULT FALSE |
| `CreatedAt` | DATETIME | Fecha de creación | NOT NULL, DEFAULT NOW() |
| `UpdatedAt` | DATETIME | Fecha de última modificación | NOT NULL, AUTO-UPDATE |

**Relaciones:**
- N:1 con `Client`
- 1:N con `NurturingEmailVersion` (historial de versiones)

**Nota sobre versiones:** La migración `AddNurturingEmailVersion` añadió soporte para versionado de newsletters. Cada vez que se regenera un newsletter, se crea una nueva versión en lugar de sobrescribir, permitiendo comparar y revertir.

---

#### `NurturingEmailVersion`

Historial de versiones de un newsletter. Permite tracking de cambios entre iteraciones.

| Atributo | Tipo | Descripción | Restricciones |
|---------|------|-------------|-------------|
| `VersionId` | GUID (PK) | Identificador único de la versión | Generado automáticamente |
| `EmailId` | GUID (FK) | Email al que pertenece esta versión | NOT NULL, FK → NurturingEmail(EmailId) ON DELETE CASCADE |
| `BodyHtml` | TEXT | HTML de esta versión | NOT NULL |
| `BodyText` | TEXT | Texto plano de esta versión | NOT NULL |
| `CreatedAt` | DATETIME | Fecha de creación de esta versión | NOT NULL, DEFAULT NOW() |

**Relaciones:**
- N:1 con `NurturingEmail`

---

#### `Conversation`

Almacena sesiones de chat entre usuarios y el asistente IA.

| Atributo | Tipo | Descripción | Restricciones |
|---------|------|-------------|-------------|
| `ConversationId` | GUID (PK) | Identificador único de la conversación | Generado automáticamente |
| `UserId` | VARCHAR(100) | Identificador del usuario (anonimizado) | NOT NULL |
| `UserName` | VARCHAR(200) | Nombre del usuario (si se proporciona) | NULLABLE |
| `Status` | ENUM | Estado: `Active`, `Closed`, `Archived` | NOT NULL, DEFAULT 'Active' |
| `CreatedAt` | DATETIME | Inicio de la conversación | NOT NULL, DEFAULT NOW() |
| `UpdatedAt` | DATETIME | Última actividad | NOT NULL, AUTO-UPDATE |

**Relaciones:**
- 1:N con `Message`

---

#### `Message`

Cada mensaje individual dentro de una conversación.

| Atributo | Tipo | Descripción | Restricciones |
|---------|------|-------------|-------------|
| `MessageId` | GUID (PK) | Identificador único del mensaje | Generado automáticamente |
| `ConversationId` | GUID (FK) | Conversación a la que pertenece | NOT NULL, FK → Conversation(ConversationId) ON DELETE CASCADE |
| `Role` | ENUM | Rol: `user`, `assistant`, `system` | NOT NULL |
| `Content` | TEXT | Contenido del mensaje | NOT NULL |
| `TokenCount` | INT | Cantidad de tokens del mensaje | NULLABLE |
| `ModelUsed` | VARCHAR(100) | Modelo que generó la respuesta (ej: `gpt-4o`, `gemini-2.0-flash`) | NULLABLE |
| `LatencyMs` | INT | Tiempo de respuesta en milisegundos | NULLABLE |
| `CreatedAt` | DATETIME | Fecha del mensaje | NOT NULL, DEFAULT NOW() |

**Relaciones:**
- N:1 con `Conversation`

---

#### `BillingInvoice`

Facturación periódica por cliente.

| Atributo | Tipo | Descripción | Restricciones |
|---------|------|-------------|-------------|
| `InvoiceId` | GUID (PK) | Identificador único de la factura | Generado automáticamente |
| `ClientId` | GUID (FK) | Cliente facturado | NOT NULL, FK → Client(ClientId) |
| `Amount` | DECIMAL(10,2) | Monto de la factura | NOT NULL |
| `Currency` | VARCHAR(3) | Código de moneda (USD, ARS, EUR) | NOT NULL, DEFAULT 'USD' |
| `Status` | ENUM | Estado: `Pending`, `Paid`, `Overdue`, `Cancelled`, `Refunded` | NOT NULL, DEFAULT 'Pending' |
| `PeriodStart` | DATE | Inicio del período facturado | NOT NULL |
| `PeriodEnd` | DATE | Fin del período facturado | NOT NULL |
| `PaymentDate` | DATETIME | Fecha de pago | NULLABLE |
| `PaymentMethod` | VARCHAR(50) | Método de pago: `Stripe`, `MercadoPago`, `Transfer` | NULLABLE |
| `ExternalReference` | VARCHAR(255) | ID de referencia en el proveedor de pagos | NULLABLE |
| `CreatedAt` | DATETIME | Fecha de emisión | NOT NULL, DEFAULT NOW() |

**Relaciones:**
- N:1 con `Client`

---

#### `RateLimit`

Reglas de rate limiting para endpoints de la API.

| Atributo | Tipo | Descripción | Restricciones |
|---------|------|-------------|-------------|
| `RuleId` | GUID (PK) | Identificador único de la regla | Generado automáticamente |
| `EndpointPath` | VARCHAR(255) | Path del endpoint a limitar (ej: `/api/chat/message`) | NOT NULL, UNIQUE |
| `MaxRequests` | INT | Máximo de requests permitidos en la ventana | NOT NULL |
| `WindowSeconds` | INT | Ventana de tiempo en segundos | NOT NULL |
| `IsActive` | BOOLEAN | Indica si la regla está activa | NOT NULL, DEFAULT TRUE |

---

#### `Lead` (Pipedrive Integration)

Registros sincronizados desde Pipedrive CRM.

| Atributo | Tipo | Descripción | Restricciones |
|---------|------|-------------|-------------|
| `LeadId` | GUID (PK) | Identificador único del lead | Generado automáticamente |
| `Name` | VARCHAR(200) | Nombre del lead/contacto | NOT NULL |
| `Email` | VARCHAR(255) | Email del lead | NOT NULL |
| `Phone` | VARCHAR(50) | Teléfono del lead | NULLABLE |
| `PipedriveDealId` | BIGINT | ID del deal en Pipedrive | NULLABLE, UNIQUE |
| `Status` | VARCHAR(50) | Estado en el pipeline de ventas | NOT NULL |
| `LastContactedAt` | DATETIME | Último contacto registrado | NULLABLE |
| `Notes` | TEXT | Notas adicionales del lead | NULLABLE |
| `CreatedAt` | DATETIME | Fecha de creación | NOT NULL, DEFAULT NOW() |
| `UpdatedAt` | DATETIME | Fecha de última modificación | NOT NULL, AUTO-UPDATE |

---

#### `AuditLog`

Auditoría de cambios en entidades del sistema.

| Atributo | Tipo | Descripción | Restricciones |
|---------|------|-------------|-------------|
| `AuditId` | BIGINT (PK) | Identificador único del registro de auditoría | AUTO-INCREMENT |
| `EntityType` | VARCHAR(100) | Tipo de entidad modificada (ej: `CommunityPublication`, `Client`) | NOT NULL |
| `EntityId` | VARCHAR(100) | ID de la entidad modificada | NOT NULL |
| `Action` | VARCHAR(50) | Acción realizada: `Create`, `Update`, `Delete`, `StatusChange` | NOT NULL |
| `OldValues` | JSON | Valores anteriores (para Updates) | NULLABLE |
| `NewValues` | JSON | Valores nuevos | NOT NULL |
| `ChangedBy` | VARCHAR(100) | Usuario o sistema que realizó el cambio | NOT NULL |
| `ChangedAt` | DATETIME | Momento del cambio | NOT NULL, DEFAULT NOW() |

---

#### `SQLite (LangGraph Checkpointer) — state_db.sqlite`

Base de datos embebida SQLite que persiste el estado del grafo LangGraph. No forma parte del modelo relacional principal, sino que es un mecanismo interno de LangGraph.

**Estructura interna** (gestionada por `langgraph.checkpoint.sqlite.SqliteSaver`):

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `thread_id` | TEXT | Identificador del hilo de ejecución |
| `checkpoint_id` | TEXT | Identificador del checkpoint |
| `parent_checkpoint_id` | TEXT | Checkpoint padre (para branching) |
| `state` | BLOB | Estado serializado del grafo en ese punto |
| `created_at` | DATETIME | Fecha del checkpoint |

**Propósito:**
- Reanudar workflows después de interrupciones HITL
- Implementar reintentos desde el último estado válido
- Depurar ejecuciones inspeccionando estados intermedios
- Soporte para branching (experimentación con diferentes caminos)

---

### 2.3 Migraciones de Base de Datos (EF Core)

El proyecto .NET utiliza **Entity Framework Core** con migraciones para gestionar el esquema. Las migraciones identificadas en el grafo son:

| Migración | Descripción |
|-----------|-------------|
| `InitialCreate` | Esquema inicial con tablas base: Client, Conversation, Message, Lead, RateLimit, AuditLog |
| `AddNurturingEmails` | Añade tabla NurturingEmail para el pipeline de newsletters |
| `AddNurturingEmailVersion` | Añade tabla NurturingEmailVersion para versionado de newsletters |
| `AddNewsletterIsOnHold` | Añade columna `IsOnHold` a NurturingEmail para pausar envíos |
| `AddCommunityPublications` | Añade tabla CommunityPublication y FeedbackHistory |
| `AddCommunityReviewStage` | Añade columna `ReviewStage` a CommunityPublication y enums relacionados |

**Patrón de migraciones:** Secuencia lineal con additive changes. No se detectan rollbacks o migraciones destructivas en el historial.

---

## 3. Diagrama de Clases

### 3.1 Diagrama General

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                          DIAGRAMA DE CLASES — NOVIT AI AGENT                                    │
│                  (Python + .NET + Angular, organizado por capas)                                │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────┐
│  CAPA 1: MODELOS DE DATOS (Pydantic + TypedDict + C# Models)   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────┐  ┌────────────────────┐  │
│  │ «TypedDict» AgentState             │  │ «TypedDict»        │  │
│  │  (langgraph)                       │  │ MultiPlatformState │  │
│  │────────────────────────────────────│  │────────────────────│  │
│  │  + input: str                     │  │  + user_prompt: str│  │
│  │  + response: str | None           │  │  + platforms: list │  │
│  │  + raw_response: str | None       │  │  + outputs: dict   │  │
│  │  + messages: list[str]            │  │  + retry_count: int│  │
│  └───────────────────┬────────────────┘  │  + is_approved:bool│  │
│                      │                   │  + image_paths:dict│  │
│                      │hereda             │  + publication_... │  │
│                      ▼                   └────────────────────┘  │
│  ┌────────────────────────────────────┐  ┌────────────────────┐  │
│  │ «TypedDict» CommunityManagerState  │  │ «TypedDict»        │  │
│  │────────────────────────────────────│  │ NewsletterState    │  │
│  │  + content_type: ContentType      │  │────────────────────│  │
│  │  + strategy: StrategyResult       │  │  + month: str      │  │
│  │  + copy: PostCopy                 │  │  + raw_report:     │  │
│  │  + media: MediaContent            │  │    RadarReport     │  │
│  │  + evaluation: EvaluationResult   │  │  + slides_plan:    │  │
│  │  + publication: PublicationResult │  │    SlidesPlan      │  │
│  └────────────────────────────────────┘  │  + quality_score:  │  │
│                                           │    float           │  │
│  ┌────────────────────────────┐          │  + published_urls: │  │
│  │ «BaseModel» WorkflowRequest│          └────────────────────┘  │
│  │────────────────────────────│                                   │
│  │  + input: str             │  ┌────────────────────────────┐   │
│  └────────────────────────────┘  │ «BaseModel»               │   │
│                                  │ MultiPlatformOutput       │   │
│  ┌────────────────────────────┐  │────────────────────────────│   │
│  │ «BaseModel» WorkflowResult│  │  + gmail: GmailOutput     │   │
│  │────────────────────────────│  │  + tiktok: TikTokOutput   │   │
│  │  + input: str             │  │  + instagram: InstaOutput │   │
│  │  + response: str | None   │  │  + whatsapp: WhatsOutput  │   │
│  │  + messages: list[str]    │  └────────────────────────────┘   │
│  └────────────────────────────┘                                   │
│                                                                  │
│  ┌────────────────────────────┐  ┌────────────────────────────┐  │
│  │ «BaseModel» GmailOutput   │  │ «BaseModel» TikTokOutput   │  │
│  │────────────────────────────│  │────────────────────────────│  │
│  │  + text: str (max 2000)   │  │  + text: str (max 150)    │  │
│  │  ⚠ requiere "IA"          │  │  ⚠ requiere "#" + "IA"    │  │
│  │  ✓ permite HTML           │  └────────────────────────────┘  │
│  └────────────────────────────┘                                   │
│                                                                  │
│  ┌────────────────────────────┐  ┌────────────────────────────┐  │
│  │ «BaseModel» InstagramOut  │  │ «BaseModel» WhatsAppOutput │  │
│  │────────────────────────────│  │────────────────────────────│  │
│  │  + text: str (max 220)    │  │  + text: str (max 500)    │  │
│  │  ⚠ requiere "#" + "IA"    │  │  ⚠ requiere "IA"          │  │
│  └────────────────────────────┘  │  ✗ prohíbe HTML           │  │
│                                   └────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│  CAPA 2: DOMINIO / NEGOCIO                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────┐  ┌─────────────────────────┐  │
│  │        RadarReport           │  │      RadarInsight       │  │
│  │──────────────────────────────│  │─────────────────────────│  │
│  │  - month: str                │  │  - id: str              │  │
│  │  - executive_summary: str    │──│  - title: str           │  │
│  │  - insights: list[RadarInsight]│  │  - summary: str        │  │
│  │  - benchmark_snapshot:       │  │  - source_url: str      │  │
│  │    BenchmarkSnapshot          │  │  - category: str       │  │
│  │  - created_at: datetime      │  │  - confidence: float   │  │
│  └──────────────────────────────┘  └─────────────────────────┘  │
│                                         1:N                      │
│                                                                  │
│  ┌──────────────────────────────┐  ┌─────────────────────────┐  │
│  │    BenchmarkSnapshot         │  │    BenchmarkEntry       │  │
│  │──────────────────────────────│  │─────────────────────────│  │
│  │  - month: str                │──│  - vendor: str          │  │
│  │  - entries: list[BMEntry]    │  │  - model: str           │  │
│  │  - source: str               │  │  - score: float         │  │
│  │  - notes: str                │  │  - category: str        │  │
│  └──────────────────────────────┘  │  - position: int        │  │
│                                    └─────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────┐  ┌─────────────────────────┐  │
│  │     IncomingMessage          │  │      ContentType        │  │
│  │──────────────────────────────│  │      (enum)             │  │
│  │  - platform: str             │  │─────────────────────────│  │
│  │  - sender_id: str            │  │  NEWS                   │  │
│  │  - content: str              │  │  SOCIAL_MEDIA           │  │
│  │  - message_type: str         │  │  AI_RADAR               │  │
│  │  - timestamp: datetime       │  │  REVIEW                 │  │
│  └──────────────────────────────┘  └─────────────────────────┘  │
│                                                                  │
│  ┌─────────────────────────────┐  ┌───────────────────────────┐ │
│  │ CommunityPublicationStatus  │  │ CommunityReviewStage      │ │
│  │ (enum)                     │  │ (enum)                    │ │
│  │─────────────────────────────│  │───────────────────────────│ │
│  │ DRAFT, PENDING_HITL,       │  │ PENDING, IN_REVIEW,       │ │
│  │ APPROVED, PUBLISHED,       │  │ APPROVED, CHANGES_REQ     │ │
│  │ FAILED, CANCELLED          │  └───────────────────────────┘ │
│  └─────────────────────────────┘                                │
├─────────────────────────────────────────────────────────────────┤
│  CAPA 3: SERVICIOS / ADAPTADORES (Abstractas + Concretas)      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────┐                            │
│  │ «ABC» PlataformaPublicacion      │                            │
│  │──────────────────────────────────│                            │
│  │  + publicar(texto, image_path)   │                            │
│  │                         → bool   │                            │
│  └────────┬─────────┬────────┬──────┘                            │
│           │         │        │                                   │
│  ┌────────┴──┐ ┌───┴────┐ ┌─┴──────┐  ┌────────────────────┐   │
│  │ Adaptador │ │Adapta  │ │Adapta  │  │ «interface»         │   │
│  │ Gmail     │ │dor TikTok│ │dor IG │  │ IAgentClient        │   │
│  │ (SMTP)    │ │(API)   │ │(Meta)  │  │────────────────────│   │
│  └───────────┘ └────────┘ └────────┘  │  + kick_draft()     │   │
│                                        │  + get_status()     │   │
│  ┌──────────────────────────┐          │  + requestRevision()│   │
│  │     MetaClient           │          └─────────┬───────────┘   │
│  │──────────────────────────│                    │implementa     │
│  │  + publish_photo(url)    │                    ▼               │
│  │  + publish_reel(url)     │  ┌──────────────────────────┐      │
│  │  + get_messages()        │  │     AgentClient          │      │
│  │  + reply_to_comment()    │  │──────────────────────────│      │
│  └──────────────────────────│  │  - _httpClient: HttpClient│      │
│                              │  │  - _baseUrl: string      │      │
│  ┌──────────────────────────┐  │  + kick_draft(req) → Guid │      │
│  │   TikTokApiClient        │  │  + get_status(id) → State│      │
│  │──────────────────────────│  │  + requestRevision(id)   │      │
│  │  + upload_video(file)    │  └──────────────────────────┘      │
│  │  + check_status(task_id) │                                     │
│  │  + get_analytics()       │  ┌──────────────────────────┐      │
│  └──────────────────────────│  │   DotNetClient           │      │
│                              │  │──────────────────────────│      │
│  ┌──────────────────────────┐  │  + create_note()         │      │
│  │  NurturingMailService    │  │  + move_deal()           │      │
│  │──────────────────────────│  │  + send_email()          │      │
│  │  + send_email(to, body)  │  │  + get_recipients()     │      │
│  │  + send_reply(to, body)  │  └──────────────────────────┘      │
│  │  + fetch_incoming()      │                                     │
│  └──────────────────────────┘                                     │
│                                                                  │
│  ┌──────────────────────────┐  ┌──────────────────────────┐      │
│  │ NewsletterPPTXPublisher  │  │ NewsletterHTMLPublisher  │      │
│  │──────────────────────────│  │──────────────────────────│      │
│  │  + generate_slides()     │  │  + generate_html()       │      │
│  │  + fill_placeholders()   │  │  + convert_to_pdf()      │      │
│  │  + add_chart(data)       │  │  + upload_assets()      │      │
│  │  + export_pptx(path)     │  └──────────────────────────┘      │
│  └──────────────────────────┘                                     │
│                                                                  │
│  ┌──────────────────────────┐  ┌──────────────────────────┐      │
│  │ GoogleSlidesRadarPublisher│  │  AzureAIChatService      │      │
│  │──────────────────────────│  │──────────────────────────│      │
│  │  + create_presentation() │  │  + GetCompletionAsync()  │      │
│  │  + build_slides()        │  │  + StreamCompletionAsync│      │
│  │  + publish()             │  │  + GetToolsAsync()       │      │
│  └──────────────────────────┘  └──────────────────────────┘      │
├─────────────────────────────────────────────────────────────────┤
│  CAPA 4: LLM / HERRAMIENTAS                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  StructuredLLMFallbackWrapper                                ││
│  │──────────────────────────────────────────────────────────────││
│  │  - _models: [GeminiClient, OpenAIClient, StaticFallback]    ││
│  │  + invoke(messages, schema, ...) → StructuredOutput         ││
│  │                                                              ││
│  │  Flujo interno:                                              ││
│  │    1. Intentar Gemini (google-genai)                         ││
│  │    2. Si falla → OpenAI (langchain-openai)                  ││
│  │    3. Si falla → respuesta estática predefinida             ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────┐ │
│  │ ImageGen     │ │ VideoGen     │ │ BlobMedia    │ │SafeJson│ │
│  │ (DALL-E/PIL) │ │ (Sora)       │ │ (Azure Blob) │ │(parser)│ │
│  └──────────────┘ └──────────────┘ └──────────────┘ └────────┘ │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  CAPA 5: INFRAESTRUCTURA                                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ │
│  │ SQLiteSaver      │ │ PostgresConver   │ │ InMemoryConvers  │ │
│  │ (LangGraph       │ │ sationStore      │ │ ationStore       │ │
│  │  Checkpointer)   │ │ (Chat History)   │ │ (Testing)        │ │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘ │
│                                                                  │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ │
│  │ NurturingSchedule│ │ AgentScheduler   │ │ CalendlyService  │ │
│  │ (cron jobs)      │ │ (cron/celery)    │ │ (appointments)   │ │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘ │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  CAPA 6: FRONTEND (Angular)                                 ││
│  │                                                              ││
│  │  ┌────────────────┐ ┌────────────────┐ ┌──────────────────┐ ││
│  │  │ AppComponent   │ │ ChatComponent  │ │ CommunityComponent│ │
│  │  │ (shell/layout) │ │ (chat UI)      │ │ (CM dashboard)   │ │
│  └──────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Explicación Detallada de las Clases

#### Capa 1 — Modelos de Datos (Pydantic / TypedDict)

Estos modelos definen la estructura de datos que fluye a través del sistema. Se dividen en dos categorías:

**TypedDicts de LangGraph (estado del grafo):**

| Clase | Archivo | Propósito | Atributos clave |
|-------|---------|-----------|----------------|
| `AgentState` | `langgraph_workflow_api/graph.py` | Estado base del agente LangGraph. Contiene el input, la respuesta del LLM y el historial de mensajes. | `input`, `response`, `raw_response`, `messages` |
| `MultiPlatformState` | `Python/src/state.py` | Estado del pipeline multiplataforma. Trackea qué plataformas están habilitadas, los outputs generados, reintentos, feedback, aprobación HITL y resultados de publicación. | `user_prompt`, `platforms`, `outputs`, `retry_count`, `platform_feedback`, `is_approved`, `image_paths`, `publication_results`, `publication_errors` |
| `CommunityManagerState` | `ProyectoAgentes/community_manager/graph/state.py` | Estado principal del agente Community Manager original. Contiene desde la estrategia hasta el resultado de publicación. Flujo: Strategist → Copywriter → Designer → Evaluator → Publisher. | `content_type`, `strategy`, `copy`, `media`, `evaluation`, `publication` |
| `NewsletterState` | `nurturing/workflow_v2.py` | Estado del pipeline de newsletter. Trackea el mes, el reporte generado, plan de slides, imágenes, score de calidad y URLs publicadas. | `month`, `raw_report`, `slides_plan`, `generated_images`, `quality_score`, `published_urls` |

**Pydantic BaseModels (validación de datos):**

| Clase | Propósito | Atributos | Validaciones |
|-------|-----------|-----------|-------------|
| `WorkflowRequest` | Request de la API REST FastAPI | `input: str` | — |
| `WorkflowResponse` | Respuesta inmediata (202 Accepted) | `run_id: str` | — |
| `WorkflowResult` | Resultado del workflow (polling) | `input`, `response`, `raw_response`, `messages` | — |
| `PlatformContent` | Contenido generado para una plataforma | `text`, `image_prompt`, `is_valid`, `errors` | — |
| `SinglePlatformOutput` | Output estructurado de una plataforma | `text`, `image_prompt` (opcional) | — |
| `MultiPlatformOutput` | Contenedor de outputs multi-plataforma | `gmail`, `tiktok`, `instagram`, `whatsapp` (todos Optional) | — |

**Outputs específicos por plataforma (con validaciones de negocio):**

| Clase | Plataforma | Longitud máx | Requisitos especiales |
|-------|-----------|-------------|----------------------|
| `GmailOutput` | Gmail/Email | 2000 caracteres | Debe contener "IA", permite HTML |
| `TikTokOutput` | TikTok | 150 caracteres | Debe contener "#" + "IA" |
| `InstagramOutput` | Instagram | 220 caracteres | Debe contener "#" + "IA" |
| `WhatsAppOutput` | WhatsApp | 500 caracteres | Debe contener "IA", prohíbe HTML |

**Patrón de diseño:** Los `*Output` usan herencia implícita de `BaseModel` (Pydantic v2) para validación automática en el parsing del LLM. El `StructuredLLMFallbackWrapper` invoca el LLM solicitando JSON que calce con estos esquemas.

---

#### Capa 2 — Dominio / Negocio

Modelos de dominio que representan los conceptos centrales del negocio.

| Clase | Propósito | Relaciones |
|-------|-----------|-----------|
| `RadarReport` | Contenedor principal del AI Radar mensual. Agrega insights, benchmarks y genera los artefactos de salida. Conecta 16+ comunidades del grafo. | 1:N con `RadarInsight`, 1:1 con `BenchmarkSnapshot` |
| `RadarInsight` | Tendencia o novedad individual de IA. Incluye fuente, confianza y categoría para filtrado. | N:1 con `RadarReport` |
| `BenchmarkSnapshot` | Captura mensual de benchmarks de modelos (precio, rendimiento, ranking). | 1:N con `BenchmarkEntry` |
| `BenchmarkEntry` | Entrada individual de benchmark: vendor, modelo, score, posición. | N:1 con `BenchmarkSnapshot` |
| `IncomingMessage` | Mensaje entrante desde redes sociales (Meta/TikTok webhooks). | Independiente (se procesa y transforma en acción) |

**Enumeradores:**

| Enumerador | Valores | Uso |
|-----------|---------|-----|
| `ContentType` | `NEWS`, `SOCIAL_MEDIA`, `AI_RADAR`, `REVIEW` | Determina qué pipeline del agente ejecutar |
| `CommunityPublicationStatus` | `DRAFT`, `PENDING_HITL`, `APPROVED`, `PUBLISHED`, `FAILED`, `CANCELLED` | Ciclo de vida de una publicación |
| `CommunityReviewStage` | `PENDING`, `IN_REVIEW`, `APPROVED`, `CHANGES_REQUESTED` | Etapa de revisión HITL |
| `CommunityRevisionTarget` | `CONTENT`, `DESIGN`, `BOTH` | Qué aspecto necesita corrección en un reintento |

---

#### Capa 3 — Servicios y Adaptadores

**Patrón Adaptador para publicación (Strategy Pattern):**

```
«ABC» PlataformaPublicacion
    │
    ├── AdaptadorGmail      → publica vía SMTP (simulado)
    ├── AdaptadorTikTok     → valida 150 chars, publica vía API
    ├── AdaptadorInstagram  → valida 220 chars, publica vía Meta API
    └── AdaptadorWhatsApp   → valida 500 chars, prohíbe HTML, publica vía API
```

El `Publisher` node en el grafo LangGraph itera sobre las plataformas solicitadas y delega la publicación al adaptador correspondiente usando un `ThreadPoolExecutor` para publicación paralela.

**Clientes de APIs externas:**

| Clase | API Externa | Métodos principales |
|-------|-----------|-------------------|
| `MetaClient` | Meta Graph API (Instagram + Facebook) | `publish_photo()`, `publish_reel()`, `get_messages()`, `reply_to_comment()` |
| `TikTokApiClient` | TikTok API | `upload_video()`, `check_status()`, `get_analytics()` |
| `DotNetClient` | Backend .NET (API interna) | `create_note()`, `move_deal()`, `send_email()`, `get_recipients()` |
| `AgentClient` | Agente Python (desde .NET) | `kick_draft()`, `get_status()`, `request_revision()` |
| `AzureAIChatService` | Azure OpenAI | `GetCompletionAsync()`, `StreamCompletionAsync()` |
| `NurturingMailService` | SMTP/IMAP | `send_email()`, `send_reply()`, `fetch_incoming()` |

**Publishers de contenido:**

| Clase | Formato de salida | Dependencias |
|-------|------------------|-------------|
| `NewsletterPPTXPublisher` | Archivo .pptx con slides profesionales | `python-pptx`, plantilla maestra |
| `NewsletterHTMLPublisher` | HTML + PDF del newsletter | `weasyprint`, plantillas HTML |
| `GoogleSlidesRadarPublisher` | Presentación en Google Slides | Google Slides API |

---

#### Capa 4 — LLM y Herramientas

**StructuredLLMFallbackWrapper**

Esta es la clase central para invocación de LLMs. Implementa un patrón **Chain of Responsibility** con fallback:

```
invoke(mensaje, schema_pydantic)
    │
    1. Intentar Gemini (google-genai) ──► si ok → devuelve StructuredOutput
    │                                       si falla → 2
    │
    2. Intentar OpenAI (langchain-openai) ─► si ok → devuelve StructuredOutput
    │                                       si falla → 3
    │
    3. Respuesta estática predefinida ─────► devuelve default seguro
```

**Propósito:** Garantizar que el sistema nunca falle por indisponibilidad del LLM. La respuesta estática es un último recurso que permite al sistema degradarse gracefulmente.

**Herramientas de soporte:**

| Clase/Función | Propósito |
|--------------|-----------|
| `ImageGen` (DALL-E / Pillow) | Genera imágenes: DALL-E 3 como primera opción, Pillow como fallback si la API no está disponible |
| `VideoGen` (Sora) | Genera videos con Sora, incluyendo avatars y branding overlay |
| `BlobMedia` (Azure Blob) | Sube media a Azure Blob Storage y genera URLs SAS con expiración |
| `SafeJson` | Parseo robusto de JSON desde LLMs con manejo de errores y defaults |

---

#### Capa 5 — Infraestructura

| Clase | Base de datos | Propósito |
|-------|--------------|-----------|
| `SQLiteSaver` | SQLite (`state_db.sqlite`) | Checkpointer de LangGraph. Persiste el estado del grafo para reanudación después de HITL interrupts. |
| `PostgresConversationStore` | PostgreSQL | Almacena historial de conversaciones del chat. Implementa `IConversationStore`. |
| `InMemoryConversationStore` | Memoria | Implementación de `IConversationStore` para pruebas y desarrollo. |
| `NurturingSchedule` | — | Gestión de cron jobs para envío programado de newsletters. |
| `AgentScheduler` | — | Scheduler general del agente para tareas periódicas. |

---

#### Capa 6 — Frontend Angular

| Componente | Ruta | Propósito |
|-----------|------|-----------|
| `AppComponent` | `/` | Componente shell con layout general, navegación y autenticación |
| `ChatComponent` | `/chat` | Interfaz de chat en vivo con streaming de respuestas |
| `CommunityComponent` | `/community` | Dashboard del gestor de comunidades: clientes, timeline, aprobaciones |

---

### 3.3 Relaciones entre Capas

```
Frontend Angular ───HTTP───► .NET Backend API ───AgentClient───► Python LangGraph
                                                                      │
                            ┌─────────────────────────────────────────┘
                            ▼
                    ┌─────────────────┐
                    │  Modelos/Pydantic│ ◄── Validación de entrada/salida
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Nodos del Grafo │ ◄── Lógica de negocio + LLM
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    │  Adaptadores    │ ◄── Publicación en plataformas
                    │  + Clientes API │
                    └─────────────────┘
```

**Principios arquitectónicos observados:**
1. **Separación de responsabilidades:** Cada capa tiene un rol bien definido y no mezcla concerns.
2. **Inmutabilidad del estado:** El estado del grafo se pasa entre nodos sin mutación directa.
3. **Failover en LLM:** El `StructuredLLMFallbackWrapper` garantiza disponibilidad.
4. **Publicación paralela:** Los adaptadores se ejecutan concurrentemente vía ThreadPoolExecutor.
5. **HITL como interrupt:** La revisión humana no es un nodo más, sino una pausa del grafo.

---

## Apéndice A: Resumen de Tecnologías

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Backend API | .NET (C#) | 10 |
| Agente IA | Python + LangGraph | 1.2.5 |
| Frontend | Angular | — |
| Base de datos principal | PostgreSQL | — |
| Checkpointer | SQLite | — |
| LLM Principal | Google Gemini | 2.0 Flash / 2.5 Pro |
| LLM Secundario | OpenAI | GPT-4o |
| LLM Chat | Azure OpenAI | — |
| Generación de imágenes | DALL-E 3 / Azure gpt-image-2 | — |
| Generación de video | OpenAI Sora | — |
| CRM | Pipedrive | API v2 |
| Scheduling | Cron (Python) | — |

## Apéndice B: Flujo de Datos Transversal

```
                    ┌──────────────────────────────────────────────────────────┐
                    │             1. INPUT (Frontend / Scheduler / Webhook)     │
                    │  ┌──────────┐  ┌───────────┐  ┌──────────────────────┐  │
                    │  │ Angular  │  │ Scheduler │  │ Webhook (Meta/TikTok) │  │
                    │  └────┬─────┘  └─────┬─────┘  └──────────┬───────────┘  │
                    └───────┼──────────────┼────────────────────┼──────────────┘
                            │              │                    │
                            ▼              ▼                    ▼
                    ┌──────────────────────────────────────────────────────────┐
                    │             2. ORQUESTACIÓN (.NET Backend)                │
                    │  Controller → Valida → AgentClient → Envía a Python     │
                    └──────────────────────────┬───────────────────────────────┘
                                               │
                                               ▼
                    ┌──────────────────────────────────────────────────────────┐
                    │             3. PROCESAMIENTO (LangGraph Python)           │
                    │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ │
                    │  │Strateg │ │Copywrit│ │Designer│ │Evaluat │ │Publish │ │
                    │  │ ist    │ │ er      │ │        │ │or      │ │er      │ │
                    │  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ │
                    │                     ↻ (max 3 reintentos)                │
                    └──────────────────────────┬───────────────────────────────┘
                                               │
                                     ┌─────────┴─────────┐
                                     ▼                   ▼
                    ┌────────────────────────┐  ┌────────────────────────┐
                    │  4a. HITL REVIEW       │  │  4b. PUBLICACIÓN       │
                    │  (si está configurado)  │  │  (si aprobado / sin    │
                    │  Pausa → Community     │  │   HITL)                │
                    │  ReviewController      │  │  ThreadPoolExecutor    │
                    └────────────────────────┘  └────────────────────────┘
                                                         │
                                                         ▼
                    ┌──────────────────────────────────────────────────────────┐
                    │             5. SALIDA (Múltiples formatos)               │
                    │  Gmail  TikTok  Instagram  WhatsApp  PPTX  HTML  Slides │
                    └──────────────────────────────────────────────────────────┘
```

---

> **Documento generado desde:** Análisis estático del código fuente + grafo Graphify (4.765 nodos, 7.942 aristas, 309 comunidades)
> **Para mantenerlo actualizado:** `graphify update .` y luego revisar las referencias a archivos y líneas
