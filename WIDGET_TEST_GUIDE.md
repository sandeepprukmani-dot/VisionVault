# Healing Widget Test Guide

## Complete Widget Flow Verification

### Prerequisites
1. ✅ Application is running on port 5000
2. ✅ Local agent is running (`python local_agent.py`)
3. ✅ Agent shows as "Connected" in the UI

### Test Procedure

#### Step 1: Create a Test with Failing Locator

1. **Open the VisionVault dashboard** in your browser
2. **Select Mode**: Choose **"Headful"** (important!)
3. **Select Execution**: Choose **"Agent"** (not server)
4. **Enter a test command** that will intentionally fail:
   ```
   Go to example.com and click the button with text "ThisButtonDoesNotExist"
   ```

#### Step 2: Execute and Monitor

1. **Click "Execute Automation"**
2. **Watch your local agent console** - You should see:
   ```
   ✅ Injected page capture for variable 'page' (browser: 'browser')
   ✅ Page captured for test X - browser will stay open for healing
   Healing attempt 1 for test X: FAILED
   ⏳ Widget injection event created, waiting for lifecycle to complete...
   
   🔔 AGENT: Received element_selector_needed event
      Test ID: X
      Mode: headful
      Failed Locator: button with text "ThisButtonDoesNotExist"
      Active Page: Available
      Event Loop: Available
   
   ✅ AGENT: All conditions met - injecting widget for test X
   ✅ Injecting element selector widget on the launched browser page for test X
   🎯 Injecting element selector for test X
      Failed locator: button with text "ThisButtonDoesNotExist"
      Please click on the correct element in your browser...
   ```

3. **Check your browser window** (the one opened by Playwright on your machine):
   - You should see a **semi-transparent dark overlay** covering the entire page
   - At the top center, there should be a **red banner** with:
     - "🔧 Element Selector Active"
     - The failed locator displayed in a code block

#### Step 3: Interact with the Widget

1. **Move your mouse** over elements on the page:
   - Elements should **highlight with a green outline** as you hover
   
2. **Click on an element**:
   - The banner should turn **green**
   - Show "✅ Element Selected!" with the selector
   - The overlay should disappear after 1 second

3. **Check agent console**:
   ```
   ✅ User selected element: button.example-class
   ✅ Widget injection lifecycle completed for test X
   ✅ Browser closed after healing attempt
   ```

### Expected Event Flow

```
[SERVER] Test fails → emits 'element_selector_needed'
    ↓
[AGENT] Receives event → checks conditions:
    ✓ Mode is headful
    ✓ Active page exists
    ✓ Event loop exists
    ↓
[AGENT] Injects JavaScript widget into browser page
    ↓
[USER] Sees overlay and clicks element
    ↓
[AGENT] Captures selection → emits 'element_selected' to server
    ↓
[SERVER] Continues healing with new selector
```

### Troubleshooting

#### Widget Not Appearing?

**Check 1: Mode Selection**
- ❌ If mode is "Headless" → Widget will NOT appear
- ✅ Mode must be "Headful"

**Check 2: Execution Location**
- ❌ If execution is "Server" → Widget will NOT appear
- ✅ Execution must be "Agent"

**Check 3: Agent Connection**
- Check if agent console shows: `🔔 AGENT: Received element_selector_needed event`
- If NOT received, check server logs for emission confirmation

**Check 4: Page Capture**
- Agent should show: `✅ Page captured for test X - browser will stay open for healing`
- If shows: `❌ Could not capture page` → The generated code doesn't match the pattern

**Check 5: Event Loop**
- Agent should show: `Event Loop: Available`
- If shows `Event Loop: None` → Agent startup issue

#### Widget Appears but Browser Closes Immediately?

- Check for timeout (default: 20 seconds for selection)
- Widget has 20 seconds before auto-closing
- Make sure you click an element within this timeframe

### Simple Test Case

Use this exact command to test:
```
Navigate to https://example.com and click on the "More information" link
```

Then when it fails (because the locator might not match exactly), you should see the widget and be able to click the actual "More information..." link on the page.

### What Success Looks Like

✅ Browser opens on your machine (headful mode)  
✅ Test runs and fails on a locator  
✅ **Red banner appears at top of browser** with "🔧 Element Selector Active"  
✅ Hovering highlights elements in green  
✅ Clicking an element captures the selector  
✅ Banner turns green showing success  
✅ Browser closes after 1 second  
✅ Healing continues with the new selector  

### Debug Checklist

- [ ] Application running on port 5000
- [ ] Agent running and connected (check UI status)
- [ ] Mode set to "Headful"
- [ ] Execution set to "Agent"
- [ ] Test command will cause a locator failure
- [ ] Agent console shows page capture success
- [ ] Agent console shows element_selector_needed event received
- [ ] Browser window opens on your machine
- [ ] Widget overlay is visible in browser
- [ ] Can hover and click elements
