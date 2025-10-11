# VisionVault - AI-Powered Browser Automation

## Overview
VisionVault is a sophisticated browser automation platform that converts natural language commands into executable Playwright scripts using OpenAI's GPT models. The application provides a beautiful web interface for creating, executing, and managing browser automation tasks.

## Project Architecture

### Backend (Python/Flask)
- **Framework**: Flask with Flask-SocketIO for real-time communication
- **AI Integration**: OpenAI GPT-4o-mini for code generation
- **Browser Automation**: Playwright for Python
- **Database**: SQLite for test history and logs
- **Security**: Code validation to prevent malicious code execution

### Frontend
- **UI**: Custom dark-themed interface with real-time updates
- **Communication**: Socket.IO for bi-directional event-based communication
- **Features**:
  - Natural language automation input
  - Headless/Headful mode selection
  - Real-time execution logs
  - Screenshot capture
  - Test history tracking

### Key Components

1. **app.py** - Main Flask application with API endpoints and SocketIO handlers
2. **executor.py** - Server-side Playwright code executor with security sandboxing
3. **code_validator.py** - Security validation for generated code
4. **local_agent.py** - Optional local agent for running tests on user's machine
5. **templates/index.html** - Main web interface
6. **action_recorder.py** - Interactive recorder for capturing and storing browser actions
7. **vector_store.py** - FAISS-based semantic search with OpenAI embeddings (1536-dimensional)

## Features

- ✅ Natural language to Playwright code conversion
- ✅ Real-time execution with live logs
- ✅ Screenshot capture on success/failure
- ✅ Test history and management
- ✅ Secure code execution with validation
- ✅ Server-side and local agent execution modes
- ✅ Multiple browser support (Chromium, Firefox, WebKit)
- ✅ **NEW:** Intelligent locator resolution with AI-powered healing
- ✅ **NEW:** Interactive element selection in headful mode
- ✅ **NEW:** Real-time healed script panel
- ✅ **NEW:** Movable semi-transparent widget for element selection
- ✅ **NEW:** AI feedback loop for continuous improvement
- ✅ **NEW:** Sequential step execution with pause/resume
- ✅ **NEW:** Persistent Learning System with semantic search and task recall

## Setup Requirements

### Environment Variables
- **OPENAI_API_KEY**: Required for AI code generation (not set - needs to be configured)
- **PORT**: Server port (default: 5000)
- **SESSION_SECRET**: Flask session secret (auto-generated if not set)

### Python Dependencies
- flask
- flask-socketio
- flask-cors
- openai
- playwright
- python-socketio
- websocket-client
- eventlet
- gunicorn

## Current Configuration

### Server
- **Host**: 0.0.0.0
- **Port**: 5000
- **Server**: Gunicorn with gevent worker
- **Worker Class**: gevent (for async/WebSocket support)
- **Workers**: 1
- **CORS**: Enabled for all origins
- **Logging**: SIGWINCH signals filtered to prevent log spam

### Playwright
- **Installed Browsers**: Chromium (headless shell)
- **Execution Mode**: Server-side (headless by default)
- **Screenshot**: Enabled for all executions

## Usage

1. **Web Interface**: Access the app through the Replit preview
2. **Natural Language Input**: Describe automation tasks like:
   - "Navigate to Amazon and search for wireless headphones"
   - "Go to LinkedIn and extract all job postings for Software Engineer"
   - "Check my Gmail inbox for invoices and download them"

3. **Execution Modes**:
   - **Server**: Runs on Replit server (headless only due to no display)
   - **Local Agent**: Download agent to run on your local machine (supports headful mode)

## Persistent Learning System

The platform includes a complete persistent learning system that enables users to teach, store, and recall automation tasks using natural language. See `PERSISTENT_LEARNING_GUIDE.md` for detailed documentation.

### Features
- **Teaching Mode**: Record browser interactions and save as reusable tasks
- **Task Library**: Browse, search, and manage learned tasks with execution history
- **Recall Mode**: Search for tasks using natural language and execute them automatically
- **Semantic Search**: AI-powered task search using FAISS vector store with OpenAI embeddings
- **Error Handling**: Graceful degradation when OPENAI_API_KEY is not configured

### Error Handling
The system provides clear, user-friendly error messages when the OpenAI API key is missing:
- Backend returns 400 (not 500) with explicit "OPENAI_API_KEY is not set" messages
- Frontend displays emoji-coded alerts (⚠️ for API key issues, ✅ for success)
- Users are guided to add the key in Replit Secrets to enable features

## Database Schema

### test_history table
- id (PRIMARY KEY)
- command (TEXT) - Natural language command
- generated_code (TEXT) - Generated Playwright code
- browser (TEXT) - Browser type
- mode (TEXT) - Execution mode (headless/headful)
- execution_location (TEXT) - server/agent
- status (TEXT) - pending/success/failed
- logs (TEXT) - JSON array of execution logs
- screenshot_path (TEXT) - Path to screenshot
- created_at (TIMESTAMP)

### learned_tasks table
- task_id (TEXT PRIMARY KEY) - Unique task identifier
- task_name (TEXT) - User-friendly task name
- description (TEXT) - Task description
- playwright_code (TEXT) - Generated Playwright code
- tags (TEXT) - Comma-separated tags
- success_count (INTEGER) - Number of successful executions
- failure_count (INTEGER) - Number of failed executions
- created_at (TIMESTAMP)
- last_executed (TIMESTAMP)

### task_executions table
- execution_id (TEXT PRIMARY KEY)
- task_id (TEXT) - References learned_tasks
- execution_result (TEXT) - Result status
- success (BOOLEAN)
- error_message (TEXT)
- execution_time_ms (INTEGER)
- executed_at (TIMESTAMP)

## Recent Changes

- **2025-10-11**: Persistent Learning System - Recall Mode Complete
  - ✅ Implemented complete Recall Mode UI with natural language task search
  - ✅ Added semantic search integration using FAISS vector store
  - ✅ Implemented task execution directly from search results
  - ✅ Added robust error handling for missing OPENAI_API_KEY
  - ✅ Backend now returns 400 (not 500) errors with clear API key guidance
  - ✅ Frontend displays user-friendly error messages with emoji indicators
  - ✅ Added navigation structure for all persistent learning features
  - ✅ Verified workflow running on port 5000 with no LSP errors
  - ✅ Architecture review confirmed production-ready implementation

- **2025-10-11**: Critical Connection & Widget Flow Fixes
  - ✅ Fixed gunicorn log spam by filtering SIGWINCH signals in gunicorn.conf.py
  - ✅ Fixed event_loop scope issue in local_agent.py (was creating local variable instead of updating global)
  - ✅ Fixed agent-server communication by targeting events to specific agent sessions instead of broadcasting
  - ✅ Added agent session ID targeting for execute_healing_attempt events
  - ✅ Added agent session ID targeting for element_selector_needed events
  - ✅ Fixed non-healing agent execution to also target specific agent
  - ✅ Removed redundant widget injection on agent - now properly waits for server trigger
  - ✅ Ensured browser opens on client environment (local agent) in headful mode
  - ✅ Verified widget launches correctly when locator fails in headful mode
  - ✅ Fixed connection stability - agent now stays connected during test execution

- **2025-10-10**: Headful Mode & Widget Fixes
  - ✅ Fixed mode parameter passing to element_selector_needed event
  - ✅ Implemented 20-second browser timeout during healing (down from 30s)
  - ✅ Added cleanup_browser() function for proper browser cleanup after healing
  - ✅ Created LOCAL_AGENT_GUIDE.md with comprehensive setup instructions
  - ✅ Verified widget injection works only on client browser in headful mode (not server)
  - ✅ Confirmed browser launches correctly in headful mode when local agent connected
  - ✅ Browser now auto-closes after element selection or 20-second timeout
  - ✅ Added exception handling for browser cleanup edge cases
  - ✅ Fixed agent connection status UI bug - now correctly shows status on page refresh

- **2025-10-10**: Major UI Automation Enhancements
  - ✅ Added intelligent locator resolution with AI-powered healing
  - ✅ Implemented interactive element selection widget for headful mode
  - ✅ Created movable, semi-transparent overlay for user element selection
  - ✅ Added real-time healed script panel that updates automatically
  - ✅ Implemented sequential step execution with pause/resume functionality
  - ✅ Added AI feedback loop to analyze failures and provide improvement insights
  - ✅ Enhanced local agent with element selector injection capabilities
  - ✅ Updated Socket.IO event handlers for bidirectional element selection workflow
  - ✅ Improved healing executor to wait for user input in headful mode
  - ✅ Added AI analysis of failure patterns for continuous improvement

- **2025-10-10**: Initial import and setup completed
  - Imported from GitHub repository (master branch)
  - Configured for Replit environment
  - Fixed Python package dependencies (python-socketio, eventlet, gevent)
  - Installed Playwright browsers
  - Configured server for port 5000 with 0.0.0.0 binding
  - Removed hardcoded API keys for security

## Next Steps
1. Set up OpenAI API key via environment variables
2. Configure deployment for production
3. Test browser automation with sample commands
4. Consider adding authentication for multi-user support
