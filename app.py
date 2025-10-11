from gevent import monkey
monkey.patch_all()

import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from openai import OpenAI
from executor import ServerExecutor
from healing_executor import HealingExecutor
from code_validator import CodeValidator
import base64
import asyncio

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'dev-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = 'uploads'
CORS(app)
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins="*")

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'screenshots'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'logs'), exist_ok=True)

openai_api_key = os.environ.get('OPENAI_API_KEY','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')
if not openai_api_key:
    raise Exception("OPENAI_API_KEY environment variable is not set!")

client = OpenAI(api_key=openai_api_key)
connected_agents = {}
active_healing_executors = {}

def init_db():
    conn = sqlite3.connect('automation.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS test_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  command TEXT NOT NULL,
                  generated_code TEXT NOT NULL,
                  healed_code TEXT,
                  browser TEXT,
                  mode TEXT,
                  execution_location TEXT,
                  status TEXT,
                  logs TEXT,
                  screenshot_path TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()


def generate_playwright_code(natural_language_command=None, browser='chromium'):
    # Dummy function: returns the given run_test code
    return """
async def run_test(browser_name='chromium', headless=True):
    from playwright.async_api import async_playwright
    logs = []
    screenshot = None
    browser = None
    page = None
    try:
        async with async_playwright() as p:
            browser = await getattr(p, browser_name).launch(headless=headless)
            page = await browser.new_page()
            await page.goto("https://practicetestautomation.com/practice-test-login/")
            logs.append("Navigated to the login page")

            await page.fill("input[name='username']", "student")
            logs.append("Filled username")

            await page.fill("input[name='password']", "Password123")
            logs.append("Filled password")

            await page.click("button[type='submit']")
            logs.append("Clicked submit button")

            # CRITICAL: Screenshot BEFORE closing
            screenshot = await page.screenshot()
            await browser.close()
            return {'success': True, 'logs': logs, 'screenshot': screenshot}
    except Exception as e:
        logs.append(f"Error: {str(e)}")
        # Try to get screenshot even on error, BEFORE cleanup
        if page:
            try:
                screenshot = await page.screenshot()
            except:
                pass
        if browser:
            try:
                await browser.close()
            except:
                pass
        return {'success': False, 'logs': logs, 'screenshot': screenshot}
"""


def igenerate_playwright_code(natural_language_command, browser='chromium'):
    if not client:
        raise Exception("OpenAI API key not configured. Please set the OPENAI_API_KEY environment variable.")
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": """You are an expert at converting natural language commands into Playwright Python code.
Generate complete, executable Playwright code that:
1. Uses async/await syntax
2. Includes proper browser launch with the specified browser
3. Has error handling with proper cleanup
4. Returns a dict with 'success', 'logs', and 'screenshot' keys
5. ALWAYS takes screenshot BEFORE closing browser (CRITICAL)
6. The code should be a complete async function named 'run_test' that takes browser_name and headless parameters

CRITICAL RULE: Always take screenshot BEFORE closing browser/page. Never close browser before screenshot.

Example structure:
async def run_test(browser_name='chromium', headless=True):
    from playwright.async_api import async_playwright
    logs = []
    screenshot = None
    browser = None
    page = None
    try:
        async with async_playwright() as p:
            browser = await getattr(p, browser_name).launch(headless=headless)
            page = await browser.new_page()
            # Your automation code here
            logs.append("Step completed")
            # CRITICAL: Screenshot BEFORE closing
            screenshot = await page.screenshot()
            await browser.close()
            return {'success': True, 'logs': logs, 'screenshot': screenshot}
    except Exception as e:
        logs.append(f"Error: {str(e)}")
        # Try to get screenshot even on error, BEFORE cleanup
        if page:
            try:
                screenshot = await page.screenshot()
            except:
                pass
        if browser:
            try:
                await browser.close()
            except:
                pass
        return {'success': False, 'logs': logs, 'screenshot': screenshot}

Only return the function code, no explanations."""},
                {"role": "user", "content": f"Convert this to Playwright code for {browser}: {natural_language_command}"}
            ],
            temperature=0.3
        )

        code = response.choices[0].message.content.strip()
        if code.startswith('```python'):
            code = code[9:]
        if code.startswith('```'):
            code = code[3:]
        if code.endswith('```'):
            code = code[:-3]

        return code.strip()
    except Exception as e:
        raise Exception(f"OpenAI API error: {str(e)}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/history')
def get_history():
    conn = sqlite3.connect('automation.db')
    c = conn.cursor()
    c.execute('SELECT * FROM test_history ORDER BY created_at DESC LIMIT 50')
    rows = c.fetchall()
    conn.close()
    
    history = []
    for row in rows:
        history.append({
            'id': row[0],
            'command': row[1],
            'generated_code': row[2],
            'browser': row[3],
            'mode': row[4],
            'execution_location': row[5],
            'status': row[6],
            'logs': row[7],
            'screenshot_path': row[8],
            'created_at': row[9]
        })
    
    return jsonify(history)

@app.route('/api/execute', methods=['POST'])
def execute_test():
    data = request.json
    command = data.get('command')
    browser = data.get('browser', 'chromium')
    mode = data.get('mode', 'headless')
    execution_location = data.get('execution_location', 'server')
    use_healing = data.get('use_healing', True)
    
    if not command:
        return jsonify({'error': 'Command is required'}), 400
    
    try:
        generated_code = generate_playwright_code(command, browser)
        
        validator = CodeValidator()
        if not validator.validate(generated_code):
            error_msg = "Generated code failed security validation: " + "; ".join(validator.get_errors())
            return jsonify({'error': error_msg}), 400
        
        conn = sqlite3.connect('automation.db')
        c = conn.cursor()
        c.execute('INSERT INTO test_history (command, generated_code, browser, mode, execution_location, status) VALUES (?, ?, ?, ?, ?, ?)',
                  (command, generated_code, browser, mode, execution_location, 'pending'))
        test_id = c.lastrowid
        conn.commit()
        conn.close()
        
        if execution_location == 'server':
            if use_healing:
                socketio.start_background_task(execute_with_healing, test_id, generated_code, browser, mode)
            else:
                socketio.start_background_task(execute_on_server, test_id, generated_code, browser, mode)
        else:
            # Agent execution - find agent's session ID
            agent_sid = None
            for sid in connected_agents:
                agent_sid = sid
                break  # Get the first available agent
            
            if use_healing:
                socketio.start_background_task(execute_agent_with_healing, test_id, generated_code, browser, mode)
            else:
                if agent_sid:
                    socketio.emit('execute_on_agent', {
                        'test_id': test_id,
                        'code': generated_code,
                        'browser': browser,
                        'mode': mode
                    }, to=agent_sid)
                else:
                    return jsonify({'error': 'No agent connected'}), 503
        
        return jsonify({'test_id': test_id, 'code': generated_code})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def execute_on_server(test_id, code, browser, mode):
    executor = ServerExecutor()
    headless = mode == 'headless'
    
    socketio.emit('execution_status', {
        'test_id': test_id,
        'status': 'running',
        'message': f'Executing on server in {mode} mode...'
    })
    
    result = executor.execute(code, browser, headless)
    
    screenshot_path = None
    if result.get('screenshot'):
        screenshot_path = f"screenshots/test_{test_id}.png"
        with open(os.path.join(app.config['UPLOAD_FOLDER'], screenshot_path), 'wb') as f:
            f.write(result['screenshot'])
    
    logs_json = json.dumps(result.get('logs', []))
    status = 'success' if result.get('success') else 'failed'
    
    conn = sqlite3.connect('automation.db')
    c = conn.cursor()
    c.execute('UPDATE test_history SET status=?, logs=?, screenshot_path=? WHERE id=?',
              (status, logs_json, screenshot_path, test_id))
    conn.commit()
    conn.close()
    
    socketio.emit('execution_complete', {
        'test_id': test_id,
        'status': status,
        'logs': result.get('logs', []),
        'screenshot_path': screenshot_path
    })

def execute_with_healing(test_id, code, browser, mode):
    healing_executor = HealingExecutor(socketio, api_key=openai_api_key)
    active_healing_executors[test_id] = healing_executor
    headless = mode == 'headless'
    
    socketio.emit('execution_status', {
        'test_id': test_id,
        'status': 'running',
        'message': f'Executing with healing in {mode} mode...'
    })
    
    try:
        result = asyncio.run(healing_executor.execute_with_healing(code, browser, headless, test_id))
    finally:
        if test_id in active_healing_executors:
            del active_healing_executors[test_id]
    
    screenshot_path = None
    if result.get('screenshot'):
        screenshot_path = f"screenshots/test_{test_id}.png"
        with open(os.path.join(app.config['UPLOAD_FOLDER'], screenshot_path), 'wb') as f:
            f.write(result['screenshot'])
    
    logs_json = json.dumps(result.get('logs', []))
    status = 'success' if result.get('success') else 'failed'
    healed_code = result.get('healed_script')
    
    conn = sqlite3.connect('automation.db')
    c = conn.cursor()
    c.execute('UPDATE test_history SET status=?, logs=?, screenshot_path=?, healed_code=? WHERE id=?',
              (status, logs_json, screenshot_path, healed_code, test_id))
    conn.commit()
    conn.close()
    
    socketio.emit('execution_complete', {
        'test_id': test_id,
        'status': status,
        'logs': result.get('logs', []),
        'screenshot_path': screenshot_path,
        'healed_script': healed_code,
        'failed_locators': result.get('failed_locators', [])
    })

def execute_agent_with_healing(test_id, code, browser, mode):
    """Execute automation on agent with server-coordinated healing."""
    import gevent
    from gevent import monkey
    
    # Find the agent's session ID
    agent_sid = None
    for sid in connected_agents:
        agent_sid = sid
        break  # Get the first available agent
    
    healing_executor = HealingExecutor(socketio, api_key=openai_api_key)
    healing_executor.execution_mode = 'agent'  # Mark as agent execution
    healing_executor.agent_sid = agent_sid  # Store agent session ID
    active_healing_executors[test_id] = healing_executor
    headless = mode == 'headless'
    
    socketio.emit('execution_status', {
        'test_id': test_id,
        'status': 'running',
        'message': f'Executing on agent with healing in {mode} mode...'
    })
    
    # Run async code in gevent-compatible way using a separate thread
    async def _run_healing():
        return await healing_executor.execute_with_healing(code, browser, headless, test_id)
    
    try:
        import threading
        import asyncio
        
        result_container = {}
        exception_container = {}
        
        def run_in_thread():
            """Run async code in a separate thread to avoid gevent event loop conflict."""
            try:
                # Create a new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                # Run the async function
                result_container['result'] = loop.run_until_complete(_run_healing())
            except Exception as e:
                exception_container['error'] = e
            finally:
                loop.close()
        
        # Run async code in a separate thread
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()  # Wait for thread to complete
        
        # Check for exceptions
        if 'error' in exception_container:
            raise exception_container['error']
        
        result = result_container.get('result')
    finally:
        if test_id in active_healing_executors:
            del active_healing_executors[test_id]
    
    screenshot_path = None
    if result.get('screenshot'):
        screenshot_path = f"screenshots/test_{test_id}.png"
        with open(os.path.join(app.config['UPLOAD_FOLDER'], screenshot_path), 'wb') as f:
            f.write(result['screenshot'])
    
    logs_json = json.dumps(result.get('logs', []))
    status = 'success' if result.get('success') else 'failed'
    healed_code = result.get('healed_script')
    
    conn = sqlite3.connect('automation.db')
    c = conn.cursor()
    c.execute('UPDATE test_history SET status=?, logs=?, screenshot_path=?, healed_code=? WHERE id=?',
              (status, logs_json, screenshot_path, healed_code, test_id))
    conn.commit()
    conn.close()
    
    socketio.emit('execution_complete', {
        'test_id': test_id,
        'status': status,
        'logs': result.get('logs', []),
        'screenshot_path': screenshot_path,
        'healed_script': healed_code,
        'failed_locators': result.get('failed_locators', [])
    })

@app.route('/api/heal', methods=['POST'])
def heal_locator():
    data = request.json
    test_id = data.get('test_id')
    failed_locator = data.get('failed_locator')
    healed_locator = data.get('healed_locator')
    
    if not all([test_id, failed_locator, healed_locator]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        conn = sqlite3.connect('automation.db')
        c = conn.cursor()
        c.execute('SELECT generated_code, healed_code FROM test_history WHERE id=?', (test_id,))
        row = c.fetchone()
        
        if not row:
            return jsonify({'error': 'Test not found'}), 404
        
        original_code = row[0]
        current_healed = row[1] or original_code
        
        new_healed = current_healed.replace(failed_locator, healed_locator)
        
        c.execute('UPDATE test_history SET healed_code=? WHERE id=?', (new_healed, test_id))
        conn.commit()
        conn.close()
        
        socketio.emit('script_healed', {
            'test_id': test_id,
            'healed_script': new_healed,
            'failed_locator': failed_locator,
            'healed_locator': healed_locator
        })
        
        return jsonify({'success': True, 'healed_script': new_healed})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/agent/download')
def download_agent():
    return send_from_directory('.', 'local_agent.py', as_attachment=True)

@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')
    emit('connected', {'sid': request.sid})
    # Send current list of connected agents to newly connected web client
    socketio.emit('agents_update', {'agents': list(connected_agents.values())})

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Client disconnected: {request.sid}')
    if request.sid in connected_agents:
        del connected_agents[request.sid]
        print(f'Updated connected_agents after disconnect: {connected_agents}')
        socketio.emit('agents_update', {'agents': list(connected_agents.values())})

@socketio.on('agent_register')
def handle_agent_register(data):
    agent_id = data.get('agent_id')
    connected_agents[request.sid] = {
        'agent_id': agent_id,
        'browsers': data.get('browsers', []),
        'connected_at': datetime.now().isoformat()
    }
    print(f'Agent registered: {agent_id}')
    print(f'Updated connected_agents after register: {connected_agents}')
    emit('agent_registered', {'status': 'success'})
    print(f'Emitting agents_update: {list(connected_agents.values())}')
    socketio.emit('agents_update', {'agents': list(connected_agents.values())})

@socketio.on('agent_result')
def handle_agent_result(data):
    test_id = data.get('test_id')
    success = data.get('success')
    logs = data.get('logs', [])
    screenshot_data = data.get('screenshot')
    
    screenshot_path = None
    if screenshot_data:
        screenshot_path = f"screenshots/test_{test_id}.png"
        screenshot_bytes = base64.b64decode(screenshot_data)
        with open(os.path.join(app.config['UPLOAD_FOLDER'], screenshot_path), 'wb') as f:
            f.write(screenshot_bytes)
    
    logs_json = json.dumps(logs)
    status = 'success' if success else 'failed'
    
    conn = sqlite3.connect('automation.db')
    c = conn.cursor()
    c.execute('UPDATE test_history SET status=?, logs=?, screenshot_path=? WHERE id=?',
              (status, logs_json, screenshot_path, test_id))
    conn.commit()
    conn.close()
    
    socketio.emit('execution_complete', {
        'test_id': test_id,
        'status': status,
        'logs': logs,
        'screenshot_path': screenshot_path
    })

@socketio.on('agent_log')
def handle_agent_log(data):
    socketio.emit('execution_status', {
        'test_id': data.get('test_id'),
        'status': 'running',
        'message': data.get('message')
    })

@socketio.on('element_selected')
def handle_element_selected(data):
    test_id = data.get('test_id')
    selector = data.get('selector')
    
    if test_id in active_healing_executors:
        healing_executor = active_healing_executors[test_id]
        healing_executor.set_user_selector(selector)
        
        socketio.emit('element_selected_confirmed', {
            'test_id': test_id,
            'selector': selector,
            'healed_script': healing_executor.healed_script
        })
    else:
        socketio.emit('error', {
            'test_id': test_id,
            'message': 'No active healing session found for this test'
        })

@socketio.on('healing_attempt_result')
def handle_healing_attempt_result(data):
    """Handle result from agent healing attempt execution."""
    test_id = data.get('test_id')
    
    if test_id in active_healing_executors:
        healing_executor = active_healing_executors[test_id]
        healing_executor.set_agent_result({
            'success': data.get('success'),
            'logs': data.get('logs', []),
            'screenshot': data.get('screenshot')
        })

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 6890))
    socketio.run(
        app,
        host='127.0.0.1',  # localhost
        port=port,
        debug=True,
        allow_unsafe_werkzeug=True
    )
