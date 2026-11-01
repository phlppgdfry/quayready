"""Aggregate only executed evidence; fail closed if a mandatory local gate is missing."""

from __future__ import annotations

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    evidence = ROOT / "evidence/final-release"
    evidence.mkdir(exist_ok=True, parents=True)
    execution = json.loads((ROOT / "evidence/rc/execution.json").read_text())
    reproduction = json.loads((evidence / "clean-reproduction.json").read_text())
    coverage = json.loads((ROOT / "evidence/rc/response-coverage.json").read_text())

    def counts(path):
        suites = list(ET.parse(path).getroot().iter("testsuite"))
        return {
            key: sum(int(s.attrib.get(key, 0)) for s in suites)
            for key in ("tests", "failures", "errors", "skipped")
        }

    standard = counts(ROOT / "evidence/rc/pytest.xml")
    cold = counts(evidence / "cold-start.xml")
    changed = [
        p["artifact"]
        for p in execution["artifacts"]
        if hashlib.sha256((ROOT / p["artifact"]).read_bytes()).hexdigest() != p["sha256"]
    ]
    audit = json.loads((ROOT / "evidence/rc/dependency-audit.json").read_text())
    vulnerabilities = sum(len(p.get("vulns", [])) for p in audit["dependencies"])
    npm = json.loads((ROOT / "evidence/rc/npm-audit.json").read_text())["metadata"][
        "vulnerabilities"
    ]["total"]
    scans = []
    for name, args in [
        ("history", ["gitleaks", "git", "--log-opts=--all", "--redact", "--no-banner"]),
        (
            "workflow",
            ["actionlint", ".github/workflows/verify.yml", ".github/workflows/pages.yml.disabled"],
        ),
    ]:
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
        scans.append({"name": name, "command": " ".join(args), "exitCode": result.returncode})
        (evidence / (name + "-check.txt")).write_text(result.stdout + result.stderr)
    ready = (
        execution["result"] == "PASS"
        and reproduction["status"] == "LOCAL PASS"
        and not changed
        and not coverage["missing"]
        and not vulnerabilities
        and not npm
        and all(x["exitCode"] == 0 for x in scans)
        and standard["tests"] > 0
        and cold["tests"] > 0
        and all(standard[k] == cold[k] == 0 for k in ("failures", "errors", "skipped"))
    )
    manifest = {
        "verdict": "PORTFOLIO RELEASE READY" if ready else "NOT READY",
        "scope": "Independent synthetic local portfolio release; source remains private",
        "version": "0.2.0rc1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceCommit": execution["gitHeadAtExecution"],
        "testedInputFingerprint": execution["workingTreeIdentifier"],
        "sourceInputsChangedAfterVerification": changed,
        "runtime": {k: execution[k] for k in ("python", "sqlite", "platform", "dependencies")},
        "localVerification": {
            "status": "LOCAL PASS" if execution["result"] == "PASS" else "FAILED",
            "tests": standard,
            "commands": execution["checks"],
        },
        "cleanWheelReproduction": {
            "status": reproduction["status"],
            "tests": cold,
            "record": "clean-reproduction.json",
        },
        "contractResponses": coverage,
        "security": {
            "pythonKnownAdvisories": vulnerabilities,
            "npmKnownAdvisories": npm,
            "scans": scans,
            "historyCommits": subprocess.check_output(
                ["git", "rev-list", "--all"], cwd=ROOT, text=True
            ).splitlines(),
            "personalMetadata": "Git author and local-machine metadata retained in private source history; excluded from static export; owner consent required before source publicity",
        },
        "browser": {
            "engine": "Playwright Chromium with axe-core; actual reports under evidence/rc/accessibility and evidence/final-release/accessibility",
            "viewports": ["1440x1000", "1280x800", "768x1024", "390x844"],
            "screenshots": "evidence/rc/ui and evidence/rc/showcase",
            "recording": "evidence/rc/video/walkthrough.webm",
        },
        "siteBuild": json.loads((ROOT / "evidence/rc/checks/final-export.txt").read_text()),
        "hostedCI": "NOT EXECUTED",
        "publication": "NOT EXECUTED; no push, merge, Pages enablement, deployment, visibility change or Release",
        "limitations": [
            "assistant-operated same-Mac reproduction, not independent-human or Linux/hosted validation",
            "synthetic/mock integrations, no production/ROI/compliance claim",
            "personal mastery and screen-reader/Safari/Firefox user testing not observed",
        ],
        "closure": "No further feature development justified; obtain owner publication approvals and complete independent exercises",
    }
    (evidence / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(manifest["verdict"])
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
