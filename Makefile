.PHONY: help install install-dev install-test install-docs install-all format lint test test-cov test-report test-all typecheck security check-deps check-updates clean clean-build clean-pyc clean-test clean-all build-docker run-docker stop-docker restart-docker logs-docker shell-docker build-docker-compose up-docker-compose down-docker-compose restart-docker-compose logs-docker-compose shell-db migrate-db upgrade-db downgrade-db reset-db init-db

# Default target
help:
	@echo "Please use 'make <target>' where <target> is one of:"
	@echo "  \033[36m  install\033[0m         Install production dependencies"
	@echo "  \033[36m  install-dev\033[0m     Install development dependencies"
	@echo "  \033[36m  install-test\033[0m    Install test dependencies"
	@echo "  \033[36m  install-docs\033[0m    Install documentation dependencies"
	@echo "  \033[36m  install-all\033[0m     Install all dependencies"
	@echo "  \033[36m  format\033[0m          Format code with Black and isort"
	@echo "  \033[36m  lint\033[0m            Lint code with flake8 and mypy"
	@echo "  \033[36m  test\033[0m            Run tests quickly with pytest"
	@echo "  \033[36m  test-cov\033[0m        Run tests with coverage report"
	@echo "  \033[36m  test-report\033[0m     Generate HTML coverage report"
	@echo "  \033[36m  test-all\033[0m        Run all tests and checks"
	@echo "  \033[36m  typecheck\033[0m       Run type checking with mypy"
	@echo "  \033[36m  security\033[0m        Check for security issues"
	@echo "  \033[36m  check-deps\033[0m      Check for outdated dependencies"
	@echo "  \033[36m  check-updates\033[0m   Check for package updates"
	@echo "  \033[36m  clean\033[0m            Remove all build, test, coverage and Python artifacts"
	@echo "  \033[36m  build-docker\033[0m     Build Docker image"
	@echo "  \033[36m  run-docker\033[0m       Run Docker container"
	@echo "  \033[36m  stop-docker\033[0m      Stop Docker container"
	@echo "  \033[36m  restart-docker\033[0m   Restart Docker container"
	@echo "  \033[36m  logs-docker\033[0m      Show Docker container logs"
	@echo "  \033[36m  shell-docker\033[0m     Open shell in Docker container"
	@echo "  \033[36m  build-docker-compose\033[0m  Build Docker Compose services"
	@echo "  \033[36m  up-docker-compose\033[0m    Start Docker Compose services"
	@echo "  \033[36m  down-docker-compose\033[0m  Stop and remove Docker Compose services"
	@echo "  \033[36m  restart-docker-compose\033[0m  Restart Docker Compose services"
	@echo "  \033[36m  logs-docker-compose\033[0m   Show Docker Compose logs"
	@echo "  \033[36m  shell-db\033[0m         Open shell in database container"
	@echo "  \033[36m  migrate-db\033[0m       Create new migration"
	@echo "  \033[36m  upgrade-db\033[0m       Upgrade database to latest migration"
	@echo "  \033[36m  downgrade-db\033[0m     Downgrade database by one migration"
	@echo "  \033[36m  reset-db\033[0m         Reset database to clean state"
	@echo "  \033[36m  init-db\033[0m          Initialize database with sample data"

# Install dependencies
install:
	poetry install --no-dev

install-dev:
	poetry install

install-test:
	poetry install --with test

install-docs:
	poetry install --with docs

install-all:
	poetry install --with dev,docs,test

# Code formatting
format:
	poetry run black .
	poetry run isort .


# Linting
lint:
	poetry run flake8 app tests
	poetry run mypy app

# Testing
test:
	poetry run pytest -v

test-cov:
	poetry run pytest --cov=app --cov-report=term-missing

test-report:
	poetry run pytest --cov=app --cov-report=html
	@echo "Open htmlcov/index.html in your browser"

test-all:
	make format
	make lint
	make test-cov

# Type checking
typecheck:
	poetry run mypy app

# Security
security:
	poetry run safety check
	poetry run bandit -r app

# Dependency management
check-deps:
	poetry show --outdated

check-updates:
	poetry update --dry-run

# Cleanup
clean: clean-build clean-pyc clean-test

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test:
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache
	rm -fr .mypy_cache

# Docker commands
build-docker:
	docker build -t mcp-server .

run-docker:
	docker run -d --name mcp-server -p 8000:8000 mcp-server

stop-docker:
	docker stop mcp-server || true
	docker rm mcp-server || true

restart-docker: stop-docker run-docker

logs-docker:
	docker logs -f mcp-server

shell-docker:
	docker exec -it mcp-server /bin/bash

# Docker Compose commands
build-docker-compose:
	docker-compose build

up-docker-compose:
	docker-compose up -d

down-docker-compose:
	docker-compose down

restart-docker-compose:
	docker-compose restart

logs-docker-compose:
	docker-compose logs -f

shell-db:
	docker-compose exec db psql -U postgres -d mcp_db

# Database commands
migrate-db:
	poetry run alembic revision --autogenerate -m "$(m)"

upgrade-db:
	poetry run alembic upgrade head

downgrade-db:
	poetry run alembic downgrade -1

reset-db:
	poetry run alembic downgrade base
	poetry run alembic upgrade head

init-db:
	poetry run python -m app.scripts.init_db

# Default target
.DEFAULT_GOAL := help
