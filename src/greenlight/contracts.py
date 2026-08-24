"""Frozen data contracts, loaded from schemas/ and enforced at runtime.

The schemas are the interface between the agent workstream and the data/UI workstream.
This module is the only place that reads them; everything else calls validate().

Invariant enforced here, not in prompts: a Flag without a citation is invalid.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "schemas"

SCHEMA_NAMES = ("scene", "entity", "flag", "report")


@cache
def load_schema(name: str) -> dict[str, Any]:
    """Load one of the frozen schemas: scene, entity, flag, report."""
    if name not in SCHEMA_NAMES:
        raise KeyError(f"unknown schema {name!r}; expected one of {SCHEMA_NAMES}")
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text())


@cache
def _validator(name: str) -> jsonschema.Validator:
    schema = load_schema(name)
    # The report schema $refs the flag schema by its $id; register it.
    registry_schemas = {load_schema("flag")["$id"]: load_schema("flag")}
    try:
        from referencing import Registry, Resource

        registry = Registry().with_resources(
            (uri, Resource.from_contents(s)) for uri, s in registry_schemas.items()
        )
        return jsonschema.Draft202012Validator(schema, registry=registry)
    except ImportError:  # pragma: no cover - referencing ships with jsonschema>=4.18
        return jsonschema.Draft202012Validator(schema)


class ContractViolation(ValueError):  # noqa: N818 - domain vocabulary, is-a ValueError
    """An object failed validation against a frozen schema."""

    def __init__(self, schema_name: str, errors: list[str]):
        self.schema_name = schema_name
        self.errors = errors
        super().__init__(f"{schema_name} contract violation: " + "; ".join(errors))


def validate(name: str, obj: dict[str, Any]) -> dict[str, Any]:
    """Validate obj against the named schema. Returns obj unchanged, or raises.

    Raises ContractViolation listing every error, not just the first — an agent
    correcting a rejected flag needs the full list in one round trip.
    """
    errors = sorted(_validator(name).iter_errors(obj), key=lambda e: list(e.path))
    if errors:
        msgs = [f"{'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}" for e in errors]
        raise ContractViolation(name, msgs)
    return obj


def is_valid(name: str, obj: dict[str, Any]) -> bool:
    try:
        validate(name, obj)
    except ContractViolation:
        return False
    return True
