import asyncio
import json
import sys
import os
import base64
import uuid
import socketio
from playwright.async_api import async_playwright

SERVER_URL = os.environ.get('AGENT_SERVER_URL', 'http://127.0.0.1:5000')

sio = socketio.Client(
    reconnection=True,
    reconnection_attempts=5,
    reconnection_delay=1,
    reconnection_delay_max=5,
    logger=False,
    engineio_logger=False
)
agent_id = str(uuid.uuid4())


@sio.event
def connect():
    print(f"Connected to server: {SERVER_URL}")
    available_browsers = detect_browsers()
    sio.emit('agent_register', {
        'agent_id': agent_id,
        'browsers': available_browsers
    })


@sio.event
def disconnect():
    print("Disconnected from server")


@sio.event
def agent_registered(data):
    print(f"Agent registered successfully: {data}")


active_page = None
pending_selector_event = None

@sio.on('execute_on_agent')
def handle_execute(data):
    test_id = data['test_id']
    code = data['code']
    browser = data['browser']
    mode = data['mode']

    print(f"\n{'=' * 50}")
    print(f"Executing test {test_id}")
    print(f"Browser: {browser}, Mode: {mode}")
    print(f"{'=' * 50}\n")

    asyncio.run(execute_test(test_id, code, browser, mode))

@sio.on('execute_healing_attempt')
def handle_healing_attempt(data):
    """Handle healing attempt execution request from server."""
    test_id = data['test_id']
    code = data['code']
    browser = data['browser']
    mode = data['mode']
    attempt = data.get('attempt', 1)

    print(f"\n{'=' * 50}")
    print(f"Healing Attempt {attempt} for test {test_id}")
    print(f"Browser: {browser}, Mode: {mode}")
    print(f"{'=' * 50}\n")

    asyncio.run(execute_healing_attempt(test_id, code, browser, mode))

@sio.on('element_selector_needed')
def handle_element_selector_needed(data):
    global pending_selector_event, active_page
    test_id = data['test_id']
    failed_locator = data['failed_locator']
    
    print(f"\n⚠️  Element selector needed for test {test_id}")
    print(f"Failed locator: {failed_locator}")
    print(f"Please click the correct element in the browser window...")
    
    pending_selector_event = data
    
    if active_page:
        asyncio.run(inject_element_selector(test_id, failed_locator))


def detect_browsers():
    browsers = []
    try:
        import subprocess

        if sys.platform == 'win32':
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            ]
            for path in chrome_paths:
                if os.path.exists(path):
                    browsers.append('chromium')
                    break
        elif sys.platform == 'darwin':
            if os.path.exists('/Applications/Google Chrome.app'):
                browsers.append('chromium')
            if os.path.exists('/Applications/Firefox.app'):
                browsers.append('firefox')
            if os.path.exists('/Applications/Safari.app'):
                browsers.append('webkit')
        else:
            result = subprocess.run(['which', 'google-chrome'], capture_output=True)
            if result.returncode == 0:
                browsers.append('chromium')
            result = subprocess.run(['which', 'firefox'], capture_output=True)
            if result.returncode == 0:
                browsers.append('firefox')

        if not browsers:
            browsers = ['chromium']

    except Exception as e:
        print(f"Browser detection error: {e}")
        browsers = ['chromium']

    print(f"Detected browsers: {browsers}")
    return browsers


async def inject_element_selector(test_id, failed_locator):
    """Inject element selector script into the browser page."""
    global active_page
    
    if not active_page:
        return
    
    try:
        selector_script = """
        (failedLocator) => {
            // Remove any existing overlay
            const existingOverlay = document.getElementById('agent-selector-overlay');
            if (existingOverlay) existingOverlay.remove();
            
            // Create overlay
            const overlay = document.createElement('div');
            overlay.id = 'agent-selector-overlay';
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                z-index: 999999;
                display: flex;
                align-items: center;
                justify-content: center;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            `;
            
            const message = document.createElement('div');
            message.style.cssText = `
                background: linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%);
                color: white;
                padding: 24px 32px;
                border-radius: 16px;
                text-align: center;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
            `;
            message.innerHTML = `
                <div style="font-size: 18px; font-weight: 600; margin-bottom: 8px;">
                    🔍 Element Selector Mode
                </div>
                <div style="font-size: 14px; opacity: 0.9;">
                    Failed locator: <code style="background: rgba(255,255,255,0.2); padding: 4px 8px; border-radius: 4px;">${failedLocator}</code>
                </div>
                <div style="font-size: 14px; margin-top: 16px;">
                    Click on the correct element...
                </div>
            `;
            
            overlay.appendChild(message);
            document.body.appendChild(overlay);
            
            // Enable element selection
            document.addEventListener('mouseover', function highlightElement(e) {
                if (e.target !== overlay && !overlay.contains(e.target)) {
                    e.target.style.outline = '3px solid #8b5cf6';
                    e.target.style.outlineOffset = '2px';
                }
            });
            
            document.addEventListener('mouseout', function removeHighlight(e) {
                if (e.target !== overlay && !overlay.contains(e.target)) {
                    e.target.style.outline = '';
                }
            });
            
            document.addEventListener('click', function selectElement(e) {
                if (e.target !== overlay && !overlay.contains(e.target)) {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    // Generate selector for clicked element
                    const element = e.target;
                    let selector = '';
                    
                    if (element.id) {
                        selector = `#${element.id}`;
                    } else if (element.className) {
                        selector = `.${element.className.split(' ')[0]}`;
                    } else {
                        selector = element.tagName.toLowerCase();
                    }
                    
                    // Store in window for retrieval
                    window.__selectedSelector = selector;
                    
                    // Remove overlay
                    overlay.remove();
                    element.style.outline = '';
                    
                    // Clean up event listeners
                    document.removeEventListener('mouseover', highlightElement);
                    document.removeEventListener('mouseout', removeHighlight);
                    document.removeEventListener('click', selectElement);
                }
            }, true);
        }
        """
        
        await active_page.evaluate(selector_script, failed_locator)
        
        # Wait for user to select element
        for _ in range(300):  # 30 seconds timeout
            await asyncio.sleep(0.1)
            selected = await active_page.evaluate('window.__selectedSelector')
            if selected:
                print(f"✅ User selected element: {selected}")
                sio.emit('element_selected', {
                    'test_id': test_id,
                    'selector': selected
                })
                break
                
    except Exception as e:
        print(f"Element selector injection error: {e}")

async def execute_healing_attempt(test_id, code, browser_name, mode):
    """Execute code for healing attempt - keeps browser open for element selection."""
    global active_page
    headless = mode == 'headless'

    try:
        local_vars = {}
        exec(code, {}, local_vars)

        if 'run_test' not in local_vars:
            sio.emit('healing_attempt_result', {
                'test_id': test_id,
                'success': False,
                'logs': ['Error: Generated code must contain a run_test function'],
                'screenshot': None
            })
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

        print(f"\nHealing attempt for test {test_id}: {'SUCCESS' if result.get('success') else 'FAILED'}")

    except Exception as e:
        print(f"Healing attempt error: {e}")
        sio.emit('healing_attempt_result', {
            'test_id': test_id,
            'success': False,
            'logs': [f'Agent execution error: {str(e)}'],
            'screenshot': None
        })

async def execute_test(test_id, code, browser_name, mode):
    global active_page
    headless = mode == 'headless'

    try:
        sio.emit('agent_log', {
            'test_id': test_id,
            'message': f'Preparing to execute test in {mode} mode...'
        })

        local_vars = {}
        exec(code, {}, local_vars)

        if 'run_test' not in local_vars:
            sio.emit('agent_result', {
                'test_id': test_id,
                'success': False,
                'logs': ['Error: Generated code must contain a run_test function'],
                'screenshot': None
            })
            return

        run_test = local_vars['run_test']

        sio.emit('agent_log', {
            'test_id': test_id,
            'message': f'Launching {browser_name} browser...'
        })

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

        print(f"\nTest {test_id} completed: {'SUCCESS' if result.get('success') else 'FAILED'}")

    except Exception as e:
        print(f"Execution error: {e}")
        sio.emit('agent_result', {
            'test_id': test_id,
            'success': False,
            'logs': [f'Agent execution error: {str(e)}'],
            'screenshot': None
        })


def main():
    print(f"Starting Browser Automation Agent")
    print(f"Agent ID: {agent_id}")
    print(f"Server URL: {SERVER_URL}")
    print(f"\nPress Ctrl+C to stop the agent\n")

    try:
        print("Connecting to server...")
        sio.connect(
            SERVER_URL,
            transports=['websocket', 'polling'],
            wait_timeout=10
        )
        print("Connection established!")
        sio.wait()
    except KeyboardInterrupt:
        print("\nShutting down agent...")
        sio.disconnect()
    except Exception as e:
        print(f"Error connecting to server: {e}")
        print(f"\nMake sure:")
        print(f"1. The server is running at {SERVER_URL}")
        print(f"2. You have set the AGENT_SERVER_URL environment variable correctly")
        print(f"3. You have network connectivity")


if __name__ == '__main__':
    main()
