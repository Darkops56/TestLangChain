## 1. Environment Configuration

- [x] 1.1 Add `openai>=1.0.0` and `python-dotenv>=1.0.0` to `requirements.txt`
- [x] 1.2 Create `.env.example` with `OPENAI_API_KEY=your-key-here` and `OPENAI_MODEL=gpt-4o-mini`
- [x] 1.3 Ensure `.env` is in `.gitignore` (add if missing)
- [x] 1.4 Add `python-dotenv` loading at the top of `app/main.py` before app creation
- [x] 1.5 Verify missing key raises clear error on startup

## 2. AI Agent Node Implementation

- [x] 2.1 Update `AgentState` TypedDict: remove `validated`, `enriched`; add `raw_response: str | None`; keep `input`, `response`, `messages`
- [x] 2.2 Remove validator_node, enricher_node, responder_node, decide_next functions
- [x] 2.3 Implement `ai_agent_node(state)` that calls OpenAI Chat Completions API
- [x] 2.4 Add system prompt for agent behavior
- [x] 2.5 Rebuild graph with single node and direct edge to END
- [x] 2.6 Update `run_workflow` to use new graph

## 3. DEPLOY.md Update

- [x] 3.1 Add `.env` setup section after venv creation: copy `.env.example`, configure key
- [x] 3.2 Add environment variables table with `OPENAI_API_KEY` and `OPENAI_MODEL` descriptions

## 4. Verification

- [x] 4.1 Install new dependencies and verify import works
- [x] 4.2 Verify missing OPENAI_API_KEY raises error at startup
- [ ] 4.3 Set a real API key in `.env` and start server
- [ ] 4.4 Test POST /workflow/run with a question — verify response is from real AI
- [x] 4.5 Verify DEPLOY.md sections render correctly
