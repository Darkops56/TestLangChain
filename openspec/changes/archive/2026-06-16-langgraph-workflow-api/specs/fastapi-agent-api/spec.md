## ADDED Requirements

### Requirement: POST /workflow/run starts a workflow
The system SHALL expose a POST endpoint at `/workflow/run` that accepts a JSON body with an `input` field (string) and returns a `run_id` (string) immediately.

#### Scenario: Successful workflow start
- **WHEN** a POST request is sent to `/workflow/run` with body `{"input": "hello"}`
- **THEN** the response SHALL have status 202 and contain a `run_id` field

#### Scenario: Missing input field returns 422
- **WHEN** a POST request is sent to `/workflow/run` with empty body `{}`
- **THEN** the response SHALL have status 422

### Requirement: GET /workflow/result/{run_id} returns workflow state
The system SHALL expose a GET endpoint at `/workflow/result/{run_id}` that returns the full AgentState for the given run.

#### Scenario: Result for completed run
- **WHEN** a GET request is sent to `/workflow/result/<existing_run_id>`
- **THEN** the response SHALL have status 200 and contain `input`, `validated`, `enriched`, `response`, and `messages` fields

#### Scenario: Result for non-existent run_id returns 404
- **WHEN** a GET request is sent to `/workflow/result/non-existent-id`
- **THEN** the response SHALL have status 404

### Requirement: GET /docs serves OpenAPI docs
The system SHALL expose the default FastAPI OpenAPI documentation at `/docs`.

#### Scenario: OpenAPI docs are accessible
- **WHEN** a GET request is sent to `/docs`
- **THEN** the response SHALL have status 200 and return HTML content

### Requirement: Agent simulation runs in-process
The agent nodes SHALL execute as in-process async functions — no external HTTP calls required for the simulation.

#### Scenario: Workflow completes without network calls
- **WHEN** a workflow run is triggered
- **THEN** it SHALL complete without making any external HTTP requests

### Requirement: Results are stored in memory
Completed workflow states SHALL be stored in an in-memory dictionary keyed by `run_id`.

#### Scenario: Result is retrievable after workflow completes
- **WHEN** a workflow completes and the result is requested via GET /workflow/result/{run_id}
- **THEN** the returned state SHALL match the final AgentState of that run
