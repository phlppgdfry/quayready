# Implemented E1 design and decisions

> This document preserves the E1 design. See [current architecture](architecture.md) and [release changes](release-verification.md) for manual reconciliation, target migration 002, strict response/deadline handling and the redesigned workbench.

[Run](../README.md) · [Evidence](verification.md) · [Learning](learning.md) · [Next phase](next-phase.md)

## Boundaries and data ownership

`api.py` owns authentication, strict contract validation and HTTP presentation. `store.py` owns local transactional use cases and audit/issue projections. `domain.py` is the single readiness rule engine. `db.py` opens a connection per transaction, enables foreign keys every time and closes it after commit/rollback. `worker.py` owns delivery reservation, HTTP and fenced results. `cli.py` provides cold start and synthetic source HTTP clients. The target runs the same package in a separate process, with its own database and trusted synthetic order seed; it cannot read the app's outbox.

Migration 001 is the approved neutral schema, unchanged. App startup checks its recorded checksum; unknown/drifted versions stop startup. Target startup checks schema version 1. SQLite STRICT tables, composite site foreign keys, immutable-record triggers and unique indexes enforce durable invariants. The app requires WAL, JSON and foreign keys. No automatic destructive rollback: fix forward in a later numbered migration or initialise a new synthetic run, retaining the original.

## Readiness, approval and delivery are separate

Readiness is computed from current evidence on every read/action, with issue episodes materialised on ingestion and a one-second maintenance poll. `BLOCKED` means hard hold or cutoff reached; otherwise missing/expired/unknown/conflicting evidence or pallet differences mean `NEEDS_REVIEW`; only an empty reason set is `ELIGIBLE_FOR_REVIEW`. A reviewer cannot override these conditions. Expiry is exclusive: at `observed + 15 minutes` evidence is expired; at cutoff the shipment is blocked. An expired hard hold remains a hard hold.

A new order starts version 1; applied snapshots and newly latched conflict guards advance it. The normal demo reaches v3 with the missing pallet and v4 after the correction. A complete newer snapshot replaces the current membership set; old immutable receipts remain history. Identical event replay returns the original receipt without renewing freshness. Stale new-ID revisions create an ignored receipt without changing the authoritative projection. Conflicting replay commits a guard on the trusted original scope before returning 409. A valid revision above the conflict floor is required to clear a source guard. An order conflict is latched for the run.

Proposal state is `PENDING_REVIEW`, `APPROVED`, `REJECTED`, `INVALIDATED` or `EXPIRED`. It binds evidence version/hash, rules version and an immutable evidence snapshot. Expiry is the earliest of five minutes after creation, either source expiry or cutoff. A stable subject cannot review its own proposal, even with both roles. Recheck occurs within the decision write transaction. APPROVE, outbox insertion, proposal update and audit commit together; the circular deferred foreign key prevents an orphan committed approval.

Delivery states are `QUEUED → SENDING → CONFIRMED`, or `RETRY_WAIT`, `MANUAL_REVIEW` and `CANCELLED_BEFORE_SEND`. Readiness can change after a historical target effect; confirmed delivery never asserts current physical readiness. Once any POST is reserved, the app cannot honestly declare the request safely cancelled.

## Delivery protocol

1. **Reserve:** `BEGIN IMMEDIATE`; reconcile evidence, inspect persisted due/budgets, increment generation and action counter, lease for 30 seconds, audit; COMMIT.
2. **Network:** with no open app transaction, send immutable payload/dispatch ID, or GET the same ID. Connect timeout 1 second, total deadline 3 seconds, maximum response 64 KiB; direct configured loopback connection, no proxy/redirect following.
3. **Record:** `BEGIN IMMEDIATE`; require state SENDING, matching generation and unexpired lease; recheck evidence, store result and audit; COMMIT. An old worker result changes nothing.

At most three reserved POSTs and three LOOKUPs are durable. A failed/uncertain POST always leads to LOOKUP first. GET 404 permits another POST only with still-valid evidence and remaining budget. Failed GET never licenses POST. Backoff is two seconds after the first failure, eight afterwards, with bounded Retry-After honoured. Expired leases recover lookup-first with a higher generation. Backwards worker time stops claims. Evidence changes before the first reservation cancel; changes afterwards allow lookup only, preserving the unresolved-dispatch barrier. A historical receipt is confirmed with a post-approval-change issue when necessary. Missing receipt with invalid evidence becomes manual uncertainty.

| Failure | Persisted outcome | Executed evidence |
|---|---|---|
| Duplicate event | Same receipt, no new projection/version | T03/T04 |
| Changed replay | 409 plus committed guard; old data intact | T06 |
| Ingest/approval database failure | Rollback; no partial receipt/approval/outbox | T10/T11 |
| Restart after approval | Same queued ID, new API session required | T12 |
| Target commit, truncated response | Uncertain app state, target count 1; GET confirms original receipt | T13 |
| Worker exit after HTTP / before local result | Persisted SENDING; lease recovery looks up | T14 |
| Expired worker returns | Generation/lease predicate rejects result | T15/T17 |
| Target remains unavailable | Bounded lookup attempts, MANUAL_REVIEW | T16 |
| Evidence changes after reservation | GET-only recovery; no replacement dispatch | T18 |

Tests include actual process termination/restart, separately simulated interruption at the pre-result seam, independent file-backed databases and real HTTP. They do not simulate power loss, disk corruption or a real vendor protocol. Guarantees depend on durable local disks and target uniqueness; no distributed atomicity or universal exactly-once claim.

## Security actually implemented

Random distinct human/source/worker tokens are generated into ignored, mode-0600 config under a mode-0700 run directory. Human sessions use random IDs, HttpOnly/SameSite=Strict cookies, real 30-minute expiry, exact Origin, session-bound CSRF and a local five-login-per-minute throttle. Server-side roles and site-filtered queries precede business operations. Source kind is bound to identity, not a caller-supplied role. Worker credentials are only sent to the configured loopback target.

Strict JSON schemas reject unknown properties, coercion, duplicate keys/pallets and invalid timestamps. Bodies are bounded at 64 KiB, including streamed input. SQL uses placeholders; the two dynamic column names and issue filters are internal allowlists. Jinja escapes output; JS uses textContent for errors, and CSP permits only same-origin scripts/styles. Audit rows cannot be updated/deleted through normal SQL because of triggers. A local database administrator can remove those protections: this is not tamper-proof audit. Secrets/source bodies are not included in application audit logs. No production security certification is claimed.

## Implementation decisions within the baseline

- **ADR-E1-01 — manual OpenAPI validation.** Use the approved JSON Schema directly instead of FastAPI's default coercion/422 responses. This preserves the wire contract; request handlers are intentionally small but explicit. A workflow response-contract test validates the emitted responses against the approved schemas. OpenAPI JSON is unchanged from the design baseline.
- **ADR-E1-02 — synchronous SQLite use cases.** Short explicit write transactions and one local worker keep the state machine inspectable. Blocking database work is small and bounded; this is not a high-throughput production service. Async maintenance runs via a thread. No ORM, broker or service split.
- **ADR-E1-03 — injected failure modes.** Target process environment permits `drop-after-commit` and `unavailable`. The first deliberately truncates the HTTP response after a committed insertion; the worker sees real transport uncertainty. No shared-table shortcuts or fake success states.
- **ADR-E1-04 — command interface.** Planned interfaces become `quayready init/serve/target/seed/correct/worker/credentials`. Reset means `init --directory NEW`; it cannot overwrite evidence. `worker --once` reserves at most one action, enabling observable queued and uncertain states. No manual force-send command.
- **ADR-E1-05 — dependency baseline.** CPython 3.13, exact dependency versions, current FastAPI/Starlette with httpx TestClient deprecation explicitly recorded. Separate real HTTP and browser tests avoid relying solely on that client. Buildtool setuptools was updated to 84.1.0 after the advisory scan; no audit finding was silently ignored.

These decisions resolve implementation details; they do not revise the approved domain scope. E2 remains a separate hardening milestone.
