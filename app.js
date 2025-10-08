const socket = io();

const editor = CodeMirror.fromTextArea(document.getElementById('code-editor'), {
    mode: 'python',
    theme: 'monokai',
    lineNumbers: true,
    indentUnit: 4,
    indentWithTabs: false,
    lineWrapping: true
});

editor.setValue(`# Example self-healing script
click('#submit-button', 'submitBtn')
wait(1000)
fill('#email', 'test@example.com', 'emailInput')
click('button:has-text("Login")', 'loginButton')
`);

const statusLog = document.getElementById('status-log');
const locatorsList = document.getElementById('locators-list');
const scriptsList = document.getElementById('scripts-list');
const executeBtn = document.getElementById('execute-btn');
const clearBtn = document.getElementById('clear-btn');
const saveScriptBtn = document.getElementById('save-script');
const startUrlInput = document.getElementById('start-url');
const scriptNameInput = document.getElementById('script-name');

function addStatus(message, type = 'info') {
    const statusDiv = document.createElement('div');
    statusDiv.className = `status-message ${type}`;
    const timestamp = new Date().toLocaleTimeString();
    statusDiv.textContent = `[${timestamp}] ${message}`;
    statusLog.insertBefore(statusDiv, statusLog.firstChild);
    
    if (statusLog.children.length > 50) {
        statusLog.removeChild(statusLog.lastChild);
    }
}

function loadLocators() {
    fetch('/api/locators')
        .then(res => res.json())
        .then(locators => {
            locatorsList.innerHTML = '';
            const entries = Object.entries(locators);
            
            if (entries.length === 0) {
                locatorsList.innerHTML = '<div class="empty-state">No saved locators yet</div>';
                return;
            }
            
            entries.forEach(([name, value]) => {
                const item = document.createElement('div');
                item.className = 'locator-item';
                item.innerHTML = `
                    <div class="locator-name">${name}</div>
                    <div class="locator-value">${value}</div>
                `;
                locatorsList.appendChild(item);
            });
        });
}

function loadScripts() {
    fetch('/api/scripts')
        .then(res => res.json())
        .then(scripts => {
            scriptsList.innerHTML = '';
            
            if (scripts.length === 0) {
                scriptsList.innerHTML = '<div class="empty-state">No saved scripts yet</div>';
                return;
            }
            
            scripts.reverse().forEach(script => {
                const item = document.createElement('div');
                item.className = 'script-item';
                const date = new Date(script.created_at).toLocaleString();
                item.innerHTML = `
                    <div class="script-name">${script.name}</div>
                    <div class="script-date">${date}</div>
                `;
                item.onclick = () => {
                    editor.setValue(script.code);
                    scriptNameInput.value = script.name;
                    addStatus(`Loaded script: ${script.name}`, 'info');
                };
                scriptsList.appendChild(item);
            });
        });
}

executeBtn.addEventListener('click', () => {
    const code = editor.getValue();
    const url = startUrlInput.value.trim();
    
    if (!code.trim()) {
        addStatus('No code to execute', 'error');
        return;
    }
    
    if (!url) {
        addStatus('Please enter a start URL', 'error');
        return;
    }
    
    executeBtn.disabled = true;
    executeBtn.textContent = '⏳ Running...';
    statusLog.innerHTML = '';
    
    addStatus('Starting execution...', 'info');
    
    socket.emit('execute_script', {
        code: code,
        url: url
    });
});

clearBtn.addEventListener('click', () => {
    editor.setValue('');
    addStatus('Editor cleared', 'info');
});

saveScriptBtn.addEventListener('click', () => {
    const code = editor.getValue();
    const name = scriptNameInput.value.trim() || 'Untitled Script';
    
    if (!code.trim()) {
        addStatus('No code to save', 'error');
        return;
    }
    
    fetch('/api/scripts', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            name: name,
            code: code
        })
    })
    .then(res => res.json())
    .then(script => {
        addStatus(`Script saved: ${script.name}`, 'success');
        loadScripts();
    })
    .catch(err => {
        addStatus(`Error saving script: ${err.message}`, 'error');
    });
});

socket.on('status', (data) => {
    addStatus(data.message, data.type);
    
    if (data.type === 'success' || data.type === 'error') {
        executeBtn.disabled = false;
        executeBtn.textContent = '▶️ Execute Script';
    }
});

socket.on('waiting_for_click', (data) => {
    addStatus(`⏸️ WAITING: Click the element for "${data.action}" action`, 'warning');
    addStatus(`Looking for: ${data.selector}`, 'warning');
});

socket.on('locator_updated', (data) => {
    addStatus(`✅ Locator updated: ${data.name}`, 'success');
    addStatus(`  Old: ${data.old}`, 'info');
    addStatus(`  New: ${data.new}`, 'success');
    loadLocators();
});

socket.on('connect', () => {
    addStatus('Connected to server', 'success');
    loadLocators();
    loadScripts();
});

socket.on('disconnect', () => {
    addStatus('Disconnected from server', 'error');
    executeBtn.disabled = false;
    executeBtn.textContent = '▶️ Execute Script';
});

loadLocators();
loadScripts();
