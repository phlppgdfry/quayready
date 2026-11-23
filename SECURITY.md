# Security scope and reporting

QuayReady is a local synthetic-data learning lab, not a supported production system. Use loopback only. Never add real operational data or vendor credentials. Keep `.runs/`, generated tokens, cookies and databases out of Git and public assets.

Use GitHub's private vulnerability reporting: open [Report a vulnerability](https://github.com/phlppgdfry/quayready/security/advisories/new), or select Security → Report a vulnerability in this public repository. GitHub sign-in is required. Do not put credentials, exploitable details or personal data in a public issue. There is no security-response SLA or professional penetration-test certification.

The publication procedure enables and verifies private vulnerability reporting through GitHub's repository settings/API. If that route is unavailable, do not open a public exploit report; ask the maintainer to restore the private reporting route. No security advisory is created merely to test the form.

Only the current release candidate is maintained for this exercise. Dependency/advisory and static-analysis checks are evidence of checks performed, not proof that no vulnerability exists. Local administrators can alter SQLite files and audit protections; they are trusted. Plain loopback HTTP sessions are not a production identity design.
