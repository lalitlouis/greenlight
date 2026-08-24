.PHONY: install dev run test lint check clean

install:
	python3 -m venv .venv && .venv/bin/pip install -q -U pip && .venv/bin/pip install -r requirements-dev.txt

dev:            ## local ADK dev UI
	.venv/bin/adk web src/greenlight/agents

run:            ## end-to-end on the fixture screenplay
	.venv/bin/python -m greenlight.cli run fixtures/slack_tide.fountain

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check src && .venv/bin/ruff format --check src

check: lint     ## lint + contest-rule dependency scan
	./scripts/check_forbidden_deps.sh && echo "compliance: OK"

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__
