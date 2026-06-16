## ADDED Requirements

### Requirement: AI agent node calls OpenAI Chat Completions
The system SHALL define a single `ai_agent` LangGraph node that invokes the OpenAI Chat Completions API with a system prompt and the user's input.

#### Scenario: Agent returns a response for valid input
- **WHEN** the ai_agent node receives state with input="Tell me about AI"
- **THEN** the response SHALL contain a non-empty `response` field and a `raw_response` field with the full API response object

#### Scenario: Agent handles empty input gracefully
- **WHEN** the ai_agent node receives state with input=""
- **THEN** the response SHALL contain a message indicating empty input was received

### Requirement: System prompt defines agent behavior
The system SHALL use a configurable system prompt that instructs the AI to be a helpful assistant.

#### Scenario: System prompt is included in API call
- **WHEN** the ai_agent node makes an OpenAI API call
- **THEN** the messages array SHALL include a system message as the first entry

### Requirement: AgentState includes raw_response field
The AgentState TypedDict SHALL include a new optional field `raw_response` (str | None) to store the full OpenAI API response content.

#### Scenario: raw_response is populated after API call
- **WHEN** the ai_agent node completes an API call
- **THEN** `raw_response` SHALL contain the response content string

### Requirement: OpenAI model is configurable
The system SHALL read the model name from the `OPENAI_MODEL` environment variable, defaulting to `gpt-4o-mini` if not set.

#### Scenario: Default model is gpt-4o-mini
- **WHEN** `OPENAI_MODEL` is not set
- **THEN** the system SHALL use `gpt-4o-mini`

#### Scenario: Custom model is used when set
- **WHEN** `OPENAI_MODEL` is set to `gpt-4o`
- **THEN** the system SHALL use `gpt-4o`
