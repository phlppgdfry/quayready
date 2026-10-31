# Security scope and reporting

QuayReady is a local synthetic-data learning lab, not a supported production system. Use loopback only. Never add real operational data or vendor credentials. Keep `.runs/`, generated tokens, cookies and databases out of Git and public assets.

For the currently private repository, report concerns directly to the repository owner through your existing private collaboration channel. Do not put credentials, exploitable details or private data in a public issue. There is no security-response SLA or professional penetration-test certification.

Before making source public, the owner must enable and verify GitHub private vulnerability reporting under Settings → Code security, then confirm the repository's Security → Report a vulnerability route works. That reporting route is a publication gate, not a feature claimed enabled here. If unavailable, ask the maintainer to establish a private contact route without posting technical exploit details publicly.

Only the current release candidate is maintained for this exercise. Dependency/advisory and static-analysis checks are evidence of checks performed, not proof that no vulnerability exists. Local administrators can alter SQLite files and audit protections; they are trusted. Plain loopback HTTP sessions are not a production identity design.
