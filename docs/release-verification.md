# Release candidate verification — 0.2.0rc1

[README](../README.md) · [Architecture](architecture.md) · [Publication decision](publication.md) · [Historical E1 evidence](verification.md)

## Scope and identity

Local branch `work/ultimate-showcase-release`, based on the clean, remote-matching `b664034` E1 implementation. The original implementation branch and E1 evidence are preserved. The private strategy repository is not modified. No push, merge, visibility change, deployment, profile edit or Release publication is performed.

The [current execution record](../evidence/rc/execution.json) identifies the tested source/configuration/public-document tree, runtime versions and actual command exit codes. [JUnit](../evidence/rc/pytest.xml) and [command output](../evidence/rc/checks/pytest.txt) contain actual final test results. A working-tree fingerprint is used because evidence is generated before the final local commit; it includes code, tests, contracts, website source, dependencies, workflows and docs. Generated outputs are excluded to avoid self-referential hashes.

## Actual baseline and engineering gates

- Unmodified E1: **39 passed, 1 warning in 14.30 seconds**, verification exit 0. [Baseline record](../evidence/rc/baseline.txt).
- E2 engineering gate before visual work: **73 passed in 30.70 seconds**, no warnings. [Engineering JUnit](../evidence/rc/engineering.xml).
- The final release suite includes further UTC/numeric boundaries, actual chunked input, manual-recovery UI, schema/version/source identity checks and static-site/browser/accessibility checks. Its final count is reported by generated JUnit, not inferred from test names.

## Confirmed defects and corrections

1. Socket inactivity timeouts alone do not enforce a total deadline under trickled headers. A real absolute-deadline shutdown now interrupts the captured transport, including detached response sockets. Delayed/trickled header and body probes are bounded; responses are limited to 64 KiB.
2. A completed response on a closing connection could reach another socket operation after closure and be mistaken for a transient transport failure. Stop reading when the complete response is closed, then validate its body. Malformed 2xx is manual review, not assumed transient success.
3. Pagination could exceed SQLite's integer range. Bound and document the cursor, returning 422 rather than an unstructured overflow.
4. Persisted timestamp range and UTC-normalisation failures are rejected before writes, including pre-epoch and year-boundary overflow. Existing precision and source-revision limits remain enforced.
5. Snapshot source identity is bound after first authoritative application. A different configured source cannot silently take it over.
6. Expired sessions are pruned. Settings repr excludes principal credentials/worker key so failing tests and diagnostic output do not expose generated secrets.
7. The operation UI no longer presents UNKNOWN warehouse status as zero observed or confirmed missing pallets. Historical approvals explicitly distinguish current evidence validity from a confirmed past target effect.
8. Static simulation transitions respect actual atomicity: approval and outbox do not appear as separately committed states. Corrected snapshot application and recalculation are explained together.
9. Independent outbound-scope review reproduced a second-site order being accepted under the single DEMO-ZEE mock credential. The worker now blocks mismatched site rows before any attempt, and manual reconciliation also refuses them. A real-HTTP regression asserts zero sends and zero target effects; the lab does not claim multi-site target routing.
10. The no-JavaScript fallback is explicitly readable instead of relying solely on browser parser treatment of noscript. The full workflow and component fallback remain available without script execution.

A new replay-conflict test initially reused the fixture's exact reason and therefore correctly replayed rather than conflicting. Its input was corrected to differ genuinely. Existing tests were not deleted or safety expectations weakened. The original TestClient warning was resolved with officially supported httpx2 2.16.0, keeping FastAPI/Starlette versions unchanged.

## Reliability and database evidence

Real independently owned worker processes overlap after lease recovery and send the same immutable identifier; only the newer generation applies its local result and the target effect count stays one. A SQLite authorizer rejects an actual result-COMMIT, the transaction rolls back to SENDING, and lease recovery GET confirms the existing target effect. SQL traces and HTTP hooks assert no open app transaction at network send.

Response loss, restart, persistent due/counters, permanent target errors, malformed/oversized/trickled/delayed responses and budget exhaustion have executable tests. These are not universal vendor-protocol guarantees or power-loss/disk-corruption tests.

Reviewer-authorised manual reconciliation performs one bounded GET only. It reserves a generation, audits request/outcome, preserves automatic counters and identifier/payload, and leaves the barrier on absent/error results. A matching receipt can confirm a historical effect, with a post-approval-change alert when appropriate. The real UI test exercises this API against the independent target.

App schema 001 remains unchanged. Target migration 002 preserves E1 data while checking DDL and migration history. Foreign keys, uniqueness, immutable triggers, atomic approval/outbox and rollback constraints are exercised in disposable file-backed SQLite databases.

## Contract and security evidence

The approved OpenAPI contract evolves to 1.1.0 only for documented changes: implemented-runtime description, GET-only reconciliation operation/role, bounded cursor and persisted UTC-range clarification. Existing endpoint decision/replay semantics remain. Unreachable generic responses (order-ingestion 404 and mock-target POST 429) were removed after the real-trigger audit; global Host-rejection 403 was added to health endpoints. Configurable exact Origin semantics are documented instead of falsely pinning every instance to port 8080. The external-peer worker still handles 429 independently of the mock API. JSON response schemas are automatically checked for every matching TestClient response, supplemented by real target/browser tests and a standards-compliant OpenAPI validator. The full gate requires every declared operation/method/status pair to have an actual schema-validated response; [response coverage](../evidence/rc/response-coverage.json) reports missing pairs explicitly. This is HTTP contract-response coverage, not source-code coverage.

Tests cover role/kind enforcement, stable-subject self-approval across two keys/sessions, expiry/logout, CSRF/Origin/Host, two configured sites across reads/mutations, invalid schemas/media/version, chunked size limits, source conflict/replay, SQL-injection probes, escaped content and credential-safe diagnostic representation. No professional penetration test or exhaustive proof against all attacks is claimed.

Bandit and dependency/advisory results are separate actual artifacts. A clean scan is not proof of absence of vulnerabilities. The local project itself is not auditable through PyPI advisories. Local administrators remain trusted; app audit is not tamper-proof. HTTP-only loopback cookies are not a production identity design.

## Browser, visual, accessibility and performance

Browser plugin/skill is not listed in this session; the repository's real Playwright/Chromium flow is used. No browser fallback failure is concealed. Actual app capture and interactive site simulation are separate.

Application flow: real HTTP sources → missing P003 → corrected v4 → operator proposal → self-approval 403 → different reviewer → QUEUED → independent target receipt. A separate flow demonstrates manual uncertainty and GET-only recovery. Site flow: real built subpath → all eleven simulation steps/reset → every failure scenario → every selectable component → documentation links → no-JavaScript fallback.

Viewports: desktop 1440×1000, laptop 1280×800, tablet 768×1024 and mobile 390×844. Test-owned local servers use temporary ports and are terminated. Screenshots are inspected for hierarchy, clipping, wrapping, empty content and error overlays. Automated axe-core 4.11.0 runs WCAG-tagged A/AA rules on login, discrepancy, confirmed/manual app states and desktop/mobile site. JSON reports retain incomplete rule IDs for manual review; zero automatic violations is not WCAG certification. Screen-reader user testing remains unverified.

[Browser captures](../evidence/rc/showcase/hero-desktop.png) and [app capture](../evidence/rc/ui/hero.jpg) are generated from execution. [Browser timing](../evidence/rc/showcase/performance.json) records local navigation/resource observations, not a benchmark, Lighthouse score or real-world performance claim. Static assets are local; the video uses preload=none and loads only on request. No external fonts or tracking scripts are included.

## Genuine recording and assets

[Walkthrough](../evidence/rc/video/walkthrough.webm) is an actual approximately 112-second browser recording, with [captions](../evidence/rc/video/walkthrough.vtt), [record metadata](../evidence/rc/video/recording.json) and [transcript](demo-transcript.md). Synthetic data only; credential entry is masked. It includes real response loss after target commit and recovery by a new worker process. Original recording remains in the ignored isolated run; VP9 compression changes encoding, not application content. There is no fabricated narration, customer quote or test animation.

Architecture, workflow, sequence and social-card sources are original SVGs with valid XML. The social PNG is rendered from its documented vector source. Screenshots depict real application states. Simulated workflow visuals remain labelled. No proprietary company imagery or research is included.

## CI, reproducibility and publication gates

Pinned upstream action SHAs and the selected Python 3.13.18 Linux build were read-only verified against official repositories/manifests. `actionlint` validates the workflow locally. Contents permission is read-only, checkout credentials are not persisted, no production secret is required and no deployment job exists. **Hosted execution is NOT RUN on this unpublished branch.** No green badge or cross-platform success is inferred.

The static exporter runs without a backend, checks local paths/anchors and SVG XML, refuses non-empty unowned external output and rejects unexpected stale output files. It exports an explicit neutral allowlist, not the repository. Correct relative assets and refresh-safe anchors are tested under `/quayready/`. Canonical/public social URL must be set to the actually approved deployment URL before publication.

A clean RC virtual environment is exercised separately on this Mac. That is not another person's cold start or Linux verification. Independent owner mastery, second-person reproduction, human security/code review, screen-reader usability and an actual hosted CI run remain unverified human/hosting gates. No known safety-critical failure may be hidden by those limitations.

## Independent critical-review pass

Review against three audiences: a recruiter should identify the missing-evidence problem and demo immediately; an operations manager should distinguish source readiness, human approval and target delivery; an engineer should inspect transaction ownership, recovery guarantees and reproducibility. Confirmed corrections include UNKNOWN count semantics, historical approval labelling, atomic simulation transitions and stale public-output rejection. No imaginary findings or production/ROI claims are added.

Final executed results, asset sizes, cold-start outcome and remaining limitations are recorded with the generated artifacts and the final release report. Publication is an informed next decision, not an action taken here.

The evidence runner excludes generated egg-info metadata from input fingerprints, then rechecks all tested source inputs after execution. An initial self-review found package-build metadata in that hash list; the runner was corrected so the recorded identifier represents stable source/configuration, not mutable build intermediates.

The final manual axe review identified the component selector div needing role=group for its accessible name; that was corrected. Remaining single-character contrast review flags refer to the decorative aria-hidden Q brand mark. Its white/harbour pair is covered by the recorded contrast calculation and visually inspected; it is not a failed text-contrast result. This still does not replace screen-reader user testing.
