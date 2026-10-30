import sqlite3

import pytest
from conftest import bodies, login, ready
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate as validate_openapi

from quayready.cli import key_for
from quayready.common import SPEC, uid

pytestmark = pytest.mark.contract


def response_contract(response, path, method):
    operation = SPEC["paths"][path][method]
    assert str(response.status_code) in operation["responses"], (
        path,
        response.status_code,
        response.text,
    )
    descriptor = operation["responses"][str(response.status_code)]
    if "$ref" in descriptor:
        descriptor = SPEC["components"]["responses"][descriptor["$ref"].split("/")[-1]]
    schema = descriptor.get("content", {}).get("application/json", {}).get("schema")
    if schema:
        Draft202012Validator(
            {**schema, "components": SPEC["components"]}, format_checker=FormatChecker()
        ).validate(response.json())


def test_T20_openapi_standard_and_complete_workflow(client, store, cfg):
    validate_openapi(SPEC)
    order, _, _ = bodies(cfg)
    headers = {"X-Source-Key": key_for(cfg, "ORDER")}
    response = client.post("/v1/orders", json=order, headers=headers)
    response_contract(response, "/v1/orders", "post")
    response_contract(client.post("/v1/orders", json=order, headers=headers), "/v1/orders", "post")
    sid = response.json()["shipmentId"]
    _, wh, doc = bodies(cfg, sid)
    wh["scannedPalletIds"] = order["expectedPalletIds"]
    for value, kind in [(wh, "WAREHOUSE"), (doc, "DOCUMENT")]:
        response_contract(
            client.post("/v1/events", json=value, headers={"X-Source-Key": key_for(cfg, kind)}),
            "/v1/events",
            "post",
        )
    h = login(client, cfg)
    response_contract(client.get(f"/v1/shipments/{sid}"), "/v1/shipments/{id}", "get")
    response = client.post(
        f"/v1/shipments/{sid}/proposals", json={"expectedEvidenceVersion": 3}, headers=h
    )
    response_contract(response, "/v1/shipments/{id}/proposals", "post")
    pid = response.json()["proposalId"]
    h = login(client, cfg, "REVIEWER")
    response = client.post(
        f"/v1/proposals/{pid}/decision",
        json={"decision": "APPROVE", "expectedEvidenceVersion": 3, "reason": "Checked"},
        headers=h,
    )
    response_contract(response, "/v1/proposals/{id}/decision", "post")
    dispatch = response.json()["dispatchId"]
    response_contract(
        client.get(f"/v1/deliveries/{dispatch}"), "/v1/deliveries/{dispatchId}", "get"
    )
    response_contract(client.get("/v1/issues?limit=1&status=ALL"), "/v1/issues", "get")
    response_contract(
        client.get(f"/v1/shipments/{sid}/audit?limit=1"), "/v1/shipments/{id}/audit", "get"
    )
    response_contract(client.get(f"/v1/shipments/{uid()}"), "/v1/shipments/{id}", "get")
    response_contract(client.post("/v1/orders", json=order), "/v1/orders", "post")
    order["orderRevision"] = 2
    response_contract(client.post("/v1/orders", json=order, headers=headers), "/v1/orders", "post")
    response_contract(client.delete("/v1/session", headers=h), "/v1/session", "delete")


def test_T11_approve_only_commit_is_rejected(store, cfg):
    sid = ready(store)
    op = cfg.principals[key_for(cfg, "OPERATOR")]
    _, p = store.proposal(op, sid, "DEMO-PROP-001", {"expectedEvidenceVersion": 4})
    with pytest.raises(sqlite3.IntegrityError):
        with store.db.transaction() as c:
            c.execute(
                "INSERT INTO review_decisions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uid(),
                    "DEMO-ZEE",
                    sid,
                    p["proposalId"],
                    "DEMO-REVIEWER",
                    "DEMO-DEC-001",
                    "0" * 64,
                    "APPROVE",
                    "Checked",
                    cfg.now(),
                    uid(),
                ),
            )


def test_T21_current_snapshot_missing_query(store, cfg):
    sid = ready(store, False)
    with store.db.transaction(False) as c:
        missing = c.execute(
            """SELECT e.pallet_id FROM expected_pallets e
            JOIN source_snapshots s ON s.site_id=e.site_id AND s.shipment_id=e.shipment_id AND s.kind='WAREHOUSE'
            LEFT JOIN warehouse_events w ON w.receipt_id=s.receipt_id AND w.pallet_id=e.pallet_id
            WHERE e.shipment_id=? AND w.pallet_id IS NULL""",
            (sid,),
        ).fetchall()
        assert [r[0] for r in missing] == ["DEMO-P003"]


def test_T11_approval_transaction_failure_rolls_back_all(store, cfg, monkeypatch):
    sid = ready(store)
    op = cfg.principals[key_for(cfg, "OPERATOR")]
    reviewer = cfg.principals[key_for(cfg, "REVIEWER")]
    _, proposal = store.proposal(op, sid, "DEMO-PROP-ROLLBACK", {"expectedEvidenceVersion": 4})

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("injected failure after decision and outbox inserts")

    monkeypatch.setattr(store, "audit", fail)
    with pytest.raises(sqlite3.OperationalError):
        store.decide(
            reviewer,
            proposal["proposalId"],
            "DEMO-DEC-ROLLBACK",
            {"decision": "APPROVE", "expectedEvidenceVersion": 4, "reason": "Checked"},
        )
    with store.db.transaction(False) as c:
        assert c.execute("SELECT COUNT(*) FROM review_decisions").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0
        assert c.execute("SELECT status FROM approval_proposals").fetchone()[0] == "PENDING_REVIEW"
