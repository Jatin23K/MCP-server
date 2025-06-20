# MCP Server - Development Guide

This document provides detailed instructions for setting up a development environment for the MCP Server project.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Development Environment Setup](#development-environment-setup)
- [Running the Application](#running-the-application)
- [Testing](#testing)
- [Code Style and Linting](#code-style-and-linting)
- [Database Migrations](#database-migrations)
- [Docker Development](#docker-development)
- [Debugging](#debugging)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Prerequisites

- Python 3.9 or higher
- [Poetry](https://python-poetry.org/) for dependency management
- [Docker](https://www.docker.com/) and [Docker Compose](https://docs.docker.com/compose/)
- [Git](https://git-scm.com/)
- [Make](https://www.gnu.org/software/make/) (optional but recommended)

## Getting Started

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/mcp-server.git
   cd mcp-server
   ```

2. **Install dependencies**:
   ```bash
   make install-all
   ```

3. **Set up pre-commit hooks**:
   ```bash
   pre-commit install
   ```

4. **Copy the example environment file**:
   ```bash
   cp .env.example .env
   ```
   
   Update the `.env` file with your local configuration.

## Development Environment Setup

### Python Virtual Environment

This project uses Poetry for dependency management. The `make install-all` command will create a virtual environment and install all dependencies.

To activate the virtual environment:

```bash
poetry shell
```

### Database Setup

1. Start the development database and Redis:
   ```bash
   docker-compose up -d db redis
   ```

2. Run database migrations:
   ```bash
   make upgrade-db
   ```

3. (Optional) Initialize the database with sample data:
   ```bash
   make init-db
   ```

## Running the Application

### Development Server

To start the development server with auto-reload:

```bash
make run-dev
```

The API will be available at `http://localhost:8000`.

### API Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Testing

### Running Tests

```bash
# Run all tests
make test

# Run tests with coverage
make test-cov

# Generate HTML coverage report
make test-report
```

### Writing Tests

- Place test files in the `tests/` directory
- Test files should be named `test_*.py`
- Use `pytest` fixtures for test dependencies
- Follow the Arrange-Act-Assert pattern

## Code Style and Linting

This project uses several tools to maintain code quality:

- **Black** for code formatting
- **isort** for import sorting
- **Flake8** for linting
- **Mypy** for static type checking

Run all code quality checks:

```bash
make format lint typecheck
```

## Database Migrations

### Creating Migrations

1. Make your model changes in `app/models/`
2. Generate a new migration:
   ```bash
   make migrate-db m="description of changes"
   ```

### Applying Migrations

```bash
make upgrade-db
```

### Reverting Migrations

To revert the last migration:

```bash
make downgrade-db
```

## Docker Development

### Starting Development Services

```bash
docker-compose up -d
```

This will start:
- MCP Server (development)
- PostgreSQL database
- Redis
- pgAdmin (http://localhost:5050)
- Prometheus (http://localhost:9090)
- Grafana (http://localhost:3000)

### Stopping Services

```bash
docker-compose down
```

### Viewing Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f mcp-server
```

## Debugging

### VS Code Debug Configuration

Add this to your `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "app.main:app",
        "--reload",
        "--host", "0.0.0.0",
        "--port", "8000"
      ],
      "jinja": true,
      "justMyCode": true,
      "env": {
        "ENVIRONMENT": "development",
        "DEBUG": "true"
      }
    }
  ]
}
```

### Debugging Tests

Add this to your `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Current File",
      "type": "python",
      "request": "launch",
      "program": "${file}",
      "purpose": ["debug-test"],
      "console": "integratedTerminal",
      "justMyCode": false
    }
  ]
}
```

## Troubleshooting

### Database Connection Issues

1. Ensure the database service is running:
   ```bash
   docker-compose ps
   ```

2. Check the database logs:
   ```bash
   docker-compose logs db
   ```

3. Test the database connection:
   ```bash
   docker-compose exec db psql -U postgres -d mcp_db -c "SELECT 1"
   ```

### Dependency Issues

1. Ensure you have the latest dependencies:
   ```bash
   poetry update
   ```

2. Clear the Poetry cache:
   ```bash
   poetry cache clear --all
   ```

3. Recreate the virtual environment:
   ```bash
   poetry env remove python
   poetry install
   ```

## Contributing

1. Create a new branch for your feature or bugfix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and commit them with a descriptive message

3. Push your branch and create a pull request

4. Ensure all tests pass and the code meets our quality standards

5. Request a code review from a maintainer
