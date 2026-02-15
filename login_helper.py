"""Quick helper to re-authenticate X.com browser session."""
import sys
import time
from playwright.sync_api import sync_playwright

profile = "data/browser-profile"
print(f"Opening browser with profile: {profile}")
print("Log in to X.com, then CLOSE the browser window to save the session.")

pw = sync_playwright().start()
ctx = pw.chromium.launch_persistent_context(
    user_data_dir=profile,
    headless=False,
    channel="chrome",
    viewport={"width": 1280, "height": 900},
    args=[
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
    ],
    ignore_default_args=["--enable-automation"],
)
page = ctx.new_page()
page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)

# Wait until the user closes the browser
try:
    while True:
        if not ctx.pages:
            break
        time.sleep(1)
except Exception:
    pass

ctx.close()
pw.stop()
print("Session saved! You can now use 'Run Now' on the dashboard.")
