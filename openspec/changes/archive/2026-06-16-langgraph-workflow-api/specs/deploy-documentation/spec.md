## ADDED Requirements

### Requirement: DEPLOY.md exists at project root
The system SHALL provide a `DEPLOY.md` file at the `langgraph-workflow-api/` root with deployment instructions.

#### Scenario: DEPLOY.md is present
- **WHEN** the project directory is listed
- **THEN** a `DEPLOY.md` file SHALL exist

### Requirement: Local deployment instructions
`DEPLOY.md` SHALL include a "Local Development" section with steps to create `.venv`, install dependencies, and start the server with uvicorn.

#### Scenario: Local dev section exists
- **WHEN** `DEPLOY.md` is read
- **THEN** it SHALL contain a "## Local Development" section with `.venv` creation, dependency installation, and server startup steps

### Requirement: Production deployment considerations
`DEPLOY.md` SHALL include a "Production Deployment" section covering at least: using a process manager (e.g., gunicorn), setting environment variables, and enabling CORS for production origins.

#### Scenario: Production section exists
- **WHEN** `DEPLOY.md` is read
- **THEN** it SHALL contain a "## Production Deployment" section

### Requirement: Docker deployment option
`DEPLOY.md` SHALL include a "Docker Deployment" section with a sample `Dockerfile` and `docker run` command.

#### Scenario: Docker section exists
- **WHEN** `DEPLOY.md` is read
- **THEN** it SHALL contain a "## Docker Deployment" section with a Dockerfile snippet and run command
