"""Real browser, real app HTTP, real target HTTP and independently persisted effects."""

import os
from pathlib import Path

import pytest
from accessibility import audit
from playwright.sync_api import expect, sync_playwright
from processes import server

from quayready.cli import key_for, seed
from quayready.store import Store
from quayready.worker import Worker


@pytest.mark.browser
def test_T30_workbench_vertical_slice(cfg):
    evidence = Path(os.getenv("QUAYREADY_EVIDENCE", str(cfg.run_dir / "screenshots")))
    evidence.mkdir(parents=True, exist_ok=True)
    errors = []
    with server(cfg, "serve"), server(cfg), sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        seed(cfg)
        page.goto(cfg.origin)
        expect(page).to_have_title("QuayReady · Operations desk")
        expect(page.locator("h1")).to_have_text("Evidence before action.")
        audit(page, "app-login")
        page.locator("#token").fill(key_for(cfg, "OPERATOR"))
        page.get_by_role("button", name="Open workbench").click()
        expect(page.locator(".identity strong")).to_have_text("DEMO-OPERATOR")
        expect(page.locator(".pallets li").filter(has_text="DEMO-P003")).to_contain_text(
            "Missing evidence"
        )
        expect(page.locator(".issue")).to_contain_text("MISSING PALLET")
        page.screenshot(path=str(evidence / "01-missing-pallet.png"), full_page=True)
        audit(page, "app-missing")
        seed(cfg, correct=True)
        page.reload()
        expect(page.locator(".section-head .badge")).to_have_text("ELIGIBLE FOR REVIEW")
        page.screenshot(path=str(evidence / "02-corrected-evidence.png"), full_page=True)
        page.get_by_role("button", name="Create review proposal").click()
        expect(page.locator(".review")).to_contain_text("PENDING REVIEW")
        page.locator(".reason").fill("Checked three pallets and fresh evidence")
        with page.expect_response(lambda response: response.url.endswith("/decision")) as denied:
            page.get_by_role("button", name="Approve request").click()
        assert denied.value.status == 403
        expect(page.locator("#message")).to_contain_text("SELF_APPROVAL")
        # Chromium logs the deliberately rejected security request as a resource error.
        assert errors == [
            "Failed to load resource: the server responded with a status of 403 (Forbidden)"
        ]
        errors.clear()
        page.get_by_role("button", name="Sign out").click()
        expect(page.locator("#token")).to_be_visible()
        page.locator("#token").fill(key_for(cfg, "REVIEWER"))
        page.get_by_role("button", name="Open workbench").click()
        expect(page.locator(".identity strong")).to_have_text("DEMO-REVIEWER")
        page.locator(".reason").fill("Independently checked synthetic evidence v4")
        page.get_by_role("button", name="Approve request").click()
        expect(page.locator(".delivery .badge")).to_have_text("QUEUED")
        page.screenshot(path=str(evidence / "02-independent-approval.png"), full_page=True)
        Worker(Store(cfg)).tick()
        page.reload()
        expect(page.locator(".delivery .badge")).to_have_text("CONFIRMED")
        expect(page.locator(".delivery")).to_contain_text("Independent target receipt")
        expect(page.locator(".audit")).to_contain_text("DEMO-REVIEWER")
        page.screenshot(path=str(evidence / "03-confirmed-desktop.png"), full_page=True)
        audit(page, "app-confirmed")
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(evidence / "hero.jpg"), type="jpeg", quality=85)
        for width, height in [(1280, 800), (768, 1024)]:
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
            expect(page.locator(".delivery .badge")).to_have_text("CONFIRMED")
            page.screenshot(path=str(evidence / f"workbench-{width}.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(evidence / "04-confirmed-mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
            "Mobile horizontal overflow"
        )
        audit(page, "app-mobile")
        assert errors == []
        context.close()
        browser.close()


@pytest.mark.browser
def test_release_manual_reconciliation_real_UI(cfg):
    from conftest import approve, ready
    from test_recovery import effects

    evidence = Path(os.getenv("QUAYREADY_EVIDENCE", "evidence/rc/ui"))
    evidence.mkdir(parents=True, exist_ok=True)
    store = Store(cfg)
    approve(store, ready(store))
    worker = Worker(store)
    with server(cfg, "serve"), server(cfg), sync_playwright() as p:
        claim = worker.claim()
        status, receipt, _ = worker.request(claim)
        assert status == 201 and effects(cfg) == 1
        worker.finish(claim, -1, None)
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(cfg.origin)
        page.locator("#token").fill(key_for(cfg, "REVIEWER"))
        page.get_by_role("button", name="Open workbench").click()
        expect(page.locator(".delivery .badge")).to_have_text("MANUAL_REVIEW")
        expect(page.locator(".delivery")).to_contain_text("Automatic delivery stopped")
        page.screenshot(path=str(evidence / "05-manual-review.png"), full_page=True)
        audit(page, "app-manual-review")
        page.get_by_role("button", name="Look up target receipt").click()
        expect(page.locator(".delivery .badge")).to_have_text("CONFIRMED")
        expect(page.locator(".receipt")).to_contain_text(receipt["receiptId"])
        assert effects(cfg) == 1
        expect(page.locator(".audit")).to_contain_text("Manual lookup confirmed")
        page.screenshot(path=str(evidence / "06-reconciled.png"), full_page=True)
        browser.close()
