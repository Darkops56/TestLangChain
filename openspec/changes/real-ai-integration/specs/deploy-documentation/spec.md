## MODIFIED Requirements

### Requirement: DEPLOY.md includes .env setup
The system SHALL update `DEPLOY.md` to include a step for copying `.env.example` to `.env` and configuring `OPENAI_API_KEY`.

#### Scenario: .env setup step is documented
- **WHEN** `DEPLOY.md` is read
- **THEN** it SHALL contain instructions to copy `.env.example` to `.env` and set the `OPENAI_API_KEY`

### Requirement: .env variables are documented
`DEPLOY.md` SHALL list all required environment variables with descriptions.

#### Scenario: Env vars section exists
- **WHEN** `DEPLOY.md` is read
- **THEN** it SHALL contain a table or list with `OPENAI_API_KEY` and `OPENAI_MODEL` and their descriptions
