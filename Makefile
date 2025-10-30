# variables
uv     := uv
python := $(uv) run python
pytest := $(uv) run pytest
ruff   := $(uv) run ruff


##@ Utility
.PHONY: help
help:  ## Display this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make <target>\033[36m\033[0m\n"} /^[a-zA-Z\._-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)


##@ Setup
.PHONY: sync
sync:  ## sync dependencies using uv
	$(uv) sync --all-extras

.PHONY: clean
clean:  ## remove virtual environment and caches
	rm -rf .venv
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

##@ Development
.PHONY: dev
dev: sync ## install dev mode
	@echo "Development environment ready"

.PHONY: test
test:  ## run tests
	$(pytest) tests

.PHONY: lint
lint:  ## run linting check
	$(ruff) check ./src

.PHONY: format
format:  ## format code with ruff
	$(ruff) format ./src
	$(ruff) check --fix ./src
