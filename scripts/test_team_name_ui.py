"""Two-name connection UI regression with mocked account pairing; real Rust lineups.

No signed-in or real public manager account is accessed by this test.
"""

import argparse
import json
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:7878")
    url = parser.parse_args().url
    request = urllib.request.Request(
        url + "/api/optimize", data=b'{"horizon":1}', headers={"Content-Type": "application/json"}
    )
    job = json.load(urllib.request.urlopen(request))["job"]
    for _ in range(100):
        result = json.load(urllib.request.urlopen(url + f"/api/jobs/{job}"))
        if result["status"] != "running":
            break
        time.sleep(0.2)
    assert result["status"] == "done", result
    squad = result["result"]["squad"]
    errors, posted, loaded = [], [], []
    candidate = {"reference": 202, "name": "Test XI", "manager": "Bob Example", "exact": True}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        context.add_init_script("localStorage.setItem('fpl-manager-tutorial-seen', 'true')")
        page.on("pageerror", lambda error: errors.append(str(error)))
        # No external website opened during this fixture test.
        page.add_init_script("window.open=()=>({opener:null,location:'',close(){}})")

        def start(route):
            body = route.request.post_data_json
            posted.append(body)
            if body.get("known_entry_id"):
                route.fulfill(json={"candidate": candidate})
            else:
                route.fulfill(
                    json={
                        "token": "a" * 64,
                        "url": "https://fantasy.premierleague.com/#fpl-local="
                        + "a" * 64
                        + "&port=7878",
                        "expires_seconds": 300,
                    }
                )

        page.route("**/api/connect/start", start)
        page.route(
            "**/api/connect/status", lambda route: route.fulfill(json={"candidate": candidate})
        )

        def team(route):
            loaded.append(route.request.url)
            route.fulfill(json={"id": 202, "name": "Test XI", "event": 10, "owned": squad})

        page.route("**/api/team/202?*", team)
        page.goto(url + "/#/settings", wait_until="networkidle")
        assert page.locator("#load-team-form input").count() == 2
        assert page.locator("#team-league,#team-id").count() == 0
        page.get_by_label("FPL team name", exact=True).fill("Test XI")
        page.get_by_label("Manager name", exact=True).fill("Bob Example")
        page.screenshot(path="reports/two-name-connection-desktop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.locator("body").evaluate("b=>b.scrollWidth<=innerWidth+1")
        page.screenshot(path="reports/two-name-connection-mobile.png", full_page=True)
        page.get_by_role("button", name="Connect my team", exact=True).click()
        page.wait_for_selector(".pitch-player[data-player]", timeout=20000)
        assert posted[-1]["name"] == "Test XI" and posted[-1]["manager"] == "Bob Example"
        assert "league_url" not in posted[-1]
        assert "expected_manager=Bob%20Example" in loaded[-1]
        stored = page.evaluate('JSON.parse(localStorage.getItem("fpl-manager-native-v1"))')
        assert stored["owned"] == squad and stored["team_manager"] == "Bob Example"
        assert stored["confirmed"] is False and stored["sale_prices"] == {}
        assert stored["risk_mode"] == "aggressive"
        page.get_by_role("button", name="Conservative", exact=True).click()
        assert page.locator(".pitch-player[data-player]").count() == 0
        page.get_by_role("button", name="Pick my best XI", exact=True).click()
        page.wait_for_selector(".pitch-player[data-player]", timeout=20000)
        assert "Conservative formation" in page.locator(".card-head").first.inner_text()
        page.reload(wait_until="networkidle")
        assert (
            page.get_by_role("button", name="Conservative", exact=True).get_attribute(
                "aria-pressed"
            )
            == "true"
        )
        page.evaluate('location.hash="/settings"')
        page.get_by_role("button", name="Connect my team", exact=True).click()
        page.wait_for_selector(".pitch-player[data-player]", timeout=20000)
        assert posted[-1]["known_entry_id"] == 202
        # A name conflict must not overwrite existing financial or squad state.
        before = page.evaluate('localStorage.getItem("fpl-manager-native-v1")')
        page.unroute("**/api/team/202?*")
        page.route(
            "**/api/team/202?*",
            lambda route: route.fulfill(
                status=409, json={"error": "Manager name changed. Reconnect."}
            ),
        )
        page.evaluate('location.hash="/settings"')
        page.get_by_role("button", name="Connect my team", exact=True).click()
        page.wait_for_timeout(300)
        assert page.evaluate('localStorage.getItem("fpl-manager-native-v1")') == before
        migration = browser.new_context()
        old = {
            "team_id": "202",
            "team_name": "Test XI",
            "owned": squad,
            "bank": 17,
            "free_transfers": 2,
            "sale_prices": {str(i): 40 for i in squad},
            "confirmed": True,
        }
        migration.add_init_script(
            'localStorage.setItem("fpl-manager-native-v1",' + json.dumps(json.dumps(old)) + ");"
        )
        migration.add_init_script("localStorage.setItem('fpl-manager-tutorial-seen', 'true')")
        migrated = migration.new_page()
        migrated.goto(url + "/#/settings", wait_until="networkidle")
        assert migrated.locator("#bank").input_value() == "1.7"
        assert migrated.locator("[data-sale]").count() == 15
        assert migrated.locator("#team-id,#team-league").count() == 0
        assert not errors, errors
        browser.close()
    out = {
        "passed": True,
        "checks": [
            "exactly two name inputs",
            "no league link or numeric input",
            "one-time helper pairing UI",
            "both names sent for verification",
            "auto-load verified account",
            "real native lineup",
            "playing style persistence and result invalidation",
            "saved connection reuse",
            "conflict preserves squad and finances",
            "legacy reference migration",
            "desktop/mobile overflow",
        ],
        "javascript_errors": errors,
        "live_signed_in_account_tested": False,
        "note": "Mock account handshake and names; real cached player pool and Rust optimizer.",
    }
    Path("reports/team-name-browser-results.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
