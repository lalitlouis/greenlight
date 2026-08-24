"""Shared agent configuration."""

from google.adk.workflow._retry_config import RetryConfig

# New GCP projects carry tight per-minute Gemini quotas; a 429 mid-loop must not
# kill a run that has live research in session state. Backoff rides out the window.
RETRY = RetryConfig(max_attempts=6, initial_delay=10, max_delay=60, backoff_factor=2)
