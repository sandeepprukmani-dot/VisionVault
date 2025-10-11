import asyncio
import base64
from playwright.async_api import async_playwright

# ---------------- Dummy Test Code ----------------
dummy_code = """
async def run_test(browser_name='chromium', headless=True):
    from playwright.async_api import async_playwright
    logs = []
    screenshot = None
    success = False

    try:
        async with async_playwright() as p:
            browser = await getattr(p, browser_name).launch(headless=headless)
            page = await browser.new_page()
            await page.goto("https://example.com")
            logs.append("Page loaded successfully")

            # Try finding a widget that may fail
            try:
                await page.wait_for_selector("#nonexistent-widget", timeout=2000)
                logs.append("Widget found!")
            except:
                logs.append("Widget not found, requires healing.")

            screenshot = await page.screenshot()
            success = True
            await browser.close()
    except Exception as e:
        logs.append(f"Error: {e}")

    return {"success": success, "logs": logs, "screenshot": screenshot}
"""

# ---------------- Test Execution ----------------
async def execute_test(test_id, code, browser_name="chromium", headless=True):
    print(f"\n=== Executing Test {test_id} ===")
    local_vars = {}
    exec(code, {}, local_vars)

    if "run_test" not in local_vars:
        print("Error: run_test function not found in code")
        return

    run_test = local_vars["run_test"]
    result = await run_test(browser_name=browser_name, headless=headless)

    print(f"Test {test_id} Result: {'SUCCESS' if result['success'] else 'FAILED'}")
    for log in result["logs"]:
        print(f" - {log}")

    if result["screenshot"]:
        filename = f"screenshot_{test_id}.png"
        with open(filename, "wb") as f:
            f.write(result["screenshot"])
        print(f"Screenshot saved as {filename}")

# ---------------- Healing Execution ----------------
async def execute_healing(test_id, code, browser_name="chromium", headless=True, attempt=1):
    print(f"\n=== Healing Attempt {attempt} for Test {test_id} ===")
    await execute_test(f"{test_id}_healing_{attempt}", code, browser_name, headless)

# ---------------- Main ----------------
if __name__ == "__main__":
    asyncio.run(execute_test("test1", dummy_code))
    asyncio.run(execute_healing("test1", dummy_code, attempt=1))
    asyncio.run(execute_healing("test1", dummy_code, attempt=2))
