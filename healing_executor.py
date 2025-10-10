import asyncio
import json
import re
from code_validator import CodeValidator
from openai import OpenAI
import os

class HealingExecutor:
    def __init__(self, socketio):
        self.socketio = socketio
        self.client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
        self.healed_script = None
        self.failed_locators = []
        self.retry_count = 0
        self.max_retries = 3
        self.user_selector_event = None
        self.user_selected_selector = None
        self.execution_mode = 'server'  # 'server' or 'agent'
        self.agent_result = None
        self.agent_result_event = None
        
    def improve_locator_with_ai(self, failed_locator, error_message, page_html_snippet=''):
        """Use AI to suggest better locator strategies."""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": """You are an expert at web automation and CSS/XPath selectors.
When a locator fails, suggest better, more robust alternatives. Consider:
1. Using text content locators when possible
2. Using data-testid or aria-labels
3. Using role-based selectors
4. Creating more specific CSS selectors
5. Using XPath as last resort

Return ONLY the improved locator string, nothing else."""},
                    {"role": "user", "content": f"""Failed locator: {failed_locator}
Error: {error_message}
Page context: {page_html_snippet[:500] if page_html_snippet else 'Not available'}

Suggest a better locator:"""}
                ],
                temperature=0.3
            )
            
            improved = response.choices[0].message.content.strip()
            if improved.startswith('```'):
                improved = improved.split('\n')[1]
            if improved.endswith('```'):
                improved = improved.rsplit('\n', 1)[0]
                
            return improved.strip('"\'')
        except Exception as e:
            print(f"AI locator improvement error: {e}")
            return failed_locator
    
    def heal_script(self, original_code, failed_locator, healed_locator):
        """Replace failed locator with healed one in the script."""
        healed = original_code.replace(failed_locator, healed_locator)
        self.healed_script = healed
        return healed
    
    async def wait_for_user_selector(self, timeout=300):
        """Wait for user to select an element interactively."""
        self.user_selector_event = asyncio.Event()
        self.user_selected_selector = None
        
        try:
            await asyncio.wait_for(self.user_selector_event.wait(), timeout=timeout)
            return self.user_selected_selector
        except asyncio.TimeoutError:
            return None
    
    def set_user_selector(self, selector):
        """Called when user selects an element."""
        self.user_selected_selector = selector
        if self.user_selector_event:
            self.user_selector_event.set()
    
    def set_agent_result(self, result):
        """Called when agent returns result."""
        self.agent_result = result
        if self.agent_result_event:
            self.agent_result_event.set()
    
    async def _execute_on_agent(self, code, browser_name, headless, test_id, attempt_num, logs):
        """Execute code on agent and wait for result."""
        import base64
        
        # Setup event to wait for agent result
        self.agent_result_event = asyncio.Event()
        self.agent_result = None
        
        # Emit execution request to agent
        mode = 'headless' if headless else 'headful'
        self.socketio.emit('execute_healing_attempt', {
            'test_id': test_id,
            'code': code,
            'browser': browser_name,
            'mode': mode,
            'attempt': attempt_num + 1
        })
        
        # Wait for agent result with timeout
        try:
            await asyncio.wait_for(self.agent_result_event.wait(), timeout=120)
        except asyncio.TimeoutError:
            return {
                'success': False,
                'logs': logs + ['❌ Agent execution timeout'],
                'screenshot': None,
                'can_heal': False
            }
        
        result = self.agent_result
        if not result:
            return {
                'success': False,
                'logs': logs + ['❌ No result from agent'],
                'screenshot': None,
                'can_heal': False
            }
        
        # Decode screenshot if present
        screenshot = None
        if result.get('screenshot'):
            try:
                screenshot = base64.b64decode(result['screenshot'])
            except:
                pass
        
        logs.extend(result.get('logs', []))
        
        if result.get('success'):
            logs.append("✅ Execution completed successfully")
            return {
                'success': True,
                'logs': logs,
                'screenshot': screenshot
            }
        else:
            # Extract failed locator from error
            error_msg = ' '.join(result.get('logs', []))
            failed_locator = self.extract_failed_locator(error_msg)
            
            if failed_locator:
                self.failed_locators.append({
                    'locator': failed_locator,
                    'error': error_msg,
                    'attempt': attempt_num + 1
                })
                
                return {
                    'success': False,
                    'logs': logs,
                    'screenshot': screenshot,
                    'can_heal': True,
                    'failed_locator': failed_locator,
                    'error_message': error_msg,
                    'page_content': ''
                }
            else:
                return {
                    'success': False,
                    'logs': logs,
                    'screenshot': screenshot,
                    'can_heal': False
                }
    
    async def execute_with_healing(self, code, browser_name, headless, test_id):
        """Execute code with automatic healing and retry on failures."""
        validator = CodeValidator()
        if not validator.validate(code):
            return {
                'success': False,
                'logs': ['Security validation failed: ' + '; '.join(validator.get_errors())],
                'screenshot': None,
                'healed_script': None
            }
        
        self.healed_script = code
        current_code = code
        
        for attempt in range(self.max_retries):
            result = await self._execute_single_attempt(current_code, browser_name, headless, test_id, attempt)
            
            if result['success']:
                final_result = {
                    'success': True,
                    'logs': result['logs'],
                    'screenshot': result['screenshot'],
                    'healed_script': self.healed_script if self.healed_script != code else None,
                    'failed_locators': self.failed_locators
                }
                
                if self.failed_locators:
                    await self.report_failures_to_ai(test_id)
                    final_result['logs'].append("📊 AI analysis complete - check insights for improvement recommendations")
                
                return final_result
            
            if not result.get('can_heal'):
                return result
            
            failed_locator = result.get('failed_locator')
            if failed_locator:
                improved_locator = None
                
                if not headless:
                    self.socketio.emit('element_selector_needed', {
                        'test_id': test_id,
                        'failed_locator': failed_locator,
                        'error': result.get('error_message', ''),
                        'attempt': attempt + 1
                    })
                    
                    result['logs'].append(f"👆 Waiting for user to select element (failed locator: {failed_locator})...")
                    
                    user_selector = await self.wait_for_user_selector(timeout=300)
                    
                    if user_selector:
                        improved_locator = user_selector
                        result['logs'].append(f"✅ User selected element: {improved_locator}")
                    else:
                        result['logs'].append(f"⏱️  User selection timeout, falling back to AI...")
                        improved_locator = self.improve_locator_with_ai(
                            failed_locator, 
                            result.get('error_message', ''),
                            result.get('page_content', '')
                        )
                        result['logs'].append(f"🤖 AI suggested locator: {improved_locator}")
                else:
                    self.socketio.emit('healing_required', {
                        'test_id': test_id,
                        'failed_locator': failed_locator,
                        'error': result.get('error_message', ''),
                        'attempt': attempt + 1,
                        'headless': headless
                    })
                    
                    improved_locator = self.improve_locator_with_ai(
                        failed_locator, 
                        result.get('error_message', ''),
                        result.get('page_content', '')
                    )
                    
                    result['logs'].append(f"🔧 Healing attempt {attempt + 1}: AI suggested locator: {improved_locator}")
                
                current_code = self.heal_script(current_code, failed_locator, improved_locator)
                
                self.socketio.emit('script_healed', {
                    'test_id': test_id,
                    'healed_script': current_code,
                    'failed_locator': failed_locator,
                    'healed_locator': improved_locator,
                    'attempt': attempt + 1
                })
                
                await asyncio.sleep(0.5)
            else:
                return result
        
        final_result = {
            'success': False,
            'logs': result.get('logs', []) + [f'❌ Failed after {self.max_retries} healing attempts'],
            'screenshot': result.get('screenshot'),
            'healed_script': self.healed_script,
            'failed_locators': self.failed_locators
        }
        
        if self.failed_locators:
            await self.report_failures_to_ai(test_id)
        
        return final_result
    
    async def _execute_single_attempt(self, code, browser_name, headless, test_id, attempt_num):
        """Execute a single attempt of the automation code."""
        logs = [f"▶️  Attempt {attempt_num + 1}: Executing automation..."]
        screenshot = None
        page_content = ''
        
        # If agent execution mode, delegate to agent
        if self.execution_mode == 'agent':
            return await self._execute_on_agent(code, browser_name, headless, test_id, attempt_num, logs)
        
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeout
            
            restricted_globals = {
                '__builtins__': {
                    'True': True, 'False': False, 'None': None,
                    'dict': dict, 'list': list, 'str': str, 'int': int,
                    'float': float, 'bool': bool, 'len': len,
                    'Exception': Exception, '__import__': __import__,
                }
            }
            
            local_vars = {}
            
            try:
                exec(code, restricted_globals, local_vars)
                
                if 'run_test' not in local_vars:
                    logs.append("❌ Error: Generated code must contain a run_test function")
                    return {
                        'success': False,
                        'logs': logs,
                        'screenshot': None,
                        'can_heal': False
                    }
                
                result = await local_vars['run_test'](browser_name=browser_name, headless=headless)
                logs.extend(result.get('logs', []))
                screenshot = result.get('screenshot')
                
                if result.get('success'):
                    logs.append("✅ Execution completed successfully")
                    return {
                        'success': True,
                        'logs': logs,
                        'screenshot': screenshot
                    }
                else:
                    error_msg = ' '.join(result.get('logs', []))
                    failed_locator = self.extract_failed_locator(error_msg)
                    
                    if failed_locator:
                        self.failed_locators.append({
                            'locator': failed_locator,
                            'error': error_msg,
                            'attempt': attempt_num + 1
                        })
                        
                        return {
                            'success': False,
                            'logs': logs,
                            'screenshot': screenshot,
                            'can_heal': True,
                            'failed_locator': failed_locator,
                            'error_message': error_msg,
                            'page_content': page_content
                        }
                    else:
                        return {
                            'success': False,
                            'logs': logs,
                            'screenshot': screenshot,
                            'can_heal': False
                        }
                        
            except PlaywrightTimeout as e:
                error_msg = str(e)
                logs.append(f"⏱️  Timeout error: {error_msg}")
                
                failed_locator = self.extract_failed_locator(error_msg)
                
                if failed_locator:
                    self.failed_locators.append({
                        'locator': failed_locator,
                        'error': error_msg,
                        'attempt': attempt_num + 1
                    })
                    
                    return {
                        'success': False,
                        'logs': logs,
                        'screenshot': screenshot,
                        'can_heal': True,
                        'failed_locator': failed_locator,
                        'error_message': error_msg,
                        'page_content': page_content
                    }
                else:
                    return {
                        'success': False,
                        'logs': logs,
                        'screenshot': screenshot,
                        'can_heal': False
                    }
            
            except Exception as e:
                error_msg = str(e)
                logs.append(f"❌ Execution error: {error_msg}")
                
                failed_locator = self.extract_failed_locator(error_msg)
                
                if failed_locator:
                    self.failed_locators.append({
                        'locator': failed_locator,
                        'error': error_msg,
                        'attempt': attempt_num + 1
                    })
                    
                    return {
                        'success': False,
                        'logs': logs,
                        'screenshot': screenshot,
                        'can_heal': True,
                        'failed_locator': failed_locator,
                        'error_message': error_msg,
                        'page_content': page_content
                    }
                else:
                    return {
                        'success': False,
                        'logs': logs,
                        'screenshot': screenshot,
                        'can_heal': False
                    }
            
        except Exception as e:
            logs.append(f'💥 Fatal error: {str(e)}')
            return {
                'success': False,
                'logs': logs,
                'screenshot': screenshot,
                'can_heal': False
            }
    
    def extract_failed_locator(self, error_message):
        """Extract the failed locator from error message."""
        patterns = [
            r'locator\("([^"]+)"\)',
            r'selector "([^"]+)"',
            r'element "([^"]+)"',
            r'get_by_text\("([^"]+)"\)',
            r'get_by_role\("([^"]+)"\)',
            r"locator\('([^']+)'\)",
            r"selector '([^']+)'",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, error_message, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    async def report_failures_to_ai(self, test_id):
        """Report all failures and healing attempts to AI for continuous improvement."""
        if not self.failed_locators or not self.client:
            return
        
        try:
            failure_report = {
                'test_id': test_id,
                'total_failures': len(self.failed_locators),
                'failures': self.failed_locators,
                'healed_script': self.healed_script
            }
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": """You are an automation quality analyst. 
Analyze the failures and healing attempts to provide insights for improving automation scripts.
Identify patterns, suggest best practices, and recommend preventive measures."""},
                    {"role": "user", "content": f"""Analyze these automation failures and healing attempts:

Test ID: {test_id}
Total Failures: {len(self.failed_locators)}

Failures:
{json.dumps(self.failed_locators, indent=2)}

Final Healed Script:
{self.healed_script[:500] if self.healed_script else 'None'}

Provide:
1. Key insights about failure patterns
2. Recommendations for better locator strategies
3. Preventive measures for future scripts"""}
                ],
                temperature=0.3
            )
            
            insights = response.choices[0].message.content.strip()
            
            self.socketio.emit('ai_insights', {
                'test_id': test_id,
                'insights': insights,
                'failure_count': len(self.failed_locators)
            })
            
            return insights
        except Exception as e:
            print(f"AI feedback error: {e}")
            return None
