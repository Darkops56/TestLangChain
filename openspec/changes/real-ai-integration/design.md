## Context

The current LangGraph workflow uses three mock nodes that return hardcoded text. The project now needs a real OpenAI integration. The three-node graph (validator → enricher → responder) will be collapsed into a single AI agent node that calls OpenAI Chat Completions. The API key will be loaded from `.env` at startup.

## Goals / Non-Goals

**Goals:**
- Replace mock nodes with a single `ai_agent` node using `openai.ChatCompletion`
- Load `OPENAI_API_KEY` from `.env` via `python-dotenv`
- Provide `.env.example` template for new developers
- Update AgentState schema: add `raw_response` (full API response), keep `input` and `messages`
- Update DEPLOY.md with `.env` setup instructions

**Non-Goals:**
- No streaming responses (kept simple for demo)
- No conversation history across runs (each run is independent)
- No fallback to mock if API key is missing (fail fast with clear error)
- No multi-model support (OpenAI only)

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| API client | `openai` Python package v1.x | Official OpenAI SDK with async support |
| Env loader | `python-dotenv` | Industry standard, zero-config |
| Env template | `.env.example` file | Document required vars without committing real keys |
| Graph structure | Single node (ai_agent) | Simpler than 3-node chain; one LLM call per run |
| Agent behavior | System prompt + user input | Autonomous: agent decides tone, depth, and structure of response |
| Error handling | Raise `ValueError` if key missing at startup | Fail fast, avoid runtime surprises |
| Model | `gpt-4o-mini` (configurable via `.env`) | Cost-effective, fast, good quality. User can override with `OPENAI_MODEL` |

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| API key committed to git by mistake | `.env` in `.gitignore`; only commit `.env.example` |
| OpenAI API cost | Use `gpt-4o-mini` (cheapest); cap max_tokens |
| Network failure / API outage | Exception propagates to HTTP 500; user retries |
| Rate limiting | Acceptable for demo; production would add retry with backoff |
| No streaming → slow responses for long inputs | Acceptable trade-off; streaming is a future enhancement |
