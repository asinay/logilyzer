"""Take screenshots of each analyzer section in the sample report."""
import pathlib
from playwright.sync_api import sync_playwright

REPORT = pathlib.Path(__file__).parent.parent / "demo" / "sample_report.html"
OUT = pathlib.Path(__file__).parent.parent / "demo" / "screenshots"
OUT.mkdir(exist_ok=True)

SECTIONS = [
    ("engine", "#sec-engine-log", "a[href='#sec-engine-log']"),
    ("error",  "#sec-error-log",  "a[href='#sec-error-log']"),
    ("access", "#sec-access-log", "a[href='#sec-access-log']"),
    ("dump",   "#sec-dump-log",   "a[href='#sec-dump-log']"),
    ("dhtml",  "#sec-dhtml-log",  "a[href='#sec-dhtml-log']"),
]

with sync_playwright() as p:
    browser = p.chromium.launch()

    # Overview: normal viewport
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(REPORT.as_uri())
    page.wait_for_load_state("networkidle")
    print("  ui-overview...")
    page.wait_for_timeout(1000)
    page.screenshot(path=str(OUT / "ui-overview.png"))
    browser.close()

    # Section shots: very tall viewport so charts have room to render
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 2400})
    page.goto(REPORT.as_uri())
    page.wait_for_load_state("networkidle")

    for name, section_id, nav_selector in SECTIONS:
        print(f"  {name}...")
        page.click(nav_selector)
        page.wait_for_timeout(1200)
        section = page.locator(section_id)
        section.scroll_into_view_if_needed()
        page.wait_for_timeout(600)
        box = section.bounding_box()
        if box:
            clip_h = min(box["height"], 2000)
            page.screenshot(
                path=str(OUT / f"{name}.png"),
                clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": clip_h},
            )
        else:
            section.screenshot(path=str(OUT / f"{name}.png"))

    browser.close()

print(f"Screenshots saved to {OUT}")
