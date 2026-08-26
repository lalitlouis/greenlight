"""Shared genai client factory: global endpoint + a real 429 retry ladder.

The genai client defaults to NO retries. Interactive features (First Look,
What-If, format checks) get a short ladder — a user is watching, so ~30s of
patience beats minutes of silence; the agent pipeline's long ladder lives on
the Gemini model instances in agents/common.py.
"""

from __future__ import annotations

import os

from google import genai
from google.genai import types

_INTERACTIVE_RETRY = types.HttpOptions(
    retry_options=types.HttpRetryOptions(
        attempts=4, initial_delay=2, max_delay=15, exp_base=2, jitter=0.5
    )
)


def vertex_client() -> genai.Client:
    return genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        http_options=_INTERACTIVE_RETRY,
    )
