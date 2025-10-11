import asyncio
from datetime import datetime
from typing import List, Dict, Optional
from playwright.async_api import Page, Browser, async_playwright
import uuid


class ActionRecorder:
    """Records browser actions for teaching mode."""
    
    def __init__(self):
        self.actions: List[Dict] = []
        self.is_recording = False
        self.page: Optional[Page] = None
        self.browser: Optional[Browser] = None
        self.playwright_instance = None
    
    async def start_recording(self, browser_name='chromium', headless=False):
        """Start recording browser actions."""
        self.actions = []
        self.is_recording = True
        
        # Launch browser
        self.playwright_instance = await async_playwright().start()
        browser_type = getattr(self.playwright_instance, browser_name)
        self.browser = await browser_type.launch(headless=headless)
        self.page = await self.browser.new_page()
        
        # Set up event listeners
        self.page.on('framenavigated', lambda frame: self._on_navigation(frame))
        
        return self.page
    
    def _on_navigation(self, frame):
        """Record navigation events."""
        if frame == self.page.main_frame:
            self.record_action({
                'type': 'navigate',
                'url': frame.url,
                'timestamp': datetime.now().isoformat()
            })
    
    def record_action(self, action: Dict):
        """Record an action."""
        if self.is_recording:
            self.actions.append(action)
    
    def record_goto(self, url: str):
        """Record a goto action."""
        self.record_action({
            'type': 'goto',
            'url': url,
            'timestamp': datetime.now().isoformat()
        })
    
    def record_click(self, selector: str, text: Optional[str] = None):
        """Record a click action."""
        self.record_action({
            'type': 'click',
            'selector': selector,
            'text': text,
            'timestamp': datetime.now().isoformat()
        })
    
    def record_fill(self, selector: str, value: str):
        """Record a fill/input action."""
        self.record_action({
            'type': 'fill',
            'selector': selector,
            'value': value,
            'timestamp': datetime.now().isoformat()
        })
    
    def record_select(self, selector: str, value: str):
        """Record a select action."""
        self.record_action({
            'type': 'select',
            'selector': selector,
            'value': value,
            'timestamp': datetime.now().isoformat()
        })
    
    def record_check(self, selector: str):
        """Record a checkbox/radio check action."""
        self.record_action({
            'type': 'check',
            'selector': selector,
            'timestamp': datetime.now().isoformat()
        })
    
    def record_wait(self, wait_type: str, selector: Optional[str] = None, timeout: int = 5000):
        """Record a wait action."""
        action = {
            'type': 'wait',
            'wait_type': wait_type,  # 'navigation', 'selector', 'timeout'
            'timeout': timeout,
            'timestamp': datetime.now().isoformat()
        }
        if selector:
            action['selector'] = selector
        self.record_action(action)
    
    async def stop_recording(self):
        """Stop recording and return captured actions."""
        self.is_recording = False
        
        # Close browser
        if self.browser:
            await self.browser.close()
        if self.playwright_instance:
            await self.playwright_instance.stop()
        
        return self.actions
    
    def generate_playwright_code(self, actions: Optional[List[Dict]] = None) -> str:
        """Generate Playwright code from recorded actions."""
        if actions is None:
            actions = self.actions
        
        if not actions:
            return ""
        
        # Start building the code
        code_lines = [
            "async def run_test(browser_name='chromium', headless=True):",
            "    from playwright.async_api import async_playwright",
            "    logs = []",
            "    screenshot = None",
            "    ",
            "    try:",
            "        async with async_playwright() as p:",
            "            browser = await getattr(p, browser_name).launch(headless=headless)",
            "            page = await browser.new_page()",
            "            ",
        ]
        
        # Convert actions to code
        for i, action in enumerate(actions):
            action_type = action.get('type')
            
            if action_type == 'goto' or action_type == 'navigate':
                url = action.get('url')
                code_lines.append(f"            await page.goto('{url}')")
                code_lines.append(f"            logs.append('Navigated to {url}')")
            
            elif action_type == 'click':
                selector = action.get('selector')
                code_lines.append(f"            await page.click('{selector}')")
                code_lines.append(f"            logs.append('Clicked {selector}')")
            
            elif action_type == 'fill':
                selector = action.get('selector')
                value = action.get('value', '').replace("'", "\\'")
                code_lines.append(f"            await page.fill('{selector}', '{value}')")
                code_lines.append(f"            logs.append('Filled {selector}')")
            
            elif action_type == 'select':
                selector = action.get('selector')
                value = action.get('value')
                code_lines.append(f"            await page.select_option('{selector}', '{value}')")
                code_lines.append(f"            logs.append('Selected option in {selector}')")
            
            elif action_type == 'check':
                selector = action.get('selector')
                code_lines.append(f"            await page.check('{selector}')")
                code_lines.append(f"            logs.append('Checked {selector}')")
            
            elif action_type == 'wait':
                wait_type = action.get('wait_type')
                if wait_type == 'navigation':
                    code_lines.append("            await page.wait_for_load_state('networkidle')")
                    code_lines.append("            logs.append('Waited for navigation')")
                elif wait_type == 'selector':
                    selector = action.get('selector')
                    timeout = action.get('timeout', 5000)
                    code_lines.append(f"            await page.wait_for_selector('{selector}', timeout={timeout})")
                    code_lines.append(f"            logs.append('Waited for {selector}')")
                elif wait_type == 'timeout':
                    timeout = action.get('timeout', 1000)
                    code_lines.append(f"            await page.wait_for_timeout({timeout})")
                    code_lines.append(f"            logs.append('Waited {timeout}ms')")
        
        # Add screenshot and closing code
        code_lines.extend([
            "            ",
            "            # Take screenshot before closing",
            "            screenshot = await page.screenshot()",
            "            logs.append('Screenshot captured')",
            "            ",
            "            await browser.close()",
            "            return {'success': True, 'logs': logs, 'screenshot': screenshot}",
            "    ",
            "    except Exception as e:",
            "        logs.append(f'Error: {str(e)}')",
            "        if 'page' in locals():",
            "            try:",
            "                screenshot = await page.screenshot()",
            "            except:",
            "                pass",
            "        if 'browser' in locals():",
            "            try:",
            "                await browser.close()",
            "            except:",
            "                pass",
            "        return {'success': False, 'logs': logs, 'screenshot': screenshot}"
        ])
        
        return "\n".join(code_lines)
    
    @staticmethod
    def parse_code_to_actions(playwright_code: str) -> List[Dict]:
        """
        Parse Playwright code to extract actions (reverse operation).
        This is a simple parser that looks for common patterns.
        """
        actions = []
        lines = playwright_code.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Parse goto
            if 'page.goto(' in line:
                import re
                match = re.search(r"page\.goto\(['\"](.+?)['\"]\)", line)
                if match:
                    actions.append({
                        'type': 'goto',
                        'url': match.group(1)
                    })
            
            # Parse click
            elif 'page.click(' in line:
                import re
                match = re.search(r"page\.click\(['\"](.+?)['\"]\)", line)
                if match:
                    actions.append({
                        'type': 'click',
                        'selector': match.group(1)
                    })
            
            # Parse fill
            elif 'page.fill(' in line:
                import re
                match = re.search(r"page\.fill\(['\"](.+?)['\"],\s*['\"](.+?)['\"]\)", line)
                if match:
                    actions.append({
                        'type': 'fill',
                        'selector': match.group(1),
                        'value': match.group(2)
                    })
            
            # Add more parsers as needed
        
        return actions


class InteractiveRecorder(ActionRecorder):
    """
    Enhanced recorder that can intercept and record actual user interactions.
    This would be used with a UI where users can click through a task.
    """
    
    async def start_interactive_recording(self, browser_name='chromium'):
        """Start interactive recording with visible browser."""
        page = await self.start_recording(browser_name, headless=False)
        
        # Inject JavaScript to capture all clicks, inputs, etc.
        await page.add_init_script("""
            window.__recordedActions = [];
            
            // Record clicks
            document.addEventListener('click', (e) => {
                const selector = getSelector(e.target);
                window.__recordedActions.push({
                    type: 'click',
                    selector: selector,
                    text: e.target.textContent,
                    timestamp: new Date().toISOString()
                });
            }, true);
            
            // Record input
            document.addEventListener('input', (e) => {
                const selector = getSelector(e.target);
                window.__recordedActions.push({
                    type: 'fill',
                    selector: selector,
                    value: e.target.value,
                    timestamp: new Date().toISOString()
                });
            }, true);
            
            // Helper to generate CSS selector
            function getSelector(element) {
                if (element.id) return '#' + element.id;
                if (element.className) return element.tagName.toLowerCase() + '.' + element.className.split(' ')[0];
                return element.tagName.toLowerCase();
            }
        """)
        
        return page
    
    async def get_recorded_actions_from_page(self):
        """Get actions recorded by JavaScript injection."""
        if not self.page:
            return []
        
        try:
            js_actions = await self.page.evaluate("window.__recordedActions || []")
            return js_actions
        except:
            return []
