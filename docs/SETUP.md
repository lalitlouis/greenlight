# Provisioning

Four external services. Steps marked **[you]** need a browser or an interactive login and cannot
be automated; everything else is scripted.

---

## 1. GitHub  **[you]**

```bash
gh auth login          # choose GitHub.com -> HTTPS -> login with a web browser
```

Then (automatable once authed):

```bash
gh repo create greenlight --public --source=. --remote=origin --push
```

The repo must be **public** with `LICENSE` at root before submission — GitHub's About sidebar
must show "MIT License". Verify with: `gh repo view --json licenseInfo`.

---

## 2. Google Cloud  **[you for the logins]**

```bash
gcloud auth login                      # [you] browser
gcloud auth application-default login  # [you] browser — this is what the SDKs actually use
```

Then create the project and enable services:

```bash
export PROJECT_ID=greenlight-<something-unique>
gcloud projects create "$PROJECT_ID"
gcloud config set project "$PROJECT_ID"

# [you] Link billing in the console — the $100 credit attaches to a billing account:
#   https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID
gcloud beta billing projects describe "$PROJECT_ID"   # confirm billingEnabled: true

gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com

gcloud storage buckets create "gs://${PROJECT_ID}-staging" --location=us-central1
```

**Cost discipline.** $100 covers the entire project. Agent Engine bills for idle replicas, so
develop against local `adk web` and deploy late. Set a budget alert at $40 and $75:
https://console.cloud.google.com/billing/budgets

---

## 3. Parallel  **[you]**

The Parallel track requires the **Search API** to be called at runtime via `parallel-web`.

1. Sign up at https://platform.parallel.ai
2. Create an API key.
3. Put it in `.env` as `PARALLEL_API_KEY`.

Docs: https://docs.parallel.ai

Smoke test before building anything on top of it:

```bash
.venv/bin/python -m greenlight.checks parallel
```

---

## 4. ClickHouse Cloud  **[you]**

Used here as a **plain database** (precedent corpus + kNN), which the rules permit on a
non-ClickHouse track. Not our submitted track, so no MCP server requirement.

1. Sign up at https://console.clickhouse.cloud (free trial).
2. Create a service in a region near `us-central1`.
3. Copy host, user, and password into `.env`.

```bash
.venv/bin/python -m greenlight.checks clickhouse
```

---

## Verify everything at once

```bash
cp .env.example .env    # fill it in
make install
.venv/bin/python -m greenlight.checks all
```

`checks all` must pass before Phase 1 work starts. Two of these are contest pass/fail gates
(Google Cloud called at runtime, Parallel called at runtime) — a broken credential is not a
minor blocker.
