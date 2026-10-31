# Changelog

## 0.2.0rc1 — local release candidate, not published

- Hardened total HTTP deadlines against delayed/trickled headers and bodies; correct complete-response handling when a connection closes.
- Added two-process worker overlap, fenced-result, actual result-COMMIT failure, terminal uncertainty and contract/security negative tests.
- Added reviewer-authorised, generation-fenced GET-only manual reconciliation. No force-send, budget reset or new dispatch identity.
- Added target migration 002 with history/checksum and DDL verification; migration 001 and existing target effects remain intact.
- Blocked outbound/manual requests outside the single configured mock-target site before HTTP.
- Bound existing snapshot identity; bounded pagination to SQLite integer range; structured unsupported-route errors; expired-session pruning; redacted credential repr.
- Resolved Starlette TestClient deprecation with supported httpx2 development dependency.
- Redesigned the real operational workbench, added state explanations, reviewer identity/reason, accessible error handling and chronological audit.
- Added a fully static case-study website with explicitly labelled simulation, failure lab and architecture explorer, no-JS fallback and subpath support.
- Added genuine captures, a captioned local walkthrough, original SVG diagrams/social assets and accessibility/performance observations.
- Prepared pinned, least-privilege verification Actions; no deployment, publication or hosted-CI success is claimed.

## 0.1.0 — E1 baseline `b664034`

Closed synthetic three-pallet workflow, version-bound independent review, transactional outbox and independent HTTP target. 39 local tests passed. Historical E1 artifacts remain under `evidence/`.
