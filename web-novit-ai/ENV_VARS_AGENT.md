# Environment Variables — AI Agent (Python / Community Manager)

> Variables needed for the **agent** service (Python/LangGraph).
> All are loaded from the shared `.env` file via `env_file: .env` in docker-compose.
> Variables shared with .NET are noted with 🔗.

## Current Novit Targets (May 2026)

These are the current deployment targets that should be wired into the shared server `.env`.
Do **not** commit real keys to git.

| Purpose | Endpoint | Deployment |
|---|---|---|
| Image generation (default / standard) | `https://rodri-mobw5zq6-eastus2.services.ai.azure.com` | `gpt-image-1-5` |
| Image generation (premium / optional) | configure explicitly in server `.env` | `gpt-image-2` |
| Video generation | `https://rodri-mobw5zq6-eastus2.services.ai.azure.com` | `sora-2-1` |
| Long-form text / content generation | Existing GPT-5.4 endpoint already configured outside this file | Existing deployment |
| Social replies / comment responses | Existing GPT-4o endpoint already configured outside this file | `gpt-4o-mini` recommended |

---

## 🔗 Shared (read by both .NET and Python)

| Variable | Required | Description |
|---|---|---|
| `INTERNAL_API_KEY` | ✅ prod | Shared secret for .NET ↔ Python internal API calls. Both services use it to authenticate `X-Internal-Key` header. Generate with `openssl rand -hex 32`. |
| `WEBHOOK_VERIFY_TOKEN` | ✅ if Meta webhooks | Token that Meta sends in the hub verification challenge. Must match what's configured in Meta App → Webhooks. |
| `META_APP_SECRET` | ✅ if Meta webhooks | Meta App Secret for HMAC-SHA256 webhook signature validation. |
| `NURTURING_V2_ENABLED` | ❌ | Feature flag. Set to `true` to delegate newsletter generation/revision/replies from .NET to Python agent. Default: `false` (original .NET nurturing). |

---

## 🤖 Azure AI Foundry — LLM (GPT-4o / GPT-4o-mini)

This is the lane for social replies / comment responses.
Per current Novit setup, keep using the existing GPT-4o endpoint already configured outside this file, and route the responder/comments to the cheaper mini deployment.

| Variable | Required | Default | Description |
|---|---|---|---|
| `AZURE_FOUNDRY_LLM_ENDPOINT` | ✅ | — | Azure AI Foundry endpoint, e.g. `https://ai-novit.cognitiveservices.azure.com` |
| `AZURE_FOUNDRY_LLM_API_KEY` | ✅ | — | API key for the endpoint |
| `AZURE_FOUNDRY_LLM_DEPLOYMENT` | ❌ | `gpt-4o` | Deployment name for the main model |
| `AZURE_FOUNDRY_LLM_API_VERSION` | ❌ | `2024-12-01-preview` | Azure API version |
| `AZURE_FOUNDRY_LLM_SMALL_DEPLOYMENT` | ❌ | `gpt-4o-mini` | Deployment name for the small/fast model |
| `AZURE_FOUNDRY_LLM_RESPONDER_DEPLOYMENT` | ❌ | `gpt-4o-mini` | Explicit deployment for IG/FB replies and comment responses. If omitted, the agent falls back to `AZURE_FOUNDRY_LLM_SMALL_DEPLOYMENT`. |

---

## 🎨 Azure AI Foundry — Image Generation

Current Novit default target: `gpt-image-1-5` on `https://rodri-mobw5zq6-eastus2.services.ai.azure.com`.
The agent can now route per publication between the standard lane (`image_1_5`) and a premium lane (`image_2`).
The standard lane defaults to high quality unless the strategy explicitly lowers it.

| Variable | Required | Default | Description |
|---|---|---|---|
| `AZURE_FOUNDRY_DALLE_ENDPOINT` | ❌ | — | Legacy/default image endpoint. Today this acts as the standard `image_1_5` lane if no explicit `..._15_...` vars are set. |
| `AZURE_FOUNDRY_DALLE_API_KEY` | ❌ | — | Legacy/default API key |
| `AZURE_FOUNDRY_DALLE_DEPLOYMENT` | ❌ | `gpt-image-1-5` | Legacy/default deployment. Today this should point to `gpt-image-1-5`. |
| `AZURE_FOUNDRY_DALLE_API_VERSION` | ❌ | `2025-04-01-preview` | Legacy/default API version |
| `AZURE_FOUNDRY_DALLE_15_ENDPOINT` | ❌ | — | Optional explicit endpoint for the standard `image_1_5` lane |
| `AZURE_FOUNDRY_DALLE_15_API_KEY` | ❌ | — | Optional explicit API key for `image_1_5` |
| `AZURE_FOUNDRY_DALLE_15_DEPLOYMENT` | ❌ | `gpt-image-1-5` | Optional explicit deployment for `image_1_5` |
| `AZURE_FOUNDRY_DALLE_15_API_VERSION` | ❌ | `2025-04-01-preview` | Optional explicit API version for `image_1_5` |
| `AZURE_FOUNDRY_DALLE_2_ENDPOINT` | ❌ | — | Optional premium endpoint for `image_2` |
| `AZURE_FOUNDRY_DALLE_2_API_KEY` | ❌ | — | Optional premium API key for `image_2` |
| `AZURE_FOUNDRY_DALLE_2_DEPLOYMENT` | ❌ | `gpt-image-2` | Optional premium deployment for `image_2` |
| `AZURE_FOUNDRY_DALLE_2_API_VERSION` | ❌ | `2025-04-01-preview` | Optional premium API version for `image_2` |
| `AZURE_FOUNDRY_DALLE_SIZE` | ❌ | `1024x1024` | Default size for both image lanes |
| `AZURE_FOUNDRY_DALLE_QUALITY` | ❌ | `high` | Default quality for both image lanes. The Strategist can override this per publication. |

---

## 🎬 Azure AI Foundry — Sora 2

Current Novit target: `sora-2-1` on `https://rodri-mobw5zq6-eastus2.services.ai.azure.com`.
If the portal still shows legacy `sora` as deprecated, don't use it for new setup.

| Variable | Required | Default | Description |
|---|---|---|---|
| `AZURE_FOUNDRY_SORA_ENDPOINT` | ❌ | — | Endpoint for Sora 2 video generation |
| `AZURE_FOUNDRY_SORA_API_KEY` | ❌ | — | API key |
| `AZURE_FOUNDRY_SORA_DEPLOYMENT` | ❌ | `sora` | Deployment name. Current Novit target: `sora-2-1` |

---

## 🪣 Azure Blob Storage — Temporary Social Media Hosting

Use this only for temporary publishable media that Meta/TikTok can fetch.
For Novit, these values should live directly in the shared server `.env`; they should not be sourced from the deploy workflow.

| Variable | Required | Default | Description |
|---|---|---|---|
| `AZURE_BLOB_STORAGE_ACCOUNT_NAME` | ✅ for Blob hosting | — | Storage account name used for temporary media hosting |
| `AZURE_BLOB_STORAGE_ACCOUNT_KEY` | ✅ for Blob hosting | — | Storage account key. Keep this only in the server `.env` |
| `AZURE_BLOB_STORAGE_CONTAINER_NAME` | ❌ | `social-publish-media` | Blob container used for temporary uploads |
| `AZURE_BLOB_STORAGE_SAS_EXPIRY_HOURS` | ❌ | `24` | Read-only SAS lifetime for generated media URLs |

---

## 📱 Meta Business API (Instagram / Facebook)

| Variable | Required | Default | Description |
|---|---|---|---|
| `META_ACCESS_TOKEN` | ❌ | — | Long-lived page access token for Instagram/Facebook publishing |
| `META_INSTAGRAM_ACCOUNT_ID` | ❌ | — | Instagram Business Account ID |
| `META_FACEBOOK_PAGE_ID` | ❌ | — | Facebook Page ID |

---

## 🎵 TikTok

| Variable | Required | Default | Description |
|---|---|---|---|
| `TIKTOK_ACCESS_TOKEN` | ❌ | — | TikTok access token for video publishing |
| `TIKTOK_OPEN_ID` | ❌ | — | TikTok Open ID |

---

## 🏢 Brand Identity

| Variable | Required | Default | Description |
|---|---|---|---|
| `BRAND_NAME` | ❌ | `Novit Software` | Brand name used in prompts |
| `BRAND_VOICE` | ❌ | `Professional yet approachable...` | Brand voice description for content generation |
| `BRAND_HASHTAGS` | ❌ | `#NovitSoftware,#Innovation,#AI,#Technology` | Comma-separated hashtags |

---

## 📰 Nurturing Newsletter AI (separate Azure endpoint)

Used when `NURTURING_V2_ENABLED=true` — the Python agent generates newsletters with a separate LLM.
Per current Novit setup, long-form content generation should continue using the existing GPT-5.4 endpoint that is already configured separately.

| Variable | Required | Default | Description |
|---|---|---|---|
| `NURTURING_NEWSLETTER_ENDPOINT` | ✅ if V2 | — | Azure endpoint for newsletter LLM, e.g. `https://rodri-mmdsfkug-eastus2.cognitiveservices.azure.com` |
| `NURTURING_NEWSLETTER_DEPLOYMENT` | ❌ | `gpt-52-chat` | Deployment name |
| `NURTURING_NEWSLETTER_KEY` | ✅ if V2 | — | API key for the newsletter endpoint |
| `NURTURING_NEWSLETTER_API_VERSION` | ❌ | `2025-04-01-preview` | API version |
| `NURTURING_SERPER_API_KEY` | ❌ | — | Serper.dev API key for web search during newsletter generation |

---

## 🔧 Internal / Infrastructure

| Variable | Required | Default | Description |
|---|---|---|---|
| `DOTNET_BASE_URL` | ❌ | `http://backend:5000` | .NET backend URL (set in docker-compose, don't add to .env) |
| `MEDIA_DIR` | ❌ | `./media` | Directory for generated media files (set in docker-compose) |
| `LOG_LEVEL` | ❌ | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## 📋 Example `.env` additions

```bash
# ── AI Agent (Community Manager) ──────────────────────────
INTERNAL_API_KEY=your-random-secret-here

# Azure AI Foundry — LLM
AZURE_FOUNDRY_LLM_ENDPOINT=https://ai-novit.cognitiveservices.azure.com
AZURE_FOUNDRY_LLM_API_KEY=your-key
AZURE_FOUNDRY_LLM_DEPLOYMENT=gpt-4o
AZURE_FOUNDRY_LLM_SMALL_DEPLOYMENT=gpt-4o-mini
AZURE_FOUNDRY_LLM_RESPONDER_DEPLOYMENT=gpt-4o-mini

# Azure AI Foundry — Image generation (standard / default)
AZURE_FOUNDRY_DALLE_ENDPOINT=https://rodri-mobw5zq6-eastus2.services.ai.azure.com
AZURE_FOUNDRY_DALLE_API_KEY=your-key
AZURE_FOUNDRY_DALLE_DEPLOYMENT=gpt-image-1-5
AZURE_FOUNDRY_DALLE_QUALITY=high

# Azure AI Foundry — Image generation (premium / optional)
AZURE_FOUNDRY_DALLE_2_ENDPOINT=https://your-image2-resource.services.ai.azure.com
AZURE_FOUNDRY_DALLE_2_API_KEY=your-image2-key
AZURE_FOUNDRY_DALLE_2_DEPLOYMENT=gpt-image-2

# Azure AI Foundry — Sora 2
AZURE_FOUNDRY_SORA_ENDPOINT=https://rodri-mobw5zq6-eastus2.services.ai.azure.com
AZURE_FOUNDRY_SORA_API_KEY=your-key
AZURE_FOUNDRY_SORA_DEPLOYMENT=sora-2-1

# Azure Blob Storage — temporary social media hosting
AZURE_BLOB_STORAGE_ACCOUNT_NAME=novitpublishmedia01
AZURE_BLOB_STORAGE_ACCOUNT_KEY=your-storage-key
AZURE_BLOB_STORAGE_CONTAINER_NAME=social-publish-media
AZURE_BLOB_STORAGE_SAS_EXPIRY_HOURS=24

# Meta Business API
META_ACCESS_TOKEN=your-meta-token
META_INSTAGRAM_ACCOUNT_ID=12345
META_FACEBOOK_PAGE_ID=67890
META_APP_SECRET=your-app-secret
WEBHOOK_VERIFY_TOKEN=your-verify-token

# Nurturing V2 (optional — enable to delegate newsletter to Python)
# NURTURING_V2_ENABLED=true
# NURTURING_NEWSLETTER_ENDPOINT=https://rodri-mmdsfkug-eastus2.cognitiveservices.azure.com
# NURTURING_NEWSLETTER_KEY=your-key
# NURTURING_SERPER_API_KEY=your-serper-key
```
