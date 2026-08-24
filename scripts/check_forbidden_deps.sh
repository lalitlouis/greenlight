#!/usr/bin/env bash
# Contest rule enforcement: the Project may use ONLY Google Cloud AI tooling at runtime.
# Non-Google AI SDKs are banned by name in the Official Rules. A single stray dependency
# is a Stage One pass/fail failure, so this runs on every file write.
#
# Exit 2 => blocking error; stderr is fed back to Claude.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT" || exit 0

# Deliberately scans only shipped code and dependency manifests. Docs and CLAUDE.md are
# excluded because they must be able to name these packages in order to forbid them.
TARGETS=()
for f in requirements.txt requirements-dev.txt pyproject.toml package.json web/package.json; do
  [[ -f "$f" ]] && TARGETS+=("$f")
done
for d in src web/src web/app; do
  [[ -d "$d" ]] && TARGETS+=("$d")
done
[[ ${#TARGETS[@]} -eq 0 ]] && exit 0

BANNED='anthropic|openai|langchain|langgraph|llama[-_]index|llamaindex|crewai|pyautogen|autogen|litellm|cohere|mistralai|ollama|replicate|huggingface_hub|azure[-_.]ai|bedrock-runtime'

HITS=$(grep -rEn --binary-files=without-match \
        --exclude-dir=node_modules --exclude-dir=__pycache__ --exclude-dir=.next \
        --exclude-dir=cassettes --exclude='*.lock' --exclude='package-lock.json' \
        "$BANNED" "${TARGETS[@]}" 2>/dev/null)

if [[ -n "$HITS" ]]; then
  cat >&2 <<MSG
BLOCKED — forbidden AI dependency detected in shipped code.

The Agentic Cinema Official Rules permit ONLY Google Cloud AI tooling at runtime and ban
non-Google AI SDKs by name (Anthropic, OpenAI, AWS, Microsoft). This is pass/fail
disqualification at Stage One, not a style issue.

$HITS

Remove it. Use google-adk / google-genai / google-cloud-aiplatform instead. There is no
exception for fallbacks, evals, tests, or commented-out code.
MSG
  exit 2
fi
exit 0
