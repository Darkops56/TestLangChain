## ADDED Requirements

### Requirement: Define AgentState schema
The system SHALL define a shared `AgentState` TypedDict with fields: `input` (str), `validated` (bool | None), `enriched` (str | None), `response` (str | None), `messages` (list[str]).

#### Scenario: State fields are accessible after creation
- **WHEN** a new AgentState is created with input="hello"
- **THEN** input SHALL be "hello", validated SHALL be None, enriched SHALL be None, response SHALL be None, messages SHALL be []

### Requirement: Graph has three agent nodes
The system SHALL define three nodes in the LangGraph: `validator`, `enricher`, and `responder`.

#### Scenario: All nodes are registered in the graph
- **WHEN** the graph is built
- **THEN** it SHALL contain exactly three nodes named "validator", "enricher", "responder"

### Requirement: Validator node validates input
The `validator` node SHALL set `validated` to True if input is non-empty, False otherwise, and append a message to `messages`.

#### Scenario: Valid input passes validation
- **WHEN** the validator node receives state with input="hello"
- **THEN** validated SHALL be True and messages SHALL contain "Validator: Input valid"

#### Scenario: Empty input fails validation
- **WHEN** the validator node receives state with input=""
- **THEN** validated SHALL be False and messages SHALL contain "Validator: Input empty"

### Requirement: Enricher node enriches valid input
The `enricher` node SHALL set `enriched` to a mock enriched version of input and append a message to `messages`. It SHALL only run when `validated` is True.

#### Scenario: Enricher produces mock enrichment
- **WHEN** the enricher node receives state with validated=True and input="hello"
- **THEN** enriched SHALL contain "hello" and messages SHALL contain "Enricher: Context added"

### Requirement: Responder node generates final response
The `responder` node SHALL set `response` to a mock final message and append to `messages`. It SHALL run after the enricher (if valid) or after the validator (if invalid).

#### Scenario: Responder produces final output after enrichment
- **WHEN** the responder node receives state with enriched="hello [enriched]"
- **THEN** response SHALL be a non-empty string and messages SHALL contain "Responder: Response generated"

### Requirement: Graph has a conditional edge from validator
The system SHALL add a conditional edge from `validator` that routes to `enricher` if validated is True, or to `responder` if validated is False.

#### Scenario: Valid input follows validator → enricher → responder path
- **WHEN** the graph is executed with input="hello"
- **THEN** validation SHALL pass, enrichment SHALL occur, and response SHALL be generated

#### Scenario: Invalid input follows validator → responder path
- **WHEN** the graph is executed with input=""
- **THEN** validation SHALL fail and responder SHALL run directly after validator
