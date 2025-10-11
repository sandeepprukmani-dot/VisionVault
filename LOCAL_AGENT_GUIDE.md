# VisionVault Local Agent Guide

## Overview

The VisionVault Local Agent allows you to run browser automations in **headful mode** on your local machine, enabling you to see the browser in action and interact with the element selector widget when locators fail.

## How It Works

### Execution Modes

1. **Headless Mode** (Default)
   - Runs on the server
   - Browser runs in the background without UI
   - Faster execution
   - No local agent required

2. **Headful Mode** (Requires Local Agent)
   - Runs on your local machine
   - Browser opens visually so you can see the automation
   - Element selector widget appears when a locator fails
   - Allows interactive healing by clicking on elements

## Setting Up the Local Agent

### Prerequisites
- Python 3.11+
- Playwright installed

### Step 1: Download the Agent
1. Go to the Configuration page in the web app
2. Click "Download Local Agent" button
3. Save `local_agent.py` to your local machine

### Step 2: Install Dependencies
```bash
pip install socketio playwright
playwright install
```

### Step 3: Configure Server URL
Set the server URL as an environment variable (or edit the script):
```bash
# On Windows
set AGENT_SERVER_URL=http://your-server-url:5000

# On Mac/Linux
export AGENT_SERVER_URL=http://your-server-url:5000
```

### Step 4: Run the Agent
```bash
python local_agent.py
```

You should see:
```
Starting Browser Automation Agent
Agent ID: [unique-id]
Server URL: [your-server-url]
Connecting to server...
Connection established! Waiting for tasks...
```

### Step 5: Verify Connection
- Go back to the web app
- The top-right badge should change from "Disconnected" to "Connected"
- The agent is now ready to receive tasks!

## Using Headful Mode

### Running Automations in Headful Mode

1. Make sure your local agent is connected (badge shows "Connected")
2. Enter your automation command
3. Click the "Headful" mode button (eye icon)
4. Click "Execute Automation"

The browser will open on your local machine and you'll see the automation run in real-time!

### Interactive Element Healing

When a locator fails during headful mode execution:

1. **Widget Appears**: A red overlay with instructions appears on the browser page
2. **Select Element**: Hover over elements to see them highlighted in green
3. **Click to Fix**: Click on the correct element you want to select
4. **Automatic Healing**: The locator is automatically updated and the script continues
5. **Auto-Close**: Browser closes after 20 seconds or when healing is complete

#### Widget Features:
- Red banner shows the failed locator
- Green outline highlights elements on hover
- Click any element to select it as the fix
- Visual confirmation when element is selected
- Auto-cleanup after selection or timeout

## Troubleshooting

### Agent Won't Connect
- Verify the server URL is correct
- Check that port 5000 is accessible
- Ensure no firewall is blocking the connection

### Browser Not Launching
- Make sure Playwright browsers are installed: `playwright install`
- Check that the agent is actually connected (green badge)
- Verify you selected "Headful" mode (not "Headless")

### Widget Not Appearing
- Only appears in **headful mode** when running on local agent
- Only triggers when a locator actually fails
- Browser must be kept open during the healing attempt

### Browser Closes Too Quickly
- Browser now stays open for 20 seconds during healing
- Closes automatically after element selection
- If you need more time, you can modify the timeout in local_agent.py (line 305)

## Architecture

```
Web App (Server) ← WebSocket → Local Agent (Your Machine)
                                      ↓
                              Playwright Browser (Headful)
                                      ↓
                              Website Under Test
                                      ↓
                              Element Selector Widget
```

1. Web app sends automation code to local agent via WebSocket
2. Local agent launches browser in headful mode on your machine
3. If locator fails, agent keeps browser open and injects widget
4. You select the correct element by clicking
5. Agent sends selected locator back to server
6. Script is healed and retried
7. Browser closes after healing or 20-second timeout

## Tips

- **Keep Agent Running**: The local agent needs to stay running to handle tasks
- **One Agent at a Time**: Only run one agent per machine for best results
- **Network**: Ensure stable connection between agent and server
- **Permissions**: You may need to allow browser automation in your security settings
- **Visual Debugging**: Use headful mode to debug and understand what your automation is doing

## Security Notes

- The agent runs code sent from the server on your local machine
- Only connect to trusted servers
- Review automation scripts before execution
- The agent uses code validation to prevent dangerous operations
