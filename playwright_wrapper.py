from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import time
import re
import os

class SelfHealingPlaywright:
    def __init__(self, socketio, locators, save_locators_fn):
        self.socketio = socketio
        self.locators = locators
        self.save_locators_fn = save_locators_fn
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.waiting_for_fix = False
        self.pending_action = None
        
    def cleanup(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
    
    def inject_overlay_script(self):
        overlay_js = """
        (function() {
            if (window.__playwright_overlay_injected) return;
            window.__playwright_overlay_injected = true;
            
            window.showLocatorOverlay = function(selector, action) {
                const overlay = document.createElement('div');
                overlay.id = 'playwright-overlay';
                overlay.style.cssText = `
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background: rgba(0, 0, 0, 0.5);
                    z-index: 999999;
                    pointer-events: none;
                    font-family: Arial, sans-serif;
                `;
                
                const message = document.createElement('div');
                message.style.cssText = `
                    position: fixed;
                    top: 20px;
                    left: 50%;
                    transform: translateX(-50%);
                    background: white;
                    padding: 20px 30px;
                    border-radius: 10px;
                    max-width: 500px;
                    text-align: center;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                    pointer-events: auto;
                    z-index: 1000000;
                    cursor: move;
                    user-select: none;
                `;
                message.innerHTML = `
                    <h2 style="color: #e74c3c; margin: 0 0 10px 0; font-size: 18px;">⚠️ Locator Not Found</h2>
                    <p style="color: #333; font-size: 14px; margin: 8px 0;">
                        Could not find: <code style="background: #f0f0f0; padding: 3px 6px; border-radius: 3px; font-size: 12px;">${selector}</code>
                    </p>
                    <p style="color: #2196F3; font-size: 14px; font-weight: bold; margin: 12px 0 8px 0;">
                        👆 Click the correct element on the page for "${action}"
                    </p>
                    <p style="color: #999; font-size: 11px; margin: 0;">
                        Drag to move • This will disappear after you click
                    </p>
                `;
                
                document.body.appendChild(overlay);
                document.body.appendChild(message);
                
                let isDragging = false;
                let currentX;
                let currentY;
                let initialX;
                let initialY;
                let xOffset = 0;
                let yOffset = 0;
                
                message.addEventListener('mousedown', function(e) {
                    initialX = e.clientX - xOffset;
                    initialY = e.clientY - yOffset;
                    isDragging = true;
                });
                
                document.addEventListener('mousemove', function(e) {
                    if (isDragging) {
                        e.preventDefault();
                        currentX = e.clientX - initialX;
                        currentY = e.clientY - initialY;
                        xOffset = currentX;
                        yOffset = currentY;
                        
                        message.style.transform = `translate(calc(-50% + ${currentX}px), ${currentY}px)`;
                    }
                });
                
                document.addEventListener('mouseup', function() {
                    isDragging = false;
                });
                
                let clickHandler = function(e) {
                    if (isDragging) return;
                    
                    if (e.target.closest('#playwright-overlay') || e.target === message || message.contains(e.target)) {
                        return;
                    }
                    
                    e.preventDefault();
                    e.stopPropagation();
                    
                    const locator = window.generateLocator(e.target);
                    
                    window.playwright_clicked_locator = {
                        selector: selector,
                        newLocator: locator,
                        action: action
                    };
                    
                    document.removeEventListener('click', clickHandler, true);
                    overlay.remove();
                    message.remove();
                };
                
                document.addEventListener('click', clickHandler, true);
            };
            
            window.generateLocator = function(element) {
                if (element.id) {
                    return '#' + element.id;
                }
                
                if (element.className && typeof element.className === 'string') {
                    const classes = element.className.trim().split(/\\s+/).join('.');
                    if (classes) {
                        const candidate = element.tagName.toLowerCase() + '.' + classes;
                        if (document.querySelectorAll(candidate).length === 1) {
                            return candidate;
                        }
                    }
                }
                
                const text = element.textContent.trim();
                if (text && text.length < 50) {
                    return `${element.tagName.toLowerCase()}:has-text("${text}")`;
                }
                
                let path = [];
                let current = element;
                while (current && current.tagName) {
                    let selector = current.tagName.toLowerCase();
                    if (current.id) {
                        selector += '#' + current.id;
                        path.unshift(selector);
                        break;
                    } else {
                        let sibling = current;
                        let nth = 1;
                        while (sibling.previousElementSibling) {
                            sibling = sibling.previousElementSibling;
                            if (sibling.tagName === current.tagName) nth++;
                        }
                        if (nth > 1) selector += `:nth-of-type(${nth})`;
                    }
                    path.unshift(selector);
                    current = current.parentElement;
                }
                
                return path.join(' > ');
            };
        })();
        """
        self.page.evaluate(overlay_js)
    
    def wait_for_user_click(self, selector, action):
        self.page.evaluate(f'window.showLocatorOverlay("{selector}", "{action}")')
        
        self.socketio.emit('waiting_for_click', {
            'selector': selector,
            'action': action
        })
        
        start_time = time.time()
        while time.time() - start_time < 300:
            try:
                result = self.page.evaluate('window.playwright_clicked_locator')
                if result:
                    self.page.evaluate('window.playwright_clicked_locator = null')
                    return result.get('newLocator')
            except:
                pass
            time.sleep(0.5)
        
        raise Exception("User did not click an element within timeout")
    
    def click(self, selector, locator_name=None):
        actual_selector = self.locators.get(locator_name, selector) if locator_name else selector
        
        try:
            self.page.click(actual_selector, timeout=5000)
            self.socketio.emit('status', {
                'message': f'Clicked: {actual_selector}',
                'type': 'info'
            })
        except PlaywrightTimeout:
            self.socketio.emit('status', {
                'message': f'Element not found: {actual_selector}. Waiting for user input...',
                'type': 'warning'
            })
            
            new_locator = self.wait_for_user_click(actual_selector, 'click')
            
            if locator_name:
                self.locators[locator_name] = new_locator
                self.save_locators_fn(self.locators)
                self.socketio.emit('locator_updated', {
                    'name': locator_name,
                    'old': actual_selector,
                    'new': new_locator
                })
            
            self.page.click(new_locator)
            self.socketio.emit('status', {
                'message': f'Clicked with new locator: {new_locator}',
                'type': 'success'
            })
    
    def fill(self, selector, value, locator_name=None):
        actual_selector = self.locators.get(locator_name, selector) if locator_name else selector
        
        try:
            self.page.fill(actual_selector, value, timeout=5000)
            self.socketio.emit('status', {
                'message': f'Filled: {actual_selector} with "{value}"',
                'type': 'info'
            })
        except PlaywrightTimeout:
            self.socketio.emit('status', {
                'message': f'Element not found: {actual_selector}. Waiting for user input...',
                'type': 'warning'
            })
            
            new_locator = self.wait_for_user_click(actual_selector, 'fill')
            
            if locator_name:
                self.locators[locator_name] = new_locator
                self.save_locators_fn(self.locators)
                self.socketio.emit('locator_updated', {
                    'name': locator_name,
                    'old': actual_selector,
                    'new': new_locator
                })
            
            self.page.fill(new_locator, value)
            self.socketio.emit('status', {
                'message': f'Filled with new locator: {new_locator}',
                'type': 'success'
            })
    
    def goto(self, url):
        self.page.goto(url)
        self.inject_overlay_script()
        self.socketio.emit('status', {
            'message': f'Navigated to: {url}',
            'type': 'info'
        })
    
    def execute(self, code, url):
        self.playwright = sync_playwright().start()
        
        use_headless = os.environ.get('PLAYWRIGHT_HEADLESS', 'false').lower() == 'true'
        
        launch_options = {
            'headless': use_headless,
            'args': ['--no-sandbox', '--disable-setuid-sandbox'] if use_headless else []
        }
        
        self.browser = self.playwright.chromium.launch(**launch_options)
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        
        self.goto(url)
        
        safe_builtins = {
            '__builtins__': {
                'range': range,
                'len': len,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'list': list,
                'dict': dict,
                'tuple': tuple,
                'set': set,
                'print': print,
                'True': True,
                'False': False,
                'None': None,
                'Exception': Exception,
                'ValueError': ValueError,
                'TypeError': TypeError,
                'enumerate': enumerate,
                'zip': zip,
                'min': min,
                'max': max,
                'sum': sum,
                'abs': abs,
                'sorted': sorted,
                'reversed': reversed,
                'any': any,
                'all': all,
                'hasattr': hasattr,
                'getattr': getattr,
                'setattr': setattr,
                'isinstance': isinstance,
                'issubclass': issubclass,
            }
        }
        
        local_vars = {
            'page': self,
            'click': self.click,
            'fill': self.fill,
            'goto': self.goto,
            'wait': lambda ms: time.sleep(ms / 1000)
        }
        
        exec(code, safe_builtins, local_vars)
