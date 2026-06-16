## MODIFIED Requirements

### Requirement: Define AgentState schema
The system SHALL define a shared `AgentState` TypedDict with fields: `input` (str), `validated` (bool | None), `enriched` (str | None), `response` (str | None), `raw_response` (str | None), `messages` (list[str]).

#### Scenario: State fields are accessible after creation
- **WHEN** a new AgentState is created with input="hello"
- **THEN** input SHALL be "hello", raw_response SHALL be None, messages SHALL be []

### Requirement: Graph has a single AI agent node
The system SHALL define one node in the LangGraph: `ai_agent`.

#### Scenario: Only one node is registered
- **WHEN** the graph is built
- **THEN** it SHALL contain exactly one node named "ai_agent"

### Requirement: Graph has a direct edge to END
The system SHALL add a direct edge from `ai_agent` to END with no conditional branching.

#### Scenario: Graph executes end-to-end
- **WHEN** the graph is executed with any input
- **THEN** the ai_agent node SHALL run once and the graph SHALL terminate

## REMOVED Requirements

### Requirement: Graph has three agent nodes
**Reason**: Replaced by single ai_agent node that calls OpenAI
**Migration**: Use ai_agent node instead of validator/enricher/responder chain

### Requirement: Graph has a conditional edge from validator
**Reason**: No longer needed — single node graph has no branching
**Migration**: Graph now uses direct edge from ai_agent to END

### Requirement: Validator node validates input
**Reason**: Validation is now handled by the AI agent's system prompt
**Migration**: Remove validator_node function and its registration

### Requirement: Enricher node enriches valid input
**Reason**: Enrichment is now handled inline by the AI agent
**Migration**: Remove enricher_node function and its registration

### Requirement: Responder node generates final response
**Reason**: Response generation is now handled by the AI agent
**Migration**: Remove responder_node function and its registration
