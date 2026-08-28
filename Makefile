.PHONY: install dev run serve test lint check clean deploy

install:
	python3 -m venv .venv && .venv/bin/pip install -q -U pip && .venv/bin/pip install -r requirements-dev.txt

dev:            ## local ADK dev UI
	.venv/bin/adk web src/greenlight/agents

run:            ## end-to-end on the fixture screenplay
	.venv/bin/python -m greenlight.cli run fixtures/slack_tide.fountain

comps-gate:
	.venv/bin/python scripts/eval_comps.py

scale-gate:     ## end-to-end on the LARGE fixture + graded scale checks
	.venv/bin/python -m greenlight.cli run fixtures/scale_gate.fountain
	.venv/bin/python scripts/eval_scale.py

serve:          ## web UI (upload / live stream / replay) on :8080
	.venv/bin/uvicorn greenlight.server:app --reload --port 8080

test:
	.venv/bin/pytest -q

deploy:         ## guarded deploy: refuses while analyses are in flight; syncs worker image
	./scripts/safe_deploy.sh

logs:           ## tail production logs (structured JSON lines)
	gcloud beta run services logs read greenlight --region us-central1 --limit 80

costs:          ## local spend tracker across GCP / Parallel / ClickHouse / domain
	.venv/bin/python scripts/costs.py

eval:           ## score the latest run against fixtures/SEEDS.md
	.venv/bin/python scripts/eval_run.py

lint:
	.venv/bin/ruff check src tests scripts && .venv/bin/ruff format --check src tests

audit:          ## dependency CVE scan (network)
	.venv/bin/pip-audit --skip-editable

check: lint     ## lint + contest-rule dependency scan
	./scripts/check_forbidden_deps.sh && echo "compliance: OK"

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__
