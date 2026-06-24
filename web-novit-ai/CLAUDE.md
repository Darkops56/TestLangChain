# Project: Novit AI Web — Agent Instructions

## Overview

This is the **Novit Software** commercial website with an embedded AI chatbot. It consists of:

- **Backend**: .NET 10 API (`src/backend/Novit.Web.Api/`) — chat, voice, contact form, nurturing newsletter system
- **Frontend**: Angular SSR (`src/frontend/`) — presentation slides + chat UI
- **Infrastructure**: Docker Compose (db, backend, frontend, caddy, calcom) on Oracle Cloud ARM VM

## Server & Deployment

- **Production URL**: `https://ia.novitsoftware.com`
- **Server**: Oracle Cloud ARM VM `158.101.19.139`, SSH user `ubuntu`, key file `ssh-key-2026-03-24.key` (in repo root)
- **Deploy**: Push to `master` → GitHub Actions (`deploy.yml`) → auto-deploy to server
- **⚠️ Application code and normal deploys must go through git push → GitHub Actions.**
- **Server-only secrets and runtime `.env` values that are intentionally not sourced from GitHub Actions may be managed directly on the server via SSH when needed.**
- SSH is for: checking logs, container status, DB queries, debugging, and managing server-only runtime configuration

### SSH Command Pattern

```bash
ssh -i ssh-key-2026-03-24.key ubuntu@158.101.19.139 "COMMAND"
```

### Docker Containers

| Container | Name |
|-----------|------|
| Backend | `web-novit-ai-backend-1` |
| Frontend | `web-novit-ai-frontend-1` |
| Database | `web-novit-ai-db-1` |
| Caddy | `web-novit-ai-caddy-1` |
| CalCom | `web-novit-ai-calcom-1` |

### Checking Logs

```bash
ssh -i ssh-key-2026-03-24.key ubuntu@158.101.19.139 "docker logs web-novit-ai-backend-1 --since 24h 2>&1 | tail -50"
```

## Nurturing Newsletter System — Operational Endpoints

The nurturing system sends a monthly AI-generated newsletter to Pipedrive leads. All admin endpoints are **protected by API key**.

### Authentication

All nurturing endpoints require the `X-Api-Key` header:

```
X-Api-Key: tiMzkDGgq8s4z17ys81bUMOydo4kRpUCwZPCYb75YoM
```

### Base URL

```
https://ia.novitsoftware.com/api/nurturing
```

### Available Endpoints

#### 1. Generate newsletter and send to reviewers

```bash
curl -X POST https://ia.novitsoftware.com/api/nurturing/trigger-review \
  -H "X-Api-Key: tiMzkDGgq8s4z17ys81bUMOydo4kRpUCwZPCYb75YoM"
```

**What it does**: Generates a new AI newsletter (using GPT-5.2 + web search), saves it to DB, and sends it as an HTML preview to the configured reviewers for validation. If a newsletter for the current month already exists, it updates the existing draft and increments the version.

**When to use**: When the user asks to generate/create a new newsletter, or to send it for review.

#### 2. Check reviewer feedback

```bash
curl -X POST https://ia.novitsoftware.com/api/nurturing/trigger-check-feedback \
  -H "X-Api-Key: tiMzkDGgq8s4z17ys81bUMOydo4kRpUCwZPCYb75YoM"
```

**What it does**: Reads the IMAP inbox for reviewer responses to `[REVISIÓN]` emails. Detects:
- **Hold requests** ("NO ENVIAR", "suspender", etc.) → puts newsletter on standby
- **Resume requests** ("REANUDAR", "ENVIAR", "aprobar") → resumes a held newsletter
- **Revision feedback** → revises newsletter with AI based on feedback, resends to reviewers

**When to use**: When the user asks to check if reviewers responded, or to process reviewer feedback.

#### 3. Send newsletter to leads

```bash
curl -X POST https://ia.novitsoftware.com/api/nurturing/trigger-send \
  -H "X-Api-Key: tiMzkDGgq8s4z17ys81bUMOydo4kRpUCwZPCYb75YoM"
```

**What it does**: Sends the current month's newsletter to all leads (from Pipedrive "Nurturing Automático" stage or RecipientOverride). Includes AI-personalized closings (using GPT-4o + Pipedrive deal history). Marks newsletter as sent.

- Add `?force=true` to send even if the newsletter is on hold.
- Uses human-like delays between sends (shorter than the background service).

**When to use**: When the user asks to send/dispatch/deliver the newsletter to leads/contacts.

#### 4. Check and respond to lead replies

```bash
curl -X POST https://ia.novitsoftware.com/api/nurturing/trigger-check-replies \
  -H "X-Api-Key: tiMzkDGgq8s4z17ys81bUMOydo4kRpUCwZPCYb75YoM"
```

**What it does**: Reads the IMAP inbox for unanswered replies from leads (not reviewers). For each reply, generates an AI response with GPT-4o and sends it. Also logs the conversation to the corresponding Pipedrive deal as a note.

**When to use**: When the user asks to check replies, check lead responses, or auto-respond to emails.

#### 5. Preview newsletter generation (no save, no send)

```bash
curl -X POST https://ia.novitsoftware.com/api/nurturing/test-generate \
  -H "X-Api-Key: tiMzkDGgq8s4z17ys81bUMOydo4kRpUCwZPCYb75YoM"
```

**What it does**: Generates a newsletter with AI but does NOT save it or send any emails. Returns the content as JSON for preview.

#### 6. List recipient contacts

```bash
curl -s https://ia.novitsoftware.com/api/nurturing/test-contacts \
  -H "X-Api-Key: tiMzkDGgq8s4z17ys81bUMOydo4kRpUCwZPCYb75YoM"
```

**What it does**: Returns the list of Pipedrive deals in the "Nurturing Automático" stage with their contact emails. Read-only, no emails sent.

**When to use**: When the user asks who will receive the newsletter, or to see the mailing list.

#### 7. Preview personalization

```bash
curl -s "https://ia.novitsoftware.com/api/nurturing/test-personalization?ai=true" \
  -H "X-Api-Key: tiMzkDGgq8s4z17ys81bUMOydo4kRpUCwZPCYb75YoM"
```

**What it does**: Shows how each contact's email would be personalized (greeting + closing). Add `?ai=true` to generate real AI closings using GPT-4o (slower but realistic). Without `?ai=true`, shows template-based closings only.

### Scheduled Background Flow

The `NurturingBackgroundService` runs automatically every ~3 hours on business days:

| When | What happens |
|------|-------------|
| Monday before last Wednesday | Generates newsletter, sends to reviewers |
| Mon–Wed (validation window) | Checks reviewer feedback every ~3h, revises if needed |
| Last Wednesday of the month | Sends newsletter to leads (auto-approves if no hold) |
| Every business day | Checks for unanswered lead replies, auto-responds |

All times are 11:00 AM Buenos Aires (UTC-3).

## AI Models

| Model | Used for | Endpoint |
|-------|----------|----------|
| GPT-5.4 | Newsletter generation, revision, scoring, extraction | `ai-novit.cognitiveservices.azure.com` |
| GPT-4o | Web chat, lead replies, AI closings | `ai-novit.cognitiveservices.azure.com` |

## Database

PostgreSQL in Docker (`web-novit-ai-db-1`). Credentials are in the server's `.env` file (`~/web-novit-ai/.env`).

### Finding credentials

```bash
ssh -i ssh-key-2026-03-24.key ubuntu@158.101.19.139 \
  "grep -iE 'postgres|ConnectionStrings' ~/web-novit-ai/.env"
```

### Querying the database

Use the username and database name from the `.env` connection string (currently `novit` / `novit`):

```bash
ssh -i ssh-key-2026-03-24.key ubuntu@158.101.19.139 \
  "docker exec web-novit-ai-db-1 psql -U novit -d novit -c 'YOUR SQL HERE;'"
```

### Tables

| Table | Purpose |
|-------|---------|
| `nurturing_emails` | Monthly newsletters (month_key, subject, body, version, is_sent, is_on_hold) |
| `conversations` | Chat conversations |
| `messages` | Chat messages |
| `leads` | Contact form leads |
| `rate_limits` | Rate limiting data |
| `__EFMigrationsHistory` | EF Core migrations tracking |

### Useful queries

```bash
# Check current newsletter status
ssh -i ssh-key-2026-03-24.key ubuntu@158.101.19.139 \
  "docker exec web-novit-ai-db-1 psql -U novit -d novit -c 'SELECT id, month_key, subject, version, is_sent, is_on_hold, sent_at FROM nurturing_emails ORDER BY created_at DESC LIMIT 5;'"

# List tables
ssh -i ssh-key-2026-03-24.key ubuntu@158.101.19.139 \
  "docker exec web-novit-ai-db-1 psql -U novit -d novit -c '\dt'"
```

### ⚠️ Important

- **Never hardcode DB credentials in code or docs.** Always read them from the server `.env` at runtime.
- If credentials change, check `~/web-novit-ai/.env` on the server.

## Build & Test

```bash
# Build backend
cd src/backend/Novit.Web.Api && dotnet build

# Run tests (70+ tests)
cd src/backend/Novit.Web.Api.Tests && dotnet test

# Frontend
cd src/frontend && npm install && ng serve
```

## Key Files

| File | Purpose |
|------|---------|
| `Services/NurturingBackgroundService.cs` | Scheduled newsletter flow (generation, feedback, send, replies) |
| `Services/NurturingMailService.cs` | IMAP/SMTP email sending with plain-text alternative |
| `Services/NurturingAIService.cs` | AI newsletter generation, revision, reply generation |
| `Controllers/NurturingController.cs` | Manual trigger endpoints + test/preview endpoints |
| `Services/AzureAIChatService.cs` | Web chatbot AI service |
| `Prompts/system-prompt-es.md` | Spanish system prompt for the chatbot |
| `Prompts/system-prompt-en.md` | English system prompt for the chatbot |
| `docker-compose.yml` | Full stack Docker Compose config |
| `Caddyfile` | Reverse proxy + TLS config |

## TODO / Future Refactors

### 🔧 Extract shared newsletter send logic (code duplication)

**Priority:** Medium — not urgent but increases maintenance risk over time.

**Problem:** The newsletter sending logic is duplicated between:
- `NurturingBackgroundService.SendNewsletterAsync()` (scheduled last-Wednesday flow)
- `NurturingController.TriggerSend()` (manual trigger endpoint)

Both independently implement: recipient fetching, AI closing generation, email personalization,
send loop with delays, RecipientOverride handling, and mark-as-sent logic. When we change
something in one (e.g. removing `status=open` filter, changing delay strategy), we need to
remember to update both.

**Solution:** Extract the shared send logic into a dedicated service (e.g. `NurturingEmailSender`)
that both the background service and the controller call, with parameters for test mode
(limit/offset/dealId) and delay strategy. The controller would pass test-mode options while
the background service would always use production settings.

**What's shared (should be extracted):**
- `GetRecipientsAsync` (exists in both — nearly identical)
- AI closing pre-generation loop
- Email send loop with personalization (WrapInHtmlEmail + closing selection)
- RecipientOverride redirect logic
- Mark-as-sent DB update

**What's different (should be parameterized):**
- Delay strategy: 2s (test) vs GetHumanLikeDelay() (production)
- limit/offset/dealId filtering (test only)
- dealId fallback via GetDealContactAsync (test only)
- HTTP response (controller returns IActionResult, background service just logs)
