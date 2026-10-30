from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from conftest import approve, bodies, login, ready

from quayready.cli import key_for
from quayready.common import Problem, iso, validate
from quayready.config import Principal
from quayready.domain import assess

pytestmark = pytest.mark.acceptance


def test_T01_T05_T20_core_contract(client, cfg):
    order, _, _ = bodies(cfg)
    r = client.post("/v1/orders", json=order, headers={"X-Source-Key": key_for(cfg, "ORDER")})
    assert r.status_code == 201, r.text
    validate("Receipt", r.json())
    sid = r.json()["shipmentId"]
    _, wh, doc = bodies(cfg, sid)
    for k, value in [("WAREHOUSE", wh), ("DOCUMENT", doc)]:
        r = client.post("/v1/events", json=value, headers={"X-Source-Key": key_for(cfg, k)})
        assert r.status_code == 201, r.text
    login(client, cfg)
    r = client.get(f"/v1/shipments/{sid}")
    validate("Shipment", r.json())
    assert r.json()["readiness"] == "NEEDS_REVIEW"
    assert r.json()["issues"][-1]["palletIds"] == ["DEMO-P003"]
    wh.update(
        eventId="DEMO-WMS-E002",
        sourceRevision=2,
        watermark="DEMO-WMS-W002",
        scannedPalletIds=order["expectedPalletIds"],
    )
    assert (
        client.post(
            "/v1/events", json=wh, headers={"X-Source-Key": key_for(cfg, "WAREHOUSE")}
        ).status_code
        == 201
    )
    view = client.get(f"/v1/shipments/{sid}").json()
    assert view["readiness"] == "ELIGIBLE_FOR_REVIEW"
    assert view["evidenceVersion"] == 4
    assert all(i["resolvedAt"] for i in view["issues"])


@pytest.mark.parametrize(
    "change",
    [
        {"orderRevision": True},
        {"orderRevision": 1.0},
        {"siteId": "OTHER-SITE"},
        {"expectedPalletIds": []},
        {"expectedPalletIds": ["DEMO-P001", "DEMO-P001"]},
        {"cutoffAt": "bad"},
    ],
)
def test_T02_strict_schema(client, cfg, change):
    order, _, _ = bodies(cfg)
    order.update(change)
    r = client.post("/v1/orders", json=order, headers={"X-Source-Key": key_for(cfg, "ORDER")})
    assert r.status_code == 422, r.text
    validate("Error", r.json())
    with client.app.state.store.db.transaction(False) as c:
        assert c.execute("SELECT COUNT(*) FROM shipments").fetchone()[0] == 0


@pytest.mark.parametrize("raw", [b'{"eventId":1,"eventId":2}', b'{"quantity":NaN}', b"not-json"])
def test_T02_invalid_json(client, cfg, raw):
    r = client.post(
        "/v1/orders",
        content=raw,
        headers={"X-Source-Key": key_for(cfg, "ORDER"), "Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_T02_body_and_future_limits(client, cfg, store):
    h = {"X-Source-Key": key_for(cfg, "ORDER"), "Content-Type": "application/json"}
    assert client.post("/v1/orders", content=b"x" * 65537, headers=h).status_code == 413
    assert (
        client.post(
            "/v1/orders", content=b"x", headers={"X-Source-Key": key_for(cfg, "ORDER")}
        ).status_code
        == 415
    )
    sid = ready(store, False)
    _, wh, _ = bodies(cfg, sid)
    wh["observedAt"] = iso(cfg.now() + 1)
    # New ID so receipt replay cannot hide invalid source time.
    wh["eventId"] = "DEMO-FUTURE-EVENT"
    assert (
        client.post(
            "/v1/events", json=wh, headers={"X-Source-Key": key_for(cfg, "WAREHOUSE")}
        ).status_code
        == 422
    )


def test_T03_T04_identical_concurrent_replay(store, cfg):
    sid = ready(store)
    order, _, _ = bodies(cfg)
    p = cfg.principals[key_for(cfg, "ORDER")]
    order["expectedPalletIds"].reverse()
    order["cutoffAt"] = "2026-11-02T13:00:00+01:00"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: store.ingest(p, order, "ORDER"), range(2)))
    assert results[0][0] == results[1][0] == 200
    assert results[0][1]["receiptId"] == results[1][1]["receiptId"]
    with store.db.transaction(False) as c:
        assert c.execute("SELECT COUNT(*) FROM shipments").fetchone()[0] == 1
        assert (
            c.execute("SELECT aggregate_version FROM shipments WHERE id=?", (sid,)).fetchone()[0]
            == 4
        )


def test_T04_stale_and_revision_replay(store, cfg):
    sid = ready(store)
    p = cfg.principals[key_for(cfg, "WAREHOUSE")]
    _, wh, _ = bodies(cfg, sid)
    wh.update(eventId="DEMO-OLDER-EVENT", hardHold=True)
    assert store.ingest(p, wh, "WAREHOUSE")[1]["result"] == "STALE_IGNORED"
    wh.update(
        eventId="DEMO-REV-REPLAY",
        sourceRevision=2,
        hardHold=False,
        watermark="DEMO-WMS-W002",
        scannedPalletIds=["DEMO-P001", "DEMO-P002", "DEMO-P003"],
    )
    assert store.ingest(p, wh, "WAREHOUSE")[1]["result"] == "REVISION_REPLAY"
    assert store.view(p, sid)["readiness"] == "ELIGIBLE_FOR_REVIEW"


def test_T06_conflict_and_recovery(store, cfg):
    sid = ready(store)
    p = cfg.principals[key_for(cfg, "WAREHOUSE")]
    _, wh, _ = bodies(cfg, sid)
    wh["hardHold"] = True
    with pytest.raises(Problem, match="Payload conflict"):
        store.ingest(p, wh, "WAREHOUSE")
    view = store.view(p, sid)
    assert view["readiness"] == "NEEDS_REVIEW"
    v = view["evidenceVersion"]
    with pytest.raises(Problem):
        store.ingest(p, wh, "WAREHOUSE")
    assert store.view(p, sid)["evidenceVersion"] == v
    wh.update(
        eventId="DEMO-CORRECT-003",
        sourceRevision=3,
        hardHold=False,
        watermark="DEMO-WMS-W003",
        scannedPalletIds=["DEMO-P001", "DEMO-P002", "DEMO-P003"],
    )
    store.ingest(p, wh, "WAREHOUSE")
    assert store.view(p, sid)["readiness"] == "ELIGIBLE_FOR_REVIEW"
    with store.db.transaction(False) as c:
        assert (
            c.execute("SELECT hard_hold FROM source_snapshots WHERE kind='WAREHOUSE'").fetchone()[0]
            == 0
        )


def test_T07_T09_time_and_hold_boundaries(store, cfg):
    sid = ready(store)
    p = cfg.principals[key_for(cfg, "OPERATOR")]
    now = cfg.now()
    cfg.domain_time = now + 899999
    assert store.view(p, sid)["readiness"] == "ELIGIBLE_FOR_REVIEW"
    cfg.domain_time = now + 900000
    assert store.view(p, sid)["readiness"] == "NEEDS_REVIEW"
    cfg.domain_time = now + 1200000
    assert store.view(p, sid)["readiness"] == "BLOCKED"
    result = assess(
        set(),
        {
            "WAREHOUSE": {
                "hard_hold": 1,
                "status": "UNKNOWN",
                "valid_until_ms": 0,
                "conflict_revision_floor": None,
            }
        },
        set(),
        1,
        10,
    )
    assert result.status == "BLOCKED" and "WAREHOUSE_EXPIRED" in result.reasons


def test_T07_oracle_vectors():
    rules = json.loads((Path(__file__).parent / "rule-cases.json").read_text())
    # Independently translate normalized facts to domain observations.
    for case in rules["cases"]:
        f = case["facts"]
        w = {
            "hard_hold": f["hard_hold"],
            "status": "UNKNOWN" if f["warehouse_unknown"] else "KNOWN",
            "valid_until_ms": 10 if f["warehouse_expired"] else 20,
            "conflict_revision_floor": 2 if f["source_conflict"] else None,
        }
        d = {
            "hard_hold": False,
            "status": "UNKNOWN"
            if f["document_unknown"]
            else "MISSING"
            if f["document_unavailable"]
            else "AVAILABLE",
            "valid_until_ms": 10 if f["document_expired"] else 20,
            "conflict_revision_floor": None,
        }
        sources = {}
        if not f["warehouse_missing"]:
            sources["WAREHOUSE"] = w
        if not f["document_missing"]:
            sources["DOCUMENT"] = d
        scanned = {"P1"}
        if f["unexpected_pallet"]:
            scanned.add("P9")
        expected = {"P1", "P2"} if f["missing_pallet"] else {"P1"}
        if f["warehouse_unknown"]:
            scanned = set()
        a = assess(expected, sources, scanned, 10, 10 if f["cutoff_reached"] else 20)
        assert a.status == case["expectedStatus"], case["id"]
        assert list(a.reasons) == case["expectedReasons"], case["id"]


def test_T08_T22_self_and_stale_review(client, store, cfg):
    sid = ready(store)
    h = login(client, cfg)
    r = client.post(
        f"/v1/shipments/{sid}/proposals", json={"expectedEvidenceVersion": 4}, headers=h
    )
    assert r.status_code == 201, r.text
    pid = r.json()["proposalId"]
    value = {"decision": "APPROVE", "expectedEvidenceVersion": 4, "reason": "Checked"}
    assert (
        client.post(f"/v1/proposals/{pid}/decision", json=value, headers=h).json()["code"]
        == "SELF_APPROVAL"
    )
    _, _, doc = bodies(cfg, sid)
    doc.update(eventId="DEMO-DOC-E002", sourceRevision=2, watermark="DEMO-DOC-W002")
    store.ingest(cfg.principals[key_for(cfg, "DOCUMENT")], doc, "DOCUMENT")
    h = login(client, cfg, "REVIEWER")
    r = client.post(f"/v1/proposals/{pid}/decision", json=value, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "STALE_PROPOSAL"
    with store.db.transaction(False) as c:
        assert c.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0


def test_T09_expired_proposal(store, cfg):
    sid = ready(store)
    op = cfg.principals[key_for(cfg, "OPERATOR")]
    _, p = store.proposal(op, sid, "DEMO-PROP-0001", {"expectedEvidenceVersion": 4})
    cfg.domain_time = cfg.now() + 300000
    with pytest.raises(Problem, match="Proposal expired"):
        store.decide(
            cfg.principals[key_for(cfg, "REVIEWER")],
            p["proposalId"],
            "DEMO-DEC-0001",
            {"decision": "APPROVE", "expectedEvidenceVersion": 4, "reason": "Checked"},
        )


def test_T11_T21_atomic_and_immutable(store, cfg):
    sid = ready(store)
    did = approve(store, sid)
    with store.db.transaction(False) as c:
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM review_decisions").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        with store.db.transaction() as c:
            c.execute("UPDATE outbox SET payload_json='[]'")
    with pytest.raises(sqlite3.IntegrityError):
        with store.db.transaction() as c:
            c.execute("DELETE FROM audit_events")
    with pytest.raises(sqlite3.IntegrityError):
        with store.db.transaction() as c:
            c.execute("INSERT INTO expected_pallets VALUES('OTHER-SITE',?,'DEMO-PPPP')", (sid,))
    assert store.delivery(cfg.principals[key_for(cfg, "OPERATOR")], did)["status"] == "QUEUED"


def test_T11_concurrent_approval(store, cfg):
    sid = ready(store)
    op = cfg.principals[key_for(cfg, "OPERATOR")]
    rev = cfg.principals[key_for(cfg, "REVIEWER")]
    _, p = store.proposal(op, sid, "DEMO-PROP-0001", {"expectedEvidenceVersion": 4})
    body = {"decision": "APPROVE", "expectedEvidenceVersion": 4, "reason": "Checked"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: store.decide(rev, p["proposalId"], "DEMO-DEC-0001", body), range(2))
        )
    assert results[0] == results[1]
    with store.db.transaction(False) as c:
        assert c.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 1


def test_T23_idempotency_scopes(store, cfg):
    sid = ready(store)
    p = cfg.principals[key_for(cfg, "OPERATOR")]
    first = store.proposal(p, sid, "DEMO-PROP-0001", {"expectedEvidenceVersion": 4})
    again = store.proposal(p, sid, "DEMO-PROP-0001", {"expectedEvidenceVersion": 4})
    assert first[0] == 201 and again[0] == 200 and first[1] == again[1]
    with pytest.raises(Problem, match="Idempotency conflict"):
        store.proposal(p, sid, "DEMO-PROP-0001", {"expectedEvidenceVersion": 5})


def test_T24_source_and_site_isolation(client, store, cfg):
    sid = ready(store)
    order, wh, _ = bodies(cfg, sid)
    assert (
        client.post(
            "/v1/orders", json=order, headers={"X-Source-Key": key_for(cfg, "OPERATOR")}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/events", json=wh, headers={"X-Source-Key": key_for(cfg, "DOCUMENT")}
        ).status_code
        == 403
    )
    other = Principal("DEMO-OTHER", "OTHER-SITE", ("operator",))
    with pytest.raises(Problem) as e:
        store.view(other, sid)
    assert e.value.status == 404


def test_T25_session_csrf_and_login_throttle(client, store, cfg):
    sid = ready(store)
    h = login(client, cfg)
    assert "HttpOnly" in client.cookies.jar.__str__() or len(client.cookies) == 1
    assert (
        client.post(
            f"/v1/shipments/{sid}/proposals",
            json={"expectedEvidenceVersion": 4},
            headers={"Origin": cfg.origin, "Idempotency-Key": "DEMO-KEY-0001"},
        ).json()["code"]
        == "CSRF_FAILED"
    )
    assert (
        client.post(
            f"/v1/shipments/{sid}/proposals",
            json={"expectedEvidenceVersion": 4},
            headers={**h, "Origin": "https://evil.invalid"},
        ).status_code
        == 403
    )
    for _ in range(4):
        assert (
            client.post(
                "/v1/session", json={"loginToken": "x" * 32}, headers={"Origin": cfg.origin}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/v1/session", json={"loginToken": "x" * 32}, headers={"Origin": cfg.origin}
        ).status_code
        == 429
    )


def test_T26_T28_workbench_escaping(client, store, cfg):
    sid = ready(store)
    login(client, cfg)
    response = client.get("/")
    assert response.status_code == 200
    assert "Evidence before action" in response.text and "DEMO-P003" in response.text
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert key_for(cfg, "OPERATOR") not in response.text
    # Untrusted audit details are rendered via escaped text, never HTML.
    with store.db.transaction() as c:
        store.audit(c, "DEMO-ZEE", sid, "<script>alert(1)</script>", "test")
    response = client.get("/")
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text


def test_T29_migration_reopen_and_refuse_drift(cfg, store):
    store.db.initialize()
    with store.db.transaction() as c:
        c.execute("UPDATE schema_migrations SET checksum='changed'")
    with pytest.raises(RuntimeError, match="Unknown or changed"):
        store.db.initialize()
