## Context

This project demonstrates a minimal LangGraph workflow served via FastAPI. Three simulated agents (Validator, Enricher, Responder) pass a shared state through a directed graph. The FastAPI layer provides REST endpoints to trigger runs and poll results, simulating how a production orchestrator would coordinate agents.

## Goals / Non-Goals

**Goals:**
- Define a LangGraph `StateGraph` with a shared `AgentState` schema (TypedDict)
- Implement 3 agent nodes: Validator (checks input), Enricher (adds context), Responder (generates final output)
- Expose POST `/workflow/run` to start a workflow execution and GET `/workflow/result/{run_id}` to retrieve it
- Use in-process async simulation (httpx mock or direct function calls) so no external services are needed
- Provide `requirements.txt` and `.venv` setup for one-command reproducibility

**Non-Goals:**
- No real LLM integration — agents return deterministic mock responses
- No database persistence — results stored in-memory (dict)
- No authentication, rate-limiting, or production hardening
- No containerization (Docker) — kept minimal for prototyping

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Graph framework | **LangGraph** (`langgraph` pkg) | Declarative state graph with built-in conditional edges and checkpointing |
| State schema | **TypedDict** (typed `dict`) | Lightweight, no extra ORM; Pydantic for API layer only |
| Agent simulation | **In-process async functions** | Avoid external HTTP overhead; each agent is an async function reading/writing `AgentState` |
| API framework | **FastAPI** | Native async support, automatic OpenAPI docs, Pydantic integration |
| Result store | **In-memory dict** (`run_id → state`) | Simplest possible; sufficient for demo purposes |
| Conditional edge | Validator decides `valid → Enricher, invalid → Responder` | Demonstrates branching logic in LangGraph |
| Project layout | Flat Python package (`langgraph_workflow_api/`) | Easy to navigate; no namespace packages needed |

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| In-memory store loses data on restart | Acceptable for demo; doc notes production would use Redis/DB |
| Agent simulation is fake (no real AI) | Explicitly documented as mock; real agents would replace function bodies |
| No async safety on result store | Use `asyncio.Lock` for write access to the in-memory dict |
| LangGraph version lock | Pin `langgraph>=0.2.0` in requirements; lock file for reproducibility |
