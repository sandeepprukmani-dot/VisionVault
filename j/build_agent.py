import PyInstaller.__main__
import sys
import os

def build_agent():
    agent_script = 'agent/local_agent.py'
    
    args = [
        agent_script,
        '--name=BrowserAutomationAgent',
        '--onefile',
        '--console',
        '--clean',
        '--noconfirm',
    ]
    
    if sys.platform == 'win32':
        args.append('--icon=NONE')
    
    print("Building standalone agent executable...")
    print(f"Platform: {sys.platform}")
    print(f"Arguments: {args}\n")
    
    PyInstaller.__main__.run(args)
    
    print("\n" + "="*50)
    print("Build complete!")
    print("="*50)
    
    if sys.platform == 'win32':
        print(f"Executable location: dist\\BrowserAutomationAgent.exe")
    else:
        print(f"Executable location: dist/BrowserAutomationAgent")
    
    print("\nTo run the agent:")
    if sys.platform == 'win32':
        print("  set AGENT_SERVER_URL=http://your-server:5000")
        print("  dist\\BrowserAutomationAgent.exe")
    else:
        print("  export AGENT_SERVER_URL=http://your-server:5000")
        print("  ./dist/BrowserAutomationAgent")

if __name__ == '__main__':
    build_agent()
