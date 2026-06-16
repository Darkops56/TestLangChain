# Error Log — LangGraph Workflow API

## 1. Message accumulation in LangGraph

**Date**: 2026-06-16
**Task**: 2.1-2.6 — LangGraph Workflow Core
**Error**: Each node's `messages` field was overwriting the previous node's messages instead of accumulating.
**Root cause**: `AgentState.messages: list[str]` uses default LangGraph behavior which replaces dict keys on each node step.
**Fix**: Changed to `messages: Annotated[list[str], operator.add]` using `typing.Annotated` and `operator.add` reducer.
**Verification**: Valid flow now returns `["Validator: Input valid", "Enricher: Context added", "Responder: Response generated"]`.

## 2. PowerShell background job failure

**Date**: 2026-06-16
**Task**: 5.1 — Start server and verify endpoints
**Error**: `Start-Job` + `Receive-Job` failed with "cannot find job" error. The job was cleaned up before output could be read.
**Root cause**: PowerShell 5.1 job lifecycle — background jobs may terminate silently on script block errors.
**Fix**: Replaced with `System.Diagnostics.Process` for direct process spawning with `RedirectStandardOutput`.
**Verification**: Server starts successfully on port 8001 and responds to requests.
