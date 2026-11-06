# Working on QuayReady

Keep changes small, synthetic and traceable to a demonstrated problem. Start from a clean branch; preserve existing evidence and migration 001. Add a numbered migration for schema changes, with rollback/fix-forward reasoning. Never reset outbox budgets or bypass the independent-review/version checks to make a demonstration pass.

Install the Python lock and `npm ci --ignore-scripts`, then run `python scripts/verify.py` inside the virtual environment. Browser binaries must be installed. This command starts only owned local test processes. Network advisory checks are separate; see the README. Never upload `.runs/` or real credentials in bug reports.

Document the trigger, expected/actual behaviour and a synthetic reproduction. A new dependency needs a concrete reason, pin, license/advisory review and reproducibility check. The static showcase is presentation-only: do not import backend authority into its simulation or label simulated animation as a test execution.

An owner reviews publication, release and deployment separately. No deployment workflow is active.
