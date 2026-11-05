# Approved static publication mechanism

The owner authorised PR #1 merge into `implementation/e1`, public static Pages publication and a private GitHub prerelease. Application source and the separate strategy repository remain private. No source-visibility change, public repository, package publishing, paid infrastructure or history rewrite is part of this release.

## Hosting and access

Public showcase: **https://phlppgdfry.github.io/quayready/**. GitHub Pro supports Pages from this private repository without a new hosting service. The website is public; source code, issues, raw evidence and the GitHub Release require repository access. No public source button is displayed. [GitHub Pages availability](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages) and [deployment workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) describe this route. GitHub may retain visitor IPs for security; the showcase adds no tracking.

## Committed deployment procedure

1. Complete `python scripts/verify.py`, advisory/history checks and clean-package installation. Verify the exact PR head and all hosted checks before a normal merge, preserving the source branch.
2. Configure Pages with `build_type=workflow`. Configure the `github-pages` environment with custom deployment branch policy allowing only `implementation/e1`.
3. Run [pages.yml](../.github/workflows/pages.yml) manually on the verified target commit. Build requires the owner as both original/rerun actor and the exact target branch. Checkout does not persist credentials. Verification/build jobs have read access only; deploy alone has `pages:write` and `id-token:write`.
4. The workflow runs the complete existing suite and advisory checks, retrieves Pages metadata with `enablement=false`, exports with the actual HTTPS URL, uploads only `.runs/site/quayready/`, then deploys through the restricted environment. No deployment branch or backend server is required.
5. Download and inspect the Pages artifact, compare its files with unauthenticated HTTPS responses, exercise the public workflow/failure/reset/architecture/mobile UI and inspect the actual deployment commit. A successful build alone is insufficient.
6. Create annotated tag `v0.2.0-rc.1` at the verified release commit, publish a **private prerelease** with the public URL, run references and closure evidence, and verify tag/release remotely. Retain version `0.2.0rc1`; this is portfolio acceptance, not production certification.

The plan supports private environments/branch restrictions but not required deployment reviewers on private Pro repositories. Owner dispatch and branch restrictions are not independent review or protection against an authorised workflow editor. No platform reviewer gate is falsely claimed and no existing protection is disabled. Do not raise billing budgets to work around quota limits.

## Public data boundary

The exporter uses a fixed allowlist: static HTML/CSS/JavaScript, approved neutral technical guides and OpenAPI, original diagrams/social art/favicon, genuine synthetic screenshots/video/captions, MIT license and a reduced verification snapshot. It rejects unexpected stale output. `.nojekyll` is retained. Relative assets work under `/quayready/`; the production export sets absolute canonical/social metadata.

Never upload the repository root, `.git`, `.runs` credentials/configuration, databases, Python source, raw JUnit/logs, research, source maps or private machine metadata. Known author/local-path metadata remains in PRIVATE history and is absent from the reduced public snapshot. Source visibility is a separate privacy decision outside this release.

## Final evidence and maintenance

[Release closure](release-closure.md) links the private prerelease whose `closure-evidence.json` attachment records actual commit/run/tag/HTTP/browser results. Earlier local and hosted audit documents are historical checkpoints and remain intact. The Actions/deployments tabs are authoritative for the latest execution. Re-run the manual workflow on a newly verified target commit when intentionally updating the website; never dispatch an unreviewed source branch.
