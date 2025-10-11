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
active_playwright_instance = None  # Playwright instance for cleanup
pending_selector_event = None
event_loop = None  # Will hold reference to main event loop
widget_injection_complete = None  # Event to coordinate browser cleanup with widget lifecycle


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
    """
    FALLBACK ONLY: This event handler is now only a fallback.
    Local agent detects failures and injects immediately for speed.
    This handler only triggers if local detection somehow fails.
    """
    global pending_selector_event, active_page, event_loop
    pending_selector_event = data
    mode = data.get('mode', 'headless')
    
    print(f"\n🔔 SERVER FALLBACK: Received element_selector_needed event (should be rare)")
    print(f"   Test ID: {data['test_id']}")
    print(f"   Failed Locator: {data.get('failed_locator')}")
    
    # Only inject if not already injected locally
    if mode == 'headful' and active_page and event_loop:
        print(f"⚠️  FALLBACK: Server triggered widget injection (local detection may have failed)")
        asyncio.run_coroutine_threadsafe(
            inject_element_selector(data['test_id'], data['failed_locator']),
            event_loop
        )
    else:
        print(f"❌ FALLBACK: Cannot inject widget (mode={mode}, page={'yes' if active_page else 'no'})")


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


def extract_failed_locator_local(error_message):
    """Extract the failed locator from Playwright error messages."""
    import re
    
    # Match patterns like: locator("text='sandeep'") or locator('text="sandeep"')
    patterns = [
        r'locator\(["\']([^"\']+)["\']\)',
        r'waiting for locator\(["\']([^"\']+)["\']\)',
        r'waiting for ([^\s]+)',
        r'Timeout.*?locator\(["\']([^"\']+)["\']\)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, error_message)
        if match:
            return match.group(1)
    
    return None


def modify_code_for_healing(code):
    """Transform code to keep browser open by removing async with context manager.
    The async with automatically closes browser/playwright on exit, so we replace it with direct calls."""
    import re
    
    # Step 1: Find the async with line and its indentation
    lines = code.split('\n')
    new_lines = []
    in_async_with_block = False
    async_with_indent = 0
    block_indent = 0
    
    for i, line in enumerate(lines):
        # Check if this line contains 'async with async_playwright() as var:'
        async_with_match = re.match(r'^(\s*)async with async_playwright\(\) as (\w+):\s*$', line)
        
        if async_with_match and not in_async_with_block:
            # Found the async with line - replace it
            indent = async_with_match.group(1)
            var_name = async_with_match.group(2)
            async_with_indent = len(indent)
            
            # Replace with two lines at the same indentation
            new_lines.append(f'{indent}{var_name} = await async_playwright().start()')
            new_lines.append(f'{indent}globals()["__p_instance__"] = {var_name}')
            
            in_async_with_block = True
            # Determine the block indentation (typically async_with_indent + 4)
            # We'll detect it from the next non-empty line
            if i + 1 < len(lines) and lines[i + 1].strip():
                block_indent = len(lines[i + 1]) - len(lines[i + 1].lstrip())
            else:
                block_indent = async_with_indent + 4  # default assumption
            
        elif in_async_with_block:
            # Check if this line is still part of the async with block
            if line.strip():  # Non-empty line
                current_indent = len(line) - len(line.lstrip())
                
                # If indentation decreased to or below async_with level, we've exited the block
                if current_indent <= async_with_indent:
                    in_async_with_block = False
                    new_lines.append(line)
                else:
                    # Dedent by one level (typically 4 spaces)
                    dedent_amount = block_indent - async_with_indent
                    if current_indent >= block_indent:
                        dedented_line = line[dedent_amount:]
                        new_lines.append(dedented_line)
                    else:
                        # Line with unexpected indentation, keep as is
                        new_lines.append(line)
            else:
                # Empty line - keep as is
                new_lines.append(line)
        else:
            # Not in async with block, keep line as is
            new_lines.append(line)
    
    modified_code = '\n'.join(new_lines)
    
    # Step 2: Inject page capture after page creation
    lines = modified_code.split('\n')
    new_lines = []
    page_captured = False
    
    for line in lines:
        new_lines.append(line)
        # Match any variable name pattern: var = await browser.new_page()
        if re.search(r'(\w+)\s*=\s*await\s+\w+\.new_page\(\)', line) and not page_captured:
            indent = len(line) - len(line.lstrip())
            var_match = re.search(r'(\w+)\s*=\s*await\s+\w+\.new_page\(\)', line)
            if var_match:
                var_name = var_match.group(1)
                new_lines.append(f'{" " * indent}globals()["__healing_page__"] = {var_name}')
                page_captured = True
                print(f"✅ Added page capture injection for variable '{var_name}'")
    
    modified_code = '\n'.join(new_lines)
    
    # Step 3: Replace browser.close() with pass to keep browser open for healing
    modified_code = re.sub(
        r'^(\s*)(await\s+)?browser\.close\(\)',
        r'\1pass  # browser.close() commented for healing',
        modified_code,
        flags=re.MULTILINE
    )
    
    print("✅ Code transformation: async with removed, body dedented, browser stays open for healing")
    return modified_code

async def execute_healing_attempt(test_id, code, browser_name, mode, attempt):
    global active_page, widget_injection_complete, active_playwright_instance
    headless = mode == 'headless'

    try:
        print(
            f"🎯 Starting healing attempt {attempt} for test {test_id} in {'headless' if headless else 'headful'} mode")

        # Clean up any previous instances
        await cleanup_browser()

        # Use original code for headless, modified for headful
        if headless:
            modified_code = code
        else:
            modified_code = modify_code_for_healing(code)
            print("✅ Code modified for headful healing mode")
            print("\n" + "="*80)
            print("MODIFIED CODE FOR DEBUGGING:")
            print("="*80)
            print(modified_code)
            print("="*80 + "\n")

        global_vars = {'__healing_page__': None, '__p_instance__': None}
        local_vars = {}

        # Execute the code
        exec(modified_code, global_vars, local_vars)

        if 'run_test' not in local_vars:
            sio.emit('healing_attempt_result',
                     {'test_id': test_id, 'success': False, 'logs': ['Error: run_test missing'], 'screenshot': None})
            return

        run_test = local_vars['run_test']

        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                run_test(browser_name=browser_name, headless=headless),
                timeout=60.0  # 60 second timeout
            )
        except asyncio.TimeoutError:
            print(f"⏱️  Execution timeout for test {test_id}")
            result = {
                'success': False,
                'logs': ['Execution timeout - browser took too long to respond'],
                'screenshot': None
            }

        # Store page reference for headful mode
        if not headless and global_vars.get('__healing_page__'):
            active_page = global_vars['__healing_page__']
            print(
                f"✅ Page captured for healing - URL: {active_page.url if not active_page.is_closed() else 'CLOSED'}")
        else:
            print(
                f"ℹ️  No page captured (headless: {headless}, page available: {bool(global_vars.get('__healing_page__'))})")

        # Handle screenshot
        screenshot_b64 = None
        if result.get('screenshot'):
            screenshot_b64 = base64.b64encode(result['screenshot']).decode('utf-8')

        print(f"Healing attempt {attempt} for test {test_id}: {'SUCCESS' if result.get('success') else 'FAILED'}")

        # Emit result to server for tracking (but don't wait for response)
        sio.emit('healing_attempt_result', {
            'test_id': test_id,
            'success': result.get('success', False),
            'logs': result.get('logs', []),
            'screenshot': screenshot_b64
        })

        # LOCAL-FIRST HEALING: Detect failure and inject widget immediately
        if not headless and not result.get('success') and active_page:
            # Extract failed locator from error message
            error_msg = ' '.join(result.get('logs', []))
            failed_locator = extract_failed_locator_local(error_msg)
            
            if failed_locator:
                print(f"🎯 LOCAL: Failed locator detected: {failed_locator}")
                print(f"🚀 LOCAL: Injecting widget immediately (no server delay)")
                
                # Inject widget immediately - no waiting for server
                global widget_injection_complete
                widget_injection_complete = asyncio.Event()
                
                try:
                    # Inject widget NOW
                    await inject_element_selector(test_id, failed_locator)
                    
                    # Wait for user interaction (5 minutes timeout)
                    print(f"⏳ Waiting for user to select element (300s timeout)...")
                    try:
                        await asyncio.wait_for(widget_injection_complete.wait(), timeout=300.0)
                        print(f"✅ User selection completed")
                    except asyncio.TimeoutError:
                        print(f"⏱️  User selection timeout (300s)")
                finally:
                    # Always cleanup browser after widget interaction or timeout
                    widget_injection_complete = None
                    print(f"🧹 Cleaning up browser after widget interaction...")
                    await cleanup_browser()
            else:
                print(f"ℹ️  No locator error detected in headful mode - browser will close normally")

    except Exception as e:
        print(f"💥 Healing attempt error: {e}")
        import traceback
        traceback.print_exc()
        sio.emit('healing_attempt_result', {'test_id': test_id, 'success': False, 'logs': [str(e)], 'screenshot': None})
        await cleanup_browser()


async def inject_element_selector(test_id, failed_locator):
    global active_page, widget_injection_complete
    if not active_page:
        print(f"❌ No active page for element selection (test {test_id})")
        if widget_injection_complete:
            widget_injection_complete.set()
        return

    try:
        # Check if page is still valid
        if active_page.is_closed():
            print(f"❌ Page already closed for test {test_id}")
            active_page = None
            if widget_injection_complete:
                widget_injection_complete.set()
            return

        print(f"🎯 Injecting element selector widget for test {test_id} on page: {active_page.url}")

        # JavaScript to inject element selector overlay
        selector_script = """
        (failedLocator) => {
            console.log('🔧 Injecting element selector for locator:', failedLocator);

            // Remove any existing overlay
            const existing = document.getElementById('healing-overlay');
            if (existing) existing.remove();

            const existingBanner = document.getElementById('healing-banner');
            if (existingBanner) existingBanner.remove();

            // Create overlay
            const overlay = document.createElement('div');
            overlay.id = 'healing-overlay';
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                background: rgba(0,0,0,0.7);
                z-index: 999999;
                cursor: crosshair;
            `;

            // Create instruction banner
            const banner = document.createElement('div');
            banner.id = 'healing-banner';
            banner.style.cssText = `
                position: fixed;
                top: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: #ff6b6b;
                color: white;
                padding: 15px 30px;
                border-radius: 8px;
                font-family: Arial, sans-serif;
                font-size: 16px;
                z-index: 1000000;
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                text-align: center;
                max-width: 80%;
            `;
            banner.innerHTML = `
                <strong>🔧 Element Selector Active</strong><br>
                <div style="margin: 8px 0; font-size: 14px;">Failed locator: <code style="background: rgba(255,255,255,0.3); padding: 2px 8px; border-radius: 4px; font-weight: bold;">${failedLocator}</code></div>
                <div style="font-size: 13px; opacity: 0.9;">Click on the correct element in the page below</div>
                <div style="font-size: 11px; opacity: 0.7; margin-top: 5px;">💡 Drag this banner to move it</div>
            `;

            // Make banner draggable
            let isDragging = false;
            let currentX;
            let currentY;
            let initialX;
            let initialY;
            let xOffset = 0;
            let yOffset = 0;

            banner.addEventListener('mousedown', (e) => {
                if (e.target === banner || banner.contains(e.target)) {
                    initialX = e.clientX - xOffset;
                    initialY = e.clientY - yOffset;
                    isDragging = true;
                    banner.style.cursor = 'grabbing';
                }
            });

            document.addEventListener('mousemove', (e) => {
                if (isDragging) {
                    e.preventDefault();
                    currentX = e.clientX - initialX;
                    currentY = e.clientY - initialY;
                    xOffset = currentX;
                    yOffset = currentY;
                    banner.style.transform = `translate(calc(-50% + ${currentX}px), ${currentY}px)`;
                }
            });

            document.addEventListener('mouseup', () => {
                if (isDragging) {
                    isDragging = false;
                    banner.style.cursor = 'grab';
                }
            });

            banner.style.cursor = 'grab';

            let hoveredElement = null;

            // Highlight on hover
            overlay.addEventListener('mousemove', (e) => {
                e.stopPropagation();
                if (hoveredElement) {
                    hoveredElement.style.outline = '';
                    hoveredElement.style.cursor = '';
                }

                // Temporarily hide overlay to get element underneath
                overlay.style.display = 'none';
                const target = document.elementFromPoint(e.clientX, e.clientY);
                overlay.style.display = 'block';
                
                if (target && target !== overlay && target !== banner) {
                    target.style.outline = '3px solid #51cf66';
                    target.style.cursor = 'pointer';
                    hoveredElement = target;
                }
            });

            // Click handler
            overlay.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();

                // Temporarily hide overlay to get element underneath
                overlay.style.display = 'none';
                const target = document.elementFromPoint(e.clientX, e.clientY);
                overlay.style.display = 'block';
                
                if (target && target !== overlay && target !== banner) {
                    // Generate multiple selector strategies
                    let selectors = [];

                    // ID selector
                    if (target.id) {
                        selectors.push(`#${target.id}`);
                    }

                    // Class selector
                    if (target.className && typeof target.className === 'string') {
                        const classes = target.className.trim().split(/\\s+/).join('.');
                        if (classes) {
                            selectors.push(`${target.tagName.toLowerCase()}.${classes}`);
                        }
                    }

                    // Attribute selector
                    if (target.hasAttribute('name')) {
                        selectors.push(`${target.tagName.toLowerCase()}[name="${target.getAttribute('name')}"]`);
                    }

                    // Text content (for buttons, links)
                    const text = target.textContent?.trim();
                    if (text && text.length < 50) {
                        selectors.push(`text="${text}"`);
                    }

                    // Fallback to basic selector
                    if (selectors.length === 0) {
                        selectors.push(target.tagName.toLowerCase());
                    }

                    // Use the first selector
                    const selector = selectors[0];
                    window.__selectedSelector = selector;

                    // Visual feedback
                    banner.style.background = '#51cf66';
                    banner.innerHTML = `
                        <strong>✅ Element Selected!</strong><br>
                        <div style="margin: 8px 0; font-size: 14px;">Selector: <code style="background: rgba(255,255,255,0.3); padding: 2px 8px; border-radius: 4px; font-weight: bold;">${selector}</code></div>
                        <div style="font-size: 12px; opacity: 0.8;">Closing...</div>
                    `;

                    console.log('🎯 User selected element with selector:', selector);

                    // Remove overlay immediately - faster response
                    setTimeout(() => {
                        overlay.remove();
                        banner.remove();
                    }, 500);
                }
            });

            document.body.appendChild(overlay);
            document.body.appendChild(banner);
            window.__selectedSelector = null;

            console.log('✅ Element selector widget injected successfully');
        }
        """

        # Inject the script
        await active_page.evaluate(selector_script, failed_locator)
        print("✅ Element selector widget injected successfully")

        # Poll for user selection (check every 0.2s for faster response, 2-minute timeout)
        print("⏳ Polling for user element selection...")
        for i in range(600):  # 600 * 0.2s = 120s = 2 minutes
            await asyncio.sleep(0.2)
            selected = await active_page.evaluate('() => window.__selectedSelector')
            if selected:
                print(f"✅ User selected element: {selected}")
                sio.emit('element_selected', {'test_id': test_id, 'selector': selected})
                # Signal completion - browser will be cleaned up by caller
                if widget_injection_complete:
                    widget_injection_complete.set()
                return
        
        print("⏱️  Element selection polling complete (300s)")

    except Exception as e:
        print(f"❌ Element selector injection error: {e}")
    finally:
        # Signal completion (browser stays open, will be cleaned up by caller)
        if widget_injection_complete:
            widget_injection_complete.set()

async def cleanup_browser():
    """Clean up browser, playwright instance, and page references."""
    global active_page, active_playwright_instance
    if active_page:
        try:
            browser = active_page.context.browser
            await browser.close()
            print("✅ Browser closed after healing attempt")
        except Exception as e:
            print(f"Browser cleanup error: {e}")
        finally:
            active_page = None
    
    if active_playwright_instance:
        try:
            await active_playwright_instance.stop()
            print("✅ Playwright instance stopped")
        except Exception as e:
            print(f"Playwright cleanup error: {e}")
        finally:
            active_playwright_instance = None


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

        # Create and store event loop reference (use global keyword)
        global event_loop
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
