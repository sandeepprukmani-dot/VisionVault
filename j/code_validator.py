import ast
import re

class CodeValidator:
    ALLOWED_IMPORTS = {
        'playwright.async_api',
        'asyncio',
        'time',
        'datetime',
        're',
        'json',
        'base64'
    }
    
    DANGEROUS_MODULES = {
        'os', 'sys', 'subprocess', 'shutil', 'eval', 'exec',
        'compile', '__import__', 'open', 'file', 'input',
        'execfile', 'reload', 'importlib', 'pickle', 'shelve',
        'socket', 'urllib', 'requests', 'http', 'ftplib',
        'telnetlib', 'smtplib', 'poplib', 'imaplib'
    }
    
    def __init__(self):
        self.errors = []
    
    def validate(self, code):
        self.errors = []
        
        if not code or not isinstance(code, str):
            self.errors.append("Code must be a non-empty string")
            return False
        
        if not self._check_function_structure(code):
            return False
        
        if not self._check_dangerous_imports(code):
            return False
        
        if not self._check_dangerous_patterns(code):
            return False
        
        try:
            tree = ast.parse(code)
            if not self._validate_ast(tree):
                return False
        except SyntaxError as e:
            self.errors.append(f"Syntax error: {str(e)}")
            return False
        
        return True
    
    def _check_function_structure(self, code):
        if 'async def run_test' not in code:
            self.errors.append("Code must contain 'async def run_test' function")
            return False
        
        if 'playwright.async_api import async_playwright' not in code:
            self.errors.append("Code must use 'from playwright.async_api import async_playwright'")
            return False
        
        return True
    
    def _check_dangerous_imports(self, code):
        for module in self.DANGEROUS_MODULES:
            patterns = [
                f'import {module}',
                f'from {module}',
                f'__import__("{module}")',
                f"__import__('{module}')"
            ]
            for pattern in patterns:
                if pattern in code:
                    self.errors.append(f"Dangerous import detected: {module}")
                    return False
        
        return True
    
    def _check_dangerous_patterns(self, code):
        dangerous_patterns = [
            (r'\beval\s*\(', 'eval() function'),
            (r'\bexec\s*\(', 'exec() function'),
            (r'\b__import__\s*\(', '__import__() function'),
            (r'\bcompile\s*\(', 'compile() function'),
            (r'\bopen\s*\(', 'open() function (file access)'),
            (r'\.system\s*\(', 'system() call'),
            (r'\.popen\s*\(', 'popen() call'),
            (r'\.spawn\s*\(', 'spawn() call'),
        ]
        
        for pattern, name in dangerous_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                self.errors.append(f"Dangerous pattern detected: {name}")
                return False
        
        return True
    
    def _validate_ast(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not self._is_allowed_import(alias.name):
                        self.errors.append(f"Disallowed import: {alias.name}")
                        return False
            
            elif isinstance(node, ast.ImportFrom):
                if node.module and not self._is_allowed_import(node.module):
                    self.errors.append(f"Disallowed import from: {node.module}")
                    return False
            
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ['eval', 'exec', 'compile', '__import__', 'open']:
                        self.errors.append(f"Dangerous function call: {node.func.id}")
                        return False
        
        return True
    
    def _is_allowed_import(self, module_name):
        for allowed in self.ALLOWED_IMPORTS:
            if module_name.startswith(allowed):
                return True
        return False
    
    def get_errors(self):
        return self.errors
