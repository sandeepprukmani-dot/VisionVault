from gevent import monkey
monkey.patch_all()

import os
import json
import sqlite3
import uuid
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from openai import OpenAI
from executor import ServerExecutor
from healing_executor import HealingExecutor
from code_validator import CodeValidator
from models import Database, LearnedTask, TaskExecution
from vector_store import SemanticSearch
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

openai_api_key = os.environ.get('OPENAI_API_KEY','')
if openai_api_key:
    client = OpenAI(api_key=openai_api_key)
    # Initialize semantic search service
    try:
        semantic_search = SemanticSearch(api_key=openai_api_key)
        print("✅ Semantic search service initialized")
    except Exception as e:
        semantic_search = None
        print(f"⚠️ Failed to initialize semantic search: {e}")
else:
    client = None
    semantic_search = None
    print("WARNING: OPENAI_API_KEY is not set. AI code generation and semantic search will not be available.")

connected_agents = {}
active_healing_executors = {}

# Initialize database with new tables
db = Database()
print("✅ Database initialized with persistent learning tables")


def generate_playwright_code(natural_language_command, browser='chromium'):
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
    
    print(f"\n💾 SAVING TO DATABASE:")
    print(f"  test_id: {test_id}")
    print(f"  status: {status}")
    print(f"  healed_code is None: {healed_code is None}")
    print(f"  healed_code length: {len(healed_code) if healed_code else 0}", flush=True)
    
    conn = sqlite3.connect('automation.db')
    c = conn.cursor()
    c.execute('UPDATE test_history SET status=?, logs=?, screenshot_path=?, healed_code=? WHERE id=?',
              (status, logs_json, screenshot_path, healed_code, test_id))
    conn.commit()
    conn.close()
    
    print(f"  ✅ Database updated successfully", flush=True)
    
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
    
    # Run async code using asyncio.run() which creates its own event loop
    async def _run_healing():
        return await healing_executor.execute_with_healing(code, browser, headless, test_id)
    
    try:
        # Use asyncio.run() to execute the async function
        # This creates a new event loop specifically for this call
        result = asyncio.run(_run_healing())
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
    
    print(f"\n💾 SAVING TO DATABASE:")
    print(f"  test_id: {test_id}")
    print(f"  status: {status}")
    print(f"  healed_code is None: {healed_code is None}")
    print(f"  healed_code length: {len(healed_code) if healed_code else 0}", flush=True)
    
    conn = sqlite3.connect('automation.db')
    c = conn.cursor()
    c.execute('UPDATE test_history SET status=?, logs=?, screenshot_path=?, healed_code=? WHERE id=?',
              (status, logs_json, screenshot_path, healed_code, test_id))
    conn.commit()
    conn.close()
    
    print(f"  ✅ Database updated successfully", flush=True)
    
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
    # Get the current server URL dynamically
    replit_domain = os.environ.get('REPLIT_DEV_DOMAIN', 'localhost:5000')
    server_url = f'https://{replit_domain}' if replit_domain != 'localhost:5000' else 'http://localhost:5000'
    
    # Read the local agent file
    with open('local_agent.py', 'r') as f:
        agent_code = f.read()
    
    # Replace the SERVER_URL line with the current URL
    agent_code = agent_code.replace(
        "SERVER_URL = os.environ.get('AGENT_SERVER_URL', 'http://127.0.0.1:7890')",
        f"SERVER_URL = os.environ.get('AGENT_SERVER_URL', '{server_url}')"
    )
    
    # Create a temporary response with the modified content
    return Response(
        agent_code,
        mimetype='text/x-python',
        headers={'Content-Disposition': 'attachment; filename=local_agent.py'}
    )

# ========== Persistent Learning API Endpoints ==========

@app.route('/api/tasks', methods=['GET'])
def get_all_tasks():
    """Get all learned tasks."""
    try:
        limit = request.args.get('limit', 100, type=int)
        tasks = LearnedTask.get_all(limit=limit)
        return jsonify([task.to_dict() for task in tasks])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    """Get a specific learned task."""
    try:
        task = LearnedTask.get_by_id(task_id)
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        return jsonify(task.to_dict())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tasks/save', methods=['POST'])
def save_learned_task():
    """Save a new learned task or update existing one."""
    try:
        data = request.json
        
        # Extract task data
        task_id = data.get('task_id') or str(uuid.uuid4())
        task_name = data.get('task_name')
        playwright_code = data.get('playwright_code')
        description = data.get('description', '')
        steps = data.get('steps', [])
        tags = data.get('tags', [])
        
        if not task_name or not playwright_code:
            return jsonify({'error': 'task_name and playwright_code are required'}), 400
        
        # Create task object
        task = LearnedTask(
            task_id=task_id,
            task_name=task_name,
            playwright_code=playwright_code,
            description=description,
            steps=steps,
            tags=tags
        )
        
        # Save to database
        task.save()
        
        # Index for semantic search
        if semantic_search:
            try:
                semantic_search.index_task(task)
                print(f"✅ Task '{task_name}' indexed for semantic search")
            except Exception as e:
                print(f"⚠️ Failed to index task for search: {e}")
        
        return jsonify({
            'success': True,
            'task': task.to_dict()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    """Delete a learned task."""
    try:
        task = LearnedTask.get_by_id(task_id)
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        
        # Remove from semantic search index
        if semantic_search:
            semantic_search.delete_task_from_index(task_id)
        
        # Delete from database
        conn = sqlite3.connect('automation.db')
        c = conn.cursor()
        c.execute('DELETE FROM learned_tasks WHERE task_id=?', (task_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tasks/search', methods=['POST'])
def search_tasks():
    """Search for tasks using natural language."""
    try:
        data = request.json
        query = data.get('query')
        top_k = data.get('top_k', 5)
        
        if not query:
            return jsonify({'error': 'query is required'}), 400
        
        if not semantic_search:
            return jsonify({
                'error': 'OPENAI_API_KEY is not set. Semantic search requires an OpenAI API key to generate embeddings.'
            }), 400
        
        # Search for relevant tasks
        results = semantic_search.search_tasks(query, top_k=top_k)
        
        return jsonify({
            'query': query,
            'results': results
        })
    except Exception as e:
        error_msg = str(e)
        # Check if it's an API key or embedding-related error
        if any(keyword in error_msg.lower() for keyword in ['api', 'key', 'embedding', 'openai', 'authentication', 'unauthorized']):
            return jsonify({
                'error': f'OPENAI_API_KEY error: {error_msg}'
            }), 400
        return jsonify({'error': str(e)}), 500

@app.route('/api/tasks/<task_id>/execute', methods=['POST'])
def execute_learned_task():
    """Execute a learned task."""
    try:
        task_id = request.view_args['task_id']
        data = request.json
        browser = data.get('browser', 'chromium')
        mode = data.get('mode', 'headless')
        execution_location = data.get('execution_location', 'server')
        
        # Get the task
        task = LearnedTask.get_by_id(task_id)
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        
        # Use the task's code instead of generating new code
        code = task.playwright_code
        
        # Validate the code
        validator = CodeValidator()
        if not validator.validate(code):
            error_msg = "Task code failed security validation: " + "; ".join(validator.get_errors())
            return jsonify({'error': error_msg}), 400
        
        # Create a test history entry for tracking
        conn = sqlite3.connect('automation.db')
        c = conn.cursor()
        c.execute('INSERT INTO test_history (command, generated_code, browser, mode, execution_location, status) VALUES (?, ?, ?, ?, ?, ?)',
                  (f"Learned Task: {task.task_name}", code, browser, mode, execution_location, 'pending'))
        test_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Execute the task
        if execution_location == 'server':
            socketio.start_background_task(execute_on_server, test_id, code, browser, mode)
        else:
            agent_sid = None
            for sid in connected_agents:
                agent_sid = sid
                break
            
            if agent_sid:
                socketio.emit('execute_on_agent', {
                    'test_id': test_id,
                    'code': code,
                    'browser': browser,
                    'mode': mode
                }, to=agent_sid)
            else:
                return jsonify({'error': 'No agent connected'}), 503
        
        # Update task execution stats
        start_time = time.time()
        
        # Record execution in background
        def record_execution():
            # Wait a bit for execution to complete
            time.sleep(2)
            
            # Get execution result from test_history
            conn = sqlite3.connect('automation.db')
            c = conn.cursor()
            c.execute('SELECT status, logs FROM test_history WHERE id=?', (test_id,))
            row = c.fetchone()
            
            if row:
                status = row[0]
                logs = row[1]
                success = status == 'success'
                
                # Update task stats
                task = LearnedTask.get_by_id(task_id)
                if task:
                    if success:
                        task.success_count += 1
                    else:
                        task.failure_count += 1
                    task.last_executed = datetime.now()
                    task.save()
                
                # Record execution
                execution_time = int((time.time() - start_time) * 1000)
                execution = TaskExecution(
                    task_id=task_id,
                    execution_result=status,
                    success=success,
                    error_message=logs if not success else None,
                    execution_time_ms=execution_time
                )
                execution.save()
            
            conn.close()
        
        socketio.start_background_task(record_execution)
        
        return jsonify({
            'test_id': test_id,
            'task_name': task.task_name,
            'message': 'Task execution started'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tasks/recall', methods=['POST'])
def recall_and_execute():
    """
    Recall Mode: Search for a task by natural language and execute it.
    This is the main entry point for the persistent learning system.
    """
    try:
        data = request.json
        query = data.get('query')
        browser = data.get('browser', 'chromium')
        mode = data.get('mode', 'headless')
        execution_location = data.get('execution_location', 'server')
        auto_execute = data.get('auto_execute', False)
        
        if not query:
            return jsonify({'error': 'query is required'}), 400
        
        if not semantic_search:
            return jsonify({
                'error': 'OPENAI_API_KEY is not set. Recall Mode requires an OpenAI API key to search for tasks.'
            }), 400
        
        # Search for the most relevant task
        try:
            results = semantic_search.search_tasks(query, top_k=1)
        except Exception as search_error:
            error_msg = str(search_error)
            if any(keyword in error_msg.lower() for keyword in ['api', 'key', 'embedding', 'openai', 'authentication', 'unauthorized']):
                return jsonify({
                    'error': f'OPENAI_API_KEY error: {error_msg}'
                }), 400
            raise
        
        if not results:
            return jsonify({
                'found': False,
                'message': 'No matching tasks found. Consider creating a new task.'
            })
        
        # Get the best match
        best_match = results[0]
        task_id = best_match['task_id']
        similarity_score = best_match.get('similarity_score', 0)
        
        # If auto_execute is True and similarity is high enough, execute immediately
        if auto_execute and similarity_score > 0.7:
            # Execute the task
            task = LearnedTask.get_by_id(task_id)
            code = task.playwright_code
            
            # Create test history entry
            conn = sqlite3.connect('automation.db')
            c = conn.cursor()
            c.execute('INSERT INTO test_history (command, generated_code, browser, mode, execution_location, status) VALUES (?, ?, ?, ?, ?, ?)',
                      (query, code, browser, mode, execution_location, 'pending'))
            test_id = c.lastrowid
            conn.commit()
            conn.close()
            
            # Execute
            if execution_location == 'server':
                socketio.start_background_task(execute_on_server, test_id, code, browser, mode)
            
            return jsonify({
                'found': True,
                'executed': True,
                'test_id': test_id,
                'task': best_match,
                'similarity_score': similarity_score
            })
        else:
            # Return the best match for user confirmation
            return jsonify({
                'found': True,
                'executed': False,
                'task': best_match,
                'similarity_score': similarity_score,
                'message': 'Task found. Please confirm execution or adjust the query.'
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Teaching Mode Recording - Global recorder instances and event loops
active_recorders = {}
active_loops = {}

@app.route('/api/teaching/start', methods=['POST'])
def start_teaching_recording():
    """Start interactive recording session for Teaching Mode."""
    try:
        from action_recorder import InteractiveRecorder
        import threading
        
        session_id = request.json.get('session_id') or str(uuid.uuid4())
        browser_name = request.json.get('browser', 'chromium')
        start_url = request.json.get('start_url', 'https://www.example.com')
        
        # Create new recorder for this session
        recorder = InteractiveRecorder()
        
        # Create persistent event loop for this session
        loop = asyncio.new_event_loop()
        active_loops[session_id] = loop
        
        # Run async recording in a separate thread with persistent loop
        def start_recording_thread():
            asyncio.set_event_loop(loop)
            try:
                # Initialize recorder and browser
                async def init_recording():
                    page = await recorder.start_interactive_recording(browser_name)
                    # Navigate to start URL so JavaScript gets injected
                    if start_url and start_url != 'about:blank':
                        await page.goto(start_url)
                        recorder.record_goto(start_url)
                    print(f"✅ Recording started for session {session_id}")
                
                # Run initialization
                loop.run_until_complete(init_recording())
                
                # Keep loop running forever for this session
                loop.run_forever()
                
            except Exception as e:
                print(f"Error in recording thread: {e}")
                import traceback
                traceback.print_exc()
            finally:
                # Clean up loop when stopped
                loop.close()
        
        thread = threading.Thread(target=start_recording_thread, daemon=True)
        thread.start()
        
        # Give browser time to start and navigate
        time.sleep(3)
        
        # Store recorder
        active_recorders[session_id] = recorder
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'message': f'Interactive browser opened at {start_url}. Your actions are being recorded automatically.'
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/teaching/navigate', methods=['POST'])
def teaching_navigate():
    """Navigate to a URL during recording."""
    try:
        session_id = request.json.get('session_id')
        url = request.json.get('url')
        
        if not session_id or session_id not in active_recorders:
            return jsonify({'error': 'No active recording session'}), 400
        
        recorder = active_recorders[session_id]
        loop = active_loops.get(session_id)
        
        if not loop or not recorder.page:
            return jsonify({'error': 'Recording session not ready'}), 400
        
        # Run navigation using the session's event loop
        try:
            asyncio.run_coroutine_threadsafe(recorder.page.goto(url), loop).result(timeout=10)
            recorder.record_goto(url)
            return jsonify({'success': True})
        except Exception as e:
            print(f"Navigation error: {e}")
            return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/teaching/actions', methods=['GET'])
def get_teaching_actions():
    """Get currently recorded actions."""
    try:
        session_id = request.args.get('session_id')
        
        if not session_id or session_id not in active_recorders:
            return jsonify({'actions': []})
        
        recorder = active_recorders[session_id]
        loop = active_loops.get(session_id)
        
        if not loop or not recorder.page:
            return jsonify({'actions': recorder.actions})
        
        # Get actions from JavaScript using the session's event loop
        try:
            js_actions = asyncio.run_coroutine_threadsafe(
                recorder.get_recorded_actions_from_page(), loop
            ).result(timeout=2)
            
            # Merge with manually recorded actions (navigation, etc.)
            all_actions = recorder.actions + (js_actions if js_actions else [])
            
            return jsonify({'actions': all_actions})
        except Exception as e:
            print(f"Error getting actions: {e}")
            return jsonify({'actions': recorder.actions})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/teaching/stop', methods=['POST'])
def stop_teaching_recording():
    """Stop recording and return captured actions."""
    try:
        session_id = request.json.get('session_id')
        
        if not session_id or session_id not in active_recorders:
            return jsonify({'error': 'No active recording session'}), 400
        
        recorder = active_recorders[session_id]
        loop = active_loops.get(session_id)
        
        if not loop:
            # Clean up and return whatever we have
            actions = recorder.actions
            del active_recorders[session_id]
            return jsonify({'success': True, 'actions': actions})
        
        # Get final actions using the session's event loop
        try:
            # Get JavaScript recorded actions
            js_actions = asyncio.run_coroutine_threadsafe(
                recorder.get_recorded_actions_from_page(), loop
            ).result(timeout=2)
            
            # Stop recording and close browser
            manual_actions = asyncio.run_coroutine_threadsafe(
                recorder.stop_recording(), loop
            ).result(timeout=5)
            
            # Combine all actions
            all_actions = manual_actions + (js_actions if js_actions else [])
            
            print(f"✅ Recording stopped for session {session_id}. Total actions: {len(all_actions)}")
            
        except Exception as e:
            print(f"Error stopping recording: {e}")
            import traceback
            traceback.print_exc()
            all_actions = recorder.actions
        finally:
            # Stop the event loop gracefully
            if loop and loop.is_running():
                loop.call_soon_threadsafe(loop.stop)
        
        # Clean up
        if session_id in active_recorders:
            del active_recorders[session_id]
        if session_id in active_loops:
            del active_loops[session_id]
        
        return jsonify({
            'success': True,
            'actions': all_actions
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

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
    failed_locator = data.get('failed_locator')  # Agent should send this
    
    print(f"\n✅ ELEMENT SELECTED EVENT RECEIVED:")
    print(f"  test_id: {test_id}")
    print(f"  selector: {selector}")
    print(f"  failed_locator: {failed_locator}", flush=True)
    
    # Get the generated code from database
    conn = sqlite3.connect('automation.db')
    c = conn.cursor()
    c.execute('SELECT generated_code FROM test_history WHERE id=?', (test_id,))
    row = c.fetchone()
    
    if not row:
        print(f"  ❌ Test {test_id} not found in database", flush=True)
        conn.close()
        socketio.emit('error', {
            'test_id': test_id,
            'message': 'Test not found in database'
        })
        return
    
    generated_code = row[0]
    
    # If failed_locator not provided by agent, try to extract from healing_executor
    if not failed_locator and test_id in active_healing_executors:
        healing_executor = active_healing_executors[test_id]
        if healing_executor.failed_locators:
            failed_locator = healing_executor.failed_locators[-1]['locator']
    
    # Heal the script
    healed_code = generated_code.replace(failed_locator, selector) if failed_locator else generated_code
    
    print(f"\n🔧 HEALING SCRIPT IN handle_element_selected:")
    print(f"  Failed locator: '{failed_locator}'")
    print(f"  Healed locator: '{selector}'")
    print(f"  Replacement successful: {healed_code != generated_code}")
    print(f"  Healed code length: {len(healed_code)}", flush=True)
    
    # Save healed code to database
    c.execute('UPDATE test_history SET healed_code=? WHERE id=?', (healed_code, test_id))
    conn.commit()
    conn.close()
    
    print(f"  ✅ Healed code saved to database for test {test_id}", flush=True)
    
    # Update healing executor if it exists
    if test_id in active_healing_executors:
        healing_executor = active_healing_executors[test_id]
        healing_executor.set_user_selector(selector)
        healing_executor.healed_script = healed_code
    
    socketio.emit('element_selected_confirmed', {
        'test_id': test_id,
        'selector': selector,
        'failed_locator': failed_locator,
        'healed_script': healed_code
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
