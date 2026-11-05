# QuayReady — Logistics Operations & Automation Case Study

## Portfolio description

QuayReady is a self-directed, AI-assisted logistics integration case study connecting business processes, system integration, operational reliability, automation and technical governance. Three pallets are expected, two are observed: the application explains missing evidence, reconciles a corrected warehouse snapshot, requires a different reviewer to approve the current evidence version and transfers the request to an independent mock transport system.

## Business challenge and users

Operations staff, reviewers and integration owners need a shared explanation of incomplete or conflicting system evidence and uncertain delivery outcomes. The synthetic scenario makes ownership, readiness, human accountability and recovery visible. It illustrates a general coordination problem; it is not a claim about a real company's internal operations or measured savings.

## Solution and technical evidence

One Python/FastAPI application uses explicit SQL, SQLite, server-rendered HTML and minimal JavaScript. Deterministic requirements drive source reconciliation and review. Approval and a durable outbox commit atomically; local HTTP reaches a separately persisted mock-TMS. Stable identifiers, target idempotency, bounded retries, leases/fencing and receipt lookup address response loss and restart. Role/site controls and independent review enforce operational boundaries. Tests, API validation, genuine captures and hosted verification support the claims; the public site includes clearly labelled simulations plus approved guides.

## My contribution — suggested honest wording

“I developed QuayReady as a self-directed portfolio and learning case with extensive AI assistance across analysis, design, implementation, verification and presentation. I use it to explain business requirements, integration boundaries and failure recovery, and I am developing the ability to modify and troubleshoot the implementation independently.”

Use this wording only alongside the decisions and exercises you can personally explain. Do not claim unaided authorship, demonstrated mastery or professional client delivery. [Practical interview package](interview-package.md).

## Limits

Synthetic data, mock integration contracts and a local identity model; no real logistics deployment, physical departure authorisation, production certification, measured ROI or company endorsement. The public demonstration runs independently from the private Python backend. A real deployment requires process/supplier validation, supported identity, continuity, privacy, capacity and integration ownership.

## Showcase and recruiter pitch

**https://phlppgdfry.github.io/quayready/**

“QuayReady shows how I approach the gap between operational processes and software systems: make missing evidence understandable, require accountable review and handle integration failures without hiding uncertainty. It combines a practical logistics scenario, a working Python/SQL/API implementation and reproducible engineering evidence, supported by an accessible public case study.”
