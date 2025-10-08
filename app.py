from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import json
import os
from datetime import datetime
from playwright_wrapper import SelfHealingPlaywright

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'dev-secret-key')
socketio = SocketIO(app, cors_allowed_origins="*")

LOCATORS_FILE = 'locators.json'
SCRIPTS_FILE = 'scripts.json'

def load_locators():
    if os.path.exists(LOCATORS_FILE):
        with open(LOCATORS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_locators(locators):
    with open(LOCATORS_FILE, 'w') as f:
        json.dump(locators, f, indent=2)

def load_scripts():
    if os.path.exists(SCRIPTS_FILE):
        with open(SCRIPTS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_scripts(scripts):
    with open(SCRIPTS_FILE, 'w') as f:
        json.dump(scripts, f, indent=2)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/locators', methods=['GET'])
def get_locators():
    return jsonify(load_locators())

@app.route('/api/scripts', methods=['GET'])
def get_scripts():
    return jsonify(load_scripts())

@app.route('/api/scripts', methods=['POST'])
def save_script():
    data = request.json if request.json else {}
    scripts = load_scripts()
    script = {
        'id': datetime.now().timestamp(),
        'name': data.get('name', 'Untitled Script'),
        'code': data.get('code', ''),
        'created_at': datetime.now().isoformat()
    }
    scripts.append(script)
    save_scripts(scripts)
    return jsonify(script)

@socketio.on('execute_script')
def handle_execute_script(data):
    code = data.get('code', '')
    url = data.get('url', 'https://example.com')
    
    playwright = SelfHealingPlaywright(socketio, load_locators(), save_locators)
    
    try:
        socketio.emit('status', {'message': 'Starting browser...', 'type': 'info'})
        playwright.execute(code, url)
        socketio.emit('status', {'message': 'Execution completed successfully!', 'type': 'success'})
    except Exception as e:
        socketio.emit('status', {'message': f'Error: {str(e)}', 'type': 'error'})
    finally:
        playwright.cleanup()

@socketio.on('element_clicked')
def handle_element_clicked(data):
    socketio.emit('locator_fixed', data)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
