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

    # Raw log + filter screenshots — use engine section (most rows)
    print("  raw-log-table...")
    page.click("a[href='#sec-engine-log']")
    page.wait_for_timeout(1000)
    # open the raw-log <details>
    page.locator("#sec-engine-log details.raw-log summary").click()
    page.wait_for_timeout(600)
    raw_section = page.locator("#sec-engine-log details.raw-log")
    raw_section.scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    box = raw_section.bounding_box()
    if box:
        clip_h = min(box["height"], 900)
        page.screenshot(
            path=str(OUT / "raw-log-table.png"),
            clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": clip_h},
        )

    print("  raw-log-filter...")
    # reset thread to All, turn off INFO → only ERROR+WARN rows remain
    page.locator(".raw-thread-select[data-table='raw-tbl-1']").select_option("")
    page.locator(".lvl-btn[data-lvl='INFO']").click()
    page.wait_for_timeout(600)
    raw_section.scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    # crop: sidebar (x=0) + content area, from raw-log top, 700px tall
    raw_box = raw_section.bounding_box()
    if raw_box:
        page.screenshot(
            path=str(OUT / "raw-log-filter.png"),
            clip={"x": 0, "y": raw_box["y"] - 20, "width": 1400, "height": 700},
        )
    else:
        page.screenshot(path=str(OUT / "raw-log-filter.png"))

    print("  sidebar-filters...")
    # sidebar-only crop showing level toggle buttons in filtered state
    sidebar = page.locator(".sidebar")
    sb_box = sidebar.bounding_box()
    if sb_box:
        page.screenshot(
            path=str(OUT / "sidebar-filters.png"),
            clip={"x": sb_box["x"], "y": sb_box["y"], "width": sb_box["width"], "height": min(sb_box["height"], 500)},
        )

    browser.close()

print(f"Screenshots saved to {OUT}")
