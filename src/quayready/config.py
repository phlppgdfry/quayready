from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import instant, wall_ms


@dataclass(frozen=True)
class Principal:
    subject: str
    site: str
    roles: tuple[str, ...]
    kind: str | None = None


@dataclass
class Settings:
    run_dir: Path
    principals: dict[str, Principal]
    worker_key: str
    domain_time: int | None = None
    app_port: int = 8080
    target_port: int = 8081
    target_fault: str = "none"

    def now(self) -> int:
        return self.domain_time if self.domain_time is not None else wall_ms()

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.app_port}"

    def __post_init__(self) -> None:
        if (
            not self.principals
            or any(len(k) < 32 for k in self.principals)
            or len(self.worker_key) < 32
        ):
            raise ValueError("Random credentials of at least 32 characters required")
        if self.worker_key in self.principals:
            raise ValueError("Worker and caller credentials must differ")
        if self.app_port == self.target_port or not all(
            1024 <= p <= 65535 for p in (self.app_port, self.target_port)
        ):
            raise ValueError("Two separate local unprivileged ports required")
        if self.target_fault not in ("none", "drop-after-commit", "unavailable"):
            raise ValueError("Unsupported test fault")


def load_settings() -> Settings:
    path = Path(os.environ["QUAYREADY_CONFIG"])
    data: dict[str, Any] = json.loads(path.read_text())
    principals = {
        key: Principal(p["subject"], p["site"], tuple(p["roles"]), p.get("kind"))
        for key, p in data["principals"].items()
    }
    return Settings(
        path.parent,
        principals,
        data["workerKey"],
        instant(data["domainTime"]) if data.get("domainTime") else None,
        data.get("appPort", 8080),
        data.get("targetPort", 8081),
        os.getenv("QUAYREADY_TARGET_FAULT", "none"),
    )
