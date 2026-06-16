## Why

Build a lightweight, reproducible Python project that demonstrates a simple LangGraph workflow exposed via FastAPI, simulating agent-to-agent communication. This provides a reusable template for rapid prototyping of agent-based systems with proper environment isolation.

## What Changes

- Create a new Python project under `langgraph-workflow-api/` with a virtual environment (`.venv`)
- Define a simple LangGraph state graph with 2-3 nodes (e.g., agent nodes that pass messages)
- Implement a FastAPI application that exposes endpoints to trigger the workflow and retrieve results
- Simulate agent connections using async HTTP calls or in-process message passing
- Include a `requirements.txt` and setup instructions for environment reproducibility
- Create a `DEPLOY.md` file with step-by-step instructions for local and production deployment

## Capabilities

### New Capabilities
- `langgraph-workflow`: Core LangGraph state graph definition — nodes, edges, state schema, and conditional routing
- `fastapi-agent-api`: FastAPI server with endpoints to start a workflow run and query agent results
- `python-environment`: Python project scaffold with `.venv`, `requirements.txt`, `.gitignore`, and activation scripts
- `deploy-documentation`: Step-by-step deployment guide in `DEPLOY.md` covering local, staging, and production environments

### Modified Capabilities
<!-- No existing specs to modify -->

## Impact

- New directory `langgraph-workflow-api/` at repo root
- Dependencies: `langgraph`, `fastapi`, `uvicorn`, `pydantic`, `httpx` (for agent simulation)
- No breaking changes to existing code
