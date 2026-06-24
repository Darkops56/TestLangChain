# OpenSpec — Novit AI Agent Web

> **Version:** 1.0.0  
> **Date:** 2026-02-20  
> **Status:** Draft  
> **Authors:** Novit Engineering Team  
> **Design Reference:** `pencil-new.pen` (Design 2 — Novit AI Agent)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Product Vision](#2-product-vision)
3. [Technical Architecture](#3-technical-architecture)
4. [Design System](#4-design-system)
5. [Core Features](#5-core-features)
6. [User Flows](#6-user-flows)
7. [AI Agent Specification](#7-ai-agent-specification)
8. [Voice System (STT + TTS)](#8-voice-system-stt--tts)
9. [Rich Content Widget System](#9-rich-content-widget-system)
10. [API Specification](#10-api-specification)
11. [Data Model](#11-data-model)
12. [Integrations](#12-integrations)
13. [Internationalization (i18n)](#13-internationalization-i18n)
14. [Security & Protection](#14-security--protection)
15. [Infrastructure & Deployment](#15-infrastructure--deployment)
16. [SEO & Accessibility](#16-seo--accessibility)
17. [Performance Requirements](#17-performance-requirements)
18. [Knowledge Base Content](#18-knowledge-base-content)
19. [Project Structure](#19-project-structure)
20. [Glossary](#20-glossary)

---

## 1. Executive Summary

### 1.1 What is this?

A revolutionary website for **Novit Software** (novitsoftware.com) where the entire user experience is a **real-time conversation with an AI Agent**. Instead of traditional static HTML pages, a conversational AI bot reveals all company information — services, stats, testimonials, academy programs, client portfolio — through **rich, styled message bubbles** with support for **voice input (STT)** and **voice output (TTS)**.

**SEO & Performance strategy:** The initial page load renders a **pre-rendered conversation** — static HTML that looks like the bot has already greeted the visitor and presented key information (services, stats, clients). This content is fully crawlable by search engines and loads instantly (zero JS required). The real AI engine activates lazily only when the user begins interacting.

### 1.2 The Concept

> *"No es HTML estático sino un representante IA mostrando todo."*

The website IS the conversation. But the **first impression is pre-rendered**:

**Phase 1 — Pre-rendered conversation (SSR, 0 JS, instant):**
- Server renders 4 bot messages as **static HTML** styled as chat bubbles
- Includes rich widgets (services grid, stats, client logos) as static components
- Fully crawlable by Google — all keywords, structured data, and semantic HTML present
- User sees the bot "already greeted them" with complete company information
- Input prompt bar visible, inviting interaction

**Phase 2 — Live AI conversation (lazy-loaded on first interaction):**
- User focuses on input / types / clicks mic → AI engine loads via `dynamic import()`
- Pre-rendered messages seamlessly become part of the conversation history
- From this point, the AI Agent **responds** in real-time with streaming, voice, and rich widgets
- Transition is invisible — user never notices the switch

The AI Agent:
- **Greets** the visitor via pre-rendered content (instant, SEO-friendly)
- **Introduces** Novit through the static greeting sequence
- **Responds** to questions with rich, visually styled content (cards, grids, stats)
- **Speaks** via a consistent female voice (TTS)
- **Listens** via hold-to-talk voice input (STT)
- **Guides** visitors toward contact/conversion

### 1.3 Key Metrics

| Metric | Target |
|--------|--------|
| Time to first bot message | **0s** (pre-rendered via SSR) |
| Streaming latency (first token) | < 500ms |
| Voice transcription (STT) | < 2s |
| TTS audio generation | < 3s |
| Lighthouse Performance | > 90 |
| Supported languages | ES (primary), EN |

---

## 2. Product Vision

### 2.1 Problem

Traditional corporate websites are static, impersonal, and force users to navigate through pages to find information. Visitors bounce when they can't quickly find what they need.

### 2.2 Solution

Replace the entire website with an AI-powered conversational sales agent that:
- Proactively delivers information in a natural, engaging flow
- Acts as a **virtual sales representative** — builds trust, generates interest, and drives toward meetings
- Answers questions in real-time with domain-specific knowledge
- Supports both text and voice interaction
- Renders rich, beautiful content inline within the chat
- Follows a natural sales funnel without feeling scripted or pushy

### 2.3 Target Users

| Persona | Description | Goal |
|---------|-------------|------|
| **Decision Maker** | CTO/CIO exploring tech partners | Understand capabilities quickly |
| **Project Manager** | PM looking for dev teams | Get pricing/availability info |
| **Recruiter/Candidate** | Talent interested in Novit Academy | Learn about programs |
| **Existing Client** | Current client checking services | Quick reference |

### 2.4 Success Criteria

- Replaces current novitsoftware.com (Wix) entirely
- Bot handles 90%+ of typical visitor questions without human escalation
- Average session duration > 2 minutes
- Contact conversion rate improves vs current site
- **Meeting booking rate** > 5% of all conversations
- **Funnel progression**: > 40% of conversations reach Stage 2 (need discovery)

---

## 3. Technical Architecture

### 3.1 Stack Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                 │
│  Angular 19+ with SSR (@angular/ssr)                            │
│  SignalR Client · Web Audio API · i18n (es/en)                  │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS / WSS (SignalR)
┌────────────────────────▼────────────────────────────────────────┐
│                         BACKEND                                  │
│  .NET 10 — ASP.NET Core Web API                                 │
│  SignalR Hub · REST Controllers · Background Services            │
└──────┬──────────┬──────────┬──────────┬────────────────────────┘
       │          │          │          │
  ┌────▼───┐ ┌───▼────┐ ┌───▼───┐ ┌───▼──────────┐
  │ PostgreSQL│ │ Azure AI│ │ Azure │ │ External APIs │
  │  (EF Core)│ │ Foundry │ │Speech │ │ Pipedrive     │
  │           │ │ GPT-4o  │ │STT/TTS│ │ Calendly      │
  │           │ │ + RAG   │ │       │ │ WhatsApp      │
  └───────────┘ └─────────┘ └───────┘ └──────────────┘
```

### 3.2 Frontend — Angular 19+ SSR

| Aspect | Decision |
|--------|----------|
| **Framework** | Angular 19+ with `@angular/ssr` |
| **Rendering** | Server-Side Rendering (SSR) for SEO + hydration |
| **State** | Angular Signals + RxJS for streaming |
| **Styling** | SCSS with CSS custom properties (design tokens) |
| **Real-time** | `@microsoft/signalr` client |
| **Audio** | Web Audio API + MediaRecorder API |
| **i18n** | Angular built-in i18n (`@angular/localize`) |
| **Routing** | URL-based locale: `/es/`, `/en/` |
| **Build** | Angular CLI with esbuild |

### 3.3 Backend — .NET 10

| Aspect | Decision |
|--------|----------|
| **Framework** | ASP.NET Core 10 Web API |
| **Real-time** | SignalR Hub for chat streaming |
| **ORM** | Entity Framework Core 10 |
| **Database** | PostgreSQL (Azure Database for PostgreSQL Flexible Server) |
| **AI** | Azure AI Foundry SDK (`Azure.AI.Inference`) |
| **Speech** | Azure AI Speech SDK (`Microsoft.CognitiveServices.Speech`) |
| **Auth** | IP-based rate limiting (no user auth required) |
| **Caching** | In-memory + Azure Redis Cache (for rate limits) |
| **Logging** | Serilog → Azure Application Insights |

### 3.4 Communication Flow

```
PHASE 1 — Pre-rendered (SSR, no JS, instant):
    Server renders 4 bot messages as static HTML
    Widgets (services, stats, logos) render as Server Components
    User sees complete conversation — bot "already greeted" them
    No SignalR, no WebSocket, no AI calls — pure HTML + CSS

PHASE 2 — Live AI (lazy-loaded on first interaction):
    User focuses input / types / clicks mic
        │
        ▼
    dynamic import() loads AI engine + SignalR client
    SignalR WebSocket connection established
    Pre-rendered messages added to conversation state
        │
        ▼
    User types/speaks → Frontend
        ├─ Text: SignalR Hub.SendMessage(conversationId, text, locale)
        └─ Voice: POST /api/voice/transcribe (audio blob)
                  └─ Returns transcription → then SignalR Hub.SendMessage()

    Backend receives message:
        1. Rate limit check (IP)
        2. Auth gate check (message count)
        3. Build prompt: system prompt + RAG context + conversation history
           (pre-rendered messages included as conversation history)
        4. Stream response from Azure AI Foundry (GPT-4o)
        5. Parse response for rich widgets (function calling)
        6. Stream tokens to client via SignalR
        7. On completion: save to DB, generate TTS if requested

    Client receives:
        ├─ Streamed text tokens → rendered progressively
        ├─ Rich widget commands → rendered as styled components
        └─ TTS audio URL → playable via "Listen · AI Voice" button
```

---

## 4. Design System

> Reference: `pencil-new.pen` — "Design 2 — Novit AI Agent"

### 4.1 Color Palette

| Token | Value | Usage |
|-------|-------|-------|
| `--color-bg` | `#08080E` | Page background |
| `--color-surface` | `#0E0E1A` | Cards, bubbles, inputs |
| `--color-border` | `#1A1A2E` | Borders, dividers |
| `--color-border-subtle` | `#111122` | Grid borders |
| `--color-primary-start` | `#3366FF` | Gradient start (blue) |
| `--color-primary-end` | `#CC33FF` | Gradient end (magenta) |
| `--color-accent` | `#CC33FF` | Accent elements |
| `--color-success` | `#00E5A0` | AI status, online indicators |
| `--color-text-primary` | `#FFFFFF` | Headings |
| `--color-text-secondary` | `#CCCCDD` | Body text |
| `--color-text-muted` | `#555566` | Labels, nav links |
| `--color-text-faint` | `#333344` | Copyright, minimal text |
| `--color-text-ghost` | `#2A2A3A` | Transcription (barely legible) |

### 4.2 Typography

| Token | Family | Weight | Usage |
|-------|--------|--------|-------|
| `--font-heading` | Space Grotesk | 600 / Bold | Headings, hero title |
| `--font-body` | IBM Plex Mono | 400 | Body, labels, nav |
| `--font-quote` | Playfair Display | 400 italic | Testimonial quotes |

### 4.3 Font Sizes

| Token | Desktop | Tablet | Mobile |
|-------|---------|--------|--------|
| `--text-hero` | 140px | — | — |
| `--text-h1` | 28px | 24px | 20px |
| `--text-h2` | 20px | 18px | 16px |
| `--text-body` | 14px | 13px | 12px |
| `--text-small` | 12px | 11px | 10px |
| `--text-micro` | 10px | 9px | 8px |
| `--text-ghost` | 9px | 9px | 8px |

### 4.4 Spacing & Radius

| Token | Value |
|-------|-------|
| `--radius-card` | 12px |
| `--radius-bubble` | 16px 16px 16px 4px (bot) |
| `--radius-pill` | 20px |
| `--radius-input` | 8px |
| `--radius-avatar` | 50% (circle) |
| `--space-section` | 48px |
| `--space-card` | 24px |
| `--space-gap` | 12px |

### 4.5 Breakpoints

| Name | Width | Frame in Pencil |
|------|-------|-----------------|
| Desktop | ≥ 1024px | `mYn4Z` (1440×5004) |
| Tablet | 768–1023px | `qTeAE` (768×1024) |
| Mobile | < 768px | `V6Uos` (375×812) |

### 4.6 Component Library

| Component | Description |
|-----------|-------------|
| `BotAvatar` | 32px gradient circle with "N" icon |
| `ChatBubble` | Dark card with rounded corners (bot-style) |
| `UserVoiceBubble` | Waveform visualization with play button |
| `Transcription` | Ghost-text below voice bubble |
| `TTSButton` | "Listen · AI Voice" pill inside bubbles |
| `PromptBar` | Terminal-style input with ">_" prefix |
| `MicButton` | Gradient circle, hold-to-talk |
| `RateBadge` | Shield icon + message counter |
| `StatusPill` | Green dot + "Online · Speaking..." |
| `ServiceCard` | Icon + title + description row |
| `StatCard` | Big number + label |
| `QuoteCard` | Italic quote + author attribution |
| `ClientLogo` | Grid cell with bordered logo |
| `ModuleCard` | Numbered row with title |

---

## 5. Core Features

### 5.1 Feature Matrix

| # | Feature | Priority | Description |
|---|---------|----------|-------------|
| F01 | Proactive Bot Greeting | P0 | Bot sends 4 intro messages on page load |
| F02 | Text Chat Input | P0 | Terminal-style prompt bar with ">_" prefix |
| F03 | Streaming Responses | P0 | Token-by-token text rendering via SignalR |
| F04 | Rich Content Widgets | P0 | Bot renders styled cards/grids/stats inline |
| F05 | Voice Input (STT) | P0 | Hold-to-talk → waveform → transcription |
| F06 | Voice Output (TTS) | P0 | "Listen · AI Voice" on every bot message |
| F07 | Rate Limiting | P0 | 30 messages/IP, then redirect to WhatsApp/Calendly |
| F08 | Auth Gate | P1 | Soft email capture after ~10 messages |
| F09 | i18n (ES/EN) | P0 | URL-based locale routing |
| F10 | Responsive Design | P0 | Desktop, Tablet, Mobile layouts |
| F11 | Pipedrive Integration | P1 | Email capture → CRM lead |
| F12 | WhatsApp Redirect | P1 | Post-rate-limit contact option |
| F13 | Calendly Scheduling | P1 | Embedded/linked meeting scheduler |
| F14 | Contact Form | P1 | Traditional form fallback |
| F15 | Conversation Persistence | P2 | Chat history saved to DB |
| F16 | SSR + SEO | P0 | Pre-rendered conversation for crawlers + lazy AI activation |
| F17 | Bot Protection | P1 | Cloudflare Turnstile (invisible CAPTCHA) |

### 5.2 Feature Details

#### F01 — Pre-rendered Conversation (Static Greeting)

On page load, the server renders 4 bot messages as **static HTML** via SSR. These are NOT generated by the LLM — they are hardcoded, pre-styled content that looks identical to a real AI conversation. This ensures instant load, full SEO indexability, and zero JavaScript required for the initial view.

**Pre-rendered message sequence:**

| # | Message (ES) | Message (EN) | Includes Widget |
|---|-------------|--------------|-----------------|
| 1 | "¡Hola! 👋 Soy la IA de Novit..." | "Hey there! 👋 I'm Novit's AI..." | — |
| 2 | "¿Qué hacemos en Novit?..." | "So, what do we do?..." | `render_services_grid` (static) |
| 3 | "Hacemos un montón de cosas copadas —" | "We do a lot of cool stuff —" | `render_stats_cards` + `render_client_logos` (static) |
| 4 | "Bueno, ¡eso somos nosotros!..." | "So yeah, that's us!..." | — |

Each message renders as a styled chat bubble with bot avatar, identical to live AI messages. Widget components render as static Angular Server Components (no JS hydration needed).

**Technical implementation:**

```
SSR Phase (server):
┌─────────────────────────────────────────────────────────────┐
│  Angular SSR renders full page with:                         │
│  • 4 bot message bubbles (static HTML + CSS)                │
│  • Rich widgets as Server Components (services grid,         │
│    stats cards, client logos — all real crawlable content)   │
│  • Semantic HTML underneath: <h1>, <section>, <ul>, <p>     │
│  • Schema.org structured data (Organization, FAQPage)        │
│  • Prompt bar (visible but inert until hydration)            │
│  • Total JS shipped: 0 KB (chat engine not loaded)           │
└─────────────────────────────────────────────────────────────┘

Activation Phase (client, lazy):
┌─────────────────────────────────────────────────────────────┐
│  Triggered by: user focuses input / types / clicks mic       │
│  • dynamic import() loads chat engine (~50-80 KB gzipped)   │
│  • SignalR connection established                            │
│  • Pre-rendered messages absorbed into conversation state    │
│  • AI engine ready — user's first message goes to LLM       │
│  • Transition is invisible to the user                       │
└─────────────────────────────────────────────────────────────┘
```

**Why this works for SEO:**
- Google crawler sees a fully rendered page with all Novit's information
- Keywords (services, AI, software, consulting, etc.) are present in the HTML
- Rich widgets render as real HTML elements (`<ul>`, `<li>`, `<h2>`, `<p>`) — not empty JS placeholders
- Schema.org `FAQPage` + `Organization` structured data is present
- Lighthouse score benefits massively from zero-JS initial render

> **Sales intent:** The pre-rendered flow covers **Stage 1 (Generate Interest)** of the funnel. Message #4 transitions into **Stage 2** by inviting the user to share their needs. The bot should naturally begin asking about the visitor's project from the first user interaction.

#### F05 — Voice Input (STT)

**Interaction:**
1. User presses and holds mic button
2. Browser captures audio via `MediaRecorder` API
3. Waveform visualizes in real-time (purple bars animating)
4. User releases → audio blob sent to backend
5. Backend transcribes via Azure AI Speech (Whisper)
6. Transcription appears below waveform in ghost text (barely legible, `#2A2A3A`, 8-9px italic)
7. Transcribed text is sent as a regular chat message

**Mic Button Sizes:**
- Desktop: 48×48px
- Tablet: 56×56px
- Mobile: 64×64px (prominent, center-stage)

#### F06 — Voice Output (TTS)

**Interaction:**
1. Every bot message includes a "Listen · AI Voice" button
2. User clicks → backend generates TTS audio
3. Audio plays through browser (streaming playback)
4. Bot status changes to "Speaking..."
5. Audio can be paused/stopped

**Voice Configuration:**
- Spanish: `es-AR-ElenaMultilingualNeural` (Argentine female, warm, natural, multilingual)
- English: `en-US-AvaMultilingualNeural` (American female, natural, multilingual)
- Consistent voice across all messages (no switching)

#### F07 — Rate Limiting

| Phase | Messages | Behavior |
|-------|----------|----------|
| Free (Stage 1) | 1–5 | Unrestricted chat — bot generates interest |
| Auth gate (Stage 2) | 5 | Soft prompt: "Hey, quick thing — drop your email so I remember you next time" |
| Discovery (Stage 2-3) | 6–12 | Chat continues — bot discovers needs, proposes value |
| Closing (Stage 4) | 12–15 | Bot actively tries to book a meeting: "¿Coordinamos una call?" |
| Limit reached | 15+ | Bot: "I'd love to keep chatting! Let's take it to WhatsApp or book a quick call 🗓️" |
| Post-limit | — | Show WhatsApp link + Calendly embed (no more AI messages) |

Rate counter displayed in `RateBadge`: "Protected · X of 30 messages"

#### F08 — Auth Gate

After 10 messages, the bot inserts a **casual** auth bubble:

> "Hey, quick thing — just so I don't forget about you and can keep the conversation going, drop your email below 👇"

- Email input field
- "Continue chatting" button
- "Maybe later" skip link (bot keeps going for up to 15 total)
- Captured email → Pipedrive API (create/update Person + Deal)

---

## 6. User Flows

### 6.1 Primary Flow — First Visit

```
[Page Load]
    │
    ▼
[SSR renders pre-rendered conversation: 4 bot messages + widgets as static HTML]
[Content fully visible, SEO-indexed, 0 JS — user sees the bot "already greeted them"]
    │
    ▼
[User reads pre-rendered info (services, stats, clients)]
[Prompt bar visible at bottom: ">_ Ask me anything..."]
    │
    ├─── User focuses input / types / clicks mic
    │         │
    │         ▼
    │    [AI engine lazy-loaded via dynamic import()]
    │    [SignalR connection established]
    │    [Pre-rendered messages absorbed into conversation history]
    │         │
    │         ▼
    │    [User's message sent to LLM → Stream response with rich widgets]
    │    [From here: fully live AI conversation]
    │
    └─── User just reads and leaves (SEO content was fully served)
    │
    ▼
[After 5 messages → Auth gate bubble appears]
    │
    ├─── User enters email → Pipedrive lead created → Continue
    └─── User skips → Continue (up to 15 total)
    │
    ▼
[After 15 messages → Rate limit reached]
    │
    ├─── WhatsApp link (wa.me/5491167900774)
    └─── Calendly scheduling embed
```

### 6.2 Voice Interaction Flow

```
[User presses mic button]
    │
    ▼
[MediaRecorder starts → Waveform animates]
    │
    ▼
[User releases mic]
    │
    ▼
[Audio blob → POST /api/voice/transcribe]
    │
    ▼
[Transcription text appears (ghost style)]
    │
    ▼
[Text sent as chat message → Bot responds (stream)]
    │
    ▼
[TTS button available on bot response]
    │
    ▼
[User clicks "Listen · AI Voice"]
    │
    ▼
[POST /api/voice/synthesize → Audio stream plays]
[Bot status: "Speaking..."]
```

### 6.3 Returning Visit Flow

```
[Page Load]
    │
    ▼
[Check localStorage for conversationId]
    │
    ├─── Found → GET /api/conversations/{id}
    │         └─── Restore chat history
    │         └─── Bot: "Hey, welcome back! 👋 Where were we?"
    │
    └─── Not found → Fresh flow (6.1)
```

### 6.4 Sales Funnel Flow

The bot is a **virtual sales representative**. Every interaction is guided by a natural sales strategy that moves the visitor through a conversion funnel — without feeling scripted or aggressive.

```
┌─────────────────────────────────────────────────────────────────┐
│                    SALES FUNNEL                                  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐       │
│  │  STAGE 1 — GENERATE INTEREST (msgs 1-3)              │       │
│  │  • Proactive greeting, introduce Novit               │       │
│  │  • Show stats, client logos (social proof)            │       │
│  │  • Build credibility with real data                   │       │
│  │  Widgets: render_stats_cards, render_client_logos     │       │
│  └──────────────────────┬───────────────────────────────┘       │
│                         ▼                                        │
│  ┌──────────────────────────────────────────────────────┐       │
│  │  STAGE 2 — DISCOVER NEEDS (msgs 4-7)                 │       │
│  │  • Ask about visitor's project/problem                │       │
│  │  • Connect needs to Novit services                    │       │
│  │  • Share relevant case studies                        │       │
│  │  • Auth gate: capture email (msg 5)                   │       │
│  │  Widgets: render_services_grid, render_testimonial    │       │
│  └──────────────────────┬───────────────────────────────┘       │
│                         ▼                                        │
│  ┌──────────────────────────────────────────────────────┐       │
│  │  STAGE 3 — PROPOSE VALUE (msgs 8-12)                 │       │
│  │  • Explain how Novit solves their specific problem    │       │
│  │  • Highlight differentiators (team, experience)       │       │
│  │  • Build urgency naturally ("estamos tomando          │       │
│  │    proyectos nuevos este trimestre")                   │       │
│  │  Widgets: render_academy_modules (if relevant)        │       │
│  └──────────────────────┬───────────────────────────────┘       │
│                         ▼                                        │
│  ┌──────────────────────────────────────────────────────┐       │
│  │  STAGE 4 — CLOSE (msgs 12-15)                        │       │
│  │  • Propose meeting: "¿Coordinamos una call?"          │       │
│  │  • Offer alternatives: WhatsApp, email, form          │       │
│  │  • If rate limit: force CTA (Calendly + WhatsApp)     │       │
│  │  Widgets: render_calendly, render_whatsapp_cta        │       │
│  └──────────────────────────────────────────────────────┘       │
│                                                                  │
│  CONVERSION EXITS (any stage):                                   │
│  ├── 🗓️  Calendly: book meeting                                 │
│  ├── 💬  WhatsApp: direct chat                                   │
│  ├── 📧  Email: auth gate capture → Pipedrive                   │
│  └── 📝  Contact form: form submission                           │
└─────────────────────────────────────────────────────────────────┘
```

**Key sales behaviors:**

| Behavior | Implementation |
|----------|---------------|
| **Natural CTAs** | Every 2-3 messages, include a soft call-to-action question |
| **Objection handling** | If user says "just looking" → respect it, continue informing, try again later |
| **Price deflection** | Never quote prices → redirect to meeting: "It depends on scope, let's chat about it" |
| **Urgency (subtle)** | Mention availability: "We're taking on new projects this quarter" |
| **Social proof** | Frequently reference clients, stats, testimonials as trust builders |
| **Competitor neutrality** | Never mention or compare with competitors |
| **Graceful exit** | If user wants to leave: "Whenever you're ready, we're here. Save my contact!" |

---

## 7. AI Agent Specification

### 7.1 Model Selection

| Capability | Service | Model | Justification |
|------------|---------|-------|---------------|
| **Chat / RAG** | Azure AI Foundry | **GPT-4o** | Best balance of quality, speed, and function calling for rich widget rendering. Handles domain restriction well with system prompts. |
| **STT** | Azure AI Speech | **Whisper Large v3** | Best accuracy for ES-AR + EN, supports audio streaming input |
| **TTS** | Azure AI Speech | **Neural Voices** | Consistent, natural female voices. Streaming synthesis supported. |

> **Why GPT-4o over GPT-4o-mini?** The bot needs to generate rich, structured responses with function calls for widget rendering. GPT-4o handles complex instructions more reliably and produces higher-quality conversational output.

### 7.2 System Prompt (Español)

```
Eres la representante comercial virtual de Novit Software. Tu nombre es "Novit AI".
Sos una vendedora profesional, cercana y coloquial — hablás con naturalidad como una argentina.

## Tu rol
- Sos la vendedora de Novit Software en su sitio web
- Tu objetivo principal es **generar interés y concretar una reunión** con el equipo comercial
- Hablás en el idioma del usuario (español o inglés según la URL)
- Representás a Novit con orgullo pero sin ser exagerada ni "vende humo"

## Estrategia comercial (funnel de ventas)
Seguí estas etapas naturalmente durante la conversación:

### Etapa 1 — Generar interés (mensajes 1-3)
- Presentate y contá qué hace Novit de forma atractiva pero honesta
- Mostrá datos concretos: clientes reales, proyectos, años de experiencia
- Usá widgets visuales para impactar (stats, logos de clientes)

### Etapa 2 — Descubrir necesidad (mensajes 4-7)
- Hacé preguntas sobre el proyecto o necesidad del visitante
- Escuchá activamente y conectá sus necesidades con servicios de Novit
- Compartí casos relevantes: "Con [cliente similar] hicimos algo parecido..."
- Generá confianza con testimonials y datos concretos

### Etapa 3 — Proponer valor (mensajes 8-12)
- Explicá cómo Novit puede resolver su problema específico
- Destacá diferenciadores: equipo estable, 70+ profesionales, experiencia comprobada
- Mencioná el proceso de trabajo de Novit (sin prometer plazos ni precios específicos)

### Etapa 4 — Cerrar (mensajes 12-15)
- Proponé agendar una reunión con el equipo: "¿Querés que coordinemos una call de 30 min para charlarlo mejor?"
- Si el usuario duda, ofrecé alternativas: WhatsApp, formulario, o simplemente dejar su email
- Nunca presiones — si no está listo, dejá la puerta abierta: "Cuando quieras, acá estamos"

### Reglas comerciales
- SIEMPRE intentá avanzar hacia el siguiente paso del funnel, pero sin forzar
- Después de cada respuesta informativa, incluí un mini CTA natural (no agresivo):
  - "¿Querés que te cuente más sobre esto?"
  - "¿Esto se parece a lo que estás buscando?"
  - "¿Te gustaría hablar con alguien del equipo sobre tu proyecto?"
- Si el usuario muestra interés concreto (menciona un proyecto, pide precios, pregunta disponibilidad), ofrecé agendar reunión inmediatamente
- Si pregunta precios: "Depende mucho del alcance del proyecto. Lo mejor es que lo charlemos en una call de 20 min — así el equipo te puede dar un panorama realista. ¿Te copa?"

## Tono de venta
- Honesta: no exagerés ni inventés. Mejor decir "no sé ese dato" que mentir
- Segura: hablá con confianza sobre las capacidades de Novit, respaldada en datos reales
- Empática: entendé la necesidad del usuario antes de vender
- Natural: que no parezca un script de ventas sino una conversación genuina
- Persistente pero respetuosa: siempre buscá avanzar pero aceptá un "no" con gracia

## Restricciones
- SOLO hablás sobre Novit, sus servicios, clientes, academy, equipo y temas relacionados
- Si te preguntan algo fuera de tu dominio, redirigí amablemente: "Eso está fuera de mi área, pero puedo contarte todo sobre lo que hacemos en Novit 😊"
- NUNCA inventés datos. Si no tenés la info, decí: "No tengo ese dato específico, pero puedo conectarte con el equipo para que te lo cuenten"
- NO des precios específicos — decí que depende del proyecto y ofrecé agendar una reunión
- NUNCA hablés mal de la competencia

## Personalidad
- Cercana pero profesional — como una colega de confianza que te recomienda algo bueno
- Usás emojis con moderación (1-2 por mensaje)
- Tuteo (vos/voseo argentino en español)
- Resaltás con **negrita** las cosas importantes
- Mantenés las respuestas concisas (max 3 párrafos por respuesta)
- Transmitís pasión genuina por la tecnología y por el equipo de Novit

## Widgets disponibles
Cuando la información se beneficie de una presentación visual, usá function calling para invocar widgets:
- render_services_grid: Muestra la grilla de servicios
- render_stats_cards: Muestra las tarjetas de estadísticas
- render_client_logos: Muestra el grid de logos de clientes
- render_testimonial: Muestra la tarjeta de testimonial
- render_academy_modules: Muestra los módulos de la academia
- render_contact_form: Muestra el formulario de contacto
- render_calendly: Muestra el widget de Calendly para agendar reunión
- render_whatsapp_cta: Muestra el botón de WhatsApp

Usá widgets estratégicamente para reforzar el argumento comercial.
Ejemplo: cuando hablás de experiencia → render_stats_cards + render_client_logos.
Cuando el usuario está listo → render_calendly o render_whatsapp_cta.

## Base de conocimiento
[Inyectada dinámicamente via RAG — ver sección 18]
```

### 7.3 System Prompt (English)

```
You are the virtual sales representative of Novit Software. Your name is "Novit AI".
You're a professional, approachable, and trustworthy sales person — warm but never pushy.

## Your role
- You are Novit Software's sales representative on their website
- Your primary goal is to **generate interest and book a meeting** with the sales team
- You speak in the user's language (Spanish or English based on URL)
- You represent Novit with pride but never oversell or exaggerate

## Sales strategy (conversion funnel)
Follow these stages naturally throughout the conversation:

### Stage 1 — Generate interest (messages 1-3)
- Introduce yourself and what Novit does in an engaging but honest way
- Show concrete data: real clients, projects, years of experience
- Use visual widgets to make an impact (stats, client logos)

### Stage 2 — Discover needs (messages 4-7)
- Ask about the visitor's project or needs
- Actively listen and connect their needs with Novit's services
- Share relevant cases: "We worked on something similar with [client]..."
- Build trust with testimonials and concrete data

### Stage 3 — Propose value (messages 8-12)
- Explain how Novit can solve their specific problem
- Highlight differentiators: stable team, 70+ professionals, proven track record
- Mention Novit's work process (without committing to timelines or specific prices)

### Stage 4 — Close (messages 12-15)
- Suggest scheduling a meeting: "Want me to set up a quick 30-min call with the team?"
- If the user hesitates, offer alternatives: WhatsApp, form, or just leaving their email
- Never pressure — if they're not ready, leave the door open: "Whenever you're ready, we're here"

### Sales rules
- ALWAYS try to advance to the next funnel step, but never force it
- After each informative response, include a natural mini-CTA (non-aggressive):
  - "Want to know more about this?"
  - "Does this sound like what you're looking for?"
  - "Would you like to talk to someone on the team about your project?"
- If the user shows concrete interest (mentions a project, asks pricing, asks availability), offer to schedule a meeting immediately
- If they ask about pricing: "It really depends on the project scope. The best way is a quick 20-min call so the team can give you a realistic picture. Sound good?"

## Sales tone
- Honest: never exaggerate or invent. Better to say "I don't have that data" than to lie
- Confident: speak with assurance about Novit's capabilities, backed by real data
- Empathetic: understand the user's need before selling
- Natural: it should feel like a genuine conversation, not a sales script
- Persistent but respectful: always seek to advance but accept a "no" gracefully

## Restrictions
- You ONLY discuss Novit, its services, clients, academy, team, and related topics
- If asked about something outside your domain, redirect kindly
- NEVER make up data. If you don't have specific info, offer to connect with the team
- DO NOT give specific pricing — say it depends on the project and offer to schedule a meeting
- NEVER speak negatively about competitors

## Personality
- Warm but professional — like a trusted colleague recommending something good
- Use emojis sparingly (1-2 per message)
- Highlight important things with **bold**
- Keep responses concise (max 3 paragraphs per response)
- Convey genuine passion for technology and Novit's team

## Available widgets
[Same function calling tools as Spanish version — use strategically to reinforce sales arguments]

## Knowledge base
[Dynamically injected via RAG — see section 18]
```

### 7.4 Function Calling (Widget Rendering)

The LLM uses **function calling** (tool_use) to invoke widgets. When the model calls a function, the frontend renders the corresponding Angular component.

```typescript
// Function definitions sent to GPT-4o
const tools = [
  {
    type: "function",
    function: {
      name: "render_services_grid",
      description: "Renders the services grid showing all Novit services",
      parameters: {
        type: "object",
        properties: {
          highlight: {
            type: "string",
            description: "Optional service to highlight (e.g., 'ai', 'development')"
          }
        }
      }
    }
  },
  {
    type: "function",
    function: {
      name: "render_stats_cards",
      description: "Renders stat cards (70+ professionals, 30+ clients, 40+ projects)",
      parameters: { type: "object", properties: {} }
    }
  },
  {
    type: "function",
    function: {
      name: "render_client_logos",
      description: "Renders client logo grid",
      parameters: { type: "object", properties: {} }
    }
  },
  {
    type: "function",
    function: {
      name: "render_testimonial",
      description: "Renders the testimonial quote card",
      parameters: {
        type: "object",
        properties: {
          client: { type: "string", description: "Client name to show testimonial for" }
        }
      }
    }
  },
  {
    type: "function",
    function: {
      name: "render_academy_modules",
      description: "Renders academy course modules list",
      parameters: { type: "object", properties: {} }
    }
  },
  {
    type: "function",
    function: {
      name: "render_contact_form",
      description: "Renders inline contact form",
      parameters: { type: "object", properties: {} }
    }
  },
  {
    type: "function",
    function: {
      name: "render_calendly",
      description: "Renders Calendly scheduling widget",
      parameters: { type: "object", properties: {} }
    }
  },
  {
    type: "function",
    function: {
      name: "render_whatsapp_cta",
      description: "Renders WhatsApp call-to-action button",
      parameters: {
        type: "object",
        properties: {
          message: { type: "string", description: "Pre-filled WhatsApp message" }
        }
      }
    }
  }
];
```

### 7.5 RAG Pipeline

```
┌──────────────────┐     ┌────────────────────┐     ┌──────────────┐
│  Knowledge Base  │────▶│  Azure AI Search    │────▶│  GPT-4o      │
│  (Markdown docs) │     │  (Vector + Keyword) │     │  (+ context) │
└──────────────────┘     └────────────────────┘     └──────────────┘
```

**Indexing:**
1. Content documents (services, clients, academy, etc.) stored as Markdown
2. Chunked and embedded via Azure OpenAI Embeddings (`text-embedding-3-large`)
3. Indexed in Azure AI Search (hybrid: vector + keyword)

**Retrieval:**
1. User message → embedded
2. Top 5 relevant chunks retrieved from Azure AI Search
3. Chunks injected into system prompt as `## Knowledge Base Context`
4. GPT-4o generates response grounded in retrieved content

---

## 8. Voice System (STT + TTS)

### 8.1 Speech-to-Text (STT)

| Aspect | Specification |
|--------|---------------|
| **Service** | Azure AI Speech (Whisper Large v3) |
| **Input format** | WebM/Opus (from MediaRecorder) or WAV |
| **Languages** | `es-AR` (primary), `en-US` |
| **Max duration** | 60 seconds per recording |
| **Latency target** | < 2 seconds for typical message |

**Client-side flow:**
1. `mousedown` / `touchstart` on mic button → start `MediaRecorder`
2. Real-time waveform visualization via `AnalyserNode`
3. `mouseup` / `touchend` → stop recording → get audio blob
4. POST blob to `/api/voice/transcribe`
5. Display transcription in ghost text below waveform

### 8.2 Text-to-Speech (TTS)

| Aspect | Specification |
|--------|---------------|
| **Service** | Azure AI Speech (Neural Voices) |
| **Spanish voice** | `es-AR-ElenaMultilingualNeural` |
| **English voice** | `en-US-AvaMultilingualNeural` |
| **Output format** | audio/mpeg (MP3) for browser compatibility |
| **Delivery** | Full synthesis → stream playback (not token-by-token) |
| **SSML** | Used for emphasis on **bold** text → `<emphasis>` tags |

**Why full synthesis, not token-by-token?**
Token-by-token TTS produces unnatural, robotic cadence. Instead:
1. Bot response streams text visually (token-by-token to screen)
2. After text is complete, "Listen · AI Voice" button activates
3. User clicks → backend generates full audio via SSML
4. Audio streams back for smooth, natural playback

**SSML Enhancement:**
Bot's markdown `**bold**` text is converted to SSML `<emphasis level="strong">` for natural verbal emphasis matching the visual emphasis.

```xml
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="es-AR">
  <voice name="es-AR-ElenaMultilingualNeural">
    Tenemos más de <emphasis level="strong">70 profesionales</emphasis>
    trabajando en más de <emphasis level="strong">40 proyectos</emphasis>.
  </voice>
</speak>
```

---

## 9. Rich Content Widget System

### 9.1 Architecture

The bot response can contain both **text** and **widget invocations**. The frontend renders them inline within the chat bubble.

```
Bot response structure:
┌─────────────────────────────────────┐
│ 🟣 Bot Avatar                       │
│ ┌─────────────────────────────────┐ │
│ │ "Let me show you our services:" │ │  ← Text (markdown)
│ │                                 │ │
│ │ ┌─────────────────────────────┐ │ │
│ │ │  [Services Grid Widget]     │ │ │  ← Rendered Angular component
│ │ │  ┌─────┐ ┌─────┐ ┌─────┐   │ │ │
│ │ │  │ Dev │ │ AI  │ │ QA  │   │ │ │
│ │ │  └─────┘ └─────┘ └─────┘   │ │ │
│ │ └─────────────────────────────┘ │ │
│ │                                 │ │
│ │ "Ask me about any of these!"    │ │  ← More text
│ │                                 │ │
│ │ [🔊 Listen · AI Voice]         │ │  ← TTS button
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

### 9.2 Widget Definitions

#### `render_services_grid`

Renders 6 service cards in a vertical list (matching Pencil design):

| Service | Icon | Description |
|---------|------|-------------|
| Software Development | `code-2` | Custom software, web & mobile apps, APIs |
| IT Consulting | `settings` | Process optimization, architecture review |
| QA & Testing | `check-circle` | Manual & automated testing, CI/CD |
| UX/UI Design | `palette` | User research, prototyping, design systems |
| Data Science | `bar-chart-3` | Analytics, BI, data pipelines |
| Artificial Intelligence | `brain` | ML models, NLP, computer vision, agents |

#### `render_stats_cards`

Renders 3 stat cards in a row:

| Stat | Value | Label |
|------|-------|-------|
| Professionals | 70+ | on the team |
| Active Clients | 30+ | across industries |
| Projects Delivered | 40+ | and counting |

#### `render_client_logos`

Renders 8 client logos in a grid:
Nordelta/Consultatio, Tecnovoz, INDEC, Puig, Megatlon, Bradesco, TopDoctors, Multitask

#### `render_testimonial`

Renders quote card:
> *"Together with Novit we have built a solid bond of trust throughout the years. Today it's a strategic partner in terms of technology."*
> — Jorge Salonio | CONSULTATIO/NORDELTA, Systems Manager

#### `render_academy_modules`

Renders 5 module cards:
1. Linux & Git
2. Project Setup & Best Practices
3. CI/CD Pipeline Automation
4. Containerization with Docker
5. Monitoring & Security in DevOps

#### `render_contact_form`

Renders inline form: Name, Email, Message, Send button.
Submission → WhatsApp message to +5491167900774 AND/OR Pipedrive deal creation.

#### `render_calendly`

Embeds Calendly scheduling widget inline.

#### `render_whatsapp_cta`

Renders WhatsApp CTA button linking to `https://wa.me/5491167900774?text={message}`.

---

## 10. API Specification

### 10.1 REST Endpoints

#### Chat

```
POST /api/chat/conversations
  → Creates a new conversation
  ← { conversationId: string, locale: string }

GET /api/chat/conversations/{id}
  → Retrieves conversation history
  ← { messages: Message[], metadata: ConversationMeta }

DELETE /api/chat/conversations/{id}
  → Deletes conversation
```

#### Voice

```
POST /api/voice/transcribe
  Content-Type: multipart/form-data
  Body: { audio: Blob, locale: "es-AR" | "en-US" }
  ← { text: string, confidence: number, durationMs: number }

POST /api/voice/synthesize
  Body: { text: string, locale: "es-AR" | "en-US", messageId: string }
  ← audio/mpeg stream (chunked transfer)
```

#### Contact

```
POST /api/contact/form
  Body: { name: string, email: string, message: string, locale: string }
  ← { success: boolean, pipedriveId?: string }

POST /api/contact/auth-gate
  Body: { email: string, conversationId: string }
  ← { success: boolean, pipedrivePersonId?: string }
```

#### Health

```
GET /api/health
  ← { status: "ok", services: { db, foundry, speech, pipedrive } }
```

### 10.2 SignalR Hub

```csharp
public class ChatHub : Hub
{
    // Client → Server
    Task SendMessage(string conversationId, string text, string locale);
    Task StartTyping(string conversationId);
    Task StopTyping(string conversationId);
    Task RequestTTS(string conversationId, string messageId);

    // Server → Client
    Task OnTokenReceived(string token);                    // Streaming text
    Task OnWidgetCommand(string widgetName, object args);  // Rich widget
    Task OnMessageComplete(MessageDto message);            // Full message saved
    Task OnBotTyping(bool isTyping);                       // Typing indicator
    Task OnTTSReady(string messageId, string audioUrl);    // TTS audio available
    Task OnError(string code, string message);             // Error handling
    Task OnRateLimitWarning(int remaining);                // Rate limit counter
    Task OnRateLimitReached(RateLimitAction action);       // Limit hit → redirect
    Task OnAuthGateTriggered();                            // Show email capture
}
```

---

## 11. Data Model

### 11.1 Entity Relationship

```
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│ Conversations │     │   Messages    │     │    Leads      │
├───────────────┤     ├───────────────┤     ├───────────────┤
│ Id (UUID) PK  │──┐  │ Id (UUID) PK  │     │ Id (UUID) PK  │
│ IpAddress     │  │  │ ConversationId│──┐  │ Email         │
│ Locale        │  └──│ Role (bot/usr)│  │  │ ConversationId│
│ Email?        │     │ Content       │  │  │ PipedriveId?  │
│ LeadId? FK    │     │ Widgets[]?    │  │  │ CreatedAt     │
│ MessageCount  │     │ AudioUrl?     │  │  └───────────────┘
│ IsRateLimited │     │ TtsUrl?       │  │
│ CreatedAt     │     │ CreatedAt     │  │  ┌───────────────┐
│ UpdatedAt     │     │ TokenCount    │  │  │  RateLimits   │
│ ExpiresAt     │     └───────────────┘  │  ├───────────────┤
└───────────────┘                        │  │ IpAddress PK  │
                                         │  │ MessageCount  │
                                         │  │ WindowStart   │
                                         └──│ ConversationId│
                                            │ IsBlocked     │
                                            └───────────────┘
```

### 11.2 Table Definitions

```sql
CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ip_address      INET NOT NULL,
    locale          VARCHAR(5) NOT NULL DEFAULT 'es',
    email           VARCHAR(255),
    lead_id         UUID REFERENCES leads(id),
    message_count   INT NOT NULL DEFAULT 0,
    is_rate_limited BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '24 hours'
);

CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(10) NOT NULL CHECK (role IN ('bot', 'user')),
    content         TEXT NOT NULL,
    widgets         JSONB,
    audio_url       TEXT,
    tts_url         TEXT,
    token_count     INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE leads (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) NOT NULL,
    conversation_id UUID REFERENCES conversations(id),
    pipedrive_id    BIGINT,
    source          VARCHAR(50) NOT NULL DEFAULT 'auth_gate',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE rate_limits (
    ip_address      INET PRIMARY KEY,
    message_count   INT NOT NULL DEFAULT 0,
    window_start    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    conversation_id UUID,
    is_blocked      BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_conversations_ip ON conversations(ip_address);
CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);
CREATE INDEX idx_leads_email ON leads(email);
CREATE INDEX idx_rate_limits_window ON rate_limits(window_start);
```

---

## 12. Integrations

### 12.1 Pipedrive CRM

| Trigger | Action |
|---------|--------|
| User submits email (auth gate) | Create Person + Deal in Pipedrive |
| User submits contact form | Create/Update Person + Deal + Note |
| Rate limit reached | Update Deal stage to "Warm Lead" |

**API:** Pipedrive REST API v1  
**Auth:** API Token (stored in Azure Key Vault)

```
POST https://api.pipedrive.com/v1/persons
POST https://api.pipedrive.com/v1/deals
POST https://api.pipedrive.com/v1/notes
```

**Deal Pipeline Stages:**
1. New Lead — auth gate email captured (Stage 2)
2. Engaged — user asks about specific project/needs (Stage 2-3)
3. Warm Lead — bot proposed meeting / rate limit reached (Stage 4)
4. Meeting Booked — user clicked Calendly (Stage 4 ✅)
5. Contacted — form submitted / WhatsApp clicked (alternative close)

### 12.2 WhatsApp

**Type:** Click-to-chat (no API integration needed)  
**Number:** +5491167900774  
**Pre-filled messages:**

| Context | Message (ES) |
|---------|-------------|
| Rate limit reached | "Hola! Estuve chateando con la IA de Novit y quiero seguir la conversación con el equipo." |
| Contact form | "Hola! Me gustaría hablar sobre un proyecto." |
| General | "Hola! Vi su web y me interesa saber más." |

**URL Format:** `https://wa.me/5491167900774?text={encodeURIComponent(message)}`

### 12.3 Calendly

**Type:** Embed (inline iframe) or popup link  
**URL:** `https://calendly.com/novitsoftware/{event-type}` *(to be configured)*  
**Trigger:** Bot invokes `render_calendly` widget when user wants to schedule a meeting or when rate limit is reached.

### 12.4 Azure AI Foundry

| Service | Usage | Model/Resource |
|---------|-------|----------------|
| Chat Completion | Conversational AI | GPT-4o (Azure AI Foundry deployment) |
| Embeddings | RAG vector search | text-embedding-3-large |
| Speech-to-Text | Voice input transcription | Whisper Large v3 |
| Text-to-Speech | Voice output synthesis | Neural Voices (Elena/Jenny) |
| AI Search | Knowledge base retrieval | Azure AI Search (hybrid) |

### 12.5 Cloudflare Turnstile

> **Nota:** Turnstile es un CAPTCHA invisible de Cloudflare. No requiere que el usuario resuelva nada — valida automáticamente que el visitante es humano. Es gratuito y ligero. Se usa para proteger el endpoint del chat contra bots/spam automatizado.

**Implementation:**
- Frontend: `<cf-turnstile>` widget (invisible mode)
- Backend: Verify token via `POST https://challenges.cloudflare.com/turnstile/v0/siteverify`
- Required before: first chat message, contact form submission

---

## 13. Internationalization (i18n)

### 13.1 Routing

| URL | Locale | Default |
|-----|--------|---------|
| `novitsoftware.com/es/` | Spanish (Argentina) | ✅ Primary |
| `novitsoftware.com/en/` | English (US) | |
| `novitsoftware.com/` | Redirect to `/es/` | |

### 13.2 What Gets Localized

| Element | Strategy |
|---------|----------|
| UI chrome (nav, buttons, labels) | Angular i18n (`$localize`) |
| Bot system prompt | Locale-specific prompt files |
| Bot responses | LLM generates in target language |
| TTS voice | Locale-specific neural voice |
| STT recognition | Locale-specific model |
| Knowledge base | Bilingual documents (ES primary, EN translations) |
| Widget static content | i18n translation files |
| URL slugs | `/es/`, `/en/` |

### 13.3 Language Detection

1. URL path takes priority (`/es/` or `/en/`)
2. Fallback: `navigator.language` header
3. Default: `es` (Spanish)

---

## 14. Security & Protection

### 14.1 Threat Model

| Threat | Mitigation |
|--------|-----------|
| LLM prompt injection | System prompt hardening + input sanitization |
| Chat spam / abuse | IP rate limiting (30 msgs) + Turnstile |
| DDoS | Azure Front Door + WAF |
| XSS via bot responses | Sanitize HTML output, CSP headers |
| Data exfiltration | Bot constrained to public knowledge only |
| Audio abuse | Max 60s recording, file size limit 10MB |

### 14.2 Rate Limiting

```
Rate Limit Configuration:
  Window:       24 hours (rolling)
  Max Messages: 30 per IP
  Auth Gate:    Triggered at message 10
  Soft Block:   At message 30 → redirect to WhatsApp/Calendly
  Hard Block:   At message 60 (if somehow bypassed) → 403

Storage: PostgreSQL (rate_limits table) + in-memory cache
```

### 14.3 Content Security

- Bot responses are sanitized before rendering
- Rich widgets render from predefined Angular components (not raw HTML from LLM)
- CSP headers prevent inline script execution
- All user input is parameterized (no SQL injection)
- Audio files validated (MIME type, size, duration)

### 14.4 Data Privacy

- Conversations expire after 24 hours (configurable)
- IP addresses stored for rate limiting only
- Emails stored only if user consents (auth gate)
- No tracking/analytics cookies
- GDPR-compliant: user can request data deletion

---

## 15. Infrastructure & Deployment

### 15.1 Azure Resources

```
Resource Group: rg-novit-web-prod
├── Azure App Service (Linux, .NET 10)        ← Backend API + SignalR
├── Azure Static Web Apps                      ← Angular SSR (or App Service)
├── Azure Database for PostgreSQL (Flex)       ← Database
├── Azure AI Foundry                           ← GPT-4o + Embeddings
├── Azure AI Speech                            ← STT + TTS
├── Azure AI Search                            ← RAG vector search
├── Azure Key Vault                            ← Secrets (API keys)
├── Azure Front Door + WAF                     ← CDN + DDoS protection
├── Azure Blob Storage                         ← Audio files (TTS cache)
├── Azure Application Insights                 ← Monitoring & logging
└── Azure Redis Cache (Basic)                  ← Rate limit caching
```

### 15.2 Environment Strategy

| Environment | Purpose | URL |
|-------------|---------|-----|
| `dev` | Development | `dev.novitsoftware.com` |
| `staging` | Pre-production | `staging.novitsoftware.com` |
| `prod` | Production | `novitsoftware.com` |

### 15.3 CI/CD Pipeline

```yaml
# GitHub Actions workflow
trigger: push to main (prod), push to develop (staging)

steps:
  1. Build Angular SSR (ng build --configuration=production)
  2. Build .NET Backend (dotnet publish)
  3. Run unit tests (frontend + backend)
  4. Run E2E tests (Playwright)
  5. Deploy to Azure App Service (staging slot)
  6. Run smoke tests
  7. Swap slots (staging → production)
```

### 15.4 Domain & DNS

| Record | Value |
|--------|-------|
| `novitsoftware.com` | Azure Front Door endpoint |
| `www.novitsoftware.com` | CNAME → Front Door |
| `api.novitsoftware.com` | CNAME → App Service |

---

## 16. SEO & Accessibility

### 16.1 SEO Strategy

Since the site is primarily a chat interface, SEO requires a **pre-rendered conversation** strategy to ensure full indexability:

#### Pre-rendered Conversation (Core SEO Strategy)

The server renders the initial 4 bot messages as **static HTML** that visually looks like a chat conversation but is actually structured, semantic HTML underneath. This guarantees Google sees rich content on every crawl.

**What Google sees:**

```html
<main>
  <h1 class="sr-only">Novit Software — Agentes de IA y Desarrollo de Software</h1>

  <article role="log" aria-label="Conversación con Novit AI">
    <!-- Message 1: Greeting -->
    <section class="chat-bubble bot" aria-label="Novit AI">
      <p>¡Hola! Soy la IA de Novit Software...</p>
    </section>

    <!-- Message 2: Services (widget renders as semantic HTML) -->
    <section class="chat-bubble bot" aria-label="Novit AI">
      <h2 class="sr-only">Servicios de Novit</h2>
      <ul>
        <li><strong>Software Development</strong> — Custom software, web &amp; mobile apps</li>
        <li><strong>IT Consulting</strong> — Process optimization, architecture review</li>
        <li><strong>QA &amp; Testing</strong> — Manual &amp; automated testing</li>
        <li><strong>UX/UI Design</strong> — User research, prototyping</li>
        <li><strong>Data Science</strong> — Analytics, BI, data pipelines</li>
        <li><strong>Artificial Intelligence</strong> — ML models, NLP, AI agents</li>
      </ul>
    </section>

    <!-- Message 3: Stats + Clients (widgets as semantic HTML) -->
    <section class="chat-bubble bot" aria-label="Novit AI">
      <h2 class="sr-only">Novit en números</h2>
      <dl>
        <dt>Profesionales</dt><dd>70+</dd>
        <dt>Clientes activos</dt><dd>30+</dd>
        <dt>Proyectos entregados</dt><dd>40+</dd>
      </dl>
    </section>

    <!-- Message 4: CTA -->
    <section class="chat-bubble bot" aria-label="Novit AI">
      <p>¿En qué puedo ayudarte?</p>
    </section>
  </article>

  <!-- Schema.org -->
  <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Organization",
      "name": "Novit Software",
      "url": "https://novitsoftware.com",
      "description": "Software factory specializing in AI agents, custom development, and digital transformation",
      ...
    }
  </script>

  <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      "mainEntity": [
        { "@type": "Question", "name": "¿Qué servicios ofrece Novit?", "acceptedAnswer": { ... } },
        { "@type": "Question", "name": "¿Cuántos profesionales tiene Novit?", "acceptedAnswer": { ... } }
      ]
    }
  </script>
</main>
```

**Key principle:** The chat bubbles are styled with CSS, but the underlying HTML is **fully semantic** (`<h1>`, `<h2>`, `<section>`, `<ul>`, `<p>`, `<dl>`). Screen readers and crawlers see a structured, content-rich page.

#### Additional SEO Measures

| Strategy | Implementation |
|----------|---------------|
| **Pre-rendered conversation** | 4 static bot messages with all key content rendered as semantic HTML |
| **Zero-JS initial render** | No JavaScript required for the pre-rendered content — pure SSR |
| **Meta tags** | Dynamic per locale (`<title>`, `<meta description>`, OG tags) |
| **Structured data** | JSON-LD for `Organization`, `WebSite`, `FAQPage` |
| **Semantic HTML** | Chat bubbles use `<section>`, `<h2>`, `<ul>`, `<dl>` underneath CSS styling |
| **Sitemap** | `/sitemap.xml` with `/es/` and `/en/` |
| **robots.txt** | Allow all, exclude `/api/` |
| **Canonical URLs** | `<link rel="canonical">` per locale |
| **Lazy AI activation** | Heavy JS (chat engine, SignalR, TTS) loaded only on user interaction |

### 16.2 Accessibility (WCAG 2.1 AA)

| Requirement | Implementation |
|-------------|---------------|
| Keyboard navigation | Full tab order through chat, prompt, buttons |
| Screen reader | ARIA labels on all interactive elements, live regions for new messages |
| Color contrast | All text meets 4.5:1 ratio (except ghost transcription — decorative) |
| Voice alternatives | TTS provides audio for all bot content |
| Motion | Reduced motion media query respected |
| Focus indicators | Visible focus rings on all interactive elements |

---

## 17. Performance Requirements

| Metric | Target | Strategy |
|--------|--------|----------|
| LCP (Largest Contentful Paint) | < 1.5s | Pre-rendered conversation via SSR, 0 JS on initial load |
| FID (First Input Delay) | < 100ms | AI engine lazy-loaded only on user interaction |
| CLS (Cumulative Layout Shift) | < 0.1 | Fixed layout, pre-rendered messages prevent shifts |
| TTI (Time to Interactive) | < 2.0s | Zero JS on initial render; prompt bar activates on focus |
| Initial JS bundle | **0 KB** | Pre-rendered page is pure HTML + CSS; JS loads on demand |
| AI engine bundle (lazy) | < 80 KB gzipped | Loaded via dynamic import() on first interaction |
| SignalR connection | < 1s | Established lazily when AI engine activates |
| Chat response (first token) | < 500ms | Streaming from Azure AI Foundry |
| STT transcription | < 2s | Azure AI Speech optimized endpoint |
| TTS generation | < 3s | Cached for repeated requests |

---

## 18. Knowledge Base Content

### 18.1 Document Structure

Knowledge base documents stored as Markdown files, indexed via Azure AI Search:

```
knowledge-base/
├── es/
│   ├── company-overview.md
│   ├── services/
│   │   ├── software-development.md
│   │   ├── it-consulting.md
│   │   ├── qa-testing.md
│   │   ├── ux-ui-design.md
│   │   ├── data-science.md
│   │   └── artificial-intelligence.md
│   ├── clients/
│   │   ├── nordelta-consultatio.md
│   │   ├── tecnovoz.md
│   │   ├── indec.md
│   │   ├── puig.md
│   │   └── ...
│   ├── academy/
│   │   └── devops-course.md
│   ├── stats.md
│   ├── testimonials.md
│   ├── team.md
│   └── contact.md
├── en/
│   └── [mirrors of es/ in English]
└── shared/
    └── faq.md
```

### 18.2 Content Source

All content sourced from the current `novitsoftware.com` site:

**Company:**
- Software factory in Buenos Aires, Argentina
- Slogan: "We Make It"
- "The software factory you need to bring your ideas to life in a simple and practical way"
- "The ideal technology partner to support your digital transformation process"

**Services:**
1. **Software Development** — Custom software, web & mobile apps, APIs
2. **IT Consulting** — Process optimization, architecture review
3. **QA & Testing** — Manual & automated testing, CI/CD quality gates
4. **UX/UI Design** — User research, prototyping, design systems
5. **Data Science** — Analytics, BI, data pipelines
6. **Artificial Intelligence** — ML models, NLP, computer vision, AI agents

**Stats:**
- 10+ years in the market (founded March 2015)
- 40+ clients worldwide
- 30+ professionals of excellence

**Key Clients & Projects:**
| Client | Project |
|--------|---------|
| Nordelta/Consultatio | Commercial management system, CRM, payment platform, banking integrations |
| Tecnovoz | CRM migration, WhatsApp API integration, TCP/IP development, VoIP |
| INDEC | Web and mobile platform for censuses and surveys |
| Puig | Optimization consulting, software development processes, KPIs |
| Megatlon | (Sport/fitness industry client) |
| TopDoctors | Staff augmentation for Healthcare |
| Various Banks | Integrations with Bancolombia and Davivienda Brasil |
| SAP Clients | Data Migration, S/4HANA implementation, ABAP, FICO consulting |

**Testimonial:**
> "Together with Novit we have built a solid bond of trust throughout the years. Today it's a strategic partner in terms of technology. We are glad to know they will keep on accompanying us in our growth with their professionalism."
> — Jorge Salonio | CONSULTATIO/NORDELTA, Systems Manager

**Academy (Novit Academy):**
- Free DevOps training program with admission process
- 100% online, synchronous, theoretical-practical
- 2 months / 32 hours
- Modules: Linux & Git, Project Setup, CI/CD, Docker, Monitoring & Security
- Hands-on final assessment with tailored feedback

**Contact:**
- Address: Córdoba Ave. 1351, 3rd floor, City of Buenos Aires
- Phone: +54 11 3176 9406
- Email: info@novitsoftware.com
- WhatsApp: +54 9 11 6790-0774
- Instagram: @novit.software
- LinkedIn: /company/novit-software

### 18.3 Extra Topics (Configurable by Admin)

The admin can add custom topics to the knowledge base that the bot can reference:

- Current job openings
- Upcoming academy cohorts and dates
- Pricing frameworks (without specific numbers)
- Technology stack expertise
- Case study details
- Team bios
- Industry-specific capabilities

> **Admin interface for KB management is out of scope for v1.** Documents are managed as Markdown files in the repository and re-indexed on deploy.

---

## 19. Project Structure

### 19.1 Repository Layout

```
web-novit-ai/
├── docs/
│   ├── openspec.md                    ← This file
│   ├── architecture.md
│   └── design/
│       └── pencil-new.pen             ← Pencil design file
│
├── src/
│   ├── frontend/                      ← Angular 19+ SSR
│   │   ├── src/
│   │   │   ├── app/
│   │   │   │   ├── core/
│   │   │   │   │   ├── services/
│   │   │   │   │   │   ├── chat.service.ts
│   │   │   │   │   │   ├── voice.service.ts
│   │   │   │   │   │   ├── tts.service.ts
│   │   │   │   │   │   ├── signalr.service.ts
│   │   │   │   │   │   ├── i18n.service.ts
│   │   │   │   │   │   └── rate-limit.service.ts
│   │   │   │   │   ├── models/
│   │   │   │   │   │   ├── message.model.ts
│   │   │   │   │   │   ├── conversation.model.ts
│   │   │   │   │   │   └── widget.model.ts
│   │   │   │   │   └── interceptors/
│   │   │   │   │       └── locale.interceptor.ts
│   │   │   │   │
│   │   │   │   ├── features/
│   │   │   │   │   ├── chat/
│   │   │   │   │   │   ├── chat.component.ts
│   │   │   │   │   │   ├── chat-message/
│   │   │   │   │   │   ├── chat-prompt/
│   │   │   │   │   │   ├── chat-header/
│   │   │   │   │   │   └── auth-gate/
│   │   │   │   │   │
│   │   │   │   │   ├── voice/
│   │   │   │   │   │   ├── mic-button/
│   │   │   │   │   │   ├── waveform/
│   │   │   │   │   │   ├── transcription/
│   │   │   │   │   │   └── tts-button/
│   │   │   │   │   │
│   │   │   │   │   └── widgets/
│   │   │   │   │       ├── services-grid/
│   │   │   │   │       ├── stats-cards/
│   │   │   │   │       ├── client-logos/
│   │   │   │   │       ├── testimonial-card/
│   │   │   │   │       ├── academy-modules/
│   │   │   │   │       ├── contact-form/
│   │   │   │   │       ├── calendly-embed/
│   │   │   │   │       └── whatsapp-cta/
│   │   │   │   │
│   │   │   │   ├── layout/
│   │   │   │   │   ├── navbar/
│   │   │   │   │   ├── footer/
│   │   │   │   │   └── bottom-bar/         ← Mobile/Tablet
│   │   │   │   │
│   │   │   │   ├── shared/
│   │   │   │   │   ├── components/
│   │   │   │   │   │   ├── bot-avatar/
│   │   │   │   │   │   ├── status-pill/
│   │   │   │   │   │   ├── rate-badge/
│   │   │   │   │   │   └── shield-badge/
│   │   │   │   │   └── pipes/
│   │   │   │   │       └── safe-html.pipe.ts
│   │   │   │   │
│   │   │   │   ├── app.component.ts
│   │   │   │   ├── app.routes.ts
│   │   │   │   └── app.config.ts
│   │   │   │
│   │   │   ├── assets/
│   │   │   │   ├── images/
│   │   │   │   │   ├── logo.svg
│   │   │   │   │   └── clients/            ← Client logo SVGs
│   │   │   │   └── i18n/
│   │   │   │       ├── es.json
│   │   │   │       └── en.json
│   │   │   │
│   │   │   ├── styles/
│   │   │   │   ├── _variables.scss         ← Design tokens
│   │   │   │   ├── _typography.scss
│   │   │   │   ├── _animations.scss
│   │   │   │   ├── _mixins.scss
│   │   │   │   └── styles.scss
│   │   │   │
│   │   │   ├── environments/
│   │   │   │   ├── environment.ts
│   │   │   │   ├── environment.staging.ts
│   │   │   │   └── environment.prod.ts
│   │   │   │
│   │   │   └── index.html
│   │   │
│   │   ├── angular.json
│   │   ├── package.json
│   │   └── tsconfig.json
│   │
│   └── backend/
│       ├── Novit.Web.Api/
│       │   ├── Controllers/
│       │   │   ├── ChatController.cs
│       │   │   ├── VoiceController.cs
│       │   │   ├── ContactController.cs
│       │   │   └── HealthController.cs
│       │   │
│       │   ├── Hubs/
│       │   │   └── ChatHub.cs
│       │   │
│       │   ├── Services/
│       │   │   ├── AI/
│       │   │   │   ├── IAIAgentService.cs
│       │   │   │   ├── AIAgentService.cs
│       │   │   │   ├── PromptBuilder.cs
│       │   │   │   └── WidgetFunctionMapper.cs
│       │   │   │
│       │   │   ├── Speech/
│       │   │   │   ├── ISpeechService.cs
│       │   │   │   ├── SpeechToTextService.cs
│       │   │   │   └── TextToSpeechService.cs
│       │   │   │
│       │   │   ├── Chat/
│       │   │   │   ├── IConversationService.cs
│       │   │   │   └── ConversationService.cs
│       │   │   │
│       │   │   ├── RateLimit/
│       │   │   │   ├── IRateLimitService.cs
│       │   │   │   └── RateLimitService.cs
│       │   │   │
│       │   │   └── Integrations/
│       │   │       ├── IPipedriveService.cs
│       │   │       ├── PipedriveService.cs
│       │   │       └── WhatsAppHelper.cs
│       │   │
│       │   ├── Data/
│       │   │   ├── NovitDbContext.cs
│       │   │   ├── Entities/
│       │   │   │   ├── Conversation.cs
│       │   │   │   ├── Message.cs
│       │   │   │   ├── Lead.cs
│       │   │   │   └── RateLimit.cs
│       │   │   └── Migrations/
│       │   │
│       │   ├── Middleware/
│       │   │   ├── RateLimitMiddleware.cs
│       │   │   └── TurnstileMiddleware.cs
│       │   │
│       │   ├── Configuration/
│       │   │   ├── AzureAIOptions.cs
│       │   │   ├── SpeechOptions.cs
│       │   │   ├── PipedriveOptions.cs
│       │   │   └── RateLimitOptions.cs
│       │   │
│       │   ├── Program.cs
│       │   ├── appsettings.json
│       │   └── Novit.Web.Api.csproj
│       │
│       └── Novit.Web.Api.Tests/
│           ├── Services/
│           ├── Hubs/
│           └── Controllers/
│
├── knowledge-base/
│   ├── es/
│   │   ├── company-overview.md
│   │   ├── services/
│   │   ├── clients/
│   │   ├── academy/
│   │   └── ...
│   └── en/
│       └── ...
│
├── infra/
│   ├── bicep/
│   │   ├── main.bicep                     ← Azure IaC
│   │   ├── modules/
│   │   │   ├── app-service.bicep
│   │   │   ├── postgresql.bicep
│   │   │   ├── ai-foundry.bicep
│   │   │   ├── speech.bicep
│   │   │   ├── ai-search.bicep
│   │   │   ├── key-vault.bicep
│   │   │   ├── front-door.bicep
│   │   │   ├── redis.bicep
│   │   │   └── storage.bicep
│   │   └── parameters/
│   │       ├── dev.bicepparam
│   │       ├── staging.bicepparam
│   │       └── prod.bicepparam
│   └── scripts/
│       ├── deploy.sh
│       └── index-knowledge-base.sh
│
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── deploy-staging.yml
│       └── deploy-prod.yml
│
├── .gitignore
├── README.md
└── docker-compose.yml                     ← Local dev (PostgreSQL + Redis)
```

---

## 20. Glossary

| Term | Definition |
|------|-----------|
| **AI Agent** | The GPT-4o powered conversational bot that represents Novit |
| **Auth Gate** | Soft email capture prompt shown after 10 messages |
| **Azure AI Foundry** | Microsoft's platform for deploying and managing AI models |
| **Function Calling** | GPT-4o capability to invoke predefined tools/functions |
| **Knowledge Base (KB)** | Curated Markdown documents containing Novit's information |
| **RAG** | Retrieval-Augmented Generation — augmenting LLM with retrieved context |
| **Rich Widget** | Pre-built Angular component rendered inline in chat (services grid, stats, etc.) |
| **SignalR** | Microsoft's real-time communication library (WebSocket-based) |
| **SSR** | Server-Side Rendering — Angular renders on server for SEO |
| **STT** | Speech-to-Text — converting voice input to text |
| **TTS** | Text-to-Speech — converting bot text responses to audio |
| **Turnstile** | Cloudflare's invisible CAPTCHA for bot protection |
| **Widget Command** | A function call from GPT-4o instructing the frontend to render a widget |

---

## Appendix A — Open Questions

| # | Question | Status |
|---|----------|--------|
| A1 | ¿Cuál es la URL exacta de Calendly de Novit? | ⏳ Pending |
| A2 | ¿API key de Pipedrive + pipeline/stages existentes? | ⏳ Pending |
| A3 | ¿Dominio actual apunta a Wix? ¿Quién gestiona DNS? | ⏳ Pending |
| A4 | ¿Logos de clientes en SVG disponibles o hay que extraerlos de la web actual? | ⏳ Pending |
| A5 | ¿Hay más testimonials además del de Jorge Salonio (Nordelta)? | ⏳ Pending |
| A6 | ¿Las estadísticas (70+ prof, 30+ clients, 40+ projects) están actualizadas? | ⏳ Pending |
| A7 | ¿Fechas actuales del próximo cohort de Novit Academy? | ⏳ Pending |
| A8 | ¿Hay presupuesto Azure estimado / tier preferido para los servicios? | ⏳ Pending |
| A9 | ¿El WhatsApp +5491167900774 es diferente al +5491131769406 de la web actual? ¿Cuál usar? | ⏳ Pending |

---

## Appendix B — Design Reference Screenshots

All visual specifications are defined in `pencil-new.pen`:

| Frame | ID | Dimensions | Description |
|-------|-----|-----------|-------------|
| Desktop | `mYn4Z` | 1440×5004 | Full desktop layout with all sections |
| Mobile | `V6Uos` | 375×812 | Mobile chat interface with bottom bar |
| Tablet | `qTeAE` | 768×1024 | Tablet layout with chat + bottom bar |

---

*End of specification. Version 1.0.0 — February 20, 2026*
