# Browser Automation Platform

## Overview
A Flask-based web application for natural language-driven browser automation using Playwright. The system supports dual execution modes:
- **Server-side execution**: Headless browser automation running directly on the Flask server
- **Local agent execution**: Standalone executable agent for headful/headless browser testing on users' machines

## Current State
Fully functional browser automation platform with:
- Web dashboard for entering natural language test commands
- OpenAI GPT-4 integration for converting commands to Playwright code
- Real-time WebSocket communication between server and local agents
- SQLite database for test history storage
- Screenshot capture and execution log viewing
- Support for Chromium, Firefox, and WebKit browsers
- PyInstaller build configuration for creating standalone agent executables

## Recent Changes (October 5, 2025)
- Initial project setup with Flask, Flask-SocketIO, Playwright, and OpenAI
- Created web dashboard UI with Bootstrap 5
- Implemented server-side Playwright executor for headless mode
- Built local agent with WebSocket client and browser detection
- Added real-time status streaming and result display
- Set up SQLite database with test history tracking
- Created PyInstaller build script for agent packaging

## Project Architecture

### Backend (Flask)
- `app.py`: Main Flask application with WebSocket server, API endpoints, and database integration
- `executor.py`: Server-side Playwright code execution engine
- `automation.db`: SQLite database storing test history

### Frontend
- `templates/index.html`: Web dashboard with natural language input, execution controls, and results viewer

### Local Agent
- `agent/local_agent.py`: Standalone agent script with WebSocket client and Playwright execution
- `agent/requirements.txt`: Agent dependencies for local installation
- `build_agent.py`: PyInstaller build script for creating executables

### Key Features
1. **Natural Language Processing**: OpenAI GPT-4 converts plain English commands into executable Playwright code
2. **Dual Execution Modes**: 
   - Server (headless only)
   - Local agent (headful or headless)
3. **Real-time Communication**: WebSocket-based bidirectional communication for live status updates
4. **Browser Support**: Auto-detection of Chrome, Firefox, Edge, Safari on local systems
5. **Test History**: Persistent storage of commands, generated code, results, and screenshots
6. **Agent Distribution**: Downloadable agent script and build tools for standalone executables

## Environment Variables
- `OPENAI_API_KEY`: Required for GPT-4 code generation
- `SESSION_SECRET`: Flask session secret (auto-generated in development)
- `AGENT_SERVER_URL`: Server URL for local agent connection (set on agent side)

## Running the Application
The Flask server runs on port 5000 with WebSocket support enabled.

## Local Agent Setup
1. Download `local_agent.py` from the web dashboard
2. Install dependencies: `pip install -r requirements.txt`
3. Install Playwright browsers: `python -m playwright install`
4. Set server URL: `export AGENT_SERVER_URL=http://your-server:5000`
5. Run agent: `python local_agent.py`

## Building Standalone Agent Executable
Run `python build_agent.py` to create platform-specific executables in the `dist/` directory.
