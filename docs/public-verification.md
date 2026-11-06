# Verification evidence

This report describes real local execution. The interactive website is a browser-only educational simulation and does not run these tests. At the historical local final sign-off, hosted CI was NOT EXECUTED. Subsequently, Ubuntu run 41359218094 on source 2117b1330b48922c5cae208929cef60f65be7009 passed 196 tests and all mandatory workflow steps. The GitHub run and artifacts require repository access while source is private. A later hosted build records its own job origin and run reference; a recorded job does not imply overall workflow or deployment success.

## What is tested

The original E1 baseline passed 39 tests. The E2 engineering gate passed 73 tests before visual feature work. Its failure probes include slowly trickled headers/body, oversized and malformed responses, permanent HTTP errors, two overlapping worker processes, an injected SQLite COMMIT failure and authorised GET-only manual reconciliation.

The final local verification snapshot is appended below from the actual generated JUnit and execution record. It is not a coverage percentage, benchmark, production reliability measurement or penetration-test result. Runtime versions and the tested code fingerprint identify the evidence. Personal technical mastery and an independent person's cold start remain unverified.

## Guarantees demonstrated

Identical event replay has one business effect; conflicting replay guards the trusted source. Independent review is server-enforced against the current evidence version. Approval/outbox creation is atomic. Lost response and worker restart recover using the stable dispatch identifier. The independent target retains one effect. Manual reconciliation performs GET only and preserves budgets and barriers.

These guarantees apply under the synthetic target contract. They do not establish universal exactly-once processing, guaranteed eventual delivery, physical departure readiness or production compliance.

## Commands

```sh
python scripts/verify.py
python -m pip_audit --format json --output evidence/rc/dependency-audit.json
npm audit --omit=optional
python -m build --no-isolation
python scripts/build_showcase.py
```

The repository additionally runs Ruff, mypy, Bandit, dependency checks, real browser workflow tests and axe-core accessibility checks. Automated accessibility results supplement keyboard and screenshot review; they are not WCAG certification. Hosted CI is prepared with pinned revisions, minimal permissions and no deployment step.

[Execution snapshot](../evidence/rc/execution.json), [API contract](../src/quayready/contracts/openapi.json), [architecture](architecture.md) and [local reproduction](public-guide.md).
