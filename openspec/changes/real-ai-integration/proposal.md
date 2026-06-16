## Why

The current workflow uses mock agents with hardcoded text (`[enriched with context]`). To make it functional, we need to replace the simulation with a real OpenAI-powered agent. The API key must be managed securely via `.env` instead of being hardcoded.

## What Changes

- Add `openai` and `python-dotenv` to `requirements.txt`
- Create `.env` file template with `OPENAI_API_KEY=<your-key>`
- Replace the three mock nodes (validator, enricher, responder) with a single AI agent node that calls OpenAI Chat Completions
- Load `OPENAI_API_KEY` from `.env` using `python-dotenv` at startup
- Add `.env` and `.env.example` to the project
- Update `DEPLOY.md` with `.env` configuration instructions

## Capabilities

### New Capabilities
- `ai-agent-node`: LangGraph node that uses OpenAI Chat Completions API to autonomously process user input and generate a contextual response
- `env-configuration`: Secure management of `OPENAI_API_KEY` via `.env` file with `python-dotenv`, plus `.env.example` template

### Modified Capabilities
- `langgraph-workflow`: Replace the three mock nodes (validator → enricher → responder) with a single AI agent node. The StateGraph is simplified to one node with a direct edge to END. AgentState schema updated to include `raw_response` field.
- `deploy-documentation`: Add `.env` setup section with instructions to copy `.env.example`, configure the key, and verify the connection

## Impact

- **BREAKING**: Existing mock workflow (`graph.py`) will be replaced — API consumers get richer responses but the output shape changes (adds `raw_response` field)
- Dependencies added: `openai>=1.0.0`, `python-dotenv>=1.0.0`
- New files: `.env`, `.env.example`
- Modified files: `requirements.txt`, `.gitignore`, `graph.py`, `DEPLOY.md`
