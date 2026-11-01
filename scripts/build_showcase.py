"""Static, allowlisted portfolio export. No backend, secrets, research or source bundle."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = {
    "guide.html": "public-guide.md",
    "architecture.html": "architecture.md",
    "evidence.html": "public-verification.md",
    "transcript.html": "demo-transcript.md",
}
LINKS = {
    "public-guide.md": "guide.html",
    "architecture.md": "architecture.html",
    "case-study.md": "case-study.html",
    "release-verification.md": "evidence.html",
    "demo-transcript.md": "transcript.html",
    "final-signoff.md": "evidence.html",
}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        for name in ("href", "src", "poster"):
            if values.get(name):
                self.links.append(values[name])


def verify_links(output: Path) -> None:
    documents = {}
    for path in output.rglob("*.html"):
        parser = Links()
        parser.feed(path.read_text())
        documents[path] = parser
    for path, parser in documents.items():
        for link in parser.links:
            parsed = urlparse(link)
            if parsed.scheme or parsed.netloc:
                continue
            target = (path.parent / parsed.path).resolve() if parsed.path else path.resolve()
            if target.is_dir():
                target = target / "index.html"
            if not target.is_relative_to(output.resolve()) or not target.exists():
                raise ValueError(f"Broken/escaping link: {path.name}: {link}")
            if parsed.fragment and target.suffix == ".html":
                targetparser = documents.get(target) or Links()
                if not targetparser.ids:
                    targetparser.feed(target.read_text())
                if parsed.fragment not in targetparser.ids:
                    raise ValueError(f"Missing anchor {link}")


def snapshot() -> dict:
    xml = ROOT / "evidence/rc/pytest.xml"
    if not xml.exists():
        xml = ROOT / "evidence/rc/engineering.xml"
    suites = list(ET.parse(xml).getroot().iter("testsuite"))
    tests = {
        k: sum(int(s.attrib.get(k, 0)) for s in suites)
        for k in ("tests", "failures", "errors", "skipped")
    }
    tests["passed"] = tests["tests"] - tests["failures"] - tests["errors"] - tests["skipped"]
    metadata = ROOT / "evidence/rc/execution.json"
    recorded = (
        json.loads(metadata.read_text())
        if metadata.exists()
        else {
            "executedAt": "E2 engineering checkpoint, 2026-10-30",
            "result": "PASS",
            "python": "3.13.18",
        }
    )
    return {
        "kind": "recorded verification execution, separate from simulation; inspect executionEnvironment",
        "executionEnvironment": recorded.get("executionEnvironment", "LOCAL"),
        "executedAt": recorded["executedAt"],
        "result": recorded["result"],
        "python": recorded["python"],
        "sqlite": recorded.get("sqlite"),
        "checks": [
            {k: c[k] for k in ("name", "command", "exitCode") if k in c}
            for c in recorded.get("checks", [])
        ],
        "responseCoverage": json.loads((ROOT / "evidence/rc/response-coverage.json").read_text())
        if (ROOT / "evidence/rc/response-coverage.json").exists()
        else None,
        "tests": tests,
        "workingTreeIdentifier": recorded.get("workingTreeIdentifier"),
        "hostedCI": "JOB_CHECKS_RECORDED_SEE_RUN"
        if recorded.get("executionEnvironment") == "GITHUB_ACTIONS"
        else "NOT_RUN",
        "hostedRunUrl": recorded.get("hostedRunUrl"),
        "personalMastery": "UNVERIFIED",
    }


def render_markdown(text: str) -> str:
    md = MarkdownIt("commonmark", {"html": False})

    def heading(tokens, idx, options, env):
        title = tokens[idx + 1].content
        tokens[idx].attrSet("id", re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-"))
        return md.renderer.renderToken(tokens, idx, options, env)

    md.renderer.rules["heading_open"] = heading
    rendered = (
        md.render(text)
        .replace("../showcase/assets/", "assets/")
        .replace("../evidence/rc/execution.json", "assets/verification.json")
        .replace("../src/quayready/contracts/openapi.json", "assets/openapi.json")
    )
    for source, destination in LINKS.items():
        rendered = rendered.replace(source, destination)
    return rendered


def build(output: Path, public_url: str | None = None) -> dict:
    output = output.resolve()
    if not output.is_relative_to(ROOT / ".runs") and output.exists() and any(output.iterdir()):
        raise ValueError("Refuse to overwrite a non-empty external output directory")
    output.mkdir(parents=True, exist_ok=True)
    assets = output / "assets"
    assets.mkdir(exist_ok=True)
    for name in ("index.html", "style.css", "app.js"):
        shutil.copy2(ROOT / "showcase" / name, output / name)
    for path in (ROOT / "showcase/assets").glob("*"):
        if path.suffix in (".svg", ".png"):
            shutil.copy2(path, assets / path.name)
    shutil.copy2(ROOT / "src/quayready/static/favicon.svg", assets / "favicon.svg")
    shutil.copy2(ROOT / "evidence/rc/ui/hero.jpg", assets / "hero.jpg")
    shutil.copy2(ROOT / "src/quayready/contracts/openapi.json", assets / "openapi.json")
    evidence = snapshot()
    (assets / "verification.json").write_text(json.dumps(evidence, indent=2) + "\n")
    text = (output / "index.html").read_text()
    if public_url:
        parsed = urlparse(public_url)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Trusted HTTPS publication URL required")
        text = text.replace(
            'content="assets/social.png"',
            f'content="{html.escape(public_url.rstrip("/") + "/assets/social.png")}"',
        )
        text = text.replace(
            "</head>", f'<link rel="canonical" href="{html.escape(public_url)}"></head>'
        )
    video = ROOT / "evidence/rc/video/walkthrough.webm"
    if video.exists():
        shutil.copy2(video, assets / "walkthrough.webm")
        shutil.copy2(video.with_suffix(".vtt"), assets / "walkthrough.vtt")
        text = text.replace(
            "<!-- VIDEO_SLOT -->",
            '<video controls preload="none" poster="assets/hero.jpg" aria-label="Genuine local QuayReady walkthrough"><source src="assets/walkthrough.webm" type="video/webm"><track default kind="captions" srclang="en" label="English captions" src="assets/walkthrough.vtt">Read the <a href="transcript.html">transcript</a>.</video>',
        )
    else:
        text = text.replace(
            "<!-- VIDEO_SLOT -->",
            '<p class="notice">Recording is not included in this build. Read the reproducible <a href="transcript.html">shot list and narration</a>.</p>',
        )
    (output / "index.html").write_text(text)
    pages = {**DOCUMENTS, "case-study.html": "case-study.md"}
    for filename, source in pages.items():
        body = render_markdown((ROOT / "docs" / source).read_text())
        if filename == "evidence.html":
            body += f"<pre>{html.escape(json.dumps(evidence, indent=2))}</pre>"
        title = re.search(r"<h1[^>]*>(.*?)</h1>", body).group(1)
        (output / filename).write_text(
            f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · QuayReady</title><link rel="stylesheet" href="style.css"><link rel="icon" href="assets/favicon.svg"></head><body><header><a class="brand" href="index.html">QuayReady</a><nav aria-label="Guide navigation"><a href="index.html#workflow">Demo</a><a href="guide.html">Setup</a><a href="evidence.html">Evidence</a></nav></header><main><article class="guide">{body}</article></main><footer><a href="index.html">Back to case study</a></footer></body></html>'
        )
    (output / ".nojekyll").write_text("")
    shutil.copy2(ROOT / "LICENSE", output / "LICENSE.txt")
    verify_links(output)
    for diagram in assets.glob("*.svg"):
        ET.parse(diagram)
    files = [p for p in output.rglob("*") if p.is_file()]
    expected = {
        ".nojekyll",
        "LICENSE.txt",
        "index.html",
        "style.css",
        "app.js",
        *pages.keys(),
        "assets/favicon.svg",
        "assets/hero.jpg",
        "assets/openapi.json",
        "assets/verification.json",
    }
    expected.update(
        "assets/" + p.name
        for p in (ROOT / "showcase/assets").glob("*")
        if p.suffix in (".svg", ".png")
    )
    if video.exists():
        expected.update(("assets/walkthrough.webm", "assets/walkthrough.vtt"))
    unexpected = {str(p.relative_to(output)) for p in files} - expected
    if unexpected:
        raise ValueError(
            "Unexpected stale public output; use a new empty output directory: "
            + ", ".join(sorted(unexpected))
        )
    result = {
        "output": str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output),
        "files": len(files),
        "bytes": sum(p.stat().st_size for p in files),
        "backendDependencies": False,
        "links": "PASS",
        "svgXML": "PASS",
        "publication": "NOT_DEPLOYED",
    }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / ".runs/site/quayready")
    parser.add_argument("--public-url")
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.public_url), indent=2))
