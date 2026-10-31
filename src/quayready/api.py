from __future__ import annotations

import asyncio
import hmac
import logging
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from importlib.resources import files
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.exceptions import HTTPException

from .common import SPEC, Json, Problem, digest, iso, parse_json, uid, validate, wall_ms
from .config import TARGET_SITE, Principal, Settings, load_settings
from .db import Database
from .store import Store

log = logging.getLogger("quayready")


def create_app(settings: Settings | None = None, target: bool = False) -> FastAPI:
    cfg = settings or load_settings()
    store = Store(cfg)
    db = Database(cfg.run_dir / "target.db", True) if target else store.db
    db.initialize()
    sessions: dict[str, tuple[Principal, str, int]] = {}
    attempts: list[float] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        async def poll() -> None:
            while True:
                try:
                    await asyncio.to_thread(store.poll)
                except sqlite3.DatabaseError:
                    log.warning("Database maintenance unavailable")
                await asyncio.sleep(1)

        task = asyncio.create_task(poll()) if not target else None
        yield
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        sessions.clear()

    app = FastAPI(
        title="QuayReady", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.store = store
    app.state.db = db
    app.state.settings = cfg
    app.state.sessions = sessions

    @app.exception_handler(Problem)
    async def problem_handler(request: Request, exc: Problem) -> JSONResponse:
        return JSONResponse(
            exc.body(),
            exc.status,
            headers={"Retry-After": "2"} if exc.status in (429, 503) else None,
        )

    @app.exception_handler(sqlite3.DatabaseError)
    async def database_handler(request: Request, exc: sqlite3.DatabaseError) -> JSONResponse:
        return JSONResponse(Problem(503, "DATABASE_UNAVAILABLE").body(), 503)

    @app.exception_handler(HTTPException)
    async def route_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            Problem(
                exc.status_code, "NOT_FOUND" if exc.status_code == 404 else "INVALID_SCHEMA"
            ).body(),
            exc.status_code,
        )

    @app.middleware("http")
    async def boundary(request: Request, call_next: Any) -> Response:
        try:
            port = cfg.target_port if target else cfg.app_port
            if request.headers.get("host") != f"127.0.0.1:{port}":
                raise Problem(403, "ORIGIN_REJECTED")
            if request.method == "POST":
                if request.headers.get("content-encoding"):
                    raise Problem(415, "UNSUPPORTED_MEDIA_TYPE")
                content_type = request.headers.get("content-type", "").replace(" ", "").lower()
                if content_type not in ("application/json", "application/json;charset=utf-8"):
                    raise Problem(415, "UNSUPPORTED_MEDIA_TYPE")
                data = bytearray()
                async for chunk in request.stream():
                    data.extend(chunk)
                    if len(data) > 65536:
                        raise Problem(413, "PAYLOAD_TOO_LARGE")
                request._body = bytes(data)
            response = await call_next(request)
        except Problem as e:
            response = JSONResponse(e.body(), e.status)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    async def body(request: Request, schema: str) -> Json:
        return validate(schema, parse_json(await request.body()))

    def human(request: Request, roles: tuple[str, ...], unsafe: bool = False) -> Principal:
        session = sessions.get(request.cookies.get("qr_session", ""))
        if not session or wall_ms() >= session[2]:
            raise Problem(401, "UNAUTHENTICATED")
        p, csrf, _ = session
        if not any(role in p.roles for role in roles):
            raise Problem(403, "FORBIDDEN")
        if unsafe:
            if request.headers.get("origin") != cfg.origin:
                raise Problem(403, "ORIGIN_REJECTED")
            if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf):
                raise Problem(403, "CSRF_FAILED")
        return p

    def machine(request: Request, kind: str | None = None) -> Principal:
        if request.headers.get("origin"):
            raise Problem(403, "ORIGIN_REJECTED")
        key = request.headers.get("x-source-key", "")
        p = next(
            (p for candidate, p in cfg.principals.items() if hmac.compare_digest(candidate, key)),
            None,
        )
        if not p:
            raise Problem(401, "UNAUTHENTICATED")
        if p.kind is None or (kind and p.kind != kind):
            raise Problem(403, "FORBIDDEN")
        return p

    def identifier(value: str) -> str:
        try:
            UUID(value)
        except ValueError:
            raise Problem(422, "INVALID_SCHEMA") from None
        return value

    def idem(request: Request) -> str:
        key = request.headers.get("idempotency-key", "")
        validate("Token", key)
        return key

    def pagination(request: Request) -> tuple[int, int]:
        try:
            rawafter = request.query_params.get("after", "0")
            rawlimit = request.query_params.get("limit", "50")
            if not rawafter.isdigit() or not rawlimit.isdigit():
                raise ValueError()
            after, limit = int(rawafter), int(rawlimit)
            if not 0 <= after <= 9223372036854775807 or not 1 <= limit <= 100:
                raise ValueError()
            return after, limit
        except ValueError:
            raise Problem(422, "INVALID_SCHEMA") from None

    @app.get("/health/live")
    def live() -> Json:
        return {"status": "ALIVE"}

    @app.get("/health/ready")
    def ready() -> Json:
        with db.transaction() as c:
            c.execute("SELECT 1")
        return {"status": "READY"}

    if target:

        def worker_auth(request: Request) -> None:
            if request.headers.get("origin"):
                raise Problem(403, "ORIGIN_REJECTED")
            if not hmac.compare_digest(request.headers.get("x-worker-key", ""), cfg.worker_key):
                raise Problem(401, "UNAUTHENTICATED")

        def target_receipt(row: sqlite3.Row) -> Json:
            return {
                "dispatchId": row["dispatch_id"],
                "receiptId": row["receipt_id"],
                "payloadHash": row["payload_hash"],
                "status": row["status"],
                "acceptedAt": iso(row["accepted_at_ms"]),
            }

        @app.post("/mock/v1/dispatch-requests")
        async def receive_dispatch(request: Request) -> Response:
            worker_auth(request)
            value = await body(request, "DispatchRequest")
            if cfg.target_fault == "unavailable":
                raise Problem(503, "DATABASE_UNAVAILABLE")
            h = digest(value)
            with db.transaction() as c:
                old = c.execute(
                    "SELECT * FROM dispatch_requests WHERE dispatch_id=?", (value["dispatchId"],)
                ).fetchone()
                if old:
                    if old["site_id"] != "DEMO-ZEE":
                        raise Problem(404, "NOT_FOUND")
                    if old["payload_hash"] != h:
                        raise Problem(409, "PAYLOAD_CONFLICT")
                    return JSONResponse(target_receipt(old), 200)
                if not c.execute(
                    "SELECT 1 FROM target_orders WHERE site_id='DEMO-ZEE' AND shipment_ref=? AND order_revision=?",
                    (value["shipmentRef"], value["orderRevision"]),
                ).fetchone():
                    raise Problem(404, "NOT_FOUND")
                if c.execute(
                    "SELECT 1 FROM dispatch_requests WHERE site_id='DEMO-ZEE' AND shipment_ref=?",
                    (value["shipmentRef"],),
                ).fetchone():
                    raise Problem(409, "TARGET_SHIPMENT_CONFLICT")
                from .common import canonical

                c.execute(
                    "INSERT INTO dispatch_requests VALUES(?,'DEMO-ZEE',?,?,?,?,?,?,'ACCEPTED_FOR_REVIEW')",
                    (
                        value["dispatchId"],
                        value["shipmentRef"],
                        1,
                        h,
                        canonical(value),
                        uid(),
                        cfg.now(),
                    ),
                )
                result = target_receipt(
                    c.execute(
                        "SELECT * FROM dispatch_requests WHERE dispatch_id=?",
                        (value["dispatchId"],),
                    ).fetchone()
                )
            if cfg.target_fault == "drop-after-commit":
                # Deliberately truncate an HTTP response after a REAL committed target effect.
                # h11 closes the connection; no receipt reaches the client. Test-only process mode.
                return Response(
                    b"", media_type="application/json", headers={"Content-Length": "100"}
                )
            return JSONResponse(result, 201)

        @app.get("/mock/v1/dispatch-requests/{id}")
        def lookup_dispatch(id: str, request: Request) -> Json:
            worker_auth(request)
            identifier(id)
            if cfg.target_fault == "unavailable":
                raise Problem(503, "DATABASE_UNAVAILABLE")
            with db.transaction(False) as c:
                row = c.execute(
                    "SELECT * FROM dispatch_requests WHERE dispatch_id=? AND site_id='DEMO-ZEE'",
                    (id,),
                ).fetchone()
                if not row:
                    raise Problem(404, "NOT_FOUND")
                return target_receipt(row)

        return app

    @app.get("/openapi.json")
    def openapi() -> Json:
        return SPEC

    @app.post("/v1/session")
    async def login(request: Request) -> Response:
        if request.headers.get("origin") != cfg.origin:
            raise Problem(403, "ORIGIN_REJECTED")
        now = time.monotonic()
        attempts[:] = [x for x in attempts if now - x < 60]
        for key, session in list(sessions.items()):
            if wall_ms() >= session[2]:
                sessions.pop(key, None)
        if len(attempts) >= 5:
            raise Problem(429, "RATE_LIMITED")
        attempts.append(now)
        value = await body(request, "SessionRequest")
        p = next(
            (
                p
                for k, p in cfg.principals.items()
                if hmac.compare_digest(k, value["loginToken"]) and p.kind is None
            ),
            None,
        )
        if not p:
            raise Problem(401, "UNAUTHENTICATED")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        expires = wall_ms() + 1800000
        sessions[token] = (p, csrf, expires)
        response = JSONResponse(
            {
                "subject": p.subject,
                "siteId": p.site,
                "roles": list(p.roles),
                "csrfToken": csrf,
                "expiresAt": iso(expires),
            }
        )
        response.set_cookie("qr_session", token, max_age=1800, httponly=True, samesite="strict")
        return response

    @app.delete("/v1/session")
    def logout(request: Request) -> Response:
        human(request, ("operator", "reviewer", "auditor"), True)
        sessions.pop(request.cookies.get("qr_session", ""), None)
        response = Response(status_code=204)
        response.delete_cookie("qr_session")
        return response

    @app.post("/v1/orders")
    async def receive_order(request: Request) -> Response:
        p = machine(request, "ORDER")
        status, value = store.ingest(p, await body(request, "Order"), "ORDER")
        return JSONResponse(value, status)

    @app.post("/v1/events")
    async def receive_event(request: Request) -> Response:
        p = machine(request)
        if p.kind not in ("WAREHOUSE", "DOCUMENT"):
            raise Problem(403, "FORBIDDEN")
        value = await body(request, "Event")
        kind = "WAREHOUSE" if value["kind"] == "warehouse_snapshot" else "DOCUMENT"
        if p.kind != kind:
            raise Problem(403, "FORBIDDEN")
        status, out = store.ingest(p, value, kind)
        return JSONResponse(out, status)

    @app.get("/v1/shipments/{id}")
    def get_shipment(id: str, request: Request) -> Json:
        p = human(request, ("operator", "reviewer", "auditor"))
        return store.view(p, identifier(id))

    @app.post("/v1/shipments/{id}/proposals")
    async def propose(id: str, request: Request) -> Response:
        p = human(request, ("operator",), True)
        status, out = store.proposal(
            p, identifier(id), idem(request), await body(request, "ProposalRequest")
        )
        return JSONResponse(out, status)

    @app.post("/v1/proposals/{id}/decision")
    async def decide(id: str, request: Request) -> Json:
        p = human(request, ("reviewer",), True)
        return store.decide(
            p, identifier(id), idem(request), await body(request, "DecisionRequest")
        )

    @app.get("/v1/deliveries/{dispatchId}")
    def delivery(dispatchId: str, request: Request) -> Json:
        return store.delivery(
            human(request, ("operator", "reviewer", "auditor")), identifier(dispatchId)
        )

    @app.post("/v1/deliveries/{dispatchId}/reconcile")
    async def reconcile_delivery(dispatchId: str, request: Request) -> Json:
        from .worker import Worker

        p = human(request, ("reviewer",), True)
        await body(request, "ReconcileRequest")
        # The bounded blocking network lookup runs outside the event loop and all DB writes.
        return await asyncio.to_thread(Worker(store).reconcile, p, identifier(dispatchId))

    @app.get("/v1/issues")
    def issues(request: Request) -> Json:
        p = human(request, ("operator", "reviewer"))
        after, limit = pagination(request)
        status = request.query_params.get("status", "OPEN")
        if status not in ("OPEN", "RESOLVED", "ALL"):
            raise Problem(422, "INVALID_SCHEMA")
        return store.page(p, "issues", after, limit, status=status)

    @app.get("/v1/shipments/{id}/audit")
    def audit(id: str, request: Request) -> Json:
        p = human(request, ("reviewer", "auditor"))
        after, limit = pagination(request)
        return store.page(p, "audit", after, limit, identifier(id))

    templates = Environment(
        loader=FileSystemLoader(str(files("quayready").joinpath("templates"))),
        autoescape=select_autoescape(),
    )
    app.mount(
        "/static", StaticFiles(directory=str(files("quayready").joinpath("static"))), name="static"
    )

    @app.get("/", response_class=HTMLResponse)
    def workbench(request: Request) -> HTMLResponse:
        session = sessions.get(request.cookies.get("qr_session", ""))
        p = None
        if session and wall_ms() < session[2]:
            p = session[0]
        ships = []
        events = []
        decisions = {}
        if p:
            with store.db.transaction(False) as c:
                ids = [
                    r[0]
                    for r in c.execute(
                        "SELECT id FROM shipments WHERE site_id=? ORDER BY created_at_ms LIMIT 100",
                        (p.site,),
                    )
                ]
            ships = [store.view(p, sid) for sid in ids]
            with store.db.transaction(False) as c:
                decisions = {
                    r["shipment_id"]: dict(r)
                    for r in c.execute(
                        "SELECT * FROM review_decisions WHERE site_id=? ORDER BY decided_at_ms",
                        (p.site,),
                    )
                }
            if ships and any(r in p.roles for r in ("reviewer", "auditor")):
                events = store.page(p, "audit", 0, 100, ships[0]["shipmentId"])["items"]
        html = templates.get_template("workbench.html").render(
            principal=p,
            csrf=session[1] if session and p else "",
            shipments=ships,
            events=events,
            decisions=decisions,
            target_site=TARGET_SITE,
            now=iso(cfg.now()),
            fixed=cfg.domain_time is not None,
        )
        return HTMLResponse(html)

    return app


def app_factory() -> FastAPI:
    return create_app()


def target_factory() -> FastAPI:
    return create_app(target=True)
