## ADDED Requirements

### Requirement: Project uses a virtual environment
The project SHALL include a `.venv` directory at the project root for Python dependency isolation. The `.venv` SHALL be listed in `.gitignore`.

#### Scenario: Virtual environment is creatable
- **WHEN** `python -m venv .venv` is run from the project root
- **THEN** a `.venv` directory SHALL exist at the project root

#### Scenario: .venv is gitignored
- **WHEN** `.gitignore` is checked
- **THEN** it SHALL contain an entry for `.venv/`

### Requirement: Dependencies are pinned in requirements.txt
The project SHALL provide a `requirements.txt` file at the project root listing all runtime dependencies with version constraints.

#### Scenario: requirements.txt contains required packages
- **WHEN** `requirements.txt` is read
- **THEN** it SHALL contain at least `langgraph`, `fastapi`, `uvicorn`, and `pydantic`

### Requirement: Project has a setup/run script
The project SHALL provide a script (`setup.ps1` for Windows, `setup.sh` for Unix) that creates the `.venv`, installs dependencies, and starts the server.

#### Scenario: Setup script exists
- **WHEN** the project directory is listed
- **THEN** a `setup.ps1` or `setup.sh` file SHALL exist

#### Scenario: Setup script installs dependencies
- **WHEN** the setup script runs
- **THEN** all packages from `requirements.txt` SHALL be installed in `.venv`

### Requirement: Project root is importable
The project SHALL be structured so that `langgraph_workflow_api` is a Python package (contains `__init__.py`).

#### Scenario: Package is importable
- **WHEN** `.venv\Scripts\python -c "import langgraph_workflow_api"` is run
- **THEN** it SHALL exit with code 0
