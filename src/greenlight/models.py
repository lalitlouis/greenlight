"""Single source of truth for model names.

3.x Gemini models serve only from the global endpoint (GOOGLE_CLOUD_LOCATION=global,
which is prod's setting; EMBED_LOCATION stays regional for text-embedding-005).
Any change to these defaults must pass the 21-check fixture eval before it lands.
"""

from __future__ import annotations

import os

FLASH_MODEL = os.getenv("GREENLIGHT_FLASH_MODEL", "gemini-3.7-flash")
PRO_MODEL = os.getenv("GREENLIGHT_PRO_MODEL", "gemini-2.5-pro")
