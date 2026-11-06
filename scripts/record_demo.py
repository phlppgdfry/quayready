"""Record the real local application. Synthetic data; masked credential entry only."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from quayready.cli import initialize, key_for, seed
from quayready.config import load_settings

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def process(cfg, command):
    env = {
        **os.environ,
        "QUAYREADY_CONFIG": str(cfg.run_dir / "config.json"),
        "QUAYREADY_TARGET_FAULT": "drop-after-commit",
    }
    with (cfg.run_dir / (command + ".log")).open("w") as log:
        child = subprocess.Popen(
            [sys.executable, "-m", "quayready.cli", command], env=env, stdout=log, stderr=log
        )
        try:
            port = cfg.app_port if command == "serve" else cfg.target_port
            for _ in range(100):
                try:
                    if (
                        httpx.get(
                            f"http://127.0.0.1:{port}/health/ready", trust_env=False, timeout=0.2
                        ).status_code
                        == 200
                    ):
                        break
                except httpx.HTTPError:
                    pass
                if child.poll() is not None:
                    raise RuntimeError("Recording server exited")
                time.sleep(0.05)
            else:
                raise RuntimeError("Recording server did not start")
            yield env
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)


def stamp(seconds: float) -> str:
    ms = int(seconds * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}.{ms % 1000:03}"


def main() -> None:
    os.chdir(ROOT)
    run = ROOT / ".runs" / ("recording-" + str(time.time_ns()))
    path = initialize(run, free_port(), free_port())
    os.environ["QUAYREADY_CONFIG"] = str(path)
    cfg = load_settings()
    destination = ROOT / "evidence/rc/video"
    destination.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        env = stack.enter_context(process(cfg, "serve"))
        stack.enter_context(process(cfg, "target"))
        p = stack.enter_context(sync_playwright())
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            record_video_dir=str(run / "video"),
            record_video_size={"width": 1440, "height": 1000},
        )
        page = context.new_page()
        start = time.monotonic()
        captions = []

        def hold(text, seconds):
            at = time.monotonic() - start
            print(text, flush=True)
            page.wait_for_timeout(seconds * 1000)
            captions.append((at, time.monotonic() - start, text))

        def login(role):
            page.locator("#token").fill(key_for(cfg, role))
            page.get_by_role("button", name="Open workbench").click()
            expect(page.locator(".identity strong")).to_have_text("DEMO-" + role)

        seed(cfg)
        page.goto(cfg.origin)
        login("OPERATOR")
        hold(
            "QuayReady: a real local synthetic integration lab. Three pallets expected; P003 has no warehouse evidence.",
            14,
        )
        seed(cfg, True)
        page.reload()
        expect(page.locator(".section-head .badge")).to_have_text("ELIGIBLE FOR REVIEW")
        hold(
            "A higher complete warehouse snapshot corrects the discrepancy. Fresh evidence makes version four eligible for review.",
            12,
        )
        page.get_by_role("button", name="Create review proposal").click()
        page.locator(".reason").fill("Independently verify current synthetic evidence")
        page.get_by_role("button", name="Approve request").click()
        expect(page.locator("#message")).to_contain_text("SELF_APPROVAL")
        hold(
            "The requesting subject cannot approve. This is a server-side rejection, even when that identity has both roles.",
            10,
        )
        page.get_by_role("button", name="Sign out").click()
        expect(page.locator("#token")).to_be_visible()
        login("REVIEWER")
        page.locator(".reason").fill(
            "Independent review of three pallets and fresh source evidence"
        )
        page.get_by_role("button", name="Approve request").click()
        expect(page.locator(".delivery .badge")).to_have_text("QUEUED")
        page.locator(".delivery").scroll_into_view_if_needed()
        hold(
            "A different subject approves evidence v4. Approval and immutable outbox commit together. Queued is not yet delivered.",
            14,
        )

        def worker():
            subprocess.run(
                [sys.executable, "-m", "quayready.cli", "worker", "--once"],
                env=env,
                check=True,
                capture_output=True,
                timeout=10,
            )

        worker()
        page.reload()
        expect(page.locator(".delivery .badge")).to_have_text("RETRY_WAIT")
        page.locator(".delivery").scroll_into_view_if_needed()
        hold(
            "The independent target committed, then deliberately lost its response. The app reports uncertainty rather than success.",
            16,
        )
        worker()
        page.reload()
        expect(page.locator(".delivery .badge")).to_have_text("CONFIRMED")
        page.locator(".delivery").scroll_into_view_if_needed()
        hold(
            "A new worker process looks up the same dispatch identifier. Its matching receipt confirms the existing target effect.",
            16,
        )
        page.locator(".timeline li").last.scroll_into_view_if_needed()
        hold(
            "The audit connects source, operator, reviewer and delivery. Real HTTP, separate databases, one effect. No physical departure authorisation.",
            12,
        )
        video = page.video
        context.close()
        browser.close()
        saved = Path(video.path())
        (destination / "walkthrough.webm").write_bytes(saved.read_bytes())
        (destination / "walkthrough.vtt").write_text(
            "WEBVTT\n\n"
            + "\n\n".join(
                f"{i + 1}\n{stamp(a)} --> {stamp(b)}\n{text}"
                for i, (a, b, text) in enumerate(captions)
            )
            + "\n"
        )
        (destination / "recording.json").write_text(
            json.dumps(
                {
                    "kind": "actual local application recording",
                    "durationSeconds": time.monotonic() - start,
                    "sourceRun": "new isolated synthetic run",
                    "fault": "target commit followed by response loss",
                    "captions": [{"start": a, "end": b, "text": t} for a, b, t in captions],
                    "noVoiceover": True,
                    "credentials": "masked local login input; no tokens displayed",
                },
                indent=2,
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
