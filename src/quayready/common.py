from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

Json = dict[str, Any]
CONTRACTS = files("quayready").joinpath("contracts")
SPEC = json.loads(CONTRACTS.joinpath("openapi.json").read_text())


class Problem(Exception):
    def __init__(self, status: int, code: str, message: str | None = None):
        self.status, self.code = status, code
        self.message = message or code.replace("_", " ").capitalize()
        super().__init__(self.message)

    def body(self) -> Json:
        return {
            "code": self.code,
            "message": self.message,
            "correlationId": uid(),
            "retryable": self.status in (429, 503),
            "fieldErrors": [],
        }


def uid() -> str:
    return str(uuid.uuid4())


def wall_ms() -> int:
    return time.time_ns() // 1_000_000


def instant(value: str) -> int:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Offset required")
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = dt.astimezone(timezone.utc) - epoch
    return delta.days * 86400000 + delta.seconds * 1000 + delta.microseconds // 1000


def iso(value: int) -> str:
    return (
        datetime.fromtimestamp(value / 1000, timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def canonical(value: Any) -> str:
    if isinstance(value, dict):
        value = {k: normalize(k, v) for k, v in value.items()}
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def normalize(key: str, value: Any) -> Any:
    if key in ("observedAt", "cutoffAt"):
        return iso(instant(value))
    if key in ("expectedPalletIds", "scannedPalletIds"):
        return sorted(value)
    return value


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate(schema: str, value: Any) -> Any:
    root = {"$ref": f"#/components/schemas/{schema}", "components": SPEC["components"]}
    errors = list(Draft202012Validator(root, format_checker=FormatChecker()).iter_errors(value))
    if errors or contains_float(value):
        raise Problem(422, "INVALID_SCHEMA")
    dates = (
        [value]
        if schema == "Instant"
        else [
            value[k]
            for k in ("observedAt", "cutoffAt", "acceptedAt")
            if isinstance(value, dict) and k in value
        ]
    )
    try:
        if any(instant(v) < 0 for v in dates):
            raise ValueError("Pre-epoch timestamps are outside the persisted contract")
    except (ValueError, OverflowError, OSError):
        raise Problem(
            422, "INVALID_SCHEMA", "Timestamp is outside the supported UTC range"
        ) from None
    return value


def contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(contains_float(v) for v in value.values())
    if isinstance(value, list):
        return any(contains_float(v) for v in value)
    return False


def parse_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> Json:
        out: Json = {}
        for key, value in items:
            if key in out:
                raise ValueError("Duplicate JSON key")
            out[key] = value
        return out

    def constant(value: str) -> Any:
        raise ValueError("Non-finite JSON")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise Problem(400, "MALFORMED_JSON") from None
