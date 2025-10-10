import os
import sys
import uuid
import base64
import time
import socketio
import asyncio
from playwright.async_api import async_playwright

SERVER_URL = os.environ.get('AGENT_SERVER_URL', 'http://127.0.0.1:7890')
agent_id = str(uuid.uuid4())

# Socket.IO client
sio = socketio.Client(
    reconnection=True,
    reconnection_attempts=5,
    reconnection_delay=1,
    reconnection_delay_max=5,
    logger=True,           # Enable logging
    engineio_logger=True
)

# Global state
active_page = None
pending_selector_event = None
event_loop = None  # Will hold reference to main event loop


def detect_browsers():
    browsers = []
    try:
        import subprocess
        if sys.platform == 'win32':
            paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            ]
            if any(os.path.exists(p) for p in paths):
                browsers.append('chromium')
        elif sys.platform == 'darwin':
            if os.path.exists('/Applications/Google Chrome.app'):
                browsers.append('chromium')
            if os.path.exists('/Applications/Firefox.app'):
                browsers.append('firefox')
            if os.path.exists('/Applications/Safari.app'):
                browsers.append('webkit')
        else:
            if subprocess.run(['which', 'google-chrome'], capture_output=True).returncode == 0:
                browsers.append('chromium')
            if subprocess.run(['which', 'firefox'], capture_output=True).returncode == 0:
                browsers.append('firefox')
        if not browsers:
            browsers = ['chromium']
    except Exception as e:
        print(f"Browser detection error: {e}")
        browsers = ['chromium']

    print(f"Detected browsers: {browsers}")
    return browsers


# ---------------- Socket.IO Events ----------------

@sio.event
def connect():
    print(f"Connected to server: {SERVER_URL}")
    available_browsers = detect_browsers()
    sio.emit('agent_register', {'agent_id': agent_id, 'browsers': available_browsers})


@sio.event
def disconnect():
    print("Disconnected from server")


@sio.event
def agent_registered(data):
    print(f"Agent registered successfully: {data}")


@sio.on('execute_on_agent')
def handle_execute(data):
    global event_loop
    if event_loop:
        asyncio.run_coroutine_threadsafe(
            execute_test(data['test_id'], data['code'], data['browser'], data['mode']),
            event_loop
        )


@sio.on('execute_healing_attempt')
def handle_healing_attempt(data):
    global event_loop
    if event_loop:
        asyncio.run_coroutine_threadsafe(
            execute_healing_attempt(data['test_id'], data['code'], data['browser'], data['mode'], data.get('attempt', 1)),
            event_loop
        )


@sio.on('element_selector_needed')
def handle_element_selector_needed(data):
    global pending_selector_event, active_page, event_loop
    pending_selector_event = data
    # Only inject widget in headful mode
    mode = data.get('mode', 'headless')
    if mode == 'headful' and active_page and event_loop:
        print(f"🔧 Injecting element selector widget in headful mode for test {data['test_id']}")
        asyncio.run_coroutine_threadsafe(
            inject_element_selector(data['test_id'], data['failed_locator']),
            event_loop
        )
    elif mode != 'headful':
        print(f"⚠️  Element selector widget requires headful mode (current mode: {mode})")
    elif not active_page:
        print(f"⚠️  No active page available for widget injection")


# ---------------- Task Execution ----------------

async def execute_test(test_id, code, browser_name, mode):
    global active_page
    headless = mode == 'headless'

    try:
        sio.emit('agent_log', {'test_id': test_id, 'message': f'Preparing to execute test in {mode} mode...'})

        local_vars = {}
        exec(code, {}, local_vars)
        if 'run_test' not in local_vars:
            sio.emit('agent_result', {'test_id': test_id, 'success': False, 'logs': ['Error: run_test missing'], 'screenshot': None})
            return

        run_test = local_vars['run_test']
        result = await run_test(browser_name=browser_name, headless=headless)

        screenshot_b64 = None
        if result.get('screenshot'):
            screenshot_b64 = base64.b64encode(result['screenshot']).decode('utf-8')

        sio.emit('agent_result', {
            'test_id': test_id,
            'success': result.get('success', False),
            'logs': result.get('logs', []),
            'screenshot': screenshot_b64
        })

        print(f"Test {test_id} completed: {'SUCCESS' if result.get('success') else 'FAILED'}")

    except Exception as e:
        print(f"Execution error: {e}")
        sio.emit('agent_result', {'test_id': test_id, 'success': False, 'logs': [str(e)], 'screenshot': None})


async def execute_healing_attempt(test_id, code, browser_name, mode, attempt):
    global active_page
    headless = mode == 'headless'

    try:
        # Modify code to keep browser/page open for healing AND capture page reference
        modified_code = code
        
        # 1. Replace browser.close() with pass to keep browser open and avoid empty blocks
        import re
        modified_code = re.sub(
            r'await browser\.close\(\)',
            'pass  # browser.close() removed for healing',
            modified_code
        )
        
        # 2. Inject code to capture page reference globally
        if 'page = await browser.new_page()' in modified_code:
            modified_code = modified_code.replace(
                'page = await browser.new_page()',
                'page = await browser.new_page()\n            globals()["__healing_page__"] = page'
            )
        
        global_vars = {'__healing_page__': None}
        local_vars = {}
        exec(modified_code, global_vars, local_vars)
        
        if 'run_test' not in local_vars:
            sio.emit('healing_attempt_result', {'test_id': test_id, 'success': False, 'logs': ['Error: run_test missing'], 'screenshot': None})
            return

        run_test = local_vars['run_test']
        result = await run_test(browser_name=browser_name, headless=headless)
        
        # Store page reference from globals
        if global_vars.get('__healing_page__'):
            active_page = global_vars['__healing_page__']
            print(f"✅ Page captured for test {test_id} - browser will stay open for healing")
        else:
            print(f"⚠️  Could not capture page for test {test_id}")

        screenshot_b64 = None
        if result.get('screenshot'):
            screenshot_b64 = base64.b64encode(result['screenshot']).decode('utf-8')

        sio.emit('healing_attempt_result', {
            'test_id': test_id,
            'success': result.get('success', False),
            'logs': result.get('logs', []),
            'screenshot': screenshot_b64
        })

        print(f"Healing attempt {attempt} for test {test_id}: {'SUCCESS' if result.get('success') else 'FAILED'}")

    except Exception as e:
        print(f"Healing attempt error: {e}")
        import traceback
        traceback.print_exc()
        sio.emit('healing_attempt_result', {'test_id': test_id, 'success': False, 'logs': [str(e)], 'screenshot': None})


async def inject_element_selector(test_id, failed_locator):
    global active_page
    if not active_page:
        print(f"❌ No active page for element selection (test {test_id})")
        return

    try:
        print(f"✅ Injecting element selector widget on the launched browser page for test {test_id}")
        # JavaScript to inject element selector overlay
        selector_script = """
        (failedLocator) => {
            // Remove any existing overlay
            const existing = document.getElementById('healing-overlay');
            if (existing) existing.remove();
            
            // Create overlay
            const overlay = document.createElement('div');
            overlay.id = 'healing-overlay';
            overlay.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 999999; cursor: crosshair;';
            
            // Create instruction banner
            const banner = document.createElement('div');
            banner.style.cssText = 'position: fixed; top: 20px; left: 50%; transform: translateX(-50%); background: #ff6b6b; color: white; padding: 15px 30px; border-radius: 8px; font-family: Arial; font-size: 16px; z-index: 1000000; box-shadow: 0 4px 6px rgba(0,0,0,0.3);';
            banner.innerHTML = `<strong>🔧 Element Selector Active</strong><br>Click on the correct element to fix: <code style="background: rgba(255,255,255,0.2); padding: 2px 6px; border-radius: 3px;">${failedLocator}</code>`;
            
            // Element highlight on hover
            let hoveredElement = null;
            overlay.addEventListener('mousemove', (e) => {
                if (hoveredElement) {
                    hoveredElement.style.outline = '';
                }
                const target = document.elementFromPoint(e.clientX, e.clientY);
                if (target && target !== overlay && target !== banner) {
                    target.style.outline = '3px solid #51cf66';
                    hoveredElement = target;
                }
            });
            
            // Click handler to select element
            overlay.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const target = document.elementFromPoint(e.clientX, e.clientY);
                if (target && target !== overlay && target !== banner) {
                    // Generate selector for clicked element
                    let selector = '';
                    if (target.id) {
                        selector = `#${target.id}`;
                    } else if (target.className) {
                        const classes = Array.from(target.classList).join('.');
                        selector = `${target.tagName.toLowerCase()}.${classes}`;
                    } else {
                        selector = target.tagName.toLowerCase();
                    }
                    
                    // Store selection
                    window.__selectedSelector = selector;
                    
                    // Visual feedback
                    target.style.outline = '3px solid #51cf66';
                    banner.style.background = '#51cf66';
                    banner.innerHTML = `<strong>✅ Element Selected!</strong><br>Selector: <code style="background: rgba(255,255,255,0.2); padding: 2px 6px; border-radius: 3px;">${selector}</code>`;
                    
                    // Remove overlay after 1 second
                    setTimeout(() => {
                        overlay.remove();
                        banner.remove();
                    }, 1000);
                }
            });
            
            document.body.appendChild(overlay);
            document.body.appendChild(banner);
            
            // Initialize
            window.__selectedSelector = null;
        }
        """
        
        print(f"\n🎯 Injecting element selector for test {test_id}")
        print(f"   Failed locator: {failed_locator}")
        print(f"   Please click on the correct element in your browser...\n")
        
        await active_page.evaluate(selector_script, failed_locator)

        # Wait for user selection
        for i in range(300):  # 30 seconds total
            await asyncio.sleep(0.1)
            selected = await active_page.evaluate('() => window.__selectedSelector')
            if selected:
                print(f"✅ User selected element: {selected}")
                sio.emit('element_selected', {'test_id': test_id, 'selector': selected})
                return
        
        print(f"⏱️  Element selection timed out for test {test_id}")
        
    except Exception as e:
        print(f"Element selector injection error: {e}")


# ---------------- Dummy Test on Startup ----------------
async def run_dummy_test():
    from playwright.async_api import async_playwright
    try:
        print("\n🚀 Running dummy browser test...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)  # headless=False to see the browser
            page = await browser.new_page()
            await page.goto("https://example.com")
            title = await page.title()
            print(f"✅ Dummy test page title: {title}")
            await browser.close()
            print("✅ Dummy test completed!\n")
    except Exception as e:
        print(f"❌ Dummy test failed: {e}")

# ---------------- Main ----------------

def main():
    global event_loop

    print(f"Starting Browser Automation Agent")
    print(f"Agent ID: {agent_id}")
    print(f"Server URL: {SERVER_URL}\n")
    print("Press Ctrl+C to stop the agent\n")

    try:
        print("Connecting to server...")
        sio.connect(SERVER_URL)
        print("Connection established! Waiting for tasks...\n")

        # Create and store event loop reference
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)

        # Keep the agent alive indefinitely
        event_loop.run_forever()

    except KeyboardInterrupt:
        print("\nShutting down agent...")
        if sio.connected:
            sio.disconnect()
        if event_loop:
            event_loop.close()
    except Exception as e:
        print(f"Connection error: {e}")
        if event_loop:
            event_loop.close()


if __name__ == '__main__':
    main()
