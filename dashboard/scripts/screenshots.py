"""Generate the screenshots in docs/screenshots/ by driving the built UI in a real browser.

Run against a live server so the images cannot drift from what the application renders:

    satsa serve &
    python dashboard/scripts/screenshots.py

Playwright's own Chromium is used when present; set SATSA_CHROME to point at another
build if the download is unavailable on an air-gapped machine.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("SATSA_BASE", "http://127.0.0.1:8000")
PERIOD = os.environ.get("SATSA_PERIOD", "2026-06")
OUT = Path(__file__).resolve().parents[2] / "docs" / "screenshots"
CHROME = os.environ.get("SATSA_CHROME")

SHOTS: list[tuple[str, str, str]] = [
    ("portfolio", f"/portfolio?period={PERIOD}", "Entity risk across the portfolio, ranked by supervisory priority"),
    ("entity", f"/entities/E03?period={PERIOD}", "The risk indicator as arithmetic: score, weight and contribution per dimension"),
    ("finding", "", "One finding from claim to evidence"),  # resolved by drill-down
    ("records", "", "The alert records behind that finding"),
    ("queue", f"/queue?period={PERIOD}", "Review queue, uncertain items first"),
    ("peer", f"/peer?period={PERIOD}&metric=note_template_score&entity=E03", "Peer distribution with the selected entity marked"),
    ("coverage", f"/coverage?period={PERIOD}", "Negative space: expected evidence that is absent"),
    ("trends", f"/trends?period={PERIOD}&entity=E03", "Risk across submission periods"),
    ("ingestion", f"/ingestion?period={PERIOD}", "Submission validation, down to the individual check"),
    ("config", f"/config?period={PERIOD}", "Weights, and the threshold derived from the cost of being wrong"),
    ("audit", f"/audit?period={PERIOD}", "The hash-chained run log"),
    ("reports", f"/reports?period={PERIOD}", "PDF and CSV export, stamped with provenance"),
    ("help", "", "The help panel, opened with Shift+/ on any screen"),  # a state, not a URL
    ("tour", "", "The product tour: everything dimmed except the control being explained"),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME) if CHROME else pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 950}, device_scale_factor=2)

        for name, path, _caption in SHOTS:
            if not path:
                continue
            page.goto(BASE + path, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1200)
            page.screenshot(path=OUT / f"{name}.png", full_page=False)
            written.append(name)
            print(f"  {name}.png")

        # The finding and its records are reached by the drill-down, not by a bare URL.
        page.goto(f"{BASE}/portfolio?period={PERIOD}", wait_until="networkidle")
        page.wait_for_timeout(800)
        page.get_by_role("link", name="E03", exact=True).first.click()
        page.wait_for_timeout(1500)
        row = page.locator("tbody tr").filter(has_text="EG-02").first
        (row if row.count() else page.locator("tbody tr").last).click()
        page.wait_for_timeout(1500)
        page.screenshot(path=OUT / "finding.png")
        written.append("finding")
        print("  finding.png")
        page.locator("[role=tab]").filter(has_text="Raw records").first.click()
        page.wait_for_timeout(1500)
        page.screenshot(path=OUT / "records.png")
        written.append("records")
        print("  records.png")

        # The help panel is a state, not a URL. Shift+/ opens it for whatever screen you are on.
        page.goto(f"{BASE}/portfolio?period={PERIOD}", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.keyboard.press("Shift+Slash")
        page.wait_for_timeout(800)
        page.screenshot(path=OUT / "help.png")
        written.append("help")
        print("  help.png")

        # The tour is an overlay, so it has to be started rather than navigated to.
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        page.click("button[aria-label^='Take a tour']")
        page.wait_for_timeout(1800)
        page.get_by_role("button", name="Next").click()
        page.wait_for_timeout(2000)
        page.screenshot(path=OUT / "tour.png")
        written.append("tour")
        print("  tour.png")

        browser.close()
    print(f"\n{len(written)} screenshots in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
