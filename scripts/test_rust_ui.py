"""Headless browser regression and responsive screenshots for the local Rust app."""

import argparse
import json
import platform
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:7878")
    parser.add_argument("--screenshots", default="reports/rust-ui")
    args = parser.parse_args()
    output = Path(args.screenshots)
    output.mkdir(parents=True, exist_ok=True)
    timings = {}
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        environment = f"Headless Chromium {browser.version} on {platform.system()}"
        page = browser.new_page(viewport={"width": 1440, "height": 1060}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        start = time.perf_counter()
        page.goto(args.url, wait_until="networkidle")
        tutorial = page.get_by_role("dialog", name="Welcome to FPL Manager")
        tutorial.wait_for()
        tutorial.get_by_role("button", name="Next").click()
        page.get_by_role("dialog", name="Load your squad").wait_for()
        page.get_by_role("button", name="Back", exact=True).click()
        tutorial.wait_for()
        for _ in range(4):
            page.get_by_role("button", name="Next", exact=True).click()
        page.get_by_role("button", name="Finish", exact=True).click()
        page.wait_for_function("localStorage.getItem('fpl-manager-tutorial-seen') === 'true'")
        page.reload(wait_until="networkidle")
        assert not page.locator("#tutorial").is_visible()
        page.get_by_role("heading", name="Your gameweek, at a glance.").wait_for()
        timings["cold_overview_seconds"] = time.perf_counter() - start
        page.screenshot(path=str(output / "desktop-overview.png"), full_page=True)
        routes = {
            "team": "My team",
            "players": "Find your next difference-maker.",
            "fixtures": "See the run ahead.",
            "models": "Local intelligence. Measured honestly.",
            "settings": "Your team, your details.",
            "transfers": "Make the next move count.",
            "captaincy": "Give the armband a second thought.",
            "chips": "Use your chips with purpose.",
            "builder": "A new squad. A fresh start.",
        }
        for route, title in routes.items():
            start = time.perf_counter()
            page.evaluate('(route) => location.hash = "/" + route', route)
            page.get_by_role("heading", name=title, exact=True, level=1).wait_for()
            timings[route + "_navigation_ms"] = (time.perf_counter() - start) * 1000
            assert page.locator("body").evaluate("(b) => b.scrollWidth <= innerWidth + 1"), route
        page.get_by_role("button", name="Build my squad", exact=True).click()
        page.get_by_role("heading", name="Your recommended squad").wait_for(timeout=25000)
        assert page.locator(".pitch-player[data-player]").count() == 11
        assert page.locator(".bench-player").count() == 4
        page.locator("#toast").evaluate("(el) => el.className = ''")
        page.screenshot(path=str(output / "desktop-pitch.png"), full_page=True)
        page.get_by_role("button", name="Use as my local squad").click()
        page.get_by_role("heading", name="My team", exact=True, level=1).wait_for()
        assert page.locator(".pitch-player[data-player]").count() == 11
        page.evaluate('location.hash = "/players"')
        page.get_by_role("heading", name=routes["players"]).wait_for()
        page.get_by_role("searchbox", name="Search players or clubs").fill("Ødegaard")
        page.wait_for_timeout(300)
        assert page.locator("tbody tr[data-player]").count() == 1
        page.locator("tbody tr[data-player]").click()
        page.get_by_role("dialog").wait_for()
        assert "Ødegaard" in page.locator("#player-title").inner_text()
        page.get_by_role("button", name="Close player details").click()
        page.evaluate('location.hash = "/settings"')
        page.get_by_role("heading", name=routes["settings"]).wait_for()
        page.get_by_role("button", name="App tutorial").click()
        tutorial.wait_for()
        tutorial.get_by_role("button", name="Skip tutorial").click()
        tutorial.wait_for(state="hidden")
        fields = page.locator("[data-sale]").all()
        assert len(fields) == 15
        missing_player = fields[0].get_attribute("aria-label").removeprefix("Selling price for ")
        page.locator("#confirmed").check()
        page.get_by_role("button", name="Save team details").click()
        assert missing_player in page.locator("#finance-error").inner_text()
        assert fields[0].evaluate("(field) => document.activeElement === field")
        response = page.request.get(args.url + "/api/state")
        assert response.ok
        prices = {str(player["id"]): player["cost"] for player in response.json()["players"]}
        for field in fields:
            field.fill(f"{prices[field.get_attribute('data-sale')] / 10:.1f}")
            field.dispatch_event("change")
        assert page.locator("#sale-price-status").inner_text() == "15 of 15 selling prices ready"
        page.locator("#confirmed").check()
        page.get_by_role("button", name="Save team details").click()
        with page.expect_download() as exported:
            page.get_by_role("button", name="Export JSON", exact=True).click()
        backup = exported.value.path()
        details = json.loads(backup.read_text(encoding="utf-8"))
        assert details["confirmed"] and len(details["sale_prices"]) == 15
        page.locator("#import-team").set_input_files(str(backup))
        page.get_by_text("Backup imported.", exact=False).wait_for()
        assert not page.locator("#confirmed").is_checked()
        assert page.locator("#sale-price-status").inner_text() == "15 of 15 selling prices ready"
        page.locator("#confirmed").check()
        page.get_by_role("button", name="Save team details").click()
        page.evaluate('location.hash = "/transfers"')
        page.get_by_role("heading", name=routes["transfers"]).wait_for()
        assert page.locator("[data-job-panel] .badge").count() == 0
        page.reload(wait_until="networkidle")
        assert page.get_by_role("button", name="Compare transfers").is_enabled()
        page.get_by_role("button", name="Compare transfers").click()
        page.locator("[data-job-panel]").get_by_text("done", exact=True).wait_for(timeout=25000)
        page.get_by_role("heading", name="XI after these transfers", exact=True).wait_for()
        assert not errors, errors
        # Mobile navigation and modals use the same fully local data, without reruns.
        page.set_viewport_size({"width": 390, "height": 844})
        for route, title in {
            "overview": "Your gameweek, at a glance.",
            "team": "My team",
            "players": routes["players"],
            "fixtures": routes["fixtures"],
            "models": routes["models"],
            "settings": routes["settings"],
        }.items():
            page.evaluate('(route) => location.hash = "/" + route', route)
            page.get_by_role("heading", name=title, exact=True, level=1).wait_for()
            assert page.locator("body").evaluate("(b) => b.scrollWidth <= innerWidth + 1"), route
        page.evaluate('location.hash = "/overview"')
        page.get_by_role("heading", name="Your gameweek, at a glance.").wait_for()
        page.locator("#toast").evaluate("(el) => el.className = ''")
        page.screenshot(path=str(output / "mobile-overview.png"), full_page=True)
        page.evaluate('location.hash = "/team"')
        page.get_by_role("heading", name="My team", exact=True, level=1).wait_for()
        page.screenshot(path=str(output / "mobile-pitch.png"), full_page=True)
        assert not errors, errors
        browser.close()
    result = {
        "timings": timings,
        "javascript_errors": errors,
        "checks": [
            "all native routes",
            "desktop/mobile overflow",
            "native squad build",
            "11 starters and 4 bench players",
            "use local draft",
            "player search",
            "player detail dialog",
            "missing selling-price validation",
            "finance confirmation through reload",
            "team backup export/import",
            "completed job banner is scoped to its page",
            "transfer job",
        ],
        "environment": environment,
    }
    (output / "browser-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
