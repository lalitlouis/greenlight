.PHONY: install dev run serve test lint check clean

install:
	python3 -m venv .venv && .venv/bin/pip install -q -U pip && .venv/bin/pip install -r requirements-dev.txt

dev:            ## local ADK dev UI
	.venv/bin/adk web src/greenlight/agents

run:            ## end-to-end on the fixture screenplay
	.venv/bin/python -m greenlight.cli run fixtures/slack_tide.fountain

serve:          ## web UI (upload / live stream / replay) on :8080
	.venv/bin/uvicorn greenlight.server:app --reload --port 8080

test:
	.venv/bin/pytest -q

costs:          ## local spend tracker across GCP / Parallel / ClickHouse / domain
	.venv/bin/python scripts/costs.py

eval:           ## score the latest run against fixtures/SEEDS.md
	.venv/bin/python scripts/eval_run.py

lint:
	.venv/bin/ruff check src && .venv/bin/ruff format --check src

check: lint     ## lint + contest-rule dependency scan
	./scripts/check_forbidden_deps.sh && echo "compliance: OK"

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__
