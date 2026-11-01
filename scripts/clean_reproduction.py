"""Full isolated-wheel reproduction; no existing application database is used."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    os.chdir(ROOT)
    run = ROOT / ".runs" / ("final-cold-start-" + str(time.time_ns()))
    run.mkdir(parents=True)
    evidence = ROOT / "evidence/final-release"
    evidence.mkdir(parents=True, exist_ok=True)
    steps = []

    def command(name, args, env=None):
        result = subprocess.run(args, capture_output=True, text=True, env=env)
        (run / (name + ".log")).write_text(result.stdout + result.stderr)
        steps.append(
            {"name": name, "command": " ".join(str(a) for a in args), "exitCode": result.returncode}
        )
        print(f"{name}: exit {result.returncode}", flush=True)
        if result.returncode:
            raise RuntimeError(f"{name} failed; inspect isolated log {run.name}/{name}.log")
        return result.stdout

    try:
        command("create-venv", [sys.executable, "-m", "venv", str(run / "venv")])
        python = run / "venv/bin/python"
        command(
            "install-lock", [str(python), "-m", "pip", "install", "-r", "requirements-dev.lock"]
        )
        command("dependency-integrity", [str(python), "-m", "pip", "check"])
        command(
            "build-wheel",
            [
                str(python),
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(run / "wheel"),
            ],
        )
        wheel = next((run / "wheel").glob("*.whl"))
        command(
            "install-wheel",
            [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
        )
        loaded = command(
            "verify-wheel-import",
            [
                str(python),
                "-c",
                "import json,quayready,sys; from pathlib import Path; p=Path(quayready.__file__).resolve(); assert p.is_relative_to(Path(sys.prefix)); print(json.dumps({'module':str(p),'prefix':sys.prefix}))",
            ],
        )
        command("frontend-lock", ["npm", "ci", "--ignore-scripts"])
        env = {
            **os.environ,
            "QUAYREADY_EVIDENCE": "evidence/final-release/ui",
            "QUAYREADY_FULL_CONTRACT_GATE": "1",
        }
        command(
            "complete-cold-suite",
            [str(python), "-m", "pytest", "-q", "--junitxml=evidence/final-release/cold-start.xml"],
            env,
        )
        status = "LOCAL PASS"
    except RuntimeError as error:
        status = "FAILED"
        print(str(error), flush=True)
    report = {
        "status": status,
        "executedAt": datetime.now(timezone.utc).isoformat(),
        "sourceCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "sourceWorkingTree": "See final execution fingerprint; audit changes may be uncommitted at execution",
        "isolatedRun": str(run.relative_to(ROOT)),
        "steps": steps,
        "wheelSha256": hashlib.sha256(wheel.read_bytes()).hexdigest()
        if "wheel" in locals()
        else None,
        "wheelImport": json.loads(loaded) if "loaded" in locals() else None,
        "databaseIsolation": "Every pytest fixture initializes new file-backed app/target databases in a new temporary directory",
        "workflowCoverage": "Full suite includes synthetic source seed/correction, independent approval, outbox, target receipt, actual process restart, response loss, retries and browser flows",
        "limitations": "Same Mac and assistant-operated; not independent-human or Linux/hosted verification",
    }
    (evidence / "clean-reproduction.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if status == "LOCAL PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
