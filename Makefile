.PHONY: help up down test lint migrate migrate-new run install

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install backend dependencies
	cd backend && pip install -e ".[dev]"

up: ## Start all services via docker-compose
	docker-compose up -d

down: ## Stop all services
	docker-compose down

run: ## Run the backend server locally
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test: ## Run backend tests
	cd backend && python -m pytest tests/ -v

lint: ## Run linter
	cd backend && python -m ruff check app/ tests/

migrate: ## Run database migrations
	cd backend && alembic upgrade head

migrate-new: ## Create a new migration (usage: make migrate-new msg="description")
	cd backend && alembic revision --autogenerate -m "$(msg)"

migrate-down: ## Downgrade one migration
	cd backend && alembic downgrade -1
