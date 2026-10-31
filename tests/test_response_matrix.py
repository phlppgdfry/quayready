"""Exercise each declared HTTP status with a real trigger, never an invented response."""

import json
import sqlite3

import pytest
from conftest import approve, bodies, login, ready
from fastapi.testclient import TestClient
from test_contracts import response_contract
from test_recovery import row

from quayready.api import create_app
from quayready.cli import key_for
from quayready.common import SPEC, uid

pytestmark = pytest.mark.contract
HUMAN_POSTS = [
    "/v1/shipments/{id}/proposals",
    "/v1/proposals/{id}/decision",
    "/v1/deliveries/{dispatchId}/reconcile",
]
POSTS = ["/v1/session", "/v1/orders", "/v1/events", *HUMAN_POSTS]
ERRORS = [
    (p, int(s)) for p in POSTS for s in SPEC["paths"][p]["post"]["responses"] if int(s) >= 400
]


def database_failure():
    raise sqlite3.OperationalError("injected unavailable database")


@pytest.mark.parametrize("route,status", ERRORS)
def test_declared_application_POST_errors(client, cfg, store, monkeypatch, route, status):
    sid = ready(store)
    order, wh, _ = bodies(cfg, sid)
    op = cfg.principals[key_for(cfg, "OPERATOR")]
    _, proposal = store.proposal(op, sid, "DEMO-MATRIX-PROPOSAL", {"expectedEvidenceVersion": 4})
    path = route.replace("{id}", proposal["proposalId"] if "decision" in route else sid).replace(
        "{dispatchId}", uid()
    )
    payload = {
        "/v1/session": {"loginToken": key_for(cfg, "OPERATOR")},
        "/v1/orders": order,
        "/v1/events": wh,
        "/v1/shipments/{id}/proposals": {"expectedEvidenceVersion": 4},
        "/v1/proposals/{id}/decision": {
            "decision": "APPROVE",
            "expectedEvidenceVersion": 4,
            "reason": "Checked",
        },
        "/v1/deliveries/{dispatchId}/reconcile": {},
    }[route]
    headers = {"Content-Type": "application/json"}
    if route == "/v1/session":
        headers["Origin"] = cfg.origin
    elif route == "/v1/orders":
        headers["X-Source-Key"] = key_for(cfg, "ORDER")
    elif route == "/v1/events":
        headers["X-Source-Key"] = key_for(cfg, "WAREHOUSE")
    else:
        headers.update(
            login(
                client,
                cfg,
                "REVIEWER" if "decision" in route or "reconcile" in route else "OPERATOR",
            )
        )
    if status == 400:
        response = client.post(path, content=b"{broken", headers=headers)
    elif status == 401:
        client.cookies.clear()
        headers.pop("X-Source-Key", None)
        if route == "/v1/session":
            payload = {"loginToken": "x" * 32}
        response = client.post(path, json=payload, headers=headers)
    elif status == 403:
        response = client.post(
            path, json=payload, headers={**headers, "Origin": "https://evil.invalid"}
        )
    elif status == 404:
        if route == "/v1/events":
            payload["shipmentId"] = uid()
            payload["eventId"] = "DEMO-MISSING-EVENT"
        elif "decision" in route:
            path = path.replace(proposal["proposalId"], uid())
        elif "proposals" in route:
            path = path.replace(sid, uid())
        response = client.post(path, json=payload, headers=headers)
    elif status == 409:
        if route == "/v1/orders":
            payload["expectedPalletIds"] = ["DEMO-OTHER-PALLET"]
        elif route == "/v1/events":
            payload["hardHold"] = True
        elif "reconcile" in route:
            # Real queued dispatch: manual investigation is not permitted before terminal state.
            store.decide(
                cfg.principals[key_for(cfg, "REVIEWER")],
                proposal["proposalId"],
                "DEMO-MATRIX-DECISION",
                {"decision": "APPROVE", "expectedEvidenceVersion": 4, "reason": "Checked"},
            )
            path = route.replace("{dispatchId}", row(store)["dispatch_id"])
        else:
            payload["expectedEvidenceVersion"] = 3
        response = client.post(path, json=payload, headers=headers)
    elif status == 413:
        response = client.post(path, content=b"x" * 65537, headers=headers)
    elif status == 415:
        response = client.post(
            path, content=b"x", headers={**headers, "Content-Type": "text/plain"}
        )
    elif status == 422:
        if "reconcile" in route:
            payload = {"forceSend": True}
        else:
            payload = {}
        response = client.post(path, json=payload, headers=headers)
    elif status == 429:
        for _ in range(5):
            client.post(path, json={"loginToken": "x" * 32}, headers=headers)
        response = client.post(path, json={"loginToken": "x" * 32}, headers=headers)
    elif status == 503:
        monkeypatch.setattr(client.app.state.store.db, "connect", database_failure)
        response = client.post(path, json=payload, headers=headers)
    else:
        raise AssertionError(("No real trigger defined", route, status))
    assert response.status_code == status, (route, status, response.text)


GETS = [p for p, v in SPEC["paths"].items() if "get" in v and not p.startswith("/mock")]
GET_CASES = [(p, int(s)) for p in GETS for s in SPEC["paths"][p]["get"]["responses"]]


@pytest.mark.parametrize("route,status", GET_CASES)
def test_declared_application_GET_statuses(client, cfg, store, monkeypatch, route, status):
    sid = ready(store)
    dispatch = approve(store, sid)
    login(client, cfg, "REVIEWER")
    path = route.replace("{id}", sid).replace("{dispatchId}", dispatch)
    headers = {}
    if status == 401:
        client.cookies.clear()
    elif status == 403:
        headers["Host"] = "evil.invalid"
    elif status == 404:
        path = path.replace(sid, uid()).replace(dispatch, uid())
    elif status == 422:
        if route == "/v1/issues":
            path += "?limit=0"
        else:
            path = path.replace(sid, "invalid").replace(dispatch, "invalid")
    elif status == 503:
        monkeypatch.setattr(client.app.state.store.db, "connect", database_failure)
    r = client.get(path, headers=headers)
    assert r.status_code == status, (route, status, r.text)


TARGET_CASES = [
    (p, m, int(s))
    for p, v in SPEC["paths"].items()
    if p.startswith("/mock")
    for m, op in v.items()
    if m in ("get", "post")
    for s in op["responses"]
]


@pytest.mark.parametrize("route,method,status", TARGET_CASES)
def test_declared_mock_target_statuses(cfg, store, monkeypatch, route, method, status):
    approve(store, ready(store))
    payload = json.loads(row(store)["payload_json"])
    with TestClient(
        create_app(cfg, target=True), base_url=f"http://127.0.0.1:{cfg.target_port}"
    ) as client:
        headers = {"X-Worker-Key": cfg.worker_key, "Content-Type": "application/json"}
        path = route.replace("{id}", payload["dispatchId"])
        if method == "get" and status == 200 or method == "post" and status in (200, 409):
            assert (
                client.post("/mock/v1/dispatch-requests", json=payload, headers=headers).status_code
                == 201
            )
        if status == 401:
            headers.pop("X-Worker-Key")
        elif status == 403:
            headers["Origin"] = cfg.origin
        elif status == 404:
            if method == "get":
                path = route.replace("{id}", uid())
            else:
                payload["shipmentRef"] = "DEMO-UNKNOWN-ORDER"
        elif status == 409:
            payload["evidenceVersion"] += 1
        elif status == 422:
            if method == "get":
                path = route.replace("{id}", "invalid")
            else:
                payload["orderRevision"] = 2
        elif status == 503:
            monkeypatch.setattr(client.app.state.db, "connect", database_failure)
        if method == "get":
            r = client.get(path, headers=headers)
        elif status == 400:
            r = client.post(path, content=b"{broken", headers=headers)
        elif status == 413:
            r = client.post(path, content=b"x" * 65537, headers=headers)
        elif status == 415:
            r = client.post(path, content=b"x", headers={**headers, "Content-Type": "text/plain"})
        else:
            r = client.post(path, json=payload, headers=headers)
        assert r.status_code == status, (route, status, r.text)
        response_contract(r, route, method)


def test_declared_additional_success_and_session_delete(client, cfg, store):
    sid = ready(store)
    order, wh, _ = bodies(cfg, sid)
    r = client.post("/v1/events", json=wh, headers={"X-Source-Key": key_for(cfg, "WAREHOUSE")})
    assert r.status_code == 200
    order.update(eventId="DEMO-NEW-ORDER-002", externalOrderRef="DEMO-ORDER-002")
    assert (
        client.post(
            "/v1/orders", json=order, headers={"X-Source-Key": key_for(cfg, "ORDER")}
        ).status_code
        == 201
    )
    h = login(client, cfg)
    path = f"/v1/shipments/{sid}/proposals"
    body = {"expectedEvidenceVersion": 4}
    assert client.post(path, json=body, headers=h).status_code == 201
    assert client.post(path, json=body, headers=h).status_code == 200
    assert (
        client.delete("/v1/session", headers={**h, "Origin": "https://evil.invalid"}).status_code
        == 403
    )
    assert client.delete("/v1/session", headers=h).status_code == 204
    assert client.delete("/v1/session", headers=h).status_code == 401
