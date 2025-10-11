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
- **Mode**: Development with debug enabled
- **CORS**: Enabled for all origins

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

## Recent Changes

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
