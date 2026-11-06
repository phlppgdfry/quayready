# Genuine application walkthrough: narration and shot list

A 90–150-second captioned walkthrough is produced from an actual local browser run. The recording contains synthetic data only; no login credentials are displayed. Captions describe what the real UI shows. The static workflow simulation is a different artifact.

## Reproduction

Use a new run directory, start the app and independent target, and seed two observed pallets. Open the workbench as the operator. Do not print credentials into the recording. Correct the source through the real API, request review, demonstrate self-approval rejection, sign out and let the independent reviewer approve. Observe QUEUED, then run the worker and observe the target receipt.

For the recovery section, use an independent new run and a target started with `QUAYREADY_TARGET_FAULT=drop-after-commit`. Reserve/send, observe RETRY_WAIT, then restart the worker and look up the same dispatch ID. Never simulate recovery by editing database rows.

## Narration

QuayReady is an independent synthetic integration lab. It asks whether the evidence behind a transport-review request is trustworthy.

The order expects three pallets, but the warehouse snapshot contains two. P003 is missing, with a clear Warehouse owner. A reviewer cannot override incomplete evidence.

A corrected complete source snapshot now contains all three pallets. With fresh document evidence, the deterministic rule engine becomes eligible for review.

The operator requests review of evidence version four. The same person cannot approve, even with a different session or role. A genuinely different subject reviews that exact evidence version.

Approval and the immutable dispatch request commit in one local transaction. QUEUED means durable work; it does not mean the target has received it.

The worker crosses a real local HTTP boundary to a separately persisted mock-TMS. Only a matching target receipt becomes confirmed. This remains a dispatch-review request, never physical departure authorisation.

A lost response is uncertainty: the target may already have committed. After restart, lookup of the original dispatch identifier finds its receipt. Repeated delivery creates one target effect under this simulated contract.

One Python codebase, explicit SQL, a transactional outbox and a deliberately independent target make these boundaries inspectable. The tests are evidence of this implementation, not proof of production deployment or personal expertise.
