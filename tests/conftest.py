from __future__ import annotations

import json
import os
import re
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quayready.api import create_app
from quayready.cli import initialize, key_for
from quayready.common import Json, iso
from quayready.config import Settings, load_settings
from quayready.store import Store

OBSERVED: set[tuple[str, str, str]] = set()


def pytest_sessionfinish(session, exitstatus):
    from quayready.common import SPEC

    expected = {
        (p, m, status)
        for p, v in SPEC["paths"].items()
        for m, op in v.items()
        if m in ("get", "post", "delete")
        for status in op["responses"]
    }
    missing = expected - OBSERVED
    full = os.getenv("QUAYREADY_FULL_CONTRACT_GATE") == "1"
    destination = Path(
        "evidence/rc/response-coverage.json" if full else ".runs/response-coverage.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "kind": "declared operation/method/status combinations actually schema-validated in execution; not code coverage",
                "declared": len(expected),
                "observed": len(OBSERVED),
                "missing": [list(x) for x in sorted(missing)],
                "fullGate": full,
            },
            indent=2,
        )
        + "\n"
    )
    if full and missing:
        session.exitstatus = 1


def port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    path = initialize(tmp_path / "run", port(), port())
    monkeypatch.setenv("QUAYREADY_CONFIG", str(path))
    return load_settings()


@pytest.fixture
def store(cfg: Settings) -> Store:
    return Store(cfg)


@pytest.fixture
def client(cfg: Settings):
    with TestClient(create_app(cfg), base_url=cfg.origin) as c:
        original = c.request

        def checked(method, url, **kwargs):
            from test_contracts import response_contract

            from quayready.common import SPEC

            result = original(method, url, **kwargs)
            path = str(url).split("?")[0]
            for route, operations in SPEC["paths"].items():
                pattern = re.sub(r"\{[^}]+\}", "[^/]+", route)
                if re.fullmatch(pattern, path) and method.lower() in operations:
                    response_contract(result, route, method.lower())
                    break
            return result

        c.request = checked
        yield c


def login(client, cfg: Settings, role: str = "OPERATOR") -> dict[str, str]:
    r = client.post(
        "/v1/session", json={"loginToken": key_for(cfg, role)}, headers={"Origin": cfg.origin}
    )
    assert r.status_code == 200, r.text
    return {
        "Origin": cfg.origin,
        "X-CSRF-Token": r.json()["csrfToken"],
        "Idempotency-Key": "DEMO-KEY-0001",
    }


def bodies(cfg: Settings, sid: str = "") -> tuple[Json, Json, Json]:
    order = {
        "schemaVersion": 1,
        "eventId": "DEMO-ORDER-E001",
        "externalOrderRef": "DEMO-ORDER-001",
        "orderRevision": 1,
        "route": "DEMO-EU-GB",
        "cutoffAt": "2026-11-02T12:00:00Z",
        "expectedPalletIds": ["DEMO-P001", "DEMO-P002", "DEMO-P003"],
    }
    wh = {
        "schemaVersion": 1,
        "eventId": "DEMO-WMS-E001",
        "shipmentId": sid,
        "sourceRevision": 1,
        "observedAt": iso(cfg.now()),
        "watermark": "DEMO-WMS-W001",
        "kind": "warehouse_snapshot",
        "status": "KNOWN",
        "scannedPalletIds": ["DEMO-P001", "DEMO-P002"],
        "hardHold": False,
    }
    doc = {
        "schemaVersion": 1,
        "eventId": "DEMO-DOC-E001",
        "shipmentId": sid,
        "sourceRevision": 1,
        "observedAt": iso(cfg.now()),
        "watermark": "DEMO-DOC-W001",
        "kind": "document_snapshot",
        "status": "AVAILABLE",
    }
    return order, wh, doc


def ready(store: Store, correct: bool = True) -> str:
    cfg = store.settings

    def source(kind):
        return cfg.principals[key_for(cfg, kind)]

    order, _, _ = bodies(cfg)
    _, r = store.ingest(source("ORDER"), order, "ORDER")
    sid = r["shipmentId"]
    _, wh, doc = bodies(cfg, sid)
    store.ingest(source("WAREHOUSE"), wh, "WAREHOUSE")
    store.ingest(source("DOCUMENT"), doc, "DOCUMENT")
    if correct:
        wh.update(
            eventId="DEMO-WMS-E002",
            sourceRevision=2,
            watermark="DEMO-WMS-W002",
            scannedPalletIds=order["expectedPalletIds"],
        )
        store.ingest(source("WAREHOUSE"), wh, "WAREHOUSE")
    return sid


def approve(store: Store, sid: str) -> str:
    cfg = store.settings
    op = cfg.principals[key_for(cfg, "OPERATOR")]
    rev = cfg.principals[key_for(cfg, "REVIEWER")]
    v = store.view(op, sid)["evidenceVersion"]
    _, proposal = store.proposal(op, sid, "DEMO-PROP-0001", {"expectedEvidenceVersion": v})
    result = store.decide(
        rev,
        proposal["proposalId"],
        "DEMO-DEC-0001",
        {
            "decision": "APPROVE",
            "expectedEvidenceVersion": v,
            "reason": "Checked synthetic sources",
        },
    )
    return result["dispatchId"]
