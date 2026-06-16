## 1. Python Environment Setup

- [x] 1.1 Create project directory `langgraph-workflow-api/` with package structure: `langgraph_workflow_api/__init__.py`
- [x] 1.2 Create `requirements.txt` with pinned dependencies: `langgraph>=0.2.0`, `fastapi>=0.115.0`, `uvicorn[standard]>=0.34.0`, `pydantic>=2.0.0`
- [x] 1.3 Create `.gitignore` with `.venv/`, `__pycache__/`, `*.pyc`
- [x] 1.4 Create `setup.ps1` script to create `.venv`, install dependencies, and start uvicorn
- [x] 1.5 Verify virtual environment creation and dependency installation

## 2. LangGraph Workflow Core

- [x] 2.1 Define `AgentState` TypedDict with fields: `input`, `validated`, `enriched`, `response`, `messages`
- [x] 2.2 Implement `validator` node: validates input is non-empty, sets `validated` flag, appends message
- [x] 2.3 Implement `enricher` node: produces mock enriched content, appends message
- [x] 2.4 Implement `responder` node: generates mock final response, appends message
- [x] 2.5 Build `StateGraph` with conditional edge: valid → enricher → responder, invalid → responder
- [x] 2.6 Compile graph and export `run_workflow(input: str) -> dict` function

## 3. FastAPI Application

- [x] 3.1 Create `app/main.py` with FastAPI app instance, CORS setup, and in-memory result store with `asyncio.Lock`
- [x] 3.2 Implement `POST /workflow/run` endpoint: accepts `{"input": "..."}`, generates UUID run_id, executes workflow asynchronously, returns 202 with run_id
- [x] 3.3 Implement `GET /workflow/result/{run_id}` endpoint: returns AgentState or 404
- [x] 3.4 Add Pydantic request/response models for type validation
- [x] 3.5 Verify `/docs` serves OpenAPI documentation

## 4. Deployment Documentation

- [x] 4.1 Create `DEPLOY.md` with "## Local Development" section covering `.venv` creation, dependency install, and server startup
- [x] 4.2 Add "## Production Deployment" section with process manager setup, env vars, and CORS configuration
- [x] 4.3 Add "## Docker Deployment" section with sample Dockerfile and `docker run` command

## 5. Verification

- [x] 5.1 Start server via `uvicorn app.main:app` and verify endpoints respond
- [x] 5.2 Test valid input flow: POST → GET result → verify all three agents executed
- [x] 5.3 Test invalid input flow: POST empty string → GET result → verify validator→responder path
- [x] 5.4 Test 404 for unknown run_id
- [x] 5.5 Test 422 for missing input field
- [x] 5.6 Verify `DEPLOY.md` renders correctly and all sections are present
