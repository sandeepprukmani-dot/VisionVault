import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import base64
import ast
import re
import asyncio
import sys
from io import StringIO

# --- Embedded HTML Template ---
INDEX_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Automation AI-Powered</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', sans-serif;
            background: #0a0a0a;
            color: #ffffff;
            min-height: 100vh;
            overflow-x: hidden;
        }
        .app-container {
            display: flex;
            min-height: 100vh;
        }
        .sidebar {
            width: 260px;
            background: #111111;
            border-right: 1px solid #1f1f1f;
            padding: 24px 0;
            position: fixed;
            height: 100vh;
            left: 0;
            top: 0;
            z-index: 1000;
            display: flex;
            flex-direction: column;
        }
        .logo-section {
            padding: 0 24px 32px 24px;
            border-bottom: 1px solid #1f1f1f;
        }
        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .logo-icon {
            width: 36px;
            height: 36px;
            background: linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
        }
        .logo-text {
            display: flex;
            flex-direction: column;
        }
        .logo-title {
            font-size: 15px;
            font-weight: 700;
            color: #ffffff;
            line-height: 1.2;
        }
        .logo-subtitle {
            font-size: 10px;
            color: #8b5cf6;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .nav-section {
            padding: 24px 0;
            flex: 1;
        }
        .nav-title {
            font-size: 11px;
            color: #555555;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            padding: 0 24px 12px 24px;
        }
        .nav-link {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 24px;
            color: #888888;
            text-decoration: none;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.2s;
            border-left: 3px solid transparent;
        }
        .nav-link:hover {
            color: #ffffff;
            background: rgba(139, 92, 246, 0.1);
        }
        .nav-link.active {
            color: #ffffff;
            background: rgba(139, 92, 246, 0.15);
            border-left-color: #8b5cf6;
        }
        .nav-link i {
            font-size: 16px;
            width: 18px;
        }
        .sidebar-footer {
            padding: 20px 24px;
            border-top: 1px solid #1f1f1f;
        }
        .status-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 0;
            font-size: 12px;
            color: #888888;
        }
        .status-label {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .status-value {
            color: #10b981;
            font-weight: 600;
        }
        .main-content {
            flex: 1;
            margin-left: 260px;
            padding: 0;
            position: relative;
        }
        .top-bar {
            display: flex;
            justify-content: flex-end;
            align-items: center;
            padding: 16px 48px;
            gap: 12px;
            border-bottom: 1px solid #1f1f1f;
        }
        .connected-badge {
            display: flex;
            align-items: center;
            gap: 8px;
            background: #8b5cf6;
            color: #ffffff;
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
        }
        .connected-badge.disconnected {
            background: #333333;
            color: #888888;
        }
        .icon-button {
            width: 36px;
            height: 36px;
            background: transparent;
            border: 1px solid #333333;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            color: #888888;
            transition: all 0.2s;
        }
        .icon-button:hover {
            background: #1a1a1a;
            border-color: #555555;
            color: #ffffff;
        }
        .content-wrapper {
            padding: 40px 48px;
        }
        .page-header {
            margin-bottom: 32px;
        }
        .page-title {
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 8px;
            color: #ffffff;
        }
        .page-subtitle {
            font-size: 15px;
            color: #888888;
        }
        .mode-toggle {
            display: flex;
            gap: 0;
            margin-bottom: 32px;
            width: fit-content;
            background: #1a1a1a;
            border-radius: 10px;
            padding: 4px;
        }
        .mode-button {
            display: flex;
            align-items: center;
            gap: 8px;
            background: transparent;
            color: #888888;
            border: none;
            border-radius: 8px;
            padding: 10px 20px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        .mode-button.active {
            background: #8b5cf6;
            color: #ffffff;
        }
        .mode-button i {
            font-size: 16px;
        }
        .form-section {
            margin-bottom: 24px;
        }
        .form-label {
            display: block;
            font-size: 13px;
            font-weight: 600;
            color: #cccccc;
            margin-bottom: 12px;
        }
        .prompt-input {
            width: 100%;
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 12px;
            padding: 16px 20px;
            color: #ffffff;
            font-size: 14px;
            line-height: 1.8;
            resize: vertical;
            min-height: 140px;
            transition: all 0.2s;
            font-family: inherit;
        }
        .prompt-input:focus {
            outline: none;
            border-color: #8b5cf6;
            box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.1);
        }
        .prompt-input::placeholder {
            color: #555555;
        }
        .hint-text {
            font-size: 12px;
            color: #666666;
            margin-top: 8px;
        }
    </style>
</head>
<body>
    <div class="app-container">
        <div class="sidebar">
            <div class="logo-section">
                <div class="logo">
                    <div class="logo-icon"><i class="bi bi-robot"></i></div>
                    <div class="logo-text">
                        <span class="logo-title">Automation AI-Powered</span>
                        <span class="logo-subtitle">Browser Testing</span>
                    </div>
                </div>
            </div>
            <div class="nav-section">
                <div class="nav-title">Navigation</div>
                <a href="#" class="nav-link active"><i class="bi bi-house"></i> Home</a>
                <a href="#" class="nav-link"><i class="bi bi-clock-history"></i> History</a>
                <a href="#" class="nav-link"><i class="bi bi-download"></i> Download Agent</a>
            </div>
            <div class="sidebar-footer">
                <div class="status-item">
                    <span class="status-label"><i class="bi bi-wifi"></i> Server</span>
                    <span class="status-value">Online</span>
                </div>
            </div>
        </div>
        <div class="main-content">
            <div class="top-bar">
                <div class="connected-badge" id="connection-status">Connected</div>
                <button class="icon-button"><i class="bi bi-gear"></i></button>
            </div>
            <div class="content-wrapper">
                <div class="page-header">
                    <div class="page-title">Automation AI-Powered</div>
                    <div class="page-subtitle">Natural language to browser automation</div>
                </div>
                <div class="mode-toggle">
                    <button class="mode-button active" id="headless-btn"><i class="bi bi-eye-slash"></i> Headless</button>
                    <button class="mode-button" id="headed-btn"><i class="bi bi-eye"></i> Headed</button>
                </div>
                <div class="form-section">
                    <label class="form-label" for="command">Test Command</label>
                    <textarea class="prompt-input" id="command" placeholder="Type your test scenario in natural language..."></textarea>
                    <div class="hint-text">e.g. Open Google and search for 'Selenium'</div>
                </div>
                <div class="form-section">
                    <label class="form-label" for="browser">Browser</label>
                    <select class="form-select" id="browser">
                        <option value="chromium">Chromium</option>
                        <option value="firefox">Firefox</option>
                        <option value="webkit">WebKit</option>
                    </select>
                </div>
                <form id="execute-form">
                    <button type="submit" class="btn btn-primary">Execute</button>
                </form>
                <div class="form-section">
                    <a href="/api/agent/download" class="btn btn-secondary">Download local_agent.py</a>
                </div>
                <div class="form-section">
                    <h2>Test History</h2>
                    <div id="history"></div>
                </div>
            </div>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.11.6/dist/umd/popper.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.min.js"></script>
    <script src="https://cdn.socket.io/4.0.0/socket.io.min.js"></script>
    <script>
        const socket = io();
        socket.on('connect', () => {
            document.getElementById('connection-status').textContent = 'Connected';
            document.getElementById('connection-status').classList.remove('disconnected');
        });
        socket.on('disconnect', () => {
            document.getElementById('connection-status').textContent = 'Disconnected';
            document.getElementById('connection-status').classList.add('disconnected');
        });
        socket.on('execution_status', (data) => {
            // Optionally update UI with execution status
        });
        socket.on('execution_complete', (data) => {
            // Optionally update UI with execution result
        });
        function fetchHistory() {
            fetch('/api/history')
                .then(response => response.json())
                .then(data => {
                    const historyDiv = document.getElementById('history');
                    historyDiv.innerHTML = '';
                    data.forEach(row => {
                        const card = document.createElement('div');
                        card.className = 'card mb-3';
                        card.innerHTML = `
                            <div class="card-body">
                                <h5 class="card-title">Test ID: ${row.id}</h5>
                                <p class="card-text"><strong>Command:</strong> ${row.command}</p>
                                <p class="card-text"><strong>Status:</strong> ${row.status}</p>
                                <p class="card-text"><strong>Logs:</strong> ${row.logs}</p>
                                ${row.screenshot_path ? `<img src="${row.screenshot_path}" class="img-fluid" alt="Screenshot">` : ''}
                            </div>
                        `;
                        historyDiv.appendChild(card);
                    });
                });
        }
        document.getElementById('execute-form').addEventListener('submit', (e) => {
            e.preventDefault();
            const command = document.getElementById('command').value;
            const browser = document.getElementById('browser').value;
            const mode = document.getElementById('headless-btn').classList.contains('active') ? 'headless' : 'headed';
            fetch('/api/execute', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ command, browser, mode })
            })
            .then(response => response.json())
            .then(data => {
                // Optionally handle response
                fetchHistory();
            });
        });
        document.getElementById('headless-btn').addEventListener('click', () => {
            document.getElementById('headless-btn').classList.add('active');
            document.getElementById('headed-btn').classList.remove('active');
        });
        document.getElementById('headed-btn').addEventListener('click', () => {
            document.getElementById('headed-btn').classList.add('active');
            document.getElementById('headless-btn').classList.remove('active');
        });
        fetchHistory();
    </script>
</body>
</html>
'''

# --- CodeValidator ---
class CodeValidator:
    ALLOWED_IMPORTS = {
        'playwright.async_api', 'asyncio', 'time', 'datetime', 're', 'json', 'base64'
    }
    DANGEROUS_MODULES = {
        'os', 'sys', 'subprocess', 'shutil', 'eval', 'exec', 'compile', '__import__', 'open', 'file', 'input', 'execfile', 'reload', 'importlib', 'pickle', 'shelve', 'socket', 'urllib', 'requests', 'http', 'ftplib', 'telnetlib', 'smtplib', 'poplib', 'imaplib'
    }
    def __init__(self):
        self.errors = []
    def validate(self, code):
        self.errors = []
        if not code or not isinstance(code, str):
            self.errors.append("Code must be a non-empty string")
            return False
        if 'async def run_test' not in code:
            self.errors.append("Code must contain 'async def run_test' function")
            return False
        if 'playwright.async_api import async_playwright' not in code:
            self.errors.append("Code must use 'from playwright.async_api import async_playwright'")
            return False
        for module in self.DANGEROUS_MODULES:
            patterns = [f'import {module}', f'from {module}', f'__import__("{module}")', f"__import__('{module}')"]
            for pattern in patterns:
                if pattern in code:
                    self.errors.append(f"Dangerous import detected: {module}")
                    return False
        dangerous_patterns = [
            (r'\beval\s*\(', 'eval() function'), (r'\bexec\s*\(', 'exec() function'), (r'\b__import__\s*\(', '__import__() function'), (r'\bcompile\s*\(', 'compile() function'), (r'\bopen\s*\(', 'open() function (file access)'), (r'\.system\s*\(', 'system() call'), (r'\.popen\s*\(', 'popen() call'), (r'\.spawn\s*\(', 'spawn() call'),
        ]
        for pattern, name in dangerous_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                self.errors.append(f"Dangerous pattern detected: {name}")
                return False
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if not self._is_allowed_import(alias.name):
                            self.errors.append(f"Disallowed import: {alias.name}")
                            return False
                elif isinstance(node, ast.ImportFrom):
                    if node.module and not self._is_allowed_import(node.module):
                        self.errors.append(f"Disallowed import from: {node.module}")
                        return False
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ['eval', 'exec', 'compile', '__import__', 'open']:
                            self.errors.append(f"Dangerous function call: {node.func.id}")
                            return False
        except SyntaxError as e:
            self.errors.append(f"Syntax error: {str(e)}")
            return False
        return True
    def _is_allowed_import(self, module_name):
        for allowed in self.ALLOWED_IMPORTS:
            if module_name.startswith(allowed):
                return True
        return False
    def get_errors(self):
        return self.errors

# --- ServerExecutor ---
class ServerExecutor:
    def execute(self, code, browser_name='chromium', headless=True):
        try:
            validator = CodeValidator()
            if not validator.validate(code):
                return {
                    'success': False,
                    'logs': ['Security validation failed: ' + '; '.join(validator.get_errors())],
                    'screenshot': None
                }
            restricted_globals = {
                '__builtins__': {
                    'True': True, 'False': False, 'None': None, 'dict': dict, 'list': list, 'str': str, 'int': int, 'float': float, 'bool': bool, 'len': len, 'range': range, 'enumerate': enumerate, 'zip': zip, 'Exception': Exception, 'ValueError': ValueError, 'TypeError': TypeError, 'KeyError': KeyError, 'AttributeError': AttributeError, 'getattr': getattr, 'setattr': setattr, 'hasattr': hasattr, 'print': print, '__import__': __import__,
                }
            }
            local_vars = {}
            exec(code, restricted_globals, local_vars)
            if 'run_test' not in local_vars:
                return {
                    'success': False,
                    'logs': ['Error: Generated code must contain a run_test function'],
                    'screenshot': None
                }
            run_test = local_vars['run_test']
            result = asyncio.run(run_test(browser_name=browser_name, headless=headless))
            return result
        except Exception as e:
            return {
                'success': False,
                'logs': [f'Execution error: {str(e)}'],
                'screenshot': None
            }

# --- Flask App ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'dev-secret-key')
app.config['UPLOAD_FOLDER'] = 'uploads'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'screenshots'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'logs'), exist_ok=True)

openai_api_key = os.environ.get('OPENAI_API_KEY','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')
try:
    from openai import OpenAI
    client = OpenAI(api_key=openai_api_key) if openai_api_key else None
except ImportError:
    client = None

connected_agents = {}

def init_db():
    conn = sqlite3.connect('automation.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS test_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  command TEXT NOT NULL,
                  generated_code TEXT NOT NULL,
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

def generate_playwright_code(natural_language_command, browser='chromium'):
    if not client:
        raise Exception("OpenAI API key not configured. Please set the OPENAI_API_KEY environment variable.")
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert at converting natural language commands into Playwright Python code. Generate complete, executable Playwright code that: 1. Uses async/await syntax 2. Includes proper browser launch with the specified browser 3. Has error handling 4. Returns a dict with 'success', 'logs', and 'screenshot' keys 5. Takes screenshot on success or error 6. The code should be a complete async function named 'run_test' that takes browser_name and headless parameters. Only return the function code, no explanations."},
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
    return Response(INDEX_HTML, mimetype='text/html')

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
            'id': row[0], 'command': row[1], 'generated_code': row[2], 'browser': row[3], 'mode': row[4], 'execution_location': row[5], 'status': row[6], 'logs': row[7], 'screenshot_path': row[8], 'created_at': row[9]
        })
    return jsonify(history)

@app.route('/api/execute', methods=['POST'])
def execute_test():
    data = request.json
    command = data.get('command')
    browser = data.get('browser', 'chromium')
    mode = data.get('mode', 'headless')
    execution_location = data.get('execution_location', 'server')
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
        c.execute('INSERT INTO test_history (command, generated_code, browser, mode, execution_location, status) VALUES (?, ?, ?, ?, ?, ?)', (command, generated_code, browser, mode, execution_location, 'pending'))
        test_id = c.lastrowid
        conn.commit()
        conn.close()
        if execution_location == 'server':
            socketio.start_background_task(execute_on_server, test_id, generated_code, browser, mode)
        else:
            socketio.emit('execute_on_agent', {'test_id': test_id, 'code': generated_code, 'browser': browser, 'mode': mode})
        return jsonify({'test_id': test_id, 'code': generated_code})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def execute_on_server(test_id, code, browser, mode):
    executor = ServerExecutor()
    headless = mode == 'headless'
    socketio.emit('execution_status', {'test_id': test_id, 'status': 'running', 'message': f'Executing on server in {mode} mode...'})
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
    c.execute('UPDATE test_history SET status=?, logs=?, screenshot_path=? WHERE id=?', (status, logs_json, screenshot_path, test_id))
    conn.commit()
    conn.close()
    socketio.emit('execution_complete', {'test_id': test_id, 'status': status, 'logs': result.get('logs', []), 'screenshot_path': screenshot_path})

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
    connected_agents[request.sid] = {'agent_id': agent_id, 'browsers': data.get('browsers', []), 'connected_at': datetime.now().isoformat()}
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
    c.execute('UPDATE test_history SET status=?, logs=?, screenshot_path=? WHERE id=?', (status, logs_json, screenshot_path, test_id))
    conn.commit()
    conn.close()
    socketio.emit('execution_complete', {'test_id': test_id, 'status': status, 'logs': logs, 'screenshot_path': screenshot_path})

@socketio.on('agent_log')
def handle_agent_log(data):
    socketio.emit('execution_status', {'test_id': data.get('test_id'), 'status': 'running', 'message': data.get('message')})

if __name__ == '__main__':
    socketio.run(app, port=6745, debug=True, allow_unsafe_werkzeug=True)

# --- End of packed file ---
