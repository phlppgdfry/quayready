# QuayReady technical guide

A local synthetic integration lab for cross-dock evidence, independent review and reliable dispatch-review requests. The showcase's interactive simulation is separate from the real application. No real warehouse, transport vendor or company infrastructure is connected.

## Reproduce the real application

Use CPython 3.13 with SQLite >=3.37 and JSON support. Obtain the application source from the owner while its repository is private. From the repository root:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install -e . --no-deps --no-build-isolation
.venv/bin/python -m playwright install chromium
.venv/bin/quayready init
```

In separate terminals run `quayready serve` and `quayready target` using `.venv/bin/quayready`. Then run `quayready seed` and retrieve the operator login token using `quayready credentials --role operator`. Only use the token on the local app at `http://127.0.0.1:8080`.

The app shows two observed pallets and missing P003. Run `quayready correct`, refresh, and request review of evidence v4. Attempt self-approval to see the server rejection. Sign out; obtain `quayready credentials --role reviewer`, sign in as the different subject and approve. The request is durably QUEUED. Run `quayready worker --once`, then refresh to see the independent receipt.

The default domain clock is fixed at 2026-11-02 11:40 UTC. Leases, retry timing and sessions use real time. This is reproducible evidence, not a live warehouse freshness model.

## Run checks

```sh
.venv/bin/python scripts/verify.py
.venv/bin/pip-audit
npm ci --ignore-scripts
npm run check
```

The release verification additionally includes real process overlap, bounded hostile-response probes, actual browser tests and automated accessibility checks. Passing local tests is not a hosted CI result or a security certification.

## Integration semantics

Order revision 1 and immutable expected pallets define the synthetic order. Complete warehouse and document snapshots carry source revisions. Canonical event replays return their original receipt without renewing evidence. Conflicting replay commits a guard; stale revisions cannot replace the current snapshot.

Readiness, human approval and delivery are separate states. Hard holds and cutoff block review. Missing, unknown, expired or conflicting evidence needs review; valid reconciled evidence becomes eligible. A version-bound proposal expires at the earliest source expiry, cutoff or five-minute review window. No override exists.

Approval, dispatch request and audit commit atomically in the app database. A worker reserves an attempt, commits, performs HTTP outside the transaction and persists a fenced result. Three automatic POST reservations and three automatic lookups are the maximum. Uncertain POST always leads to lookup first. A reviewer can perform an explicit GET-only investigation of terminal uncertainty; this cannot resend, reset counters or change the dispatch identifier.

The mock-TMS is a separate HTTP process with a separate database and stable, idempotent receipt. This constrains target effects under the simulated contract; it does not establish universal exactly-once processing or guaranteed eventual delivery.

## Security and continuity

Generated local credentials, stable-subject role/site enforcement, CSRF, exact Origin/Host checks, bounded JSON, parameterised SQL, output escaping and CSP protect this lab. Plain loopback HTTP omits Secure on the session cookie; this must change before any production design. A local database administrator remains trusted and can alter audit protections.

Reset means creating a new run with `init --directory NEW`, preserving the old evidence. Use that directory on every subsequent command. Never connect a real system, reset delivery counters or force-send an uncertain request. Source code, research and publication decisions are separate.

## Learning

Independently write a missing-pallet LEFT JOIN query; explain one boundary test; reproduce two-session self-approval rejection; narrate lost-response recovery. For each, predict the result before running it and record any AI help. Generated explanations and passing tests do not prove personal mastery.

## Further reading

[Architecture](architecture.md), [case study](case-study.md) and [execution evidence](release-verification.md). The public case study includes no private recruitment or company research. No customer, endorsement, measured ROI or production compliance is claimed.
