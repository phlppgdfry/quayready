# QuayReady interview and independent mastery package

[Case study](case-study.md) · [Detailed exercises](learning.md) · [Actual recording](demo-transcript.md)

## Two-minute pitch

QuayReady is my independent, AI-assisted logistics integration and learning project. It demonstrates a small cross-dock problem: three pallets are expected but only two appear in the warehouse snapshot. The application explains which evidence is missing and who needs to correct it.

A complete higher warehouse revision corrects the discrepancy. With fresh document evidence, the deterministic rules make the shipment eligible for review. An operator creates a proposal bound to that exact evidence version. A genuinely different subject must review it; another session or role cannot bypass the server's self-approval check.

Approval and an immutable dispatch-review request are saved together. A worker then crosses real local HTTP to a mock transport system with its own database. If the target commits but the response is lost, the app reports uncertainty. It looks up the original identifier instead of blindly resending with a new one.

The project goes beyond CRUD through transactional integrity, source revisions, failure recovery, independent authorisation and an observable system boundary. Its public simulation explains the workflow; it is separate from real application recordings and test evidence. The data and integrations are synthetic. It is not production deployment, physical departure authority or proof of professional client experience. I use the exercises to demonstrate what I can actually explain and change without AI.

## Eight-minute technical walkthrough

| Time | Show / explain | Evidence to inspect |
|---|---|---|
| 0:00–1:00 | Business problem, three expected pallets and missing P003; source owner, no override | Real workbench after seed; explain UNKNOWN versus confirmed absence |
| 1:00–2:00 | Correct warehouse snapshot, current receipt pointer and evidence v4 | Source revision, immutable receipts, current-snapshot SQL JOIN |
| 2:00–3:00 | Proposal, expiry and independent stable subject; demonstrate self-approval rejection | Server request/response and proposal evidence binding |
| 3:00–4:00 | Independent approval commits decision/outbox together | QUEUED before worker; deferred FK and rollback test |
| 4:00–5:00 | Worker reserve → COMMIT → HTTP → fenced result | Immutable payload/ID, separate target.db and receipt |
| 5:00–6:00 | Lost response and restart; distinguish unknown from failed | Genuine captioned recording or new synthetic run; one target effect |
| 6:00–7:00 | Bounded retries, lease generations and GET-only terminal investigation | Actual recovery/overlap tests; no counter reset or force-send |
| 7:00–8:00 | Why this stack, security/trust boundaries, build-versus-buy and limits | Architecture and execution manifest; identify personal knowledge gaps honestly |

## Ten likely interview questions

1. What exact operational decision does this support, and what remains outside scope?
2. Why compare only the current warehouse snapshot rather than all scans?
3. What differs between identical replay, conflicting replay and a stale source revision?
4. Why can UNKNOWN evidence not be represented as zero pallets?
5. How does a proposal become stale or expire without a new human action?
6. Why is another session insufficient for independent approval?
7. What does the approval/outbox transaction guarantee, and what cannot it guarantee remotely?
8. Why can a timeout coexist with a successful target commit?
9. What does a lease generation fence, and why must the target also be idempotent?
10. What source/vendor contracts, identity, support and continuity decisions are needed before a real deployment?

## Five independent exercises

| Task | Expected reasoning | Common mistake |
|---|---|---|
| Write a small Python readiness example and boundary test | Sets, explicit clock and reasons; predict exact cutoff/expiry result | Guessing UNKNOWN or using an off-by-one boundary |
| Write a parameterised SQL LEFT JOIN for missing pallets | Join expected pallets to the current source receipt's membership | Counting historical scans or interpolating SQL |
| Write an API client for replay/conflict | Show original receipt/version on identical replay; real 409 guard for changed content | Inventing a new event ID to hide retry semantics |
| Diagnose a paused/crashed worker | Inspect persisted lease, budget and dispatch ID; choose GET-first recovery | Resetting counters or claiming timeout proves no effect |
| Demonstrate two-session self-approval rejection and explain architecture tradeoffs | Stable subject, role, site and transaction are separate controls | Relying on disabled UI buttons; claiming a portfolio proves enterprise leadership |

## Self-assessment

For every task: predict before running; attempt unaided; explain each relevant function/query/HTTP status; locate one deliberate defect; show the real result; state limits and record AI help. Score 0 (cannot explain), 1 (guided), 2 (independent), or 3 (independent diagnosis and tradeoff explanation). A second person should observe level 2 on all five foundations. No exercise is marked passed on the owner's behalf. Supplier evaluation and organisational delivery experience require evidence beyond this solo project.
