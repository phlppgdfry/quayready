"""Adversarial peers and independently owned processes; no production connections."""

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import approve, ready
from processes import server
from test_recovery import effects, row

from quayready.cli import key_for
from quayready.common import Problem, wall_ms
from quayready.db import Database
from quayready.worker import Worker

pytestmark = pytest.mark.integration


@contextmanager
def peer(cfg, mode, status=200, payload=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                # Consume the known worker request before closing this HTTP/1.0 peer.
                # Unread inbound bytes can cause a TCP reset, unintentionally truncating
                # the response instead of exercising the selected response fault.
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                if mode == "headers":
                    for byte in b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n":
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        time.sleep(0.15)
                    return
                if mode == "delay":
                    time.sleep(4)
                data = (
                    b"x" * 65537
                    if mode == "oversize"
                    else b"{broken"
                    if mode == "malformed"
                    else b"{}"
                )
                self.send_response(status)
                if payload is not None:
                    data = json.dumps(payload).encode()
                self.send_header(
                    "Content-Type", "text/plain" if mode == "wrong-mime" else "application/json"
                )
                self.send_header("Content-Length", str(len(data) if mode != "trickle" else 100))
                self.end_headers()
                if mode == "trickle":
                    for _ in range(30):
                        self.wfile.write(b"x")
                        self.wfile.flush()
                        time.sleep(0.2)
                else:
                    self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        do_GET = do_POST

    http = ThreadingHTTPServer(("127.0.0.1", cfg.target_port), Handler)
    http.daemon_threads = True
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("mode", ["delay", "trickle", "headers", "oversize", "malformed"])
def test_E2_absolute_deadline_and_response_limits(cfg, store, mode):
    approve(store, ready(store))
    worker = Worker(store)
    with peer(cfg, mode):
        started = time.monotonic()
        worker.tick()
        elapsed = time.monotonic() - started
    assert elapsed < 3.8, (mode, elapsed)
    assert row(store)["state"] == (
        "MANUAL_REVIEW" if mode in ("oversize", "malformed") else "RETRY_WAIT"
    )
    assert row(store)["post_attempts"] == 1


@pytest.mark.parametrize("status", [301, 400, 401, 403, 404, 409, 422])
def test_E2_permanent_target_error_never_retried(cfg, store, status):
    approve(store, ready(store))
    with peer(cfg, "error", status):
        Worker(store).tick()
    assert row(store)["state"] == "MANUAL_REVIEW"
    assert Worker(store).tick() is None


def test_E2_real_result_COMMIT_failure_rolls_back_then_recovers(cfg, store, monkeypatch):
    approve(store, ready(store))
    clock = [wall_ms()]
    worker = Worker(store, lambda: clock[0])
    claim = worker.claim()
    with server(cfg):
        result = worker.request(claim)
        assert effects(cfg) == 1
        original = store.db.connect

        def fail_commit():
            c = original()
            c.set_authorizer(
                lambda action, a, b, d, s: (
                    sqlite3.SQLITE_DENY
                    if action == sqlite3.SQLITE_TRANSACTION and a == "COMMIT"
                    else sqlite3.SQLITE_OK
                )
            )
            return c

        with monkeypatch.context() as m:
            m.setattr(store.db, "connect", fail_commit)
            with pytest.raises(sqlite3.DatabaseError):
                worker.finish(claim, *result)
        assert row(store)["state"] == "SENDING"
        clock[0] += 30001
        worker.tick()
        assert row(store)["state"] == "CONFIRMED" and effects(cfg) == 1


def test_E2_manual_reconcile_GET_only_authorized_and_barrier_preserved(cfg, store, client):
    dispatch = approve(store, ready(store))
    worker = Worker(store)
    with server(cfg):
        claim = worker.claim()
        status, receipt, _ = worker.request(claim)
        # A contract error leaves target's real committed effect uncertain locally.
        worker.finish(claim, -1, None)
        before = row(store)
        source = cfg.principals[key_for(cfg, "ORDER")]
        with pytest.raises(Problem) as denied:
            worker.reconcile(source, dispatch)
        assert denied.value.status == 403
        reviewer = cfg.principals[key_for(cfg, "REVIEWER")]
        requests = []
        worker.before_http = lambda r: requests.append(r["next_action"])
        result = worker.reconcile(reviewer, dispatch)
        assert result["status"] == "CONFIRMED" and result["targetReceipt"] == receipt
        assert requests == ["LOOKUP"] and effects(cfg) == 1
        after = row(store)
        assert (
            before["post_attempts"],
            before["lookup_attempts"],
            before["dispatch_id"],
            before["payload_hash"],
        ) == (
            after["post_attempts"],
            after["lookup_attempts"],
            after["dispatch_id"],
            after["payload_hash"],
        )


def test_E2_manual_reconcile_404_remains_uncertain(cfg, store):
    approve(store, ready(store))
    worker = Worker(store)
    claim = worker.claim()
    worker.finish(claim, -1, None)
    with server(cfg):
        result = worker.reconcile(cfg.principals[key_for(cfg, "REVIEWER")], claim["dispatch_id"])
        assert result["status"] == "MANUAL_REVIEW" and effects(cfg) == 0
    with store.db.transaction(False) as c:
        assert (
            c.execute(
                "SELECT COUNT(*) FROM audit_events WHERE kind='manual_lookup_unresolved'"
            ).fetchone()[0]
            == 1
        )
        assert (
            c.execute(
                "SELECT COUNT(*) FROM outbox WHERE state!='CANCELLED_BEFORE_SEND'"
            ).fetchone()[0]
            == 1
        )


def test_E2_target_migrates_existing_E1_without_losing_effect(cfg):
    path = cfg.run_dir / "legacy.db"
    from quayready.common import CONTRACTS, canonical, digest, uid

    payload = {
        "dispatchId": uid(),
        "shipmentRef": "DEMO-ORDER-001",
        "orderRevision": 1,
        "evidenceVersion": 4,
        "evidenceHash": "0" * 64,
        "rulesVersion": "readiness-v1",
        "approvedProposalId": uid(),
        "requestType": "REQUEST_DISPATCH_REVIEW",
    }
    receipt_id = uid()

    with sqlite3.connect(path) as c:
        c.executescript(CONTRACTS.joinpath("001-target.sql").read_text())
        c.execute("PRAGMA user_version=1")
        c.execute("INSERT INTO target_orders VALUES('DEMO-ZEE','DEMO-ORDER-001',1)")
        c.execute(
            "INSERT INTO dispatch_requests VALUES(?,'DEMO-ZEE','DEMO-ORDER-001',1,?,?,?,?, 'ACCEPTED_FOR_REVIEW')",
            (payload["dispatchId"], digest(payload), canonical(payload), receipt_id, cfg.now()),
        )
    db = Database(path, True)
    db.initialize()
    db.initialize()
    with db.transaction() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 2
        assert c.execute("SELECT COUNT(*) FROM target_orders").fetchone()[0] == 1
        effect = c.execute("SELECT * FROM dispatch_requests").fetchone()
        assert (
            effect["dispatch_id"] == payload["dispatchId"]
            and effect["receipt_id"] == receipt_id
            and effect["payload_hash"] == digest(payload)
        )
        c.execute("UPDATE schema_migrations SET checksum='bad' WHERE version=2")
    with pytest.raises(RuntimeError, match="migration"):
        db.initialize()


def test_E2_two_overlapping_worker_PROCESSES_fenced_single_target_effect(cfg, store):
    approve(store, ready(store))
    now = wall_ms()
    code = """
import json,sys,time
from pathlib import Path
from quayready.config import load_settings
from quayready.store import Store
from quayready.worker import Worker
cfg=load_settings(); role=sys.argv[1];clock=[int(sys.argv[2])];w=Worker(Store(cfg),lambda:clock[0])
if role=='b':
    w.tick();clock[0]+=10000
r=w.claim();assert r is not None
(cfg.run_dir/(role+'-ready')).write_text('ready')
deadline=time.monotonic()+10
while not (cfg.run_dir/'release').exists():
    assert time.monotonic()<deadline;time.sleep(.01)
result=w.request(r);applied=w.finish(r,*result)
(cfg.run_dir/(role+'-result')).write_text(json.dumps({'applied':applied,'generation':r['lease_generation']}))
"""
    env = {**os.environ, "QUAYREADY_CONFIG": str(cfg.run_dir / "config.json")}
    processes = []

    def wait_file(name):
        for _ in range(200):
            if (cfg.run_dir / name).exists():
                return
            assert all(p.poll() is None for p in processes)
            time.sleep(0.02)
        pytest.fail("Worker barrier timed out")

    with server(cfg), (cfg.run_dir / "overlap.log").open("w") as log:
        try:
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-c", code, "a", str(now)], env=env, stdout=log, stderr=log
                )
            )
            wait_file("a-ready")
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-c", code, "b", str(now + 30001)],
                    env=env,
                    stdout=log,
                    stderr=log,
                )
            )
            wait_file("b-ready")
            (cfg.run_dir / "release").write_text("go")
            for p in processes:
                assert p.wait(timeout=8) == 0
            a = json.loads((cfg.run_dir / "a-result").read_text())
            b = json.loads((cfg.run_dir / "b-result").read_text())
            assert not a["applied"] and b["applied"] and b["generation"] > a["generation"]
            assert row(store)["state"] == "CONFIRMED" and effects(cfg) == 1
        finally:
            for p in processes:
                if p.poll() is None:
                    p.kill()
                    p.wait(timeout=3)


def test_release_SQL_trace_proves_network_outside_transaction(cfg, store, monkeypatch):
    approve(store, ready(store))
    active = set()
    traces = []
    original = store.db.connect

    def connect():
        c = original()
        identifier = id(c)

        def trace(sql):
            traces.append(sql.split()[0])
            if sql.startswith("BEGIN"):
                active.add(identifier)
            if sql in ("COMMIT", "ROLLBACK"):
                active.discard(identifier)

        c.set_trace_callback(trace)
        return c

    monkeypatch.setattr(store.db, "connect", connect)
    worker = Worker(store)
    checks = []

    def network(_):
        checks.append(len(active))
        assert not active

    worker.before_http = network
    with server(cfg):
        worker.tick()
    assert checks == [0] and "BEGIN" in traces and "COMMIT" in traces and not active


def test_release_target_conflict_and_auth_contract(cfg, store):
    import httpx
    from test_contracts import response_contract

    approve(store, ready(store))
    worker = Worker(store)
    claim = worker.claim()
    payload = json.loads(claim["payload_json"])
    with server(cfg) as url, httpx.Client(base_url=url, trust_env=False) as client:
        headers = {"X-Worker-Key": cfg.worker_key}
        r = client.post("/mock/v1/dispatch-requests", json=payload, headers=headers)
        assert r.status_code == 201
        response_contract(r, "/mock/v1/dispatch-requests", "post")
        payload["evidenceVersion"] += 1
        r = client.post("/mock/v1/dispatch-requests", json=payload, headers=headers)
        assert r.status_code == 409
        response_contract(r, "/mock/v1/dispatch-requests", "post")
        assert client.post("/mock/v1/dispatch-requests", json=payload).status_code == 401
        assert (
            client.post(
                "/mock/v1/dispatch-requests",
                json=payload,
                headers={**headers, "Origin": cfg.origin},
            ).status_code
            == 403
        )
        payload["orderRevision"] = 2
        assert (
            client.post("/mock/v1/dispatch-requests", json=payload, headers=headers).status_code
            == 422
        )
        assert effects(cfg) == 1


def test_release_real_HTTP_chunked_body_limit(cfg):
    import http.client

    with server(cfg, "serve"):
        connection = http.client.HTTPConnection("127.0.0.1", cfg.app_port, timeout=3)
        connection.request(
            "POST",
            "/v1/orders",
            body=iter([b"x" * 8192 for _ in range(9)]),
            headers={"Content-Type": "application/json", "X-Source-Key": key_for(cfg, "ORDER")},
            encode_chunked=True,
        )
        response = connection.getresponse()
        assert response.status == 413
        assert json.loads(response.read())["code"] == "PAYLOAD_TOO_LARGE"
        connection.close()


@pytest.mark.parametrize("mode", ["wrong-mime", "wrong-hash", "wrong-id", "wrong-status"])
def test_release_success_shape_is_not_sufficient_to_confirm(cfg, store, mode):
    from quayready.common import iso, uid

    approve(store, ready(store))
    worker = Worker(store)
    claim = worker.claim()
    receipt = {
        "dispatchId": claim["dispatch_id"],
        "receiptId": uid(),
        "payloadHash": claim["payload_hash"],
        "status": "ACCEPTED_FOR_REVIEW",
        "acceptedAt": iso(cfg.now()),
    }
    if mode == "wrong-hash":
        receipt["payloadHash"] = "0" * 64
    if mode == "wrong-id":
        receipt["dispatchId"] = uid()
    with peer(cfg, mode, 202 if mode == "wrong-status" else 200, receipt):
        status, value, retry = worker.request(claim)
        worker.finish(claim, status, value, retry)
    assert row(store)["state"] == "MANUAL_REVIEW" and row(store)["target_receipt_id"] is None


def test_release_outbound_site_binding_never_crosses_mock_scope(cfg):
    from dataclasses import replace

    from quayready.store import Store

    other_cfg = replace(
        cfg, principals={k: replace(p, site="OTHER-SITE") for k, p in cfg.principals.items()}
    )
    other = Store(other_cfg)
    dispatch = approve(other, ready(other))
    worker = Worker(other)
    requests = []
    worker.before_http = lambda r: requests.append(r["site_id"])
    with server(cfg):
        worker.tick()
    assert row(other)["state"] == "MANUAL_REVIEW"
    assert row(other)["post_attempts"] == 0 and effects(cfg) == 0 and not requests
    with pytest.raises(Problem) as denied:
        worker.reconcile(other_cfg.principals[key_for(other_cfg, "REVIEWER")], dispatch)
    assert denied.value.status == 403
