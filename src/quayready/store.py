from __future__ import annotations

import json
import sqlite3

from .common import Json, Problem, canonical, digest, iso, uid
from .config import Principal, Settings
from .db import Database
from .domain import Assessment, assess


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = Database(settings.run_dir / "app.db")

    def shipment(self, c: sqlite3.Connection, site: str, sid: str) -> sqlite3.Row:
        row = c.execute("SELECT * FROM shipments WHERE site_id=? AND id=?", (site, sid)).fetchone()
        if row is None:
            raise Problem(404, "NOT_FOUND")
        return row

    def evidence(
        self, c: sqlite3.Connection, site: str, sid: str
    ) -> tuple[sqlite3.Row, Json, set[str], set[str], Assessment]:
        s = self.shipment(c, site, sid)
        snapshots = {
            r["kind"]: dict(r)
            for r in c.execute(
                "SELECT * FROM source_snapshots WHERE site_id=? AND shipment_id=?", (site, sid)
            )
        }
        expected = {
            r[0]
            for r in c.execute(
                "SELECT pallet_id FROM expected_pallets WHERE site_id=? AND shipment_id=?",
                (site, sid),
            )
        }
        w = snapshots.get("WAREHOUSE")
        scanned = (
            {
                r[0]
                for r in c.execute(
                    "SELECT pallet_id FROM warehouse_events WHERE receipt_id=?", (w["receipt_id"],)
                )
            }
            if w
            else set()
        )
        a = assess(
            expected,
            snapshots,
            scanned,
            self.settings.now(),
            s["cutoff_ms"],
            bool(s["order_conflicted"]),
        )
        return s, snapshots, expected, scanned, a

    def audit(
        self,
        c: sqlite3.Connection,
        site: str,
        sid: str,
        actor: str,
        kind: str,
        detail: Json | None = None,
    ) -> None:
        c.execute(
            "INSERT INTO audit_events(site_id,shipment_id,actor,kind,at_ms,correlation_id,detail_json) VALUES(?,?,?,?,?,?,?)",
            (site, sid, actor, kind, self.settings.now(), uid(), canonical(detail or {})),
        )

    def issue(
        self, c: sqlite3.Connection, site: str, sid: str, code: str, owner: str, pallets: list[str]
    ) -> None:
        old = c.execute(
            "SELECT sequence,detail_json FROM operational_issues WHERE site_id=? AND shipment_id=? AND reason_code=? AND resolved_at_ms IS NULL",
            (site, sid, code),
        ).fetchone()
        details = canonical({"palletIds": pallets})
        if old:
            if old["detail_json"] != details:
                c.execute(
                    "UPDATE operational_issues SET detail_json=? WHERE sequence=?",
                    (details, old["sequence"]),
                )
        else:
            c.execute(
                "INSERT INTO operational_issues(site_id,shipment_id,reason_code,owner,detail_json,first_seen_ms) VALUES(?,?,?,?,?,?)",
                (site, sid, code, owner, details, self.settings.now()),
            )
            self.audit(c, site, sid, "DEMO-SYSTEM", "issue_opened", {"reason": code})

    def reconcile(self, c: sqlite3.Connection, site: str, sid: str) -> Assessment:
        s, _, _, _, a = self.evidence(c, site, sid)
        for code, (owner, pallets) in a.reasons.items():
            self.issue(c, site, sid, code, owner, pallets)
        for row in c.execute(
            "SELECT sequence,reason_code FROM operational_issues WHERE site_id=? AND shipment_id=? AND resolved_at_ms IS NULL",
            (site, sid),
        ).fetchall():
            if row["reason_code"] not in a.reasons and row["reason_code"] != "POST_APPROVAL_CHANGE":
                c.execute(
                    "UPDATE operational_issues SET resolved_at_ms=? WHERE sequence=?",
                    (self.settings.now(), row["sequence"]),
                )
                self.audit(
                    c, site, sid, "DEMO-SYSTEM", "issue_resolved", {"reason": row["reason_code"]}
                )
        for p in c.execute(
            "SELECT * FROM approval_proposals WHERE site_id=? AND shipment_id=? AND status IN ('PENDING_REVIEW','APPROVED')",
            (site, sid),
        ).fetchall():
            delivery = c.execute("SELECT * FROM outbox WHERE proposal_id=?", (p["id"],)).fetchone()
            invalid = (
                p["evidence_version"] != s["aggregate_version"]
                or p["rules_version"] != "readiness-v1"
            )
            expired = self.settings.now() >= p["expires_at_ms"]
            if not (invalid or expired):
                continue
            if not delivery or delivery["state"] != "CONFIRMED":
                status = "INVALIDATED" if invalid else "EXPIRED"
                c.execute("UPDATE approval_proposals SET status=? WHERE id=?", (status, p["id"]))
                self.audit(
                    c,
                    site,
                    sid,
                    "DEMO-SYSTEM",
                    "proposal_" + status.lower(),
                    {"proposalId": p["id"]},
                )
            if delivery:
                if delivery["post_attempts"]:
                    self.issue(c, site, sid, "POST_APPROVAL_CHANGE", "Integration", [])
                    if delivery["state"] in ("QUEUED", "RETRY_WAIT"):
                        c.execute(
                            "UPDATE outbox SET next_action='LOOKUP' WHERE dispatch_id=?",
                            (delivery["dispatch_id"],),
                        )
                elif delivery["state"] in ("QUEUED", "RETRY_WAIT"):
                    c.execute(
                        "UPDATE outbox SET state='CANCELLED_BEFORE_SEND',lease_until_ms=NULL WHERE dispatch_id=?",
                        (delivery["dispatch_id"],),
                    )
        return a

    def poll(self) -> None:
        with self.db.transaction() as c:
            for row in c.execute("SELECT site_id,id FROM shipments").fetchall():
                self.reconcile(c, row["site_id"], row["id"])

    def receipt(self, row: sqlite3.Row, replay: bool = False) -> Json:
        return {
            "receiptId": row["id"],
            "shipmentId": row["shipment_id"],
            "eventId": row["event_id"],
            "result": row["result"],
            "receivedAt": iso(row["received_at_ms"]),
            "replayed": replay,
        }

    def conflict(
        self, c: sqlite3.Connection, p: Principal, sid: str, kind: str, revision: int
    ) -> None:
        s = self.shipment(c, p.site, sid)
        changed = False
        if kind == "ORDER":
            if not s["order_conflicted"]:
                c.execute("UPDATE shipments SET order_conflicted=1 WHERE id=?", (sid,))
                changed = True
        else:
            current = c.execute(
                "SELECT * FROM source_snapshots WHERE site_id=? AND shipment_id=? AND kind=?",
                (p.site, sid, kind),
            ).fetchone()
            if current:
                floor = max(
                    current["source_revision"], revision, current["conflict_revision_floor"] or 0
                )
                changed = current["conflict_revision_floor"] != floor
                c.execute(
                    "UPDATE source_snapshots SET conflict_revision_floor=? WHERE site_id=? AND shipment_id=? AND kind=?",
                    (floor, p.site, sid, kind),
                )
        if changed:
            c.execute(
                "UPDATE shipments SET aggregate_version=aggregate_version+1 WHERE id=?", (sid,)
            )
        self.audit(c, p.site, sid, p.subject, "source_conflict", {"kind": kind})
        self.reconcile(c, p.site, sid)

    def ingest(self, p: Principal, body: Json, kind: str) -> tuple[int, Json]:
        with self.db.transaction() as c:
            result = self._ingest(c, p, body, kind)
        # Conflict guards commit before returning 409. Never throw them inside the transaction.
        if isinstance(result, Problem):
            raise result
        return result

    def _ingest(
        self, c: sqlite3.Connection, p: Principal, body: Json, kind: str
    ) -> tuple[int, Json] | Problem:
        request_hash = digest(body)
        content_hash = digest({k: v for k, v in body.items() if k != "eventId"})
        old = c.execute(
            "SELECT * FROM inbound_receipts WHERE site_id=? AND source_id=? AND event_id=?",
            (p.site, p.subject, body["eventId"]),
        ).fetchone()
        if old:
            if old["request_hash"] == request_hash:
                return 200, self.receipt(old, True)
            rev = (
                body.get("sourceRevision", 1)
                if old["kind"] == kind
                and body.get("shipmentId", old["shipment_id"]) == old["shipment_id"]
                else old["source_revision"]
            )
            self.conflict(c, p, old["shipment_id"], old["kind"], rev)
            return Problem(409, "PAYLOAD_CONFLICT")
        result = "APPLIED"
        if kind == "ORDER":
            if c.execute(
                "SELECT id FROM shipments WHERE site_id=? AND order_source_id=? AND external_order_ref=?",
                (p.site, p.subject, body["externalOrderRef"]),
            ).fetchone():
                raise Problem(409, "ORDER_EXISTS")
            sid = uid()
            from .common import instant

            c.execute(
                "INSERT INTO shipments(id,site_id,order_source_id,external_order_ref,route,order_revision,cutoff_ms,aggregate_version,created_at_ms) VALUES(?,?,?,?,?,1,?,1,?)",
                (
                    sid,
                    p.site,
                    p.subject,
                    body["externalOrderRef"],
                    body["route"],
                    instant(body["cutoffAt"]),
                    self.settings.now(),
                ),
            )
            c.executemany(
                "INSERT INTO expected_pallets VALUES(?,?,?)",
                [(p.site, sid, x) for x in body["expectedPalletIds"]],
            )
            revision, observed = 1, None
        else:
            from .common import instant

            sid = body["shipmentId"]
            self.shipment(c, p.site, sid)
            observed = instant(body["observedAt"])
            if observed > self.settings.now():
                raise Problem(422, "INVALID_SCHEMA", "Source observation is in the future")
            revision = body["sourceRevision"]
            cur = c.execute(
                "SELECT * FROM source_snapshots WHERE site_id=? AND shipment_id=? AND kind=?",
                (p.site, sid, kind),
            ).fetchone()
            if cur:
                if cur["source_id"] != p.subject:
                    raise Problem(403, "FORBIDDEN", "Snapshot source identity is already bound")
                if revision < cur["source_revision"]:
                    result = "STALE_IGNORED"
                elif revision == cur["source_revision"]:
                    old_hash = c.execute(
                        "SELECT content_hash FROM inbound_receipts WHERE id=?", (cur["receipt_id"],)
                    ).fetchone()[0]
                    if old_hash == content_hash:
                        result = "REVISION_REPLAY"
                    else:
                        self.conflict(c, p, sid, kind, revision)
                        return Problem(409, "REVISION_CONFLICT")
                elif observed < cur["observed_at_ms"] or revision <= (
                    cur["conflict_revision_floor"] or 0
                ):
                    self.conflict(c, p, sid, kind, revision)
                    return Problem(
                        409,
                        "REVISION_TIME_CONFLICT"
                        if observed < cur["observed_at_ms"]
                        else "REVISION_CONFLICT",
                    )
        rid = uid()
        c.execute(
            "INSERT INTO inbound_receipts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                rid,
                p.site,
                sid,
                p.subject,
                body["eventId"],
                kind,
                request_hash,
                content_hash,
                canonical(body),
                revision,
                observed,
                self.settings.now(),
                result,
            ),
        )
        if kind != "ORDER" and result == "APPLIED":
            if observed is None:
                raise RuntimeError("Snapshot observation required")
            c.execute(
                "INSERT INTO source_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL) ON CONFLICT(site_id,shipment_id,kind) DO UPDATE SET receipt_id=excluded.receipt_id,source_revision=excluded.source_revision,observed_at_ms=excluded.observed_at_ms,valid_until_ms=excluded.valid_until_ms,watermark=excluded.watermark,status=excluded.status,hard_hold=excluded.hard_hold,conflict_revision_floor=NULL",
                (
                    p.site,
                    sid,
                    kind,
                    p.subject,
                    rid,
                    revision,
                    observed,
                    observed + 900000,
                    body["watermark"],
                    body["status"],
                    int(body.get("hardHold", body["status"] == "HOLD")),
                ),
            )
            if kind == "WAREHOUSE":
                c.executemany(
                    "INSERT INTO warehouse_events VALUES(?,?,?,?)",
                    [(p.site, sid, rid, x) for x in body["scannedPalletIds"]],
                )
            c.execute(
                "UPDATE shipments SET aggregate_version=aggregate_version+1 WHERE id=?", (sid,)
            )
        self.audit(
            c, p.site, sid, p.subject, "source_" + result.lower(), {"receiptId": rid, "kind": kind}
        )
        self.reconcile(c, p.site, sid)
        row = c.execute("SELECT * FROM inbound_receipts WHERE id=?", (rid,)).fetchone()
        return 201, self.receipt(row)

    def proposal_view(self, c: sqlite3.Connection, p: sqlite3.Row) -> Json:
        s = self.shipment(c, p["site_id"], p["shipment_id"])
        valid = (
            p["evidence_version"] == s["aggregate_version"]
            and self.settings.now() < p["expires_at_ms"]
            and p["rules_version"] == "readiness-v1"
        )
        status = p["status"]
        if status in ("PENDING_REVIEW", "APPROVED") and not valid:
            confirmed = c.execute(
                "SELECT 1 FROM outbox WHERE proposal_id=? AND state='CONFIRMED'", (p["id"],)
            ).fetchone()
            if not confirmed:
                status = (
                    "INVALIDATED" if p["evidence_version"] != s["aggregate_version"] else "EXPIRED"
                )
        return {
            "proposalId": p["id"],
            "shipmentId": p["shipment_id"],
            "requestedBy": p["requested_by"],
            "evidenceVersion": p["evidence_version"],
            "evidenceHash": p["evidence_hash"],
            "rulesVersion": p["rules_version"],
            "createdAt": iso(p["created_at_ms"]),
            "expiresAt": iso(p["expires_at_ms"]),
            "status": status,
            "currentlyValid": valid and status in ("PENDING_REVIEW", "APPROVED"),
        }

    def proposal(self, p: Principal, sid: str, key: str, body: Json) -> tuple[int, Json]:
        h = digest({"shipmentId": sid, **body})
        with self.db.transaction() as c:
            self.shipment(c, p.site, sid)
            self.reconcile(c, p.site, sid)
            old = c.execute(
                "SELECT * FROM approval_proposals WHERE site_id=? AND requested_by=? AND idempotency_key=?",
                (p.site, p.subject, key),
            ).fetchone()
            if old:
                if old["request_hash"] != h:
                    raise Problem(409, "IDEMPOTENCY_CONFLICT")
                return 200, self.proposal_view(c, old)
            s, sn, expected, scanned, a = self.evidence(c, p.site, sid)
            if body["expectedEvidenceVersion"] != s["aggregate_version"]:
                raise Problem(409, "STALE_PROPOSAL")
            if a.status != "ELIGIBLE_FOR_REVIEW":
                raise Problem(409, "NOT_ELIGIBLE")
            if c.execute(
                "SELECT 1 FROM outbox WHERE site_id=? AND shipment_id=? AND state!='CANCELLED_BEFORE_SEND'",
                (p.site, sid),
            ).fetchone():
                raise Problem(409, "DISPATCH_EXISTS")
            if c.execute(
                "SELECT 1 FROM approval_proposals WHERE site_id=? AND shipment_id=? AND status='PENDING_REVIEW'",
                (p.site, sid),
            ).fetchone():
                raise Problem(409, "ACTIVE_PROPOSAL")
            evidence = {
                "orderRef": s["external_order_ref"],
                "orderRevision": 1,
                "cutoff": s["cutoff_ms"],
                "expected": sorted(expected),
                "sources": sn,
                "rulesVersion": "readiness-v1",
                "scanned": sorted(scanned),
            }
            expires = min(
                self.settings.now() + 300000,
                s["cutoff_ms"],
                *(x["valid_until_ms"] for x in sn.values()),
            )
            pid = uid()
            c.execute(
                "INSERT INTO approval_proposals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    pid,
                    p.site,
                    sid,
                    p.subject,
                    key,
                    h,
                    s["aggregate_version"],
                    digest(evidence),
                    "readiness-v1",
                    canonical(evidence),
                    self.settings.now(),
                    expires,
                    "PENDING_REVIEW",
                ),
            )
            self.audit(c, p.site, sid, p.subject, "proposal_created", {"proposalId": pid})
            return 201, self.proposal_view(
                c, c.execute("SELECT * FROM approval_proposals WHERE id=?", (pid,)).fetchone()
            )

    def decision_view(self, row: sqlite3.Row) -> Json:
        return {
            "decisionId": row["id"],
            "proposalId": row["proposal_id"],
            "decision": row["action"],
            "reviewer": row["reviewer"],
            "decidedAt": iso(row["decided_at_ms"]),
            "dispatchId": row["dispatch_id"],
        }

    def decide(self, p: Principal, pid: str, key: str, body: Json) -> Json:
        h = digest({"proposalId": pid, **body})
        with self.db.transaction() as c:
            prop = c.execute(
                "SELECT * FROM approval_proposals WHERE site_id=? AND id=?", (p.site, pid)
            ).fetchone()
            if not prop:
                raise Problem(404, "NOT_FOUND")
            if prop["requested_by"] == p.subject:
                raise Problem(403, "SELF_APPROVAL")
            old = c.execute(
                "SELECT * FROM review_decisions WHERE site_id=? AND reviewer=? AND idempotency_key=?",
                (p.site, p.subject, key),
            ).fetchone()
            if old:
                if old["request_hash"] != h:
                    raise Problem(409, "IDEMPOTENCY_CONFLICT")
                return self.decision_view(old)
            if c.execute("SELECT 1 FROM review_decisions WHERE proposal_id=?", (pid,)).fetchone():
                raise Problem(409, "DECISION_EXISTS")
            sid = prop["shipment_id"]
            self.reconcile(c, p.site, sid)
            pv = self.proposal_view(c, prop)
            if pv["status"] == "EXPIRED":
                raise Problem(409, "PROPOSAL_EXPIRED")
            if (
                pv["status"] != "PENDING_REVIEW"
                or prop["evidence_version"] != body["expectedEvidenceVersion"]
            ):
                raise Problem(409, "STALE_PROPOSAL")
            s, _, _, _, a = self.evidence(c, p.site, sid)
            if body["decision"] == "APPROVE" and a.status != "ELIGIBLE_FOR_REVIEW":
                raise Problem(409, "NOT_ELIGIBLE")
            if c.execute(
                "SELECT 1 FROM outbox WHERE site_id=? AND shipment_id=? AND state!='CANCELLED_BEFORE_SEND'",
                (p.site, sid),
            ).fetchone():
                raise Problem(409, "DISPATCH_EXISTS")
            did, dispatch = uid(), uid() if body["decision"] == "APPROVE" else None
            c.execute(
                "INSERT INTO review_decisions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    did,
                    p.site,
                    sid,
                    pid,
                    p.subject,
                    key,
                    h,
                    body["decision"],
                    body["reason"],
                    self.settings.now(),
                    dispatch,
                ),
            )
            if dispatch:
                payload = {
                    "dispatchId": dispatch,
                    "shipmentRef": s["external_order_ref"],
                    "orderRevision": 1,
                    "evidenceVersion": prop["evidence_version"],
                    "evidenceHash": prop["evidence_hash"],
                    "rulesVersion": "readiness-v1",
                    "approvedProposalId": pid,
                    "requestType": "REQUEST_DISPATCH_REVIEW",
                }
                c.execute(
                    "INSERT INTO outbox(dispatch_id,site_id,shipment_id,proposal_id,payload_json,payload_hash,state,next_action,next_attempt_at_ms) VALUES(?,?,?,?,?,?,'QUEUED','POST',0)",
                    (dispatch, p.site, sid, pid, canonical(payload), digest(payload)),
                )
            c.execute(
                "UPDATE approval_proposals SET status=? WHERE id=?",
                ("APPROVED" if dispatch else "REJECTED", pid),
            )
            self.audit(
                c,
                p.site,
                sid,
                p.subject,
                "decision_recorded",
                {"decisionId": did, "dispatchId": dispatch, "decision": body["decision"]},
            )
            return self.decision_view(
                c.execute("SELECT * FROM review_decisions WHERE id=?", (did,)).fetchone()
            )

    def delivery_view(self, row: sqlite3.Row) -> Json:
        receipt = None
        if row["target_receipt_id"]:
            receipt = {
                "dispatchId": row["dispatch_id"],
                "receiptId": row["target_receipt_id"],
                "payloadHash": row["payload_hash"],
                "status": "ACCEPTED_FOR_REVIEW",
                "acceptedAt": iso(row["confirmed_at_ms"]),
            }
        return {
            "dispatchId": row["dispatch_id"],
            "shipmentId": row["shipment_id"],
            "status": row["state"],
            "postAttempts": row["post_attempts"],
            "lookupAttempts": row["lookup_attempts"],
            "nextAction": row["next_action"],
            "targetReceipt": receipt,
            "lastErrorCode": row["last_error_code"],
        }

    def delivery(self, p: Principal, did: str) -> Json:
        with self.db.transaction(False) as c:
            row = c.execute(
                "SELECT * FROM outbox WHERE site_id=? AND dispatch_id=?", (p.site, did)
            ).fetchone()
            if not row:
                raise Problem(404, "NOT_FOUND")
            return self.delivery_view(row)

    def issue_view(self, row: sqlite3.Row) -> Json:
        return {
            "sequence": row["sequence"],
            "shipmentId": row["shipment_id"],
            "reasonCode": row["reason_code"],
            "owner": row["owner"],
            "palletIds": json.loads(row["detail_json"])["palletIds"],
            "firstSeenAt": iso(row["first_seen_ms"]),
            "resolvedAt": iso(row["resolved_at_ms"]) if row["resolved_at_ms"] is not None else None,
        }

    def view(self, p: Principal, sid: str) -> Json:
        with self.db.transaction(False) as c:
            s, sn, expected, scanned, a = self.evidence(c, p.site, sid)
            prop = c.execute(
                "SELECT * FROM approval_proposals WHERE site_id=? AND shipment_id=? ORDER BY rowid DESC LIMIT 1",
                (p.site, sid),
            ).fetchone()
            out = c.execute(
                "SELECT * FROM outbox WHERE site_id=? AND shipment_id=? ORDER BY rowid DESC LIMIT 1",
                (p.site, sid),
            ).fetchone()
            return {
                "shipmentId": sid,
                "siteId": p.site,
                "externalOrderRef": s["external_order_ref"],
                "orderRevision": 1,
                "cutoffAt": iso(s["cutoff_ms"]),
                "expectedPalletIds": sorted(expected),
                "scannedPalletIds": sorted(scanned),
                "evidenceVersion": s["aggregate_version"],
                "readiness": a.status,
                "evaluatedAt": iso(self.settings.now()),
                "sources": [
                    {
                        "kind": kind,
                        "receiptId": r["receipt_id"],
                        "sourceRevision": r["source_revision"],
                        "observedAt": iso(r["observed_at_ms"]),
                        "expiresAt": iso(r["valid_until_ms"]),
                        "expired": self.settings.now() >= r["valid_until_ms"],
                        "status": r["status"],
                        "conflicted": r["conflict_revision_floor"] is not None,
                    }
                    for kind, r in sorted(sn.items())
                ],
                "issues": [
                    self.issue_view(r)
                    for r in c.execute(
                        "SELECT * FROM operational_issues WHERE site_id=? AND shipment_id=? ORDER BY sequence",
                        (p.site, sid),
                    )
                ],
                "latestProposal": self.proposal_view(c, prop) if prop else None,
                "delivery": self.delivery_view(out) if out else None,
            }

    def page(
        self,
        p: Principal,
        kind: str,
        after: int,
        limit: int,
        sid: str | None = None,
        status: str = "OPEN",
    ) -> Json:
        with self.db.transaction(False) as c:
            if kind == "audit":
                self.shipment(c, p.site, str(sid))
                rows = c.execute(
                    "SELECT * FROM audit_events WHERE site_id=? AND shipment_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                    (p.site, sid, after, limit + 1),
                ).fetchall()
                items = [
                    {
                        "sequence": r["sequence"],
                        "actor": r["actor"],
                        "kind": r["kind"],
                        "at": iso(r["at_ms"]),
                        "correlationId": r["correlation_id"],
                        "detail": r["detail_json"],
                    }
                    for r in rows[:limit]
                ]
            else:
                rows = c.execute(
                    "SELECT * FROM operational_issues WHERE site_id=? AND sequence>? AND (?='ALL' OR (?='OPEN' AND resolved_at_ms IS NULL) OR (?='RESOLVED' AND resolved_at_ms IS NOT NULL)) ORDER BY sequence LIMIT ?",
                    (p.site, after, status, status, status, limit + 1),
                ).fetchall()
                items = [self.issue_view(r) for r in rows[:limit]]
            return {
                "items": items,
                "nextAfter": rows[limit - 1]["sequence"] if len(rows) > limit else None,
            }
