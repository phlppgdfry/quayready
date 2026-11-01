"""Reproducible local checks. Never prints credentials or reads private research."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def execution_context() -> dict[str, str | None]:
    hosted = os.getenv("GITHUB_ACTIONS") == "true"
    repository = os.getenv("GITHUB_REPOSITORY", "")
    run = os.getenv("GITHUB_RUN_ID", "")
    valid = bool(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repository)
    ) and bool(re.fullmatch(r"[0-9]{1,20}", run))
    return {
        "executionEnvironment": "GITHUB_ACTIONS" if hosted else "LOCAL",
        "hostedRunUrl": f"https://github.com/{repository}/actions/runs/{run}"
        if hosted and valid
        else None,
    }


def artifacts() -> list[Path]:
    paths = [
        ROOT / name
        for name in (
            "pyproject.toml",
            "requirements-dev.lock",
            "package.json",
            "package-lock.json",
            "README.md",
            "LICENSE",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            ".gitignore",
        )
    ]
    for directory in ("src", "tests", "scripts", "showcase", ".github", "docs"):
        paths.extend(
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.suffix != ".pyc"
            and not any(part.endswith(".egg-info") for part in p.parts)
        )
    return sorted(paths)


def main() -> int:
    os.chdir(ROOT)
    destination = ROOT / "evidence/rc"
    (destination / "checks").mkdir(parents=True, exist_ok=True)
    fingerprints = [
        {"artifact": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in artifacts()
    ]
    fingerprint = hashlib.sha256(json.dumps(fingerprints, sort_keys=True).encode()).hexdigest()
    head = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], capture_output=True, text=True)
    report = {
        **execution_context(),
        "executedAt": datetime.now(timezone.utc).isoformat(),
        "workingTreeIdentifier": fingerprint,
        "gitHeadAtExecution": head.stdout.strip() if head.returncode == 0 else None,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in (
                "fastapi",
                "starlette",
                "httpx",
                "httpx2",
                "uvicorn",
                "jsonschema",
                "jinja2",
                "pytest",
                "playwright",
                "ruff",
                "mypy",
                "setuptools",
                "openapi-spec-validator",
            )
        },
        "artifacts": fingerprints,
        "checks": [],
    }
    commands = [
        ("ruff", [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"]),
        ("format", [sys.executable, "-m", "ruff", "format", "--check", "src", "tests", "scripts"]),
        ("mypy", [sys.executable, "-m", "mypy", "src"]),
        ("dependencies", [sys.executable, "-m", "pip", "check"]),
        ("frontend-format", ["npm", "run", "check"]),
        ("bandit", [sys.executable, "-m", "bandit", "-r", "src", "-q"]),
        ("package", [sys.executable, "-m", "build", "--no-isolation"]),
        ("pytest", [sys.executable, "-m", "pytest", "-q", "--junitxml=evidence/rc/pytest.xml"]),
        ("showcase", [sys.executable, "scripts/build_showcase.py"]),
    ]
    success = True
    for name, command in commands:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "QUAYREADY_EVIDENCE": "evidence/rc/ui",
                "QUAYREADY_FULL_CONTRACT_GATE": "1",
            },
        )
        output = result.stdout + result.stderr
        (destination / "checks" / (name + ".txt")).write_text(output)
        report["checks"].append(
            {
                "name": name,
                "command": " ".join(
                    ["python" if command[0] == sys.executable else command[0], *command[1:]]
                ),
                "exitCode": result.returncode,
            }
        )
        print(f"{name}: exit {result.returncode}")
        success = success and result.returncode == 0
    # Materialise this generated artifact before validating links to it on a cold run.
    (destination / "execution.json").write_text(json.dumps(report, indent=2) + "\n")
    # Existing local run credentials are canaries: only match them, never emit them.
    secrets = []
    for config in (ROOT / ".runs").glob("*/config.json"):
        data = json.loads(config.read_text())
        secrets.extend(data.get("principals", {}))
        if data.get("workerKey"):
            secrets.append(data["workerKey"])
    candidates = [
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and not any(
            part
            in (
                ".git",
                ".runs",
                ".venv",
                "__pycache__",
                ".pytest_cache",
                ".mypy_cache",
                ".ruff_cache",
                "node_modules",
                "dist",
                "build",
            )
            or part.endswith(".egg-info")
            for part in p.relative_to(ROOT).parts
        )
    ]
    leaked = [
        str(p.relative_to(ROOT))
        for p in candidates
        if any(s.encode() in p.read_bytes() for s in secrets)
    ]
    broken = []
    for path in [ROOT / "README.md", *(ROOT / "docs").glob("*.md")]:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if (
                "://" not in target
                and not target.startswith("#")
                and not (path.parent / target.split("#")[0]).exists()
            ):
                broken.append(f"{path.relative_to(ROOT)}: {target}")
    report["checks"].extend(
        [
            {
                "name": "local-secret-canaries",
                "count": len(secrets),
                "leakedFiles": leaked,
                "exitCode": int(bool(leaked)),
            },
            {"name": "documentation-links", "broken": broken, "exitCode": int(bool(broken))},
        ]
    )
    changed = [
        p["artifact"]
        for p in fingerprints
        if hashlib.sha256((ROOT / p["artifact"]).read_bytes()).hexdigest() != p["sha256"]
    ]
    report["checks"].append(
        {"name": "tested-input-integrity", "changed": changed, "exitCode": int(bool(changed))}
    )
    success = success and not leaked and not broken and not changed
    report["result"] = "PASS" if success else "FAIL"
    (destination / "execution.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"canaries: {len(secrets)} checked; links: {len(broken)} broken; result: {report['result']}"
    )
    if success:
        # Export the JUST-recorded result, rather than shipping an earlier run's metadata.
        final = subprocess.run(
            [sys.executable, "scripts/build_showcase.py"], capture_output=True, text=True
        )
        (destination / "checks/final-export.txt").write_text(final.stdout + final.stderr)
        if final.returncode:
            report["result"] = "FAIL"
            success = False
        report["checks"].append(
            {
                "name": "final-evidence-export",
                "command": "python scripts/build_showcase.py",
                "exitCode": final.returncode,
            }
        )
        (destination / "execution.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
