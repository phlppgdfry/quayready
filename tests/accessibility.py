"""Automated checks supplement manual keyboard/screenshots; no certification claim."""

import json
import os
from pathlib import Path


def audit(page, name):
    source = Path("node_modules/axe-core/axe.min.js")
    if not source.exists():
        raise RuntimeError("Run npm ci --ignore-scripts before accessibility tests")
    page.evaluate(source.read_text())
    result = page.evaluate(
        """async () => await axe.run(document, {runOnly: {type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}})"""
    )
    report = {
        "surface": name,
        "url": page.url,
        "viewport": page.viewport_size,
        "engine": result["testEngine"],
        "violations": [
            {
                "id": v["id"],
                "impact": v["impact"],
                "help": v["help"],
                "targets": [n["target"] for n in v["nodes"]],
            }
            for v in result["violations"]
        ],
        "incomplete": [v["id"] for v in result["incomplete"]],
        "limitations": "Automated subset; no screen-reader user test or WCAG certification",
    }
    destination = Path(os.getenv("QUAYREADY_EVIDENCE", "evidence/rc/ui")).parent / "accessibility"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / (name + ".json")).write_text(json.dumps(report, indent=2) + "\n")
    assert report["violations"] == [], report["violations"]
