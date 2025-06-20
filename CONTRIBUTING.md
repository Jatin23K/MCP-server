# Contributing to MCP Server

We're excited that you're interested in contributing to MCP Server! This document outlines the process for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Pull Request Process](#pull-request-process)
- [Code Style](#code-style)
- [Testing](#testing)
- [Documentation](#documentation)
- [Reporting Bugs](#reporting-bugs)
- [Feature Requests](#feature-requests)
- [License](#license)

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** the project to your own machine
3. **Commit** changes to your own branch
4. **Push** your work back up to your fork
5. Submit a **Pull Request** so that we can review your changes

## Development Setup

### Prerequisites

- Python 3.9+
- Poetry (for dependency management)
- Docker and Docker Compose (for containerized development)
- Git

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/mcp-server.git
   cd mcp-server
   ```

2. Install dependencies:
   ```bash
   make install-all
   ```

3. Set up pre-commit hooks:
   ```bash
   pre-commit install
   ```

4. Copy the example environment file and update it with your configuration:
   ```bash
   cp .env.example .env
   ```

5. Start the development services:
   ```bash
   make up-docker-compose
   ```

6. Run database migrations:
   ```bash
   make upgrade-db
   ```

7. Start the development server:
   ```bash
   make run-dev
   ```

The API will be available at `http://localhost:8000` and the API documentation at `http://localhost:8000/docs`.

## Making Changes

1. Create a new branch for your feature or bugfix:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bugfix-name
   ```

2. Make your changes following the [Code Style](#code-style) guidelines

3. Run tests and ensure they pass:
   ```bash
   make test-all
   ```

4. Commit your changes with a descriptive commit message:
   ```bash
   git commit -m "Add feature: your feature description"
   ```

5. Push your changes to your fork:
   ```bash
   git push origin your-branch-name
   ```

## Pull Request Process

1. Ensure any install or build dependencies are removed before the end of the layer when doing a build.
2. Update the README.md with details of changes to the interface, this includes new environment variables, exposed ports, useful file locations, and container parameters.
3. Increase the version numbers in any examples files and the README.md to the new version that this Pull Request would represent.
4. The PR must pass all CI/CD checks before it can be merged.
5. The PR must be reviewed by at least one maintainer before it can be merged.
6. Once the PR is approved, a maintainer will merge it.

## Code Style

We use the following tools to maintain code quality and style:

- **Black** for code formatting
- **isort** for import sorting
- **Flake8** for linting
- **Mypy** for static type checking

Run the following command to format and check your code:

```bash
make format lint typecheck
```

## Testing

We use `pytest` for testing. To run the tests:

```bash
make test
```

To run tests with coverage:

```bash
make test-cov
```

To generate an HTML coverage report:

```bash
make test-report
```

## Documentation

We use Sphinx for documentation. To build the documentation:

```bash
make docs
```

Documentation will be available in the `docs/_build/html` directory.

## Reporting Bugs

Please use the [GitHub issue tracker](https://github.com/yourusername/mcp-server/issues) to report bugs. Include the following information in your bug report:

1. A clear and descriptive title
2. Steps to reproduce the issue
3. Expected behavior
4. Actual behavior
5. Screenshots if applicable
6. Your environment (OS, Python version, etc.)

## Feature Requests

We welcome feature requests! Please use the [GitHub issue tracker](https://github.com/yourusername/mcp-server/issues) to suggest new features. Include the following information in your feature request:

1. A clear and descriptive title
2. A description of the problem you're trying to solve
3. Any alternative solutions or features you've considered
4. Additional context or screenshots if applicable

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
