import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from conftest import approve, bodies, ready
from processes import server

from quayready.cli import key_for
from quayready.common import uid, wall_ms
from quayready.db import Database
from quayready.store import Store
from quayready.worker import Worker

pytestmark = pytest.mark.integration


def row(store):
    with store.db.transaction(False) as c:
        return dict(c.execute("SELECT * FROM outbox").fetchone())


def effects(cfg):
    with Database(cfg.run_dir / "target.db", True).transaction(False) as c:
        return c.execute("SELECT COUNT(*) FROM dispatch_requests").fetchone()[0]


def test_T13_T19_T32_response_loss_real_HTTP(cfg, store):
    sid = ready(store)
    dispatch = approve(store, sid)
    clock = [wall_ms()]
    worker = Worker(store, lambda: clock[0])
    checks = []
    worker.before_http = lambda _: checks.append(not store.db.transaction_active)
    with server(cfg, fault="drop-after-commit") as url:
        worker.tick()
        assert row(store)["state"] == "RETRY_WAIT"
        assert effects(cfg) == 1
        clock[0] += 3000
        # New Store and Worker instances cannot rely on an in-memory receipt.
        restarted = Worker(Store(cfg), lambda: clock[0])
        restarted.before_http = worker.before_http
        assert restarted.tick()["next_action"] == "LOOKUP"
        result = row(store)
        assert result["state"] == "CONFIRMED" and result["dispatch_id"] == dispatch
        assert result["post_attempts"] == result["lookup_attempts"] == 1
        payload = json.loads(result["payload_json"])
        headers = {"X-Worker-Key": cfg.worker_key}
        with httpx.Client(base_url=url, trust_env=False) as client:
            receipt = client.get(f"/mock/v1/dispatch-requests/{dispatch}", headers=headers)
            duplicate = client.post("/mock/v1/dispatch-requests", json=payload, headers=headers)
            assert duplicate.status_code == 200 and duplicate.json() == receipt.json()
            payload["dispatchId"] = uid()
            assert (
                client.post("/mock/v1/dispatch-requests", json=payload, headers=headers).status_code
                == 409
            )
        assert effects(cfg) == 1
    assert checks == [True, True]
    with server(cfg) as url:
        assert (
            httpx.get(
                url + f"/mock/v1/dispatch-requests/{dispatch}", headers=headers, trust_env=False
            ).json()
            == receipt.json()
        )


def test_T12_real_API_restart_persists_queue_and_invalidates_session(cfg):
    with server(cfg, "serve") as url:
        with httpx.Client(base_url=url, trust_env=False) as client:
            store = Store(cfg)
            sid = ready(store)
            dispatch = approve(store, sid)
            assert row(store)["state"] == "QUEUED"
            r = client.post(
                "/v1/session",
                json={"loginToken": key_for(cfg, "OPERATOR")},
                headers={"Origin": url},
            )
            assert r.status_code == 200
            cookie = client.cookies.get("qr_session")
    with server(cfg, "serve") as url, server(cfg):
        assert (
            httpx.get(
                url + f"/v1/shipments/{sid}", cookies={"qr_session": cookie}, trust_env=False
            ).status_code
            == 401
        )
        Worker(Store(cfg)).tick()
        assert row(Store(cfg))["state"] == "CONFIRMED"
        assert row(Store(cfg))["dispatch_id"] == dispatch and effects(cfg) == 1


def test_T14_T17_crash_after_target_commit_before_local_result(cfg, store):
    approve(store, ready(store))
    clock = [wall_ms()]
    worker = Worker(store, lambda: clock[0])

    class Crash(Exception):
        pass

    def crash(_):
        raise Crash()

    worker.after_http = crash
    with server(cfg):
        with pytest.raises(Crash):
            worker.tick()
        old = row(store)
        assert old["state"] == "SENDING" and effects(cfg) == 1
        clock[0] += 30001
        restarted = Worker(Store(cfg), lambda: clock[0])
        assert restarted.tick()["next_action"] == "LOOKUP"
        assert row(store)["state"] == "CONFIRMED" and effects(cfg) == 1
        assert not worker.finish(old, 0, None)


def test_T15_T17_claim_crash_fence_and_clock_rollback(cfg, store):
    approve(store, ready(store))
    clock = [wall_ms()]
    worker = Worker(store, lambda: clock[0])
    with ThreadPoolExecutor(2) as pool:
        claims = list(pool.map(lambda _: Worker(Store(cfg), lambda: clock[0]).claim(), range(2)))
    old = next(c for c in claims if c)
    assert len([c for c in claims if c]) == 1
    clock[0] -= 1
    with pytest.raises(RuntimeError, match="backwards"):
        worker.claim()
    clock[0] += 30002
    with server(cfg):
        assert worker.tick()["next_action"] == "LOOKUP"
        assert row(store)["next_action"] == "POST"
        assert not worker.finish(old, 0, None)
        clock[0] += 10000
        worker.tick()
        assert row(store)["state"] == "CONFIRMED"
        assert row(store)["post_attempts"] == 2 and effects(cfg) == 1


def test_T16_retry_exhaustion_persists(cfg, store):
    approve(store, ready(store))
    clock = [wall_ms()]
    with server(cfg, fault="unavailable"):
        for _ in range(8):
            Worker(Store(cfg), lambda: clock[0]).tick()
            clock[0] += 10000
    result = row(store)
    assert result["state"] == "MANUAL_REVIEW"
    assert result["post_attempts"] == 1 and result["lookup_attempts"] == 3
    assert result["last_error_code"] == "RETRY_EXHAUSTED" and effects(cfg) == 0
    assert Worker(Store(cfg), lambda: clock[0]).tick() is None


@pytest.mark.parametrize("reserved", [False, True])
def test_T18_source_change_no_new_POST(cfg, store, reserved):
    sid = ready(store)
    approve(store, sid)
    clock = [wall_ms()]
    worker = Worker(store, lambda: clock[0])
    if reserved:
        worker.claim()  # A crashed POST reservation is uncertain even with no network send.
    _, _, doc = bodies(cfg, sid)
    doc.update(eventId="DEMO-DOC-CHANGED", sourceRevision=2, status="MISSING")
    store.ingest(cfg.principals[key_for(cfg, "DOCUMENT")], doc, "DOCUMENT")
    with server(cfg):
        clock[0] += 30001
        worker.tick()
    expected = "MANUAL_REVIEW" if reserved else "CANCELLED_BEFORE_SEND"
    assert row(store)["state"] == expected and effects(cfg) == 0
    assert row(store)["post_attempts"] == int(reserved)


def test_T10_database_failure_rolls_back_receipt(client, store, cfg, monkeypatch):
    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("injected local commit-stage failure")

    monkeypatch.setattr(client.app.state.store, "audit", broken)
    order, _, _ = bodies(cfg)
    response = client.post(
        "/v1/orders", json=order, headers={"X-Source-Key": key_for(cfg, "ORDER")}
    )
    assert response.status_code == 503
    with store.db.transaction(False) as c:
        for table in ("shipments", "expected_pallets", "inbound_receipts", "audit_events"):
            assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
