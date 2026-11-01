# Publication decision — nothing deployed

The private application and strategy repositories remain private. No push, merge, Pages setting, public repository or GitHub Release is authorised by this local consolidation assignment. The working branch is a local release candidate; an informed owner decision is required for each publication action below.

## Availability checked, not enabled

A read-only GitHub account query returned the **Pro** plan. [GitHub's current Pages documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages) says Pro supports Pages from private repositories. This does not make the resulting website private: restricted private-site access requires an eligible Enterprise Cloud organisation, per [Pages access-control documentation](https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/changing-the-visibility-of-your-github-pages-site). Reviewed 2026-10-31, Brussels time.

A public static Pages site from the existing private application repository is therefore technically suitable without changing source visibility. Only the allowlisted static build would be deployed. Repository source and research must not be uploaded. GitHub may log visitor IP addresses for security even though the showcase adds no tracking.

An optional separate public static repository is also possible, but is not necessary for account compatibility. Its remote creation is a separate approval. No remote or local nested Git repository has been created for it.

## Decision sequence and exact scope

1. **Approve pushing the existing local release branch only:** `git push -u origin release/final-portfolio-signoff`. This would trigger the prepared read-only verification workflow; it does not publish a site or Release. Inspect the actual run and fix any Linux/hosted compatibility issue before proceeding. Hosted success is currently UNVERIFIED.
2. **Review source access independently.** Keep `quayready` private unless the owner explicitly authorises a visibility change. Do not add a public GitHub button to the showcase until source is public and the URL has been verified.
3. **Approve public static exposure and its chosen URL.** Recommended existing-repository project path, if approved: `https://phlppgdfry.github.io/quayready/`. This is a proposed address, not a deployed link. Run `python scripts/build_showcase.py --public-url APPROVED_HTTPS_URL` to generate correct absolute canonical/social metadata. Review the output manifest, video, public evidence and absence of research/credentials.
4. **Prepare deployment only after that approval.** In repository Settings → Pages choose GitHub Actions; add a separately reviewed workflow that uploads only `.runs/site/quayready/` and deploys through a protected `github-pages` environment with the minimum `pages:write` and `id-token:write` permissions. The existing verify workflow deliberately has no such permissions or deployment job. Require owner environment approval. Run and verify the actual public path, asset URLs, refresh navigation, captions and mobile controls before advertising it.
5. **Optional public static-only repository:** approve its name/creation separately, export only the built output to an empty staging folder, inspect every file, initialise its local repository and push only after permission. Enable Pages on its static root/approved workflow. Do not copy `.git`, Python source, `.runs` configs, databases, strategy or the whole app repository.
6. **Release publication is another decision.** After hosted CI and public artifact review, approve a tag and GitHub Release using `docs/release-notes.md`. Do not publish this local RC as production-ready. No tag or release has been created.

## Metadata prepared, not applied

Description: `Synthetic cross-dock readiness, independent review and reliable HTTP integration — a verified Python/FastAPI/SQLite lab.`

Suggested topics: `python`, `fastapi`, `sqlite`, `logistics`, `system-integration`, `transactional-outbox`, `idempotency`, `software-architecture`, `portfolio`.

Website field: set only after actual deployment validation. Suggested pin: one of the owner's first three repositories, described as an independent integration/operations case study. No profile or unrelated repository has been changed.

Before public source release, confirm a private vulnerability-reporting route, retain MIT/dependency notices, inspect source history for secrets, verify the actual hosted run, update CI references honestly and review the personal-learning disclaimer. Second-person cold start and owner mastery remain human gates, not checks an assistant can claim passed.

## Exact prepared deployment template

[pages.yml.disabled](../.github/workflows/pages.yml.disabled) is complete but ignored by GitHub. After separate approval: review the actual hosted verification result; authorise the required merge to the selected/default release branch; protect the github-pages environment with an owner reviewer; rename the template to pages.yml in an approved commit; choose Actions under Pages settings; run workflow_dispatch on the approved commit. configure-pages explicitly has enablement=false. Only the deploy job has pages:write/id-token:write. The build verifies tests/advisories and uploads only the allowlisted static folder. Do not enable, push, merge, dispatch or deploy automatically.

Source-publication review: existing Git author email and local machine metadata in raw JUnit/build evidence are personal metadata, not credentials. They are not exported by the static allowlist. Keep source private as instructed; inspect/consent to those fields before any separate visibility change. Do not rewrite published history under this audit. Proposed RC tag after approval: v0.2.0-rc.1; not v1.0.0 while hosting/human sign-off is unexecuted.
