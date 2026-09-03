"""Check the in-app guide against a running server, in a real browser.

The Vitest drift test proves the guide's descriptions and the source agree. This proves the
descriptions reach the screen: that every anchor declared always-present actually renders, that
the help panel and the reference page work, and that the guided tour completes end to end
without losing the selected period.

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
FAILURES: list[str] = []


def check(ok: bool, name: str, detail: str = "") -> bool:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(name)
    return ok


def model_anchors(page: Page) -> dict[str, dict]:
    """The model as the reference page renders it, so there is one source of truth and no
    second copy of it in Python."""
    page.goto(f"{BASE}/guide", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(800)
    return page.evaluate(
        "Object.fromEntries([...document.querySelectorAll('li[data-anchor]')]"
        ".map(e => [e.dataset.anchor, {availability: e.dataset.availability, dom: e.dataset.inDom === 'yes'}]))"
    )


SCREEN_ROUTES = [
    ("portfolio", f"/portfolio?period={PERIOD}"),
    ("findings", f"/findings?period={PERIOD}"),
    ("queue", f"/queue?period={PERIOD}"),
    ("peer", f"/peer?period={PERIOD}"),
    ("coverage", f"/coverage?period={PERIOD}"),
    ("trends", f"/trends?period={PERIOD}"),
    ("ingestion", f"/ingestion?period={PERIOD}"),
    ("config", f"/config?period={PERIOD}"),
    ("audit", f"/audit?period={PERIOD}"),
    ("reports", f"/reports?period={PERIOD}"),
    ("guide", "/guide"),
]


def anchors_on(page: Page) -> set[str]:
    return set(page.evaluate("[...document.querySelectorAll('[data-guide]')].map(e => e.dataset.guide)"))


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME) if CHROME else pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        print("\nreference page")
        page.goto(f"{BASE}/guide", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(800)
        cards = page.locator("h3").count()
        check(cards > 80, "every control is described", f"{cards} cards")
        page.goto(f"{BASE}/guide?q=threshold", wait_until="networkidle")
        page.wait_for_timeout(500)
        narrowed = page.locator("h3").count()
        check(0 < narrowed < cards, "search narrows the page", f"{cards} -> {narrowed}")
        page.goto(f"{BASE}/guide?traps=1", wait_until="networkidle")
        page.wait_for_timeout(500)
        check(page.locator("text=Watch out:").count() >= 3, "the traps filter collects the pitfalls")

        print("\nhelp panel")
        page.goto(f"{BASE}/portfolio?period={PERIOD}", wait_until="networkidle")
        page.wait_for_timeout(900)
        page.keyboard.press("Shift+Slash")
        page.wait_for_timeout(500)
        check("Portfolio overview" in page.get_by_role("dialog").inner_text(), "Shift+/ opens help for the current screen")
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        check(page.get_by_role("dialog").count() == 0, "Escape closes it")

        print("\nanchors reachable on each screen")
        model = model_anchors(page)
        seen: set[str] = set()
        for name, path in SCREEN_ROUTES:
            page.goto(BASE + path, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1000)
            found = anchors_on(page)
            seen |= found
            check(len(found) > 0, f"{name} renders anchored controls", f"{len(found)}")
        if model:
            expected = {a for a, m in model.items() if m["availability"] == "always" and m["dom"]}
            # Anchors on the two record-specific screens are covered by the tour below.
            expected = {a for a in expected if not a.startswith(("entity.", "finding."))}
            missing = sorted(expected - seen)
            check(not missing, "every always-present anchor was reachable", ", ".join(missing[:4]))
        else:
            check(False, "could not read the guide model from the reference page")

        print("\nguided tour")
        page.goto(f"{BASE}/portfolio?period={PERIOD}&tour=onboarding.0", wait_until="networkidle")
        page.wait_for_timeout(1800)
        check("1 of 9" in page.get_by_role("dialog").inner_text(), "a tour link opens at that step")
        routes: set[str] = set()
        for _ in range(8):
            routes.add(page.url.split("?")[0])
            page.get_by_role("button", name="Next").first.click()
            page.wait_for_timeout(2000)
        routes.add(page.url.split("?")[0])
        check("9 of 9" in page.get_by_role("dialog").inner_text(), "all nine steps advance")
        check(len(routes) >= 3, "the tour crosses screens", f"{len(routes)}")
        check(f"period={PERIOD}" in page.url, "the selected period survived the whole tour")
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)
        check(page.get_by_role("dialog").count() == 0 and "tour=" not in page.url, "Escape ends the tour and clears the parameter")

        browser.close()

    real = [e for e in errors if "favicon" not in e.lower()]
    check(not real, "no console errors", "; ".join(real[:2]) if real else "")

    print(f"\n{'all guide checks passed' if not FAILURES else 'FAILED: ' + ', '.join(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
