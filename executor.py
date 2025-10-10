import asyncio
import sys
from io import StringIO
from code_validator import CodeValidator

class ServerExecutor:
    def execute(self, code, browser_name='chromium', headless=True):
        try:
            validator = CodeValidator()
            if not validator.validate(code):
                return {
                    'success': False,
                    'logs': ['Security validation failed: ' + '; '.join(validator.get_errors())],
                    'screenshot': None
                }
            
            restricted_globals = {
                '__builtins__': {
                    'True': True,
                    'False': False,
                    'None': None,
                    'dict': dict,
                    'list': list,
                    'str': str,
                    'int': int,
                    'float': float,
                    'bool': bool,
                    'len': len,
                    'range': range,
                    'enumerate': enumerate,
                    'zip': zip,
                    'Exception': Exception,
                    'ValueError': ValueError,
                    'TypeError': TypeError,
                    'KeyError': KeyError,
                    'AttributeError': AttributeError,
                    'getattr': getattr,
                    'setattr': setattr,
                    'hasattr': hasattr,
                    'print': print,
                    '__import__': __import__,

                }
            }
            
            local_vars = {}
            exec(code, restricted_globals, local_vars)
            
            if 'run_test' not in local_vars:
                return {
                    'success': False,
                    'logs': ['Error: Generated code must contain a run_test function'],
                    'screenshot': None
                }
            
            run_test = local_vars['run_test']
            
            result = asyncio.run(run_test(browser_name=browser_name, headless=headless))
            
            return result
        except Exception as e:
            return {
                'success': False,
                'logs': [f'Execution error: {str(e)}'],
                'screenshot': None
            }
