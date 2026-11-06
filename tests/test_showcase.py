import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from accessibility import audit
from playwright.sync_api import expect, sync_playwright

# This build is entirely static; no backend is started by these tests.
from scripts.build_showcase import build


@pytest.mark.browser
def test_release_static_simulation_subpath_and_no_JS(tmp_path):
    output = tmp_path / "quayready"
    build(output)
    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))

    class Quiet(handler.func):
        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(tmp_path)))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{http.server_port}/quayready/"
    destination = Path("evidence/rc/showcase")
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(url)
            expect(page).to_have_title("QuayReady — evidence before action")
            expect(page.locator("h1")).to_contain_text("Evidence")
            metrics = page.evaluate(
                """() => ({navigationMs:performance.getEntriesByType('navigation')[0].duration, transferBytes:performance.getEntriesByType('resource').reduce((n,r)=>n+r.transferSize,0), scripts:document.scripts.length, cacheState:'fresh browser context initial navigation'})"""
            )
            video = page.locator("video")
            expect(video).to_have_attribute("preload", "none")
            video.evaluate("(v)=>v.play()")
            page.wait_for_function('document.querySelector("video").currentTime>0')
            duration = video.evaluate("(v)=>v.duration")
            assert 90 <= duration <= 150
            page.wait_for_function(
                'document.querySelector("video").textTracks[0].cues?.length >= 7'
            )
            video.evaluate("(v)=>v.pause()")
            page.keyboard.press("Tab")
            expect(page.get_by_role("link", name="Skip to case study")).to_be_focused()
            page.keyboard.press("Enter")
            for _ in range(3):
                page.locator("#sim-next").click()
            expect(page.locator("#sim-pallets li").nth(2)).to_contain_text("Missing")
            for _ in range(7):
                page.locator("#sim-next").click()
            expect(page.locator("#sim-delivery")).to_have_text("Confirmed")
            assert page.locator("#sim-next").is_disabled()
            page.locator("#sim-reset").click()
            expect(page.locator("#sim-title")).to_have_text("Order created")
            for incident in (
                "duplicate",
                "conflict",
                "stale",
                "self",
                "timeout",
                "restart",
                "lost",
            ):
                page.locator("#incident").select_option(incident)
                assert page.locator("#incident-timeline li").count() >= 4
            for component in page.locator("[data-component]").all():
                component.click()
                expect(component).to_have_attribute("aria-pressed", "true")
                assert page.locator("#component-panel").inner_text()
            audit(page, "showcase-desktop")
            page.goto(url)
            page.screenshot(path=str(destination / "hero-desktop.png"), full_page=False)
            page.screenshot(path=str(destination / "desktop.png"), full_page=True)
            for width, height in [(1280, 800), (768, 1024), (390, 844)]:
                page.set_viewport_size({"width": width, "height": height})
                page.goto(url)
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width
                page.screenshot(path=str(destination / f"viewport-{width}.png"), full_page=True)
                if width == 390:
                    page.screenshot(path=str(destination / "hero-mobile.png"), full_page=False)
            audit(page, "showcase-mobile")
            assert errors == [], errors
            for name in (
                "guide.html",
                "architecture.html",
                "evidence.html",
                "case-study.html",
                "transcript.html",
            ):
                assert page.goto(url + name).status == 200
                assert page.locator("h1").inner_text()
            context.close()
            nojs = browser.new_context(java_script_enabled=False)
            q = nojs.new_page()
            q.goto(url)
            expect(q.locator(".no-js")).to_be_visible()
            assert q.locator(".workflow-steps li").count() == 11
            q.locator(".architecture-fallback summary").click()
            expect(q.get_by_text("App database owns immutable", exact=False)).to_be_visible()
            nojs.close()
            browser.close()
            (destination / "performance.json").write_text(
                json.dumps(
                    {
                        "kind": "local Chromium observation, not a benchmark or Lighthouse score",
                        **metrics,
                    },
                    indent=2,
                )
                + "\n"
            )
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=2)


def test_static_export_refuses_nonempty_unowned_output(tmp_path):
    (tmp_path / "private-note.txt").write_text("private sentinel")
    with pytest.raises(ValueError, match="overwrite"):
        build(tmp_path)
    assert (tmp_path / "private-note.txt").read_text() == "private sentinel"
