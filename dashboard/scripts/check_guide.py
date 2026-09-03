"""Walk the in-app product tour in a real browser and assert it works.

The Vitest drift test proves the tour's targets exist in the source. This proves they reach the
screen: that the launcher is present, that the overlay dims and blurs everything except the
highlighted control, that every step advances across every screen, and that Back, Skip and
Finish behave.

    satsa serve &
    python dashboard/scripts/check_guide.py

Exits non-zero if any check fails. SATSA_BASE, SATSA_PERIOD and SATSA_CHROME work as they do
in screenshots.py.
"""

from __future__ import annotations

import os
import sys

from playwright.sync_api import Page, sync_playwright

BASE = os.environ.get("SATSA_BASE", "http://127.0.0.1:8000")
PERIOD = os.environ.get("SATSA_PERIOD", "2026-06")
CHROME = os.environ.get("SATSA_CHROME")

VEIL = "div.backdrop-blur-\\[3px\\]"
FAILURES: list[str] = []


def check(ok: bool, name: str, detail: str = "") -> bool:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(name)
    return ok


def progress(page: Page) -> tuple[int, int]:
    """The "3 / 20" readout in the popup, as (step, total)."""
    for line in page.get_by_role("dialog").inner_text().splitlines():
        if line.count("/") == 1 and line.replace("/", "").replace(" ", "").isdigit():
            a, b = line.split("/")
            return int(a.strip()), int(b.strip())
    return 0, 0


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME) if CHROME else pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        launcher = page.locator("button[aria-label^='Take a tour']")

        print("\nthe tour is not a page")
        page.goto(f"{BASE}/portfolio?period={PERIOD}", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(900)
        check(page.locator("nav[aria-label='Primary'] a").count() == 10, "navigation has ten items, no guide route")

        print("\nlauncher")
        for path in ["/portfolio", "/queue", "/coverage", "/audit", "/reports"]:
            page.goto(f"{BASE}{path}?period={PERIOD}", wait_until="networkidle")
            page.wait_for_timeout(700)
            if not launcher.is_visible():
                check(False, f"launcher visible on {path}")
                break
        else:
            check(True, "launcher visible on every main screen")
        box = launcher.bounding_box()
        check(box is not None and box["x"] < 60 and box["y"] > 860, "fixed bottom-left", f"{box['x']:.0f},{box['y']:.0f}")

        print("\noverlay")
        page.goto(f"{BASE}/portfolio?period={PERIOD}", wait_until="networkidle")
        page.wait_for_timeout(900)
        route_before = page.url.split("?")[0]
        launcher.click()
        page.wait_for_timeout(1800)
        check(page.get_by_role("dialog").count() == 1, "the tour opens a popup")
        check(page.url.split("?")[0] == route_before, "without navigating to a new page")
        check(page.locator(VEIL).count() == 4, "four blurred panels surround the target")
        blurred = page.evaluate(
            "[...document.querySelectorAll('div.backdrop-blur-\\\\[3px\\\\]')]"
            ".every(e => getComputedStyle(e).backdropFilter.includes('blur'))"
        )
        check(blurred, "the rest of the screen is actually blurred")
        reachable = page.evaluate(
            "(() => {const t = document.querySelector('[data-guide=\"global.period\"]');"
            "if (!t) return false; const r = t.getBoundingClientRect();"
            "return t.contains(document.elementFromPoint(r.left + r.width/2, r.top + r.height/2));})()"
        )
        check(reachable, "the highlighted control stays on top and reachable")
        check(
            page.evaluate("(() => {const d = document.querySelector('[role=dialog]'); return !!d && d.parentElement === document.body;})()"),
            "the overlay is portalled to document.body",
        )

        print("\nevery step")
        step, total = progress(page)
        check(step == 1 and total > 1, "progress starts at step 1", f"{step} / {total}")
        routes = set()
        for _ in range(total - 1):
            routes.add(page.url.split("?")[0].replace(BASE, ""))
            page.get_by_role("button", name="Next").click()
            page.wait_for_timeout(2100)
            if page.get_by_role("dialog").count() == 0:
                break
        routes.add(page.url.split("?")[0].replace(BASE, ""))
        step, _ = progress(page)
        check(step == total, f"all {total} steps advance", f"reached {step}")
        check(len(routes) >= 10, f"the tour covered {len(routes)} screens", ", ".join(sorted(routes)))
        check(f"period={PERIOD}" in page.url, "the selected period survived the whole tour")
        last = page.get_by_role("dialog").inner_text()
        check("Finish" in last and "Next" not in last, "the last step offers Finish, not Next")

        print("\nback, finish and skip")
        page.get_by_role("button", name="Back").click()
        page.wait_for_timeout(1800)
        check(progress(page)[0] == total - 1, "Back steps backwards")
        page.get_by_role("button", name="Skip the guide").click()
        page.wait_for_timeout(800)
        check(page.get_by_role("dialog").count() == 0, "Skip guide closes the overlay")
        check(page.locator(VEIL).count() == 0, "the dim and blur are removed")
        check(launcher.is_visible(), "and the launcher returns")

        page.goto(f"{BASE}/portfolio?period={PERIOD}&tour=onboarding.{total - 1}", wait_until="networkidle")
        page.wait_for_timeout(2200)
        if check(page.get_by_role("button", name="Finish").count() == 1, "a deep link opens the last step"):
            page.get_by_role("button", name="Finish").click()
            page.wait_for_timeout(800)
            check(page.get_by_role("dialog").count() == 0 and "tour=" not in page.url, "Finish closes the tour and clears the URL")

        print("\nmobile")
        phone = browser.new_page(viewport={"width": 390, "height": 844})
        phone.goto(f"{BASE}/portfolio?period={PERIOD}", wait_until="networkidle")
        phone.wait_for_timeout(1200)
        phone.locator("button[aria-label^='Take a tour']").click()
        phone.wait_for_timeout(1900)
        pop = phone.get_by_role("dialog")
        if check(pop.count() == 1, "the tour runs on a phone viewport"):
            b = pop.bounding_box()
            check(b["width"] <= 370 and b["y"] + b["height"] <= 844, "the popup fits on screen", f"{b['width']:.0f}px")
        phone.close()

        browser.close()

    real = [e for e in errors if "favicon" not in e.lower()]
    check(not real, "no console errors", "; ".join(real[:2]) if real else "")

    print(f"\n{'all tour checks passed' if not FAILURES else 'FAILED: ' + ', '.join(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
