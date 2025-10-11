import os
import sys
import uuid
import base64
import time
import socketio
import asyncio
from playwright.async_api import async_playwright

SERVER_URL = os.environ.get('AGENT_SERVER_URL',
                            'https://bf6da548-44ce-4eaf-808d-73cf687e1702-00-36thk1trv5zjp.pike.replit.dev')
agent_id = str(uuid.uuid4())

# Socket.IO client
sio = socketio.Client(
    reconnection=True,
    reconnection_attempts=5,
    reconnection_delay=1,
    reconnection_delay_max=5,
    logger=True,
    engineio_logger=True
)

# Global state
active_page = None
active_playwright_instance = None
pending_selector_event = None
event_loop = None
widget_injection_complete = None


# ---------------- Browser Detection ----------------

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
            execute_healing_attempt(data['test_id'], data['code'], data['browser'], data['mode'],
                                    data.get('attempt', 1)),
            event_loop
        )


@sio.on('element_selector_needed')
def handle_element_selector_needed(data):
    global pending_selector_event, active_page, event_loop
    pending_selector_event = data
    mode = data.get('mode', 'headless')

    if mode == 'headful' and active_page and event_loop:
        asyncio.run_coroutine_threadsafe(
            inject_element_selector(data['test_id'], data['failed_locator']),
            event_loop
        )


# ---------------- Task Execution ----------------

async def execute_test(test_id, code, browser_name, mode):
    global active_page
    headless = mode == 'headless'

    try:
        sio.emit('agent_log', {'test_id': test_id, 'message': f'Preparing to execute test in {mode} mode...'})

        local_vars = {}
        exec(code, {}, local_vars)
        if 'run_test' not in local_vars:
            sio.emit('agent_result',
                     {'test_id': test_id, 'success': False, 'logs': ['Error: run_test missing'], 'screenshot': None})
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

    except Exception as e:
        sio.emit('agent_result', {'test_id': test_id, 'success': False, 'logs': [str(e)], 'screenshot': None})


# ---------------- Helpers ----------------

def extract_failed_locator_local(error_message):
    import re
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
    import re
    lines = code.split('\n')
    new_lines = []
    in_async_with_block = False
    async_with_indent = 0
    block_indent = 0

    for i, line in enumerate(lines):
        async_with_match = re.match(r'^(\s*)async with async_playwright\(\) as (\w+):\s*$', line)
        if async_with_match and not in_async_with_block:
            indent = async_with_match.group(1)
            var_name = async_with_match.group(2)
            async_with_indent = len(indent)
            new_lines.append(f'{indent}{var_name} = await async_playwright().start()')
            new_lines.append(f'{indent}globals()["__p_instance__"] = {var_name}')
            in_async_with_block = True
            if i + 1 < len(lines) and lines[i + 1].strip():
                block_indent = len(lines[i + 1]) - len(lines[i + 1].lstrip())
            else:
                block_indent = async_with_indent + 4
        elif in_async_with_block:
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= async_with_indent:
                in_async_with_block = False
                new_lines.append(line)
            else:
                dedent_amount = block_indent - async_with_indent
                if current_indent >= block_indent:
                    new_lines.append(line[dedent_amount:])
                else:
                    new_lines.append(line)
        else:
            new_lines.append(line)

    modified_code = '\n'.join(new_lines)

    # Inject page capture
    lines = modified_code.split('\n')
    new_lines = []
    page_captured = False
    for line in lines:
        new_lines.append(line)
        if re.search(r'(\w+)\s*=\s*await\s+\w+\.new_page\(\)', line) and not page_captured:
            var_match = re.search(r'(\w+)\s*=\s*await\s+\w+\.new_page\(\)', line)
            if var_match:
                var_name = var_match.group(1)
                new_lines.append(f'{" " * (len(line) - len(line.lstrip()))}globals()["__healing_page__"] = {var_name}')
                page_captured = True
    modified_code = '\n'.join(new_lines)

    modified_code = re.sub(r'^(\s*)(await\s+)?browser\.close\(\)', r'\1pass  # browser.close() commented for healing',
                           modified_code, flags=re.MULTILINE)
    return modified_code


async def execute_healing_attempt_step(test_id, step_func, failed_locator, page):
    try:
        healed_code = step_func['locator'].replace(failed_locator, step_func['healed_selector'])
        globals()['__healing_page__'] = page
        local_vars = {}
        exec(healed_code, globals(), local_vars)
        if 'step' in local_vars:
            result = await local_vars['step'](page)
        else:
            result = {'success': False, 'logs': ['Step function missing'], 'screenshot': None}
        sio.emit('healing_step_result', {
            'test_id': test_id,
            'step_name': step_func['name'],
            'success': result.get('success', False),
            'logs': result.get('logs', []),
            'selector': step_func['healed_selector']
        })
    except Exception as e:
        sio.emit('healing_step_result', {
            'test_id': test_id,
            'step_name': step_func['name'],
            'success': False,
            'logs': [str(e)],
            'selector': step_func['healed_selector']
        })


# ---------------- Element Selector Widget ----------------

async def inject_element_selector(test_id, failed_locator):
    global active_page, widget_injection_complete
    if not active_page or active_page.is_closed():
        if widget_injection_complete: widget_injection_complete.set()
        return

    selector_script = """
    (failedLocator) => {
        const overlay = document.createElement('div');
        overlay.id = 'healing-overlay';
        overlay.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;background:rgba(0,0,0,0.7);z-index:999999;cursor:crosshair';
        const banner = document.createElement('div');
        banner.id = 'healing-banner';
        banner.style.cssText = 'position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#ff6b6b;color:white;padding:15px 30px;border-radius:8px;font-family:Arial;font-size:16px;z-index:1000000;text-align:center';
        banner.innerHTML = `<strong>🔧 Element Selector Active</strong><br>Failed locator: <code>${failedLocator}</code><br>Click element below`;
        document.body.appendChild(overlay);
        document.body.appendChild(banner);
        window.__selectedSelector = null;

        overlay.addEventListener('click', e => {
            e.preventDefault(); e.stopPropagation();
            overlay.style.display = 'none';
            const target = document.elementFromPoint(e.clientX, e.clientY);
            overlay.style.display = 'block';
            if(target && target!==overlay && target!==banner){
                let sel = target.id ? `#${target.id}` : target.tagName.toLowerCase();
                window.__selectedSelector = sel;
                banner.style.background = '#51cf66';
                banner.innerHTML = `✅ Element Selected: <code>${sel}</code>`;
                setTimeout(()=>{overlay.remove(); banner.remove();}, 500);
            }
        });
    }
    """
    await active_page.evaluate(selector_script, failed_locator)
    for _ in range(600):
        await asyncio.sleep(0.2)
        selected = await active_page.evaluate('() => window.__selectedSelector')
        if selected:
            sio.emit('element_selected', {'test_id': test_id, 'selector': selected, 'failed_locator': failed_locator})
            if widget_injection_complete: widget_injection_complete.set()
            return
    if widget_injection_complete: widget_injection_complete.set()


# ---------------- Healing Attempt ----------------

async def execute_healing_attempt(test_id, code, browser_name, mode, attempt):
    global active_page, widget_injection_complete
    headless = mode == 'headless'

    try:
        await cleanup_browser()
        modified_code = code if headless else modify_code_for_healing(code)
        local_vars = {}
        exec(modified_code, globals(), local_vars)
        if 'run_test' not in local_vars:
            return

        run_test = local_vars['run_test']
        result = await run_test(browser_name=browser_name, headless=headless)
        if not headless and globals().get('__healing_page__'):
            active_page = globals()['__healing_page__']

        if not headless and not result.get('success') and active_page:
            error_msg = ' '.join(result.get('logs', []))
            failed_locator = extract_failed_locator_local(error_msg)
            if failed_locator:
                widget_injection_complete = asyncio.Event()
                await inject_element_selector(test_id, failed_locator)
                try:
                    await asyncio.wait_for(widget_injection_complete.wait(), timeout=300)
                    healed_selector = await active_page.evaluate('() => window.__selectedSelector')
                    step_func = {'name': 'failing_step', 'locator': code, 'healed_selector': healed_selector}
                    await execute_healing_attempt_step(test_id, step_func, failed_locator, active_page)
                except asyncio.TimeoutError:
                    print("User selection timeout")
    except Exception as e:
        print(f"Healing attempt error: {e}")
        import traceback;
        traceback.print_exc()
    finally:
        await cleanup_browser()


# ---------------- Browser Cleanup ----------------

async def cleanup_browser():
    global active_page, active_playwright_instance
    if active_page:
        try:
            browser = active_page.context.browser
            await browser.close()
        except:
            pass
        finally:
            active_page = None
    if active_playwright_instance:
        try:
            await active_playwright_instance.stop()
        except:
            pass
        finally:
            active_playwright_instance = None


# ---------------- Main ----------------

def main():
    global event_loop
    print(f"Starting Browser Automation Agent (ID: {agent_id})")
    try:
        sio.connect(SERVER_URL)
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)
        event_loop.run_forever()
    except KeyboardInterrupt:
        if sio.connected: sio.disconnect()
        if event_loop: event_loop.close()


if __name__ == '__main__':
    main()
