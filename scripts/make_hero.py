"""Rebuilds docs/site-hero.png (README picture and link preview) from docs/index.html with headless Chromium via Playwright.
Needs `pip install playwright && playwright install chromium`, which are not project dependencies. `python scripts/make_hero.py`."""

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    try:
        sync_playwright = importlib.import_module("playwright.sync_api").sync_playwright
    except ImportError:
        sys.exit("Playwright is not installed: pip install playwright && playwright install chromium")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
        page.goto((ROOT / "docs/index.html").as_uri() + "?theme=light&company=messy")
        page.wait_for_timeout(800)
        top = page.locator("#h-1").bounding_box()
        bottom = page.locator("#ran").bounding_box()
        if not (top and bottom):
            sys.exit("The page has no headline or what-ran panel to photograph.")
        y = top["y"] - 24
        page.screenshot(
            path=str(ROOT / "docs/site-hero.png"),
            full_page=True,
            clip={"x": 20, "y": y, "width": 1240, "height": bottom["y"] + 230 - y},
        )
        browser.close()
    print("wrote docs/site-hero.png")


if __name__ == "__main__":
    main()
