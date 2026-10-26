#!/usr/bin/env python3
"""Full-page screenshots of every dashboard section, for docs/ and reviews.

  python server.py &                      # or: make demo
  python tools/screenshots.py [--url http://127.0.0.1:8000] [--width 1280] [--out docs/screenshots]

Needs ``pip install playwright`` and a Chromium: either ``playwright install chromium``
or an installed Chrome passed with --chrome (default: google-chrome on PATH, if any).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

TABS = ("whatif", "proof", "port", "about")
ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=800)
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "screenshots")
    ap.add_argument("--suffix", default="", help="appended to each file name, e.g. -1920")
    ap.add_argument("--whatif-fuel", default="coal_50_alt_50",
                    help="fuel-mix preset (whatif/kiln.toml) to select so the Fuel & Permit Check shot differs from today")
    ap.add_argument("--chrome", default=shutil.which("google-chrome") or shutil.which("chromium"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chrome) if args.chrome else p.chromium.launch()
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        for tab in TABS:
            page.goto(f"{args.url}/#{tab}")
            page.wait_for_load_state("networkidle")
            page.wait_for_selector('.screen.active .loading', state='detached', timeout=60_000)
            if tab == "whatif" and args.whatif_fuel:
                page.locator(f'#wi-fuel input[value="{args.whatif_fuel}"]').check(force=True)
                page.wait_for_load_state("networkidle")
            page.mouse.wheel(0, -100_000)  # back to the top, so the sticky header sits there in the full-page shot
            page.wait_for_timeout(500)
            path = args.out / f"{tab}{args.suffix}.png"
            page.screenshot(path=str(path), full_page=True)
            print(path)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
