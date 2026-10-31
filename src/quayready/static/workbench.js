"use strict";
const message = document.querySelector("#message");
const csrf = document.querySelector("#session")?.dataset.csrf;
const guidance = {
  SELF_APPROVAL:
    "Sign out and ask the independent reviewer to review this evidence version.",
  STALE_PROPOSAL:
    "Refresh and inspect the changed source evidence before requesting a new review.",
  PROPOSAL_EXPIRED:
    "This review window expired. Refresh the evidence before creating a new proposal.",
  CSRF_FAILED: "Refresh the page to obtain a current session token.",
  UNAUTHENTICATED: "Your session expired. Refresh and sign in again.",
  NOT_ELIGIBLE: "Resolve the source issues before requesting a review.",
  DATABASE_UNAVAILABLE:
    "The local database is temporarily unavailable. Retry with the same action key.",
};
function showError(error) {
  message.textContent = error.message;
  message.focus();
}
async function send(path, method, data, key) {
  const headers = { "Content-Type": "application/json" };
  if (csrf) headers["X-CSRF-Token"] = csrf;
  if (key) headers["Idempotency-Key"] = key;
  const response = await fetch(path, {
    method,
    headers,
    body: data ? JSON.stringify(data) : undefined,
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(`${error.code}: ${guidance[error.code] || error.message}`);
  }
  return response;
}
function action(element, callback) {
  element.addEventListener("click", async () => {
    element.disabled = true;
    element.setAttribute("aria-busy", "true");
    try {
      await callback();
      location.reload();
    } catch (error) {
      showError(error);
      element.disabled = false;
      element.removeAttribute("aria-busy");
    }
  });
}
const login = document.querySelector("#login");
if (login)
  login.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await send("/v1/session", "POST", {
        loginToken: document.querySelector("#token").value,
      });
      location.reload();
    } catch (error) {
      showError(error);
    }
  });
document.querySelectorAll("[data-propose]").forEach((button) =>
  action(button, () => {
    button.dataset.key ||= crypto.randomUUID();
    return send(
      `/v1/shipments/${button.dataset.propose}/proposals`,
      "POST",
      { expectedEvidenceVersion: Number(button.dataset.version) },
      button.dataset.key,
    );
  }),
);
document.querySelectorAll("[data-decision]").forEach((button) =>
  action(button, () => {
    button.dataset.key ||= crypto.randomUUID();
    const reason = button.closest(".actions").querySelector(".reason").value;
    return send(
      `/v1/proposals/${button.dataset.decision}/decision`,
      "POST",
      {
        decision: button.dataset.action,
        expectedEvidenceVersion: Number(button.dataset.version),
        reason,
      },
      button.dataset.key,
    );
  }),
);
const logout = document.querySelector("#logout");
if (logout) action(logout, () => send("/v1/session", "DELETE"));
document
  .querySelectorAll("[data-reconcile]")
  .forEach((button) =>
    action(button, () =>
      send(`/v1/deliveries/${button.dataset.reconcile}/reconcile`, "POST", {}),
    ),
  );
