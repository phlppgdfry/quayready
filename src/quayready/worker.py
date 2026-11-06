from __future__ import annotations

import http.client
import socket
import threading
import time
from collections.abc import Callable
from typing import Any

from .common import Json, Problem, instant, parse_json, validate, wall_ms
from .config import TARGET_SITE
from .store import Store


class Worker:
    def __init__(self, store: Store, clock: Callable[[], int] = wall_ms):
        self.store, self.clock = store, clock
        self.before_http: Callable[[Json], None] | None = None
        self.after_http: Callable[[Json], None] | None = None

    def valid(self, c: Any, row: Any) -> bool:
        p = c.execute(
            "SELECT * FROM approval_proposals WHERE id=?", (row["proposal_id"],)
        ).fetchone()
        s, _, _, _, a = self.store.evidence(c, row["site_id"], row["shipment_id"])
        return (
            p["status"] == "APPROVED"
            and p["evidence_version"] == s["aggregate_version"]
            and p["rules_version"] == "readiness-v1"
            and self.store.settings.now() < p["expires_at_ms"]
            and a.status == "ELIGIBLE_FOR_REVIEW"
        )

    def claim(self) -> Json | None:
        now = self.clock()
        with self.store.db.transaction() as c:
            latest = c.execute("SELECT COALESCE(MAX(last_worker_at_ms),0) FROM outbox").fetchone()[
                0
            ]
            if now < latest:
                raise RuntimeError("Worker clock moved backwards; no delivery attempted")
            for s in c.execute("SELECT site_id,id FROM shipments").fetchall():
                self.store.reconcile(c, s["site_id"], s["id"])
            expired = c.execute(
                "SELECT * FROM outbox WHERE state='SENDING' AND lease_until_ms<=?", (now,)
            ).fetchall()
            for r in expired:
                c.execute(
                    "UPDATE outbox SET state='RETRY_WAIT',next_action='LOOKUP',lease_generation=lease_generation+1,lease_until_ms=NULL,next_attempt_at_ms=?,last_worker_at_ms=? WHERE dispatch_id=? AND state='SENDING' AND lease_generation=?",
                    (now, now, r["dispatch_id"], r["lease_generation"]),
                )
                self.store.audit(
                    c, r["site_id"], r["shipment_id"], "DEMO-WORKER", "lease_recovered"
                )
            row = c.execute(
                "SELECT * FROM outbox WHERE state IN ('QUEUED','RETRY_WAIT') AND next_attempt_at_ms<=? ORDER BY rowid LIMIT 1",
                (now,),
            ).fetchone()
            if row is None:
                return None
            if row["site_id"] != TARGET_SITE:
                c.execute(
                    "UPDATE outbox SET state='MANUAL_REVIEW',last_error_code='TARGET_CONTRACT_ERROR' WHERE dispatch_id=?",
                    (row["dispatch_id"],),
                )
                self.store.audit(
                    c,
                    row["site_id"],
                    row["shipment_id"],
                    "DEMO-WORKER",
                    "target_scope_rejected",
                    {"dispatchId": row["dispatch_id"]},
                )
                return None
            good = self.valid(c, row)
            if not good and row["post_attempts"] == 0:
                c.execute(
                    "UPDATE outbox SET state='CANCELLED_BEFORE_SEND' WHERE dispatch_id=?",
                    (row["dispatch_id"],),
                )
                return None
            action = row["next_action"] if good else "LOOKUP"
            counter = "post_attempts" if action == "POST" else "lookup_attempts"
            if row[counter] >= 3:
                c.execute(
                    "UPDATE outbox SET state='MANUAL_REVIEW',last_error_code='RETRY_EXHAUSTED',last_worker_at_ms=? WHERE dispatch_id=?",
                    (now, row["dispatch_id"]),
                )
                self.store.audit(
                    c, row["site_id"], row["shipment_id"], "DEMO-WORKER", "retry_exhausted"
                )
                return None
            c.execute(
                "UPDATE outbox SET state='SENDING',next_action=?,post_attempts=post_attempts+CASE WHEN ?='POST' THEN 1 ELSE 0 END,lookup_attempts=lookup_attempts+CASE WHEN ?='LOOKUP' THEN 1 ELSE 0 END,lease_generation=lease_generation+1,lease_until_ms=?,last_worker_at_ms=? WHERE dispatch_id=?",
                (action, action, action, now + 30000, now, row["dispatch_id"]),
            )
            self.store.audit(
                c,
                row["site_id"],
                row["shipment_id"],
                "DEMO-WORKER",
                "delivery_reserved",
                {"action": action},
            )
            return dict(
                c.execute(
                    "SELECT * FROM outbox WHERE dispatch_id=?", (row["dispatch_id"],)
                ).fetchone()
            )

    def request(self, row: Json) -> tuple[int, Json | None, int]:
        if self.store.db.transaction_active:
            raise RuntimeError("HTTP inside database transaction is forbidden")
        if row["site_id"] != TARGET_SITE:
            return -1, None, 0
        if self.before_http:
            self.before_http(row)
        conn = http.client.HTTPConnection("127.0.0.1", self.store.settings.target_port, timeout=1)
        deadline = time.monotonic() + 3
        timer: threading.Timer | None = None
        try:
            conn.connect()
            transport = conn.sock
            if transport is None:
                raise OSError("Target connection unavailable")

            def interrupt() -> None:
                # A socket inactivity timeout is insufficient against trickled headers/body.
                # Shutdown also interrupts a read after HTTPConnection detaches its socket.
                try:
                    transport.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            timer = threading.Timer(max(0, deadline - time.monotonic()), interrupt)
            timer.daemon = True
            timer.start()
            path = "/mock/v1/dispatch-requests"
            if row["next_action"] == "LOOKUP":
                path += "/" + row["dispatch_id"]
            body = row["payload_json"] if row["next_action"] == "POST" else None
            conn.request(
                "POST" if body else "GET",
                path,
                body=body,
                headers={
                    "X-Worker-Key": self.store.settings.worker_key,
                    "Content-Type": "application/json",
                },
            )
            transport.settimeout(max(0.01, deadline - time.monotonic()))
            response = conn.getresponse()
            chunks: list[bytes] = []
            size = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                transport.settimeout(remaining)
                chunk = response.read1(min(8192, 65537 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > 65536:
                    return -1, None, 0
                if response.isclosed():
                    break
            if response.length not in (None, 0):
                raise http.client.IncompleteRead(b"", response.length)
            retry = response.getheader("Retry-After", "")
            retry_ms = (
                int(retry) * 1000
                if retry.isascii() and retry.isdigit() and len(retry) <= 10 and int(retry) <= 60
                else 0
            )
            accepted = (200, 201) if row["next_action"] == "POST" else (200,)
            if 200 <= response.status < 300 and response.status not in accepted:
                return -1, None, 0
            if response.status in accepted:
                if time.monotonic() >= deadline:
                    return 0, None, 0
                if (
                    response.getheader("Content-Type", "").split(";")[0].strip().lower()
                    != "application/json"
                ):
                    return -1, None, 0
                try:
                    value = parse_json(b"".join(chunks))
                    validate("TargetReceipt", value)
                    if (
                        value["dispatchId"] != row["dispatch_id"]
                        or value["payloadHash"] != row["payload_hash"]
                    ):
                        return -1, None, 0
                except Problem:
                    return -1, None, 0
                return response.status, value, retry_ms
            return response.status, None, retry_ms
        except (OSError, http.client.HTTPException):
            return 0, None, 0
        finally:
            if timer:
                timer.cancel()
            conn.close()

    def reconcile(self, principal: Any, dispatch_id: str) -> Json:
        """Explicit reviewer GET-only investigation; automatic attempt budgets never reset."""
        if "reviewer" not in principal.roles:
            raise Problem(403, "FORBIDDEN")
        with self.store.db.transaction() as c:
            current = c.execute(
                "SELECT * FROM outbox WHERE site_id=? AND dispatch_id=?",
                (principal.site, dispatch_id),
            ).fetchone()
            if not current:
                raise Problem(404, "NOT_FOUND")
            if current["site_id"] != TARGET_SITE:
                raise Problem(403, "FORBIDDEN", "No target is configured for this site")
            if current["state"] != "MANUAL_REVIEW":
                raise Problem(
                    409, "TARGET_UNCERTAIN", "Only manual-review deliveries can be reconciled"
                )
            c.execute(
                "UPDATE outbox SET lease_generation=lease_generation+1,next_action='LOOKUP' WHERE dispatch_id=?",
                (dispatch_id,),
            )
            row = dict(
                c.execute("SELECT * FROM outbox WHERE dispatch_id=?", (dispatch_id,)).fetchone()
            )
            self.store.audit(
                c,
                principal.site,
                row["shipment_id"],
                principal.subject,
                "manual_lookup_requested",
                {"dispatchId": dispatch_id},
            )
        row["next_action"] = "LOOKUP"
        status, receipt, _ = self.request(row)
        with self.store.db.transaction() as c:
            current = c.execute(
                "SELECT * FROM outbox WHERE dispatch_id=? AND state='MANUAL_REVIEW' AND lease_generation=?",
                (dispatch_id, row["lease_generation"]),
            ).fetchone()
            if not current:
                raise Problem(409, "TARGET_UNCERTAIN", "A newer reconciliation owns the result")
            self.store.reconcile(c, principal.site, row["shipment_id"])
            if receipt:
                if not self.valid(c, current):
                    self.store.issue(
                        c,
                        principal.site,
                        row["shipment_id"],
                        "POST_APPROVAL_CHANGE",
                        "Integration",
                        [],
                    )
                c.execute(
                    "UPDATE outbox SET state='CONFIRMED',target_receipt_id=?,confirmed_at_ms=?,last_error_code=NULL WHERE dispatch_id=?",
                    (receipt["receiptId"], instant(receipt["acceptedAt"]), dispatch_id),
                )
            self.store.audit(
                c,
                principal.site,
                row["shipment_id"],
                principal.subject,
                "manual_lookup_confirmed" if receipt else "manual_lookup_unresolved",
                {"dispatchId": dispatch_id, "httpStatus": status},
            )
            return self.store.delivery_view(
                c.execute("SELECT * FROM outbox WHERE dispatch_id=?", (dispatch_id,)).fetchone()
            )

    def finish(self, row: Json, status: int, receipt: Json | None, retry_after: int = 0) -> bool:
        now = self.clock()
        with self.store.db.transaction() as c:
            current = c.execute(
                "SELECT * FROM outbox WHERE dispatch_id=? AND state='SENDING' AND lease_generation=? AND lease_until_ms>?",
                (row["dispatch_id"], row["lease_generation"], now),
            ).fetchone()
            if not current:
                return False
            self.store.reconcile(c, row["site_id"], row["shipment_id"])
            good = self.valid(c, current)
            error: str | None = "TARGET_CONTRACT_ERROR"
            state, next_action = "MANUAL_REVIEW", "LOOKUP"
            if receipt is not None:
                state, error = "CONFIRMED", None
                if not good:
                    self.store.issue(
                        c,
                        row["site_id"],
                        row["shipment_id"],
                        "POST_APPROVAL_CHANGE",
                        "Integration",
                        [],
                    )
            elif status == 404 and row["next_action"] == "LOOKUP":
                if good and current["post_attempts"] < 3:
                    state, next_action, error = "RETRY_WAIT", "POST", "TARGET_UNCERTAIN"
                else:
                    error = "TARGET_UNCERTAIN"
            elif status == 0 or status == 429 or status >= 500:
                if current["lookup_attempts"] < 3:
                    state, error = "RETRY_WAIT", "TARGET_UNCERTAIN"
                else:
                    error = "RETRY_EXHAUSTED"
            attempts = current["post_attempts"] + current["lookup_attempts"]
            delay = max(2000 if attempts == 1 else 8000, retry_after)
            c.execute(
                "UPDATE outbox SET state=?,next_action=?,lease_until_ms=NULL,next_attempt_at_ms=?,last_worker_at_ms=?,target_receipt_id=?,confirmed_at_ms=?,last_error_code=? WHERE dispatch_id=? AND lease_generation=? AND state='SENDING'",
                (
                    state,
                    next_action,
                    now + delay,
                    now,
                    receipt["receiptId"] if receipt else None,
                    instant(receipt["acceptedAt"]) if receipt else None,
                    error,
                    row["dispatch_id"],
                    row["lease_generation"],
                ),
            )
            self.store.audit(
                c,
                row["site_id"],
                row["shipment_id"],
                "DEMO-WORKER",
                "delivery_" + state.lower(),
                {
                    "dispatchId": row["dispatch_id"],
                    "action": row["next_action"],
                    "httpStatus": status,
                },
            )
            return True

    def tick(self) -> Json | None:
        row = self.claim()
        if row:
            status, receipt, retry = self.request(row)
            if self.after_http:
                self.after_http(row)
            self.finish(row, status, receipt, retry)
        return row
