# Private GitHub release-candidate handoff

> Historical checkpoint preserved. The owner subsequently authorised merge, static Pages publication and a private prerelease. See [current release closure](release-closure.md) for the final publication record.
## Verified scope

The owner authorised only a feature-branch push, draft PR, hosted verification and corrections. [Draft PR #1](https://github.com/phlppgdfry/quayready/pull/1) uses `work/ultimate-showcase-release` → `implementation/e1`. The previously unpushed branch was advanced from `2a94609` to include the final audit work at `2117b13`; no merge commit, default-branch push, force-push or history rewrite was used. The strategy repository is unchanged.

## Actual execution, not inferred success

- **LOCAL PASS:** fresh pre-push `python scripts/verify.py`, 196 tests, no failures/errors/skips; 108/108 declared API operation/method/status combinations schema-validated. Ruff, format, mypy, pip integrity, Bandit, package build, browser/axe, static export, credential canaries and documentation links pass. Current Python/npm advisory checks return zero known vulnerabilities.
- **HOSTED CI PASS:** [run 41359218094](https://github.com/phlppgdfry/quayready/actions/runs/41359218094), source `2117b1330b48922c5cae208929cef60f65be7009`, Ubuntu 24.04 / Python 3.13.18 / Node 24. All mandatory steps and both uploads succeeded. Downloaded JUnit records 196 tests with no failures/errors/skips. Execution metadata identifies `GITHUB_ACTIONS`, all verification exit codes are zero, and the static evidence records 108/108 response combinations. The Python advisory artifact has zero known vulnerabilities; the npm audit step also succeeded.
- **PRESERVED:** original local RC and cold-wheel manifests remain historical evidence. They are not rewritten to pretend they were hosted. [Hosted evidence summary](../evidence/publication/hosted-run.json) retains the immutable run/source/artifact identifiers. The PR's latest head checks are authoritative for subsequent documentation-only commits.

Commands actually executed include `python scripts/verify.py`, `pip-audit --format json`, `npm audit --json`, `gitleaks git --log-opts=--all --redact --no-banner`, `actionlint .github/workflows/verify.yml .github/workflows/pages.yml.disabled`, `git diff origin/implementation/e1...HEAD --check`, `gh run view`, and `gh run download`. Run details record each hosted step. Downloaded artifacts expire after 14 days; the concise committed summary preserves their IDs/digests without claiming permanent artifact availability.

## Confirmed artifact correction

The first successful hosted preview download contained 20 files: upload-artifact excludes hidden files by default, omitting the empty `.nojekyll` marker from the 21-file build. Internal links and runtime assets were intact. The final workflow explicitly includes hidden files **only inside the validated static allowlist directory**; execution/configuration directories remain excluded. Verify the corrected preview artifact on the final PR head rather than assuming that workflow success proves export completeness. No test or contract was weakened.

## Safety and provenance

The complete relevant pre-push history (five commits) was scanned with no detected secrets. Review of tracked paths, package contents and the public allowlist found no databases, environment credentials, private research or unrelated code. Original E1 contracts and later modifications are documented in [provenance](provenance.md); code/assets are independently authored with AI assistance, under MIT, with pinned third-party dependencies retaining their own licenses. No third-party imagery or copied vendor branding is included.

Known personal metadata is intentional repository-owner authorship plus local machine/path fields in PRIVATE raw evidence. These are not credentials and are excluded from the static export. Public source visibility still requires separate privacy review. This is a scoped publication review, not proof that automated scanners detect every possible exposure or a professional penetration test.

GitHub reports the Pro plan, included Actions usage and zero net billed Actions amount at the check. Only standard Ubuntu runners are used; no paid runner or billing settings were enabled. Do not raise budgets to resolve any future quota failure.

## Website and publication decision

The independent static export contains 21 files and needs no Python backend, secret or server session. A local production export with `--public-url https://phlppgdfry.github.io/quayready/` validates canonical/social URLs and all internal links. Browser tests exercise the repository subpath, workflow/reset, all failure scenarios, selectable architecture, no-JavaScript fallback, real media/captions and 1440/1280/768/390-pixel layouts. Simulations remain labelled; app screenshots/video are genuine execution captures. Automated axe checks and manual keyboard/visual review do not certify WCAG; Safari/Firefox and screen-reader user testing remain unexecuted.

Prefer **Pages from the existing private application repository**, exporting only the allowlisted static folder. Pro supports this without exposing source; the resulting website would be public. A separate public static repository is an optional alternative, not required for compatibility. See the [exact publication checklist and disabled workflow](publication.md). Required-reviewer protection is unavailable for private Pro repositories; owner-only dispatch/reruns plus branch restrictions are the prepared proportionate alternative, not independent approval.

No merge, Pages enablement, deployment, visibility change, tag, Release or package publication occurred. Keep `0.2.0rc1`; the local/hosted software candidate is ready for review, not production certification or a claim of owner mastery.

## Professional review and stop decision

For a hiring manager, the case study connects a concrete discrepancy to inspectable evidence and honest outcomes. For an operations manager, missing evidence, independent review and uncertain delivery have distinct explanations. For an integration engineer, version binding, transaction boundaries, target persistence, idempotency, fencing and recovery are executable and tested. No additional feature or engineering blocker was identified. Independent owner exercises and another person's reproduction remain unverified; complete [the interview package](interview-package.md) without claiming AI-generated work proves personal skill.

Further feature development is not justified. Next actions are review, independently observed learning and separately approved public publication decisions.
