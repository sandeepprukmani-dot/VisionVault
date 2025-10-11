# Widget Flow Guide - How Browser Opens on Client & Widget Appears

## Overview
This document explains how the browser automation system ensures that:
1. The browser opens on the client machine (local agent)
2. The interactive widget appears when a locator fails

## Complete Flow

### 1. Test Execution Request
```
User submits test → Server generates code → Server sends to agent
```

**Key Fix Applied:**
- ✅ Events are now **targeted to specific agent** using `to=agent_sid` parameter
- ✅ Previously, events were broadcast to all connected clients (causing connection issues)

### 2. Browser Opens on Client (Local Agent)

When you run a test with:
- **Execution Location**: Agent
- **Mode**: Headful
- **Healing**: Enabled

**What Happens:**
1. Server sends `execute_healing_attempt` event **directly to your local agent**
2. Your local agent's event loop receives the event
3. Agent executes the test code using Playwright
4. Browser window **opens on your local machine** (not the server)

**Key Fix Applied:**
- ✅ Fixed `event_loop` scope issue - it was creating a local variable instead of updating the global
- ✅ Now the event loop properly receives and processes execution requests

### 3. Locator Failure Detection

When a locator fails (e.g., button not found):

**Server Side:**
1. Agent sends test result back to server via `healing_attempt_result`
2. Server's `HealingExecutor` analyzes the error
3. If a failed locator is detected, server extracts it from error message

**Agent Side:**
1. Browser stays open (code is modified to comment out `browser.close()`)
2. Active page reference is stored globally for widget injection

### 4. Widget Injection Flow

**When locator fails in headful mode:**

```
Server detects failed locator
    ↓
Server emits 'element_selector_needed' → Agent (targeted)
    ↓
Agent receives event
    ↓
Agent checks: mode='headful' AND active_page exists AND event_loop exists
    ↓
Agent injects JavaScript widget into active browser page
    ↓
User sees overlay and can click to select element
```

**Key Fixes Applied:**
- ✅ Widget injection is triggered by server (not by agent automatically)
- ✅ `element_selector_needed` event is targeted to specific agent session
- ✅ Removed redundant widget injection that happened too early
- ✅ Proper flow ensures widget only appears when server confirms locator failure

### 5. Element Selection

When widget appears:
1. **Overlay** covers the page with dark transparent background
2. **Banner** appears at top with instructions
3. User hovers over elements (they highlight in yellow)
4. User clicks desired element
5. Agent generates CSS selector for clicked element
6. Agent sends selector back to server via `element_selected` event
7. Server updates the code with new selector
8. Server re-runs the test with healed code

## Architecture Diagrams

### Agent-Server Communication
```
Local Agent (Your Computer)          Server (Replit)
─────────────────────────────        ───────────────────
                                     
1. Connect & Register
   agent_register ──────────────→   
                  ←──────────────   agent_registered
                                     
2. Execute Test
                  ←──────────────   execute_healing_attempt (targeted)
   [Browser Opens]
   [Test Runs]
   healing_attempt_result ──────→   
                                     
3. Widget Flow (if locator fails)
                  ←──────────────   element_selector_needed (targeted)
   [Widget Injects]
   [User Clicks]
   element_selected ─────────────→   
                                     
4. Retry with Healed Code
                  ←──────────────   execute_healing_attempt (targeted)
   [Browser Runs Fixed Code]
   healing_attempt_result ──────→   
```

### Browser Lifecycle in Headful Mode
```
Test Start
    ↓
Agent receives execute_healing_attempt
    ↓
Code is modified:
  - Playwright context manager → manual start/stop
  - browser.close() → commented out
  - Page reference → stored globally
    ↓
Browser launches on LOCAL MACHINE
    ↓
Test executes
    ↓
IF SUCCESS:
  - Emit result
  - Browser closes
  
IF FAILURE:
  - Extract failed locator
  - Emit result (browser stays open)
  - Wait for element_selector_needed
  - Inject widget when received
  - Wait for user selection
  - Update code
  - Retry (browser still open)
```

## Key Configuration Files

### gunicorn.conf.py
```python
# Filters out SIGWINCH signals to prevent log spam
logconfig_dict = {
    'filters': {
        'winch_filter': {
            '()': lambda: type('WinchFilter', (), {
                'filter': lambda self, record: 'Handling signal: winch' not in record.getMessage()
            })()
        }
    }
}
```

### local_agent.py - Event Loop Setup
```python
def main():
    global event_loop  # ✅ CRITICAL: Use global keyword
    
    sio.connect(SERVER_URL)
    
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    
    event_loop.run_forever()
```

### healing_executor.py - Targeted Events
```python
# ✅ Events are sent to specific agent, not broadcast
if self.agent_sid:
    self.socketio.emit('element_selector_needed', {
        'test_id': test_id,
        'failed_locator': failed_locator,
        'mode': mode
    }, to=self.agent_sid)  # ← Targeted emission
```

## Testing the Flow

### To verify browser opens on client:
1. Start local agent on your computer
2. Create a test with execution location = "Agent"
3. Set mode to "Headful"
4. Run the test
5. **Expected:** Browser window opens on YOUR computer (not Replit server)

### To verify widget appears:
1. Create a test that will fail (e.g., "click button with text 'NonExistentButton'")
2. Enable healing
3. Set execution location = "Agent"
4. Set mode = "Headful"
5. Run the test
6. **Expected:** 
   - Browser opens on your computer
   - Test fails to find button
   - Dark overlay appears with red banner
   - You can click any element to select it

## Troubleshooting

### Browser doesn't open on client
- ✅ Ensure local agent is connected (check green badge in UI)
- ✅ Verify execution location is set to "Agent"
- ✅ Check local agent console for event_loop initialization message

### Widget doesn't appear
- ✅ Ensure mode is set to "Headful" (not "Headless")
- ✅ Verify the test actually failed (widget only appears on failure)
- ✅ Check that a locator was detected in the error message
- ✅ Ensure browser window is still open when widget should inject

### Connection drops
- ✅ All fixed! Events are now properly targeted
- ✅ Check firewall isn't blocking WebSocket connections
- ✅ Verify server URL is correct in local agent

## Summary of Fixes

✅ **Connection Stability**
- Fixed event_loop scope issue
- Targeted events to specific agent instead of broadcasting
- Proper session management

✅ **Browser on Client**
- Event loop properly initialized and accessible
- Execute events targeted to agent
- Browser launches locally in headful mode

✅ **Widget Injection**
- Server-triggered (not automatic)
- Only in headful mode with failed locator
- Properly waits for page to be ready
- Targeted communication prevents interference

✅ **Clean Logs**
- SIGWINCH signals filtered
- No more log spam
- Clear execution flow visibility
