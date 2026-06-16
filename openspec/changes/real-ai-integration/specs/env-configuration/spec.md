## ADDED Requirements

### Requirement: API key loaded from .env file
The system SHALL load `OPENAI_API_KEY` from a `.env` file at project root using `python-dotenv` on application startup.

#### Scenario: Key is loaded successfully
- **WHEN** the application starts and `.env` contains `OPENAI_API_KEY=sk-...`
- **THEN** the OpenAI client SHALL be initialized with that key

#### Scenario: Missing key raises error
- **WHEN** the application starts and `OPENAI_API_KEY` is not set in environment or `.env`
- **THEN** the system SHALL raise a `ValueError` with a clear message

### Requirement: .env.example template provided
The system SHALL include a `.env.example` file at project root with the required variables documented.

#### Scenario: .env.example contains required vars
- **WHEN** `.env.example` is read
- **THEN** it SHALL contain `OPENAI_API_KEY=your-key-here` and `OPENAI_MODEL=gpt-4o-mini`

### Requirement: .env is gitignored
The system SHALL ensure `.env` is listed in `.gitignore` to prevent accidental commits.

#### Scenario: .env is ignored by git
- **WHEN** `.gitignore` is checked
- **THEN** it SHALL contain an entry for `.env`
