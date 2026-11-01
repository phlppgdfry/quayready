"use strict";
// Presentation-only state machine. No backend calls, credentials or decision authority.
const steps = [
  [
    "Order created",
    "A synthetic transport order expects three pallet identifiers.",
    0,
    "Needs review",
    "Not requested",
    "Not requested",
  ],
  [
    "Expected pallets registered",
    "P001, P002 and P003 form the immutable expected set.",
    0,
    "Needs review",
    "Not requested",
    "Not requested",
  ],
  [
    "Warehouse evidence received",
    "The current complete snapshot contains only P001 and P002.",
    2,
    "Needs review",
    "Not requested",
    "Not requested",
  ],
  [
    "Missing pallet explained",
    "P003 has no warehouse evidence. The Warehouse owner must correct the source; a reviewer cannot override this.",
    2,
    "Needs review",
    "Unavailable",
    "Not requested",
  ],
  [
    "Corrected snapshot received",
    "A higher complete warehouse snapshot is applied and readiness recalculates in the same transaction. Old receipts remain history.",
    3,
    "Eligible for review",
    "Not requested",
    "Not requested",
  ],
  [
    "Readiness recalculated",
    "With fresh document evidence, no hard holds and time before cutoff, the deterministic result is eligible for review.",
    3,
    "Eligible for review",
    "Not requested",
    "Not requested",
  ],
  [
    "Version-bound proposal created",
    "DEMO-OPERATOR requests review of evidence v4. A source change or expiry invalidates that proposal.",
    3,
    "Eligible for review",
    "Pending review · v4",
    "Not requested",
  ],
  [
    "Independent reviewer approves",
    "DEMO-REVIEWER checks the same current evidence version. Approval and outbox commit atomically.",
    3,
    "Eligible for review",
    "Approved · v4",
    "Queued",
  ],
  [
    "Request durably queued",
    "Approval and immutable outbox are committed together. No network call happens inside this write transaction.",
    3,
    "Eligible for review",
    "Approved · v4",
    "Queued",
  ],
  [
    "Mock-TMS receives request",
    "A worker sends the stable dispatch ID over HTTP. The target commits its unique effect in its own database.",
    3,
    "Eligible for review",
    "Approved · v4",
    "Sending · receipt not yet recorded",
  ],
  [
    "Independent receipt confirmed",
    "The app records the matching target receipt. One target effect exists. This remains a dispatch-review request, not a physical departure authorisation.",
    3,
    "Eligible for review",
    "Approved · v4",
    "Confirmed",
  ],
];
let step = 0;
const byId = (id) => document.getElementById(id);
function renderStep(announce = true) {
  const [title, description, count, readiness, review, delivery] = steps[step];
  byId("sim-step").textContent = `Step ${step + 1} of ${steps.length}`;
  byId("sim-title").textContent = title;
  byId("sim-description").textContent = description;
  byId("sim-readiness").textContent = readiness;
  byId("sim-review").textContent = review;
  byId("sim-delivery").textContent = delivery;
  document.querySelectorAll("#sim-pallets li").forEach((li, index) => {
    li.dataset.state =
      index < count ? "observed" : count === 2 ? "missing" : "expected";
    li.querySelector("span").textContent =
      index < count ? "Observed" : count === 2 ? "Missing" : "Expected";
  });
  byId("sim-back").disabled = step === 0;
  byId("sim-next").disabled = step === steps.length - 1;
  document.querySelectorAll(".workflow-steps li").forEach((li, index) => {
    if (index === step) li.setAttribute("aria-current", "step");
    else li.removeAttribute("aria-current");
  });
  if (announce)
    byId("sim-announcement").textContent = `${title}. ${description}`;
}
byId("sim-next").addEventListener("click", () => {
  if (step < steps.length - 1) step++;
  renderStep();
});
byId("sim-back").addEventListener("click", () => {
  if (step > 0) step--;
  renderStep();
});
byId("sim-reset").addEventListener("click", () => {
  step = 0;
  renderStep();
});
renderStep(false);
const incidents = {
  lost: {
    events: [
      "Request sent with a stable dispatch ID.",
      "Target commits one durable effect.",
      "Client loses the response; outcome is unknown.",
      "After restart, GET finds the original receipt.",
      "App confirms historical delivery; target effect count stays one.",
    ],
    technical:
      "Reserve → COMMIT → HTTP → fenced result. An uncertain POST leads to GET of the same identifier. Target uniqueness constrains effects, even when delivery repeats.",
  },
  duplicate: {
    events: [
      "Source sends an event with a stable event ID.",
      "Receipt and projection commit once.",
      "Identical payload arrives again.",
      "Original receipt is returned; no version bump or freshness renewal.",
    ],
    technical:
      "Identity scope is site + source + event ID. Canonical hashes normalise object/pallet ordering and equivalent timestamps. Delivery replay is distinct from new evidence.",
  },
  conflict: {
    events: [
      "A trusted event has already been committed.",
      "The same event ID arrives with changed content.",
      "API returns 409 and commits a source-conflict guard.",
      "Original receipt stays immutable; a valid revision above the conflict floor is needed.",
    ],
    technical:
      "Returning a conflict must not roll back its safety guard. The trusted original scope is used, not a forged shipment field in the changed payload.",
  },
  stale: {
    events: [
      "Operator creates a proposal for evidence v4.",
      "New relevant source evidence advances the aggregate version.",
      "Old proposal is invalidated.",
      "A stale decision returns 409; no new dispatch is created.",
    ],
    technical:
      "Decision validation and outbox creation share BEGIN IMMEDIATE. A POST reservation before an evidence change is already uncertain; further automatic work becomes lookup-only.",
  },
  self: {
    events: [
      "Operator requests a review.",
      "The same subject signs in with another session or role.",
      "Server rejects self-approval with 403.",
      "A genuinely different stable subject must review current evidence.",
    ],
    technical:
      "Separation compares stable subjects, not session IDs or visible buttons. Role membership alone cannot bypass the subject check.",
  },
  timeout: {
    events: [
      "A worker reserves POST before HTTP.",
      "No valid response arrives within the bounded deadline.",
      "Outcome remains unknown; retry waits persist.",
      "GET is attempted first; only 404 plus still-valid evidence can permit POST retry.",
      "Exhausted automatic budgets stop in manual review.",
    ],
    technical:
      "Three reserved POSTs and three automatic lookups maximum. Failed lookup never licenses POST. Explicit manual investigation is GET-only and preserves budgets and dispatch barriers.",
  },
  restart: {
    events: [
      "Worker reserves a lease generation and consumes an attempt.",
      "Process exits before recording a result.",
      "A new worker recovers the expired lease with a higher generation.",
      "Lookup checks for the original target receipt before any resend.",
      "A late result from the old generation cannot overwrite current state.",
    ],
    technical:
      "Leases coordinate work; fencing rejects stale local results. Neither can retract a packet already sent. Idempotency must also be enforced by the target.",
  },
};
byId("incident").addEventListener("change", (e) => {
  const incident = incidents[e.target.value];
  byId("incident-timeline").replaceChildren(
    ...incident.events.map((text) => {
      const li = document.createElement("li");
      li.textContent = text;
      return li;
    }),
  );
  byId("incident-technical").textContent = incident.technical;
});
const components = {
  sources: [
    "Synthetic sources",
    "Inputs: synthetic order, complete warehouse/document snapshots. Outputs: authenticated JSON events. Owns simulated observations and source revisions, not app readiness. Duplicate delivery is expected; conflicting content is guarded.",
  ],
  api: [
    "FastAPI ingestion",
    "Inputs: authenticated JSON. Outputs: strict receipts or structured errors. Owns request validation, source/site boundaries and transactional use-case calls. Invalid schema and unauthorised writes have no business effects.",
  ],
  domain: [
    "Domain validation",
    "Inputs: current expected/observed sets, source facts and clock. Outputs: readiness and explicit reasons. Owns deterministic rules, not persistence. Missing, expired or unknown evidence never becomes a guessed success.",
  ],
  review: [
    "Operator / reviewer workbench",
    "Inputs: real persisted evidence and human actions. Outputs: version-bound proposals and independent decisions. Uses server-rendered Jinja, sessions and CSRF. Stale/self approval is rejected on the server.",
  ],
  db: [
    "App SQLite persistence",
    "Inputs: parameterised transactional writes. Outputs: immutable receipts, current snapshots and audit. Owns app facts with foreign keys, uniqueness and triggers. A failed commit rolls back the whole local operation.",
  ],
  outbox: [
    "Transactional outbox",
    "Inputs: approved decision in the same transaction. Outputs: immutable request and durable delivery metadata. Owns dispatch identity, budgets, leases and unresolved barrier. No approval can commit without its outbox.",
  ],
  worker: [
    "Worker / HTTP boundary",
    "Inputs: due outbox rows. Outputs: bounded POST/GET and fenced results. Owns reservation and recovery protocol. No HTTP occurs in an open app transaction; uncertain results are looked up first.",
  ],
  target: [
    "Independent mock-TMS",
    "Inputs: authenticated HTTP dispatch/lookup. Outputs: persistent target receipts. Owns unique target effects in target.db, separately from app.db. A commit can succeed while its response is lost; repeat ID/hash returns the original receipt.",
  ],
};
document.querySelectorAll("[data-component]").forEach((button) =>
  button.addEventListener("click", () => {
    document
      .querySelectorAll("[data-component]")
      .forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
    const [title, text] = components[button.dataset.component];
    const h = document.createElement("h3");
    h.textContent = title;
    const p = document.createElement("p");
    p.textContent = text;
    byId("component-panel").replaceChildren(h, p);
  }),
);
fetch("assets/verification.json")
  .then((r) => {
    if (!r.ok) throw new Error("Evidence unavailable");
    return r.json();
  })
  .then((data) => {
    if (data.tests?.passed !== undefined)
      document.querySelector("[data-test-count]").textContent =
        `${data.tests.passed} passed`;
    byId("verification-date").textContent =
      data.hostedCI === "NOT_RUN"
        ? `Local verification snapshot: ${data.executedAt}. Hosted CI: not executed for this snapshot.`
        : `GitHub Actions job snapshot: ${data.executedAt}. A recorded job does not establish the overall workflow or deployment outcome.`;
  })
  .catch(() => {
    byId("verification-date").textContent =
      "Open the bundled evidence report for the recorded local verification. Hosted CI remains unverified.";
  });

document.documentElement.classList.add("interactive");
