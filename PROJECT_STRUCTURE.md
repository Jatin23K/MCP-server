# MCP Server Project Structure

This document outlines the structure of the MCP Server project and describes the purpose of each file and directory.

## Root Directory

```
mcp-server/
├── .github/                     # GitHub specific configuration
│   └── workflows/               # GitHub Actions workflows
│       ├── ci-cd.yml           # CI/CD pipeline configuration
│       └── release.yml         # Release workflow
│
├── app/                       # Main application package
│   ├── api/                    # API route definitions
│   │   ├── __init__.py
│   │   ├── dependencies.py     # FastAPI dependencies
│   │   ├── endpoints/          # API endpoint modules
│   │   └── routers/            # API routers
│   │
│   ├── core/                  # Core application logic
│   │   ├── __init__.py
│   │   ├── config.py          # Application configuration
│   │   ├── security.py        # Authentication and authorization
│   │   └── file_manager.py    # File handling logic
│   │
│   ├── db/                    # Database related code
│   │   ├── __init__.py
│   │   ├── base.py            # Base database configuration
│   │   ├── models/            # SQLAlchemy models
│   │   └── repositories/      # Database repositories
│   │
│   ├── schemas/              # Pydantic models/schemas
│   │   ├── __init__.py
│   │   ├── user.py            # User related schemas
│   │   └── file.py            # File related schemas
│   │
│   ├── services/             # Business logic services
│   │   ├── __init__.py
│   │   ├── auth.py           # Authentication service
│   │   └── file_service.py   # File management service
│   │
│   ├── static/               # Static files
│   │   └── ...
│   │
│   ├── templates/            # HTML templates (if any)
│   │   └── ...
│   │
│   ├── tests/                # Test files
│   │   ├── __init__.py
│   │   ├── conftest.py       # Pytest configuration
│   │   ├── test_api/         # API tests
│   │   └── test_services/    # Service layer tests
│   │
│   ├── utils/                # Utility functions
│   │   ├── __init__.py
│   │   └── helpers.py        # Helper functions
│   │
│   ├── __init__.py
│   └── main.py               # Application entry point
│
├── migrations/               # Database migration files (Alembic)
│   ├── versions/            # Generated migration scripts
│   ├── env.py               # Migration environment
│   └── script.py.mako       # Migration script template
│
├── scripts/                  # Utility scripts
│   ├── __init__.py
│   ├── create_admin.py      # Admin user creation script
│   └── setup_database.py    # Database setup script
│
├── tests/                   # Integration and end-to-end tests
│   ├── __init__.py
│   ├── conftest.py
│   └── integration/         # Integration tests
│
├── .dockerignore           # Files to exclude from Docker builds
├── .editorconfig            # Editor configuration
├── .env.example             # Example environment variables
├── .gitattributes           # Git attributes for line endings
├── .gitignore              # Git ignore file
├── .pre-commit-config.yaml  # Pre-commit hooks configuration
├── docker-compose.yml       # Docker Compose configuration
├── Dockerfile               # Docker configuration
├── LICENSE                 # Project license
├── pyproject.toml          # Project configuration and dependencies
├── README.md               # Project documentation
└── wait-for-it.sh          # Script to wait for services
```

## File and Directory Descriptions

### Configuration Files
- `.dockerignore` - Specifies files to exclude from Docker builds
- `.editorconfig` - Defines coding styles for different file types
- `.env.example` - Example environment variables (copy to `.env` for local development)
- `.gitattributes` - Configures Git attributes for consistent line endings
- `.gitignore` - Specifies intentionally untracked files to ignore
- `.pre-commit-config.yaml` - Configuration for pre-commit hooks
- `pyproject.toml` - Project metadata, dependencies, and tool configurations
- `docker-compose.yml` - Defines and runs multi-container Docker applications
- `Dockerfile` - Instructions for building the Docker image

### Documentation
- `README.md` - Main project documentation
- `README-DEVELOPMENT.md` - Development-specific documentation
- `CONTRIBUTING.md` - Guidelines for contributing to the project
- `CODE_OF_CONDUCT.md` - Community code of conduct
- `CHANGELOG.md` - Record of notable changes for each version
- `SECURITY.md` - Security policy and reporting guidelines
- `ROADMAP.md` - Future plans and milestones
- `MAINTAINERS.md` - Information about project maintainers
- `PROJECT_STRUCTURE.md` - This file, describing the project structure

### Core Application (`app/`)
- `main.py` - Application entry point and FastAPI app configuration
- `api/` - API route definitions and request/response models
- `core/` - Core application logic and configurations
- `db/` - Database models and repositories
- `schemas/` - Pydantic models for request/response validation
- `services/` - Business logic services
- `utils/` - Utility functions and helpers
- `tests/` - Unit and integration tests

### Database
- `migrations/` - Database migration scripts (Alembic)
  - `versions/` - Generated migration files
  - `env.py` - Migration environment configuration
  - `script.py.mako` - Migration script template

### Scripts
- `scripts/` - Utility scripts for development and deployment
  - `create_admin.py` - Script to create admin users
  - `setup_database.py` - Script to set up the database

### Development Tools
- `wait-for-it.sh` - Script to wait for services to be available
- `.github/workflows/` - GitHub Actions workflows for CI/CD

## Development Workflow

1. **Setup**:
   - Copy `.env.example` to `.env` and configure environment variables
   - Install dependencies with `poetry install`
   - Set up pre-commit hooks with `pre-commit install`

2. **Database**:
   - Start database services with `docker-compose up -d db`
   - Run migrations with `alembic upgrade head`

3. **Development**:
   - Run the development server with `uvicorn app.main:app --reload`
   - Access the API at `http://localhost:8000`
   - View API documentation at `http://localhost:8000/docs`

4. **Testing**:
   - Run tests with `pytest`
   - Run linting with `black`, `isort`, and `flake8`
   - Run type checking with `mypy`

5. **Deployment**:
   - Build the Docker image with `docker-compose build`
   - Deploy with `docker-compose up -d`

This structure follows best practices for Python projects and provides a solid foundation for developing and maintaining the MCP Server application.
