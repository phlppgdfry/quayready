# Personal technical mastery: explain, change, verify

[Run](../README.md) · [Design](implementation.md) · [Evidence](verification.md)

Implementation with an AI assistant is not evidence that the owner can independently design or maintain it. None of the following personal assessments has been passed on the owner's behalf. Keep a private learning log: date, task, unaided attempt, assistance received, defect found and explanation in your own words. Do not commit login tokens or private research.

## 1. Python and deterministic readiness

**Component/purpose:** [domain.py](../src/quayready/domain.py) compares sets and evidence facts. Operations needs one understandable explanation for a missing pallet, regardless of UI or API caller. It demonstrates functions, dictionaries, sets, branching and typed return values.

**Inspect/debug:** read `assess`, run `pytest -q -k T07`, then put a debugger breakpoint inside it and inspect expected/scanned sets and the clock. Trace an empty `UNKNOWN` snapshot: absence of knowledge is not evidence of zero pallets.

**Personal exercise:** without AI writing the solution, add a unit-test case for one unexpected pallet and explain every reason returned. Then deliberately change `<` to `<=` at an expiry boundary, predict the failure and revert the change. Explain exception vs return-value handling in `common.py`.

**Three interview questions:** Why use a set? Why can an expired hard hold still block? Why must the UI not calculate readiness again?

**Mastery:** independently predict statuses/reasons for missing, extra, unknown and exact-expiry examples; locate a wrong result with the debugger; explain the fix and test without reading an AI answer.

## 2. SQL, current snapshots and database access

**Component/purpose:** [store.py](../src/quayready/store.py) reads the latest source pointer and immutable memberships. The business question is what is missing **now**, not how many historical scans exist. Concepts: SELECT, WHERE, JOIN, LEFT JOIN, GROUP BY, foreign keys, placeholders and row mapping.

**Inspect/debug:** open an expendable run database read-only. Inspect `shipments`, `expected_pallets`, `source_snapshots`, `warehouse_events` and `inbound_receipts`; compare counts to the workbench. The SQL test `T21_current_snapshot_missing_query` is a reference to consult only after your attempt.

**Personal exercise:** write a parameterised LEFT JOIN query returning P003 before correction and zero rows afterwards. Write a GROUP BY query counting receipts by kind; explain why this count is not the current pallet count. Do not use the SQLite CLI to modify evidence as a substitute for the API.

**Three interview questions:** Why does joining all old receipts double-count? What does foreign-key enforcement on every connection protect? Why use parameters instead of SQL string concatenation?

**Mastery:** write both queries unaided, explain each join/filter, show before/after results from real source ingestion and identify a deliberately incorrect historical join.

## 3. REST API ingestion and idempotency

**Component/purpose:** [api.py](../src/quayready/api.py) and [common.py](../src/quayready/common.py) validate/authenticate incoming JSON. Repeated transport delivery must not create repeated business effects. Concepts: HTTP methods/statuses, JSON, source credentials, validation, exceptions and canonical hashing.

**Inspect/debug:** follow `seed` through HTTP into `receive_order`, `Store.ingest` and receipt creation. Use a debugger or an unauthenticated request first; never paste a real token into a public API explorer or learning log. Run T01/T03/T06 and inspect safe receipt IDs and versions.

**Personal exercise:** write a small Python client that sends the same event twice, prints status/receipt/version only, then sends the same ID with a different pallet set. Predict 201/200/409 before execution. Explain why reordering pallets or equivalent timezone formatting does not create a new effect.

**Three interview questions:** How do event ID and content hash differ? Why is a stale revision not a conflicting replay? Why can retrying with a new identifier be dangerous?

**Mastery:** independently create the client, handle non-success responses explicitly, demonstrate no version bump on identical replay and explain the committed guard on conflict.

## 4. Transactions, approval and state machines

**Component/purpose:** proposal/decision use cases bind human review to the evidence actually inspected. The transaction couples a consequential approval to a durable dispatch request. Concepts: BEGIN/COMMIT/ROLLBACK, unique constraints, deferred foreign keys and concurrency.

**Inspect/debug:** read `Store.proposal/decide`, the review/outbox schema and `T11_approval_transaction_failure_rolls_back_all`. Draw readiness, proposal and delivery as **three separate** state machines. Observe QUEUED before starting a worker.

**Personal exercise:** on a temporary run, create a proposal, change the document snapshot and attempt approval. Explain the rejected version and demonstrate zero new outbox rows. Independently explain a failed transaction in which decision and outbox inserts are rolled back together.

**Three interview questions:** Why is hiding a button insufficient? What race does BEGIN IMMEDIATE resolve? Why does approval not prove physical departure readiness later?

**Mastery:** explain every database write in the approval transaction; predict both event-before-decision and decision-before-event outcomes; show how the database rejects an orphan APPROVE.

## 5. Integration architecture, retries and debugging

**Component/purpose:** [worker.py](../src/quayready/worker.py) transfers an immutable request across an independent system boundary. A timeout is uncertainty, not proof that the target did nothing. Concepts: HTTP deadlines, exceptions, counters, lease generations, durable timers and target ownership.

**Inspect/debug:** follow `claim → request → finish`. Inspect safe outbox fields, audit and independent target counts during the lost-response demo. Run `pytest -q -m integration -k 'T13 or T17 or T32'`. Do not reset a counter to force a green result.

**Personal exercise:** predict the exact persisted state at four interruption points: before claim, after reservation, after target commit and after local confirmation. Run the lost-response exercise and identify the GET that resolves uncertainty. Explain how generation rejects an old worker's result and why it cannot retract an already sent packet.

**Three interview questions:** Why perform no HTTP inside a write transaction? Why can a GET failure never license a POST? What assumptions make the target effect idempotent?

**Mastery:** independently explain a safe recovery sequence and its limits; identify which database owns each fact; distinguish reserved attempts from actual packets and target effects.

## 6. Identity, authorisation and browser behaviour

**Component/purpose:** stable identities and server-side role/site checks prevent self-approval and cross-site access. Session CSRF, exact Origin and escaped templates protect local browser actions. Concepts: authentication vs authorisation, cookies, CSRF, XSS and safe error handling.

**Inspect/debug:** read `human`, `machine` and `login` in api.py, then inspect browser network statuses and cookie attributes without exporting cookie values. Run T22/T25/T26 and the browser test. Login and logout are real requests.

**Personal exercise:** use two sessions for the same operator subject and demonstrate that the second session cannot approve the first's proposal. Explain why a genuinely different reviewer succeeds. Show a request missing CSRF rejected even when its session is valid.

**Three interview questions:** Why compare subjects instead of session IDs? Why use HttpOnly and SameSite? Why is a writable local database outside the audit-integrity guarantee?

**Mastery:** explain each negative test's threat and server-side control; demonstrate failure without relying on hidden buttons; explain why this local identity design must change before production.

## 7. Business analysis and supplier judgment

**Component/purpose:** [the scope and decisions](implementation.md) connect technical choices to missing evidence, review accountability and operational continuity. Concepts: requirements, acceptance criteria, BPMN, risks, build-versus-buy and supplier assessment.

**Personal exercise:** draw a small BPMN process with source correction, an independent review lane and a target timeout exception. Write one business requirement, three observable acceptance criteria and one risk/mitigation. Compare building this lab with buying a real integration service: ask suppliers about stable IDs, reconciliation, versioning, source ownership, support and recovery responsibility.

**Three interview questions:** What operational decision does this app support? Which business problem remains outside scope? What evidence would you demand before buying a vendor integration?

**Mastery:** explain the scenario to a non-technical operator in three minutes, defend one build-versus-buy decision and honestly identify the organisational experience a portfolio cannot prove.

## First independent assessment

Do four short exercises before adding features: the missing-pallet SQL query, a new readiness-boundary test, two-session self-approval rejection and a narrated lost-response recovery. A second person should ask the questions and inspect the real results. Record help honestly. A test-suite pass or AI-generated explanation cannot substitute for this assessment.

## Release mastery rubric and common mistakes

Score each task independently: **0** cannot explain; **1** can follow a worked example with help; **2** predicts and performs it independently; **3** can diagnose an unexpected result and explain the tradeoff. Record AI help explicitly. No overall professional seniority is inferred. Aim for level 2 on every foundation before adding features.

| Exercise | Expected reasoning | Common mistake |
|---|---|---|
| Write a Python set-comparison function and one boundary test | Separate input facts from deterministic output; predict exact missing IDs | Treating UNKNOWN as an empty confirmed set; copying an AI answer without predicting output |
| Write SELECT/WHERE/JOIN/GROUP BY queries against a new run | Join current receipt membership; explain each key and parameter | Summing historical snapshots or interpolating user input into SQL |
| Send identical and changed event payloads using a small personal client | Distinguish 201/200/409 and stable receipt/version | Changing the event ID to hide a retry problem |
| Inject validation and HTTP failures | Schema errors reject before business writes; timeout is uncertain | Interpreting timeout as proof of no target effect |
| Explain approval/outbox transaction and simulate rollback | A single local COMMIT protects the pair, not the remote system | Claiming distributed atomicity across HTTP |
| Trace an expired lease and an overlapping worker | Generation fences old local results; target uniqueness handles repeated packets | Assuming a lease retracts a packet already sent |
| Perform GET-only manual reconciliation | Investigate an existing identifier; preserve counters and barrier | Force-send, new dispatch ID or counter reset to make the UI green |
| Demonstrate same subject in two sessions | Stable identity, role and site are different checks | Treating a new session or hidden button as separation of duties |
| Explain the public simulation | It is independent educational presentation, not backend execution | Showing simulated steps as real integration/test proof |

Debugging challenge: introduce one wrong missing-pallet JOIN or a deliberate expiry comparison defect on a personal branch. Predict the failing test, locate the defect with a debugger, repair it and explain the root cause without asking AI to write the fix. Keep the release branch unchanged.

Business analyst interview: What requirement prevents a reviewer override? Which stakeholder owns missing warehouse evidence? What measurable operational KPI would need a real pilot rather than this synthetic lab?

Integration engineer interview: Why GET after lost response? Who owns idempotency and payload conflict detection? What does fencing protect, and what cannot it protect?

Architecture interview: Why explicit SQL and one codebase here? What supplier contract would be needed for target reconciliation? When would SQLite or the local identity model cease to be appropriate?

Two-minute interview demonstration: show missing P003; apply a real source correction; explain evidence v4; demonstrate self-approval rejection and independent approval; show QUEUED before delivery; explain the target receipt and narrate the real lost-response recording. Finish by stating the synthetic, local and learning limitations. The genuine video and transcript are in the release documentation; a simulation is never substituted for this demonstration.
