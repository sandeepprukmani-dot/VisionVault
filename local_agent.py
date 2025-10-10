import os
import sys
import uuid
import base64
import time
import socketio
import asyncio
from playwright.async_api import async_playwright

SERVER_URL = os.environ.get('AGENT_SERVER_URL', 'http://127.0.0.1:6890')
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
    asyncio.get_event_loop().create_task(
        execute_test(data['test_id'], data['code'], data['browser'], data['mode'])
    )


@sio.on('execute_healing_attempt')
def handle_healing_attempt(data):
    asyncio.get_event_loop().create_task(
        execute_healing_attempt(data['test_id'], data['code'], data['browser'], data['mode'], data.get('attempt', 1))
    )


@sio.on('element_selector_needed')
def handle_element_selector_needed(data):
    global pending_selector_event, active_page
    pending_selector_event = data
    if active_page:
        asyncio.get_event_loop().create_task(
            inject_element_selector(data['test_id'], data['failed_locator'])
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
        local_vars = {}
        exec(code, {}, local_vars)
        if 'run_test' not in local_vars:
            sio.emit('healing_attempt_result', {'test_id': test_id, 'success': False, 'logs': ['Error: run_test missing'], 'screenshot': None})
            return

        run_test = local_vars['run_test']
        result = await run_test(browser_name=browser_name, headless=headless)

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
        sio.emit('healing_attempt_result', {'test_id': test_id, 'success': False, 'logs': [str(e)], 'screenshot': None})


async def inject_element_selector(test_id, failed_locator):
    global active_page
    if not active_page:
        return

    try:
        selector_script = """(failedLocator) => { /* your overlay + click logic here */ }"""
        await active_page.evaluate(selector_script, failed_locator)

        # Wait for user selection
        for _ in range(300):
            await asyncio.sleep(0.1)
            selected = await active_page.evaluate('window.__selectedSelector')
            if selected:
                print(f"User selected element: {selected}")
                sio.emit('element_selected', {'test_id': test_id, 'selector': selected})
                break
    except Exception as e:
        print(f"Element selector injection error: {e}")


# ---------------- Main ----------------

def main():
    print(f"Starting Browser Automation Agent")
    print(f"Agent ID: {agent_id}")
    print(f"Server URL: {SERVER_URL}\n")
    print("Press Ctrl+C to stop the agent\n")

    try:
        print("Connecting to server...")
        sio.connect(SERVER_URL)
        print("Connection established! Waiting for tasks...\n")

        # Keep the agent alive indefinitely
        loop = asyncio.get_event_loop()
        loop.run_forever()

    except KeyboardInterrupt:
        print("\nShutting down agent...")
        if sio.connected:
            sio.disconnect()
    except Exception as e:
        print(f"Connection error: {e}")


if __name__ == '__main__':
    main()
