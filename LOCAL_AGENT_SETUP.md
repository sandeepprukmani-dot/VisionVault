# Local Agent Setup Guide

This guide will help you connect your local Windows machine to the Replit server to run browser automation tasks locally.

## Issue

You're seeing this error:
```
websocket-client package not installed, only polling transport is available
Error connecting to server:
```

## Solution

### Step 1: Install websocket-client Package

In your Windows local environment, install the missing package:

```bash
# Activate your virtual environment first
C:\Users\Sandeep\Downloads\VisionVault (1)\VisionVault\.venv\Scripts\activate

# Then install the package
pip install websocket-client
```

### Step 2: Set the Server URL Environment Variable

Set the `AGENT_SERVER_URL` environment variable to your Replit server URL:

**Option A: Set temporarily in Command Prompt**
```cmd
set AGENT_SERVER_URL=https://17224f25-a5db-43b9-bc54-70218d1b1d9c-00-3cy058l4tt5xn.sisko.replit.dev
python local_agent.py
```

**Option B: Set temporarily in PowerShell**
```powershell
$env:AGENT_SERVER_URL="https://17224f25-a5db-43b9-bc54-70218d1b1d9c-00-3cy058l4tt5xn.sisko.replit.dev"
python local_agent.py
```

**Option C: Set permanently in Windows**
1. Press `Win + X` and select "System"
2. Click "Advanced system settings"
3. Click "Environment Variables"
4. Under "User variables", click "New"
5. Variable name: `AGENT_SERVER_URL`
6. Variable value: `https://17224f25-a5db-43b9-bc54-70218d1b1d9c-00-3cy058l4tt5xn.sisko.replit.dev`
7. Click OK and restart your command prompt

### Step 3: Run the Local Agent

```bash
python local_agent.py
```

## Expected Output

When successful, you should see:
```
Starting Browser Automation Agent
Agent ID: [some-uuid]
Server URL: https://17224f25-a5db-43b9-bc54-70218d1b1d9c-00-3cy058l4tt5xn.sisko.replit.dev

Press Ctrl+C to stop the agent

Connecting to server...
Connected to server: https://17224f25-a5db-43b9-bc54-70218d1b1d9c-00-3cy058l4tt5xn.sisko.replit.dev
Detected browsers: ['chromium']
Agent registered successfully: {'status': 'success'}
```

## What the Local Agent Does

Once connected, your local agent:
- Detects browsers available on your Windows machine (Chrome, Firefox, etc.)
- Registers with the Replit server
- Receives automation tasks from the server
- Executes Playwright scripts on your local machine
- Sends results (logs and screenshots) back to the server

This allows you to run browser automation tasks on your local machine while controlling them from the Replit web interface.

## Troubleshooting

### Issue: "Error connecting to server"
- **Check your internet connection**
- **Verify the server is running** on Replit
- **Check if your firewall is blocking the connection**

### Issue: "ImportError: No module named 'playwright'"
```bash
pip install playwright
playwright install
```

### Issue: Browser not detected
- Make sure Chrome is installed at the standard location:
  - `C:\Program Files\Google\Chrome\Application\chrome.exe` OR
  - `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`

## Notes

- The local agent runs automation tasks on YOUR computer, not on the Replit server
- This is useful when you want to automate tasks on websites that require authentication or when you need to see the browser window
- Make sure your OpenAI API key is configured on the Replit server for code generation
