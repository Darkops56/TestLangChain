## ADDED Requirements

### Requirement: Extract CM agent into standalone project

The system SHALL extract all Community Manager agent code from the monorepo into a standalone Python project `cm-agent/`.

#### Scenario: CM agent code isolated
- **WHEN** the extraction is complete
- **THEN** `cm-agent/` runs independently without importing any code from `chat-agent/`

#### Scenario: Shared core extracted
- **WHEN** extraction completes
- **THEN** common LLM tools (`tools/llm.py`), schemas (`models/schemas.py`), and config utilities reside in `shared-core/` as a pip-installable package

### Requirement: Chatbot remains unmodified

The system SHALL preserve the existing chatbot project with no functional changes.

#### Scenario: Chatbot unchanged
- **WHEN** running chatbot tests after extraction
- **THEN** all existing tests pass with no modifications to chatbot code

### Requirement: Independent CI/CD pipelines

Each project SHALL have its own CI/CD pipeline (build, test, deploy).

#### Scenario: CI/CD separation
- **WHEN** a change is pushed to `cm-agent/`
- **THEN** only the CM pipeline runs, without triggering chatbot tests
