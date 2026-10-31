import secrets

import pytest
from conftest import approve, bodies, login, ready
from test_contracts import response_contract

from quayready.cli import key_for
from quayready.common import uid, validate
from quayready.config import Principal

pytestmark = pytest.mark.contract


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "limit=true",
        "after=-1",
        "after=1.5",
        "after=9223372036854775808",
        "status=oops",
    ],
)
def test_E2_pagination_validation(client, cfg, store, query):
    ready(store)
    login(client, cfg)
    r = client.get("/v1/issues?" + query)
    assert r.status_code == 422
    response_contract(r, "/v1/issues", "get")


def test_E2_pagination_no_duplicates_and_boundaries(client, cfg, store):
    sid = ready(store, False)
    login(client, cfg)
    all_items = client.get("/v1/issues?status=ALL&limit=100").json()["items"]
    actual = []
    after = 0
    while True:
        r = client.get(f"/v1/issues?status=ALL&limit=1&after={after}")
        response_contract(r, "/v1/issues", "get")
        actual.extend(r.json()["items"])
        after = r.json()["nextAfter"]
        if after is None:
            break
    assert actual == all_items and len({i["sequence"] for i in actual}) == len(actual)
    assert client.get("/v1/issues?after=9223372036854775807").json()["items"] == []
    r = client.get(f"/v1/shipments/{sid}/audit?limit=100")
    response_contract(r, "/v1/shipments/{id}/audit", "get")


def test_E2_expired_session_logout_and_cookie_flags(client, cfg, store):
    sid = ready(store)
    login(client, cfg)
    session_key = client.cookies.get("qr_session")
    principal, csrf, expires = client.app.state.sessions[session_key]
    client.app.state.sessions[session_key] = (principal, csrf, 0)
    assert client.get(f"/v1/shipments/{sid}").status_code == 401
    r = client.post(
        "/v1/session", json={"loginToken": key_for(cfg, "REVIEWER")}, headers={"Origin": cfg.origin}
    )
    assert "HttpOnly" in r.headers["set-cookie"] and "SameSite=strict" in r.headers["set-cookie"]
    assert session_key not in client.app.state.sessions
    assert (
        client.delete(
            "/v1/session", headers={"Origin": cfg.origin, "X-CSRF-Token": r.json()["csrfToken"]}
        ).status_code
        == 204
    )
    assert client.get(f"/v1/shipments/{sid}").status_code == 401


def test_E2_same_subject_different_key_and_session_cannot_self_approve(client, cfg, store):
    sid = ready(store)
    h = login(client, cfg)
    p = client.post(
        f"/v1/shipments/{sid}/proposals", json={"expectedEvidenceVersion": 4}, headers=h
    ).json()
    alias = secrets.token_urlsafe(32)
    cfg.principals[alias] = cfg.principals[key_for(cfg, "OPERATOR")]
    r = client.post("/v1/session", json={"loginToken": alias}, headers={"Origin": cfg.origin})
    headers = {**h, "X-CSRF-Token": r.json()["csrfToken"]}
    r = client.post(
        f"/v1/proposals/{p['proposalId']}/decision",
        json={
            "decision": "APPROVE",
            "expectedEvidenceVersion": 4,
            "reason": "Different login, same person",
        },
        headers=headers,
    )
    assert r.status_code == 403 and r.json()["code"] == "SELF_APPROVAL"


def test_E2_two_sites_every_object_boundary(client, cfg, store):
    sid = ready(store)
    dispatch = approve(store, sid)
    with store.db.transaction(False) as c:
        pid = c.execute("SELECT id FROM approval_proposals").fetchone()[0]
    key = secrets.token_urlsafe(32)
    source = secrets.token_urlsafe(32)
    cfg.principals[key] = Principal(
        "DEMO-OTHER-HUMAN", "OTHER-SITE", ("operator", "reviewer", "auditor")
    )
    cfg.principals[source] = Principal(
        "DEMO-OTHER-WMS", "OTHER-SITE", ("warehouse_source",), "WAREHOUSE"
    )
    r = client.post("/v1/session", json={"loginToken": key}, headers={"Origin": cfg.origin})
    h = {
        "Origin": cfg.origin,
        "X-CSRF-Token": r.json()["csrfToken"],
        "Idempotency-Key": "DEMO-CROSS-SITE",
    }
    for path in [
        f"/v1/shipments/{sid}",
        f"/v1/shipments/{sid}/audit",
        f"/v1/deliveries/{dispatch}",
    ]:
        assert client.get(path).status_code == 404
    assert client.get("/v1/issues?status=ALL").json()["items"] == []
    for path, body in [
        (f"/v1/shipments/{sid}/proposals", {"expectedEvidenceVersion": 4}),
        (
            f"/v1/proposals/{pid}/decision",
            {"decision": "APPROVE", "expectedEvidenceVersion": 4, "reason": "Cross-site"},
        ),
        (f"/v1/deliveries/{dispatch}/reconcile", {}),
    ]:
        assert client.post(path, json=body, headers=h).status_code == 404
    _, wh, _ = bodies(cfg, sid)
    assert client.post("/v1/events", json=wh, headers={"X-Source-Key": source}).status_code == 404
    with store.db.transaction(False) as c:
        assert (
            c.execute("SELECT aggregate_version FROM shipments WHERE id=?", (sid,)).fetchone()[0]
            == 4
        )
    # A legitimate independent order in the other site has separate ownership.
    orderkey = secrets.token_urlsafe(32)
    cfg.principals[orderkey] = Principal(
        "DEMO-OTHER-ORDER", "OTHER-SITE", ("order_source",), "ORDER"
    )
    order, _, _ = bodies(cfg)
    r = client.post("/v1/orders", json=order, headers={"X-Source-Key": orderkey})
    assert r.status_code == 201
    view = client.get("/v1/shipments/" + r.json()["shipmentId"])
    assert view.json()["siteId"] == "OTHER-SITE"
    validate("Shipment", view.json())


@pytest.mark.parametrize("path", ["/v2/orders", "/v0/events", "/v1/unknown"])
def test_E2_unsupported_routes_structured_404(client, path):
    r = client.get(path)
    assert r.status_code == 404
    validate("Error", r.json())


def test_E2_manual_reconcile_HTTP_contract_auth_and_no_counter_reset(client, cfg, store):
    dispatch = approve(store, ready(store))
    path = f"/v1/deliveries/{dispatch}/reconcile"
    assert client.post(path, json={}).status_code == 401
    h = login(client, cfg, "AUDITOR")
    assert client.post(path, json={}, headers=h).status_code == 403
    h = login(client, cfg, "REVIEWER")
    r = client.post(path, json={}, headers=h)
    assert r.status_code == 409
    response_contract(r, "/v1/deliveries/{dispatchId}/reconcile", "post")
    assert client.post(path, json={"forceSend": True}, headers=h).status_code == 422
    assert client.post(path, json={}, headers={**h, "X-CSRF-Token": "wrong"}).status_code == 403


def test_E2_host_origin_encoding_injection_and_redaction(client, cfg, store, caplog):
    ready(store)
    login(client, cfg)
    assert client.get("/", headers={"Host": "evil.invalid"}).status_code == 403
    order, _, _ = bodies(cfg)
    headers = {"X-Source-Key": key_for(cfg, "ORDER"), "Content-Encoding": "gzip"}
    assert client.post("/v1/orders", json=order, headers=headers).status_code == 415
    response = client.get("/v1/shipments/'%20OR%201=1--")
    assert response.status_code == 422 and "SELECT" not in response.text
    assert client.get(f"/v1/shipments/{uid()}").status_code == 404
    for key in cfg.principals:
        assert key not in caplog.text
    assert cfg.worker_key not in caplog.text


def test_E2_decision_replay_conflict_and_independent_reviewer_scope(client, cfg, store):
    sid = ready(store)
    dispatch = approve(store, sid)
    with store.db.transaction(False) as c:
        pid = c.execute("SELECT id FROM approval_proposals").fetchone()[0]
    h = login(client, cfg, "REVIEWER")
    h["Idempotency-Key"] = "DEMO-DEC-0001"
    body = {
        "decision": "APPROVE",
        "expectedEvidenceVersion": 4,
        "reason": "Tampered replay reason",
    }
    # Same key/different body must conflict; the approved dispatch remains immutable.
    r = client.post(f"/v1/proposals/{pid}/decision", json=body, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert client.get(f"/v1/deliveries/{dispatch}").json()["dispatchId"] == dispatch


def test_release_settings_repr_never_contains_credentials(cfg):
    assert cfg.worker_key not in repr(cfg)
    for key in cfg.principals:
        assert key not in repr(cfg)


def test_release_reject_decision_and_replay_contract(client, cfg, store):
    sid = ready(store)
    h = login(client, cfg)
    proposal = client.post(
        f"/v1/shipments/{sid}/proposals", json={"expectedEvidenceVersion": 4}, headers=h
    ).json()
    h = login(client, cfg, "REVIEWER")
    body = {
        "decision": "REJECT",
        "reason": "Independent reviewer needs clarification",
        "expectedEvidenceVersion": 4,
    }
    path = f"/v1/proposals/{proposal['proposalId']}/decision"
    first = client.post(path, json=body, headers=h)
    assert first.status_code == 200 and first.json()["dispatchId"] is None
    assert client.post(path, json=body, headers=h).json() == first.json()
    with store.db.transaction(False) as c:
        assert c.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"sourceRevision": 2147483648},
        {"sourceRevision": True},
        {"observedAt": "1969-01-01T00:00:00Z"},
        {"observedAt": "0001-01-01T00:00:00+23:59"},
        {"observedAt": "9999-12-31T23:59:59-23:59"},
        {"observedAt": "2026-02-30T11:40:00Z"},
        {"status": "UNKNOWN"},
    ],
)
def test_release_snapshot_numeric_and_UTC_boundaries(client, cfg, store, change):
    sid = ready(store)
    _, wh, _ = bodies(cfg, sid)
    wh.update(change)
    r = client.post("/v1/events", json=wh, headers={"X-Source-Key": key_for(cfg, "WAREHOUSE")})
    assert r.status_code == 422
    with store.db.transaction(False) as c:
        assert c.execute("SELECT aggregate_version FROM shipments").fetchone()[0] == 4


def test_release_schema_version_and_source_identity_binding(client, cfg, store):
    sid = ready(store)
    _, wh, _ = bodies(cfg, sid)
    wh["schemaVersion"] = 2
    assert (
        client.post(
            "/v1/events", json=wh, headers={"X-Source-Key": key_for(cfg, "WAREHOUSE")}
        ).status_code
        == 422
    )
    wh.update(schemaVersion=1, sourceRevision=3, eventId="DEMO-UNBOUND-SOURCE")
    key = secrets.token_urlsafe(32)
    cfg.principals[key] = Principal(
        "DEMO-UNBOUND-WMS", "DEMO-ZEE", ("warehouse_source",), "WAREHOUSE"
    )
    assert client.post("/v1/events", json=wh, headers={"X-Source-Key": key}).status_code == 403
    with store.db.transaction(False) as c:
        assert c.execute("SELECT aggregate_version FROM shipments").fetchone()[0] == 4


def test_release_manual_reconcile_success_response_contract(client, cfg, store):
    from processes import server

    from quayready.worker import Worker

    approve(store, ready(store))
    worker = Worker(store)
    with server(cfg):
        claim = worker.claim()
        worker.request(claim)
        worker.finish(claim, -1, None)
        h = login(client, cfg, "REVIEWER")
        r = client.post(f"/v1/deliveries/{claim['dispatch_id']}/reconcile", json={}, headers=h)
        assert r.status_code == 200 and r.json()["status"] == "CONFIRMED"


def test_release_unknown_warehouse_is_not_displayed_as_zero(client, cfg, store):
    sid = ready(store)
    _, wh, _ = bodies(cfg, sid)
    wh.update(eventId="DEMO-UNKNOWN-WMS", sourceRevision=3, status="UNKNOWN", scannedPalletIds=[])
    store.ingest(cfg.principals[key_for(cfg, "WAREHOUSE")], wh, "WAREHOUSE")
    login(client, cfg)
    html = client.get("/").text
    assert "Unknown evidence" in html and "Warehouse evidence unknown" in html
    assert "Observed pallets</span><strong>—" in html
    assert store.view(cfg.principals[key_for(cfg, "OPERATOR")], sid)["readiness"] == "NEEDS_REVIEW"
