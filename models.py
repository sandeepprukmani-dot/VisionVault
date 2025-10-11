import sqlite3
import json
from datetime import datetime

class Database:
    def __init__(self, db_path='automation.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize all database tables."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Existing test_history table
        c.execute('''CREATE TABLE IF NOT EXISTS test_history
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      command TEXT NOT NULL,
                      generated_code TEXT NOT NULL,
                      healed_code TEXT,
                      browser TEXT,
                      mode TEXT,
                      execution_location TEXT,
                      status TEXT,
                      logs TEXT,
                      screenshot_path TEXT,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # New learned_tasks table for persistent learning
        c.execute('''CREATE TABLE IF NOT EXISTS learned_tasks
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      task_id TEXT UNIQUE NOT NULL,
                      task_name TEXT NOT NULL,
                      description TEXT,
                      steps TEXT,
                      playwright_code TEXT NOT NULL,
                      tags TEXT,
                      embedding_vector BLOB,
                      version INTEGER DEFAULT 1,
                      parent_task_id TEXT,
                      success_count INTEGER DEFAULT 0,
                      failure_count INTEGER DEFAULT 0,
                      last_executed TIMESTAMP,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Task execution history for feedback loop
        c.execute('''CREATE TABLE IF NOT EXISTS task_executions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      task_id TEXT NOT NULL,
                      execution_result TEXT,
                      success BOOLEAN,
                      error_message TEXT,
                      execution_time_ms INTEGER,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (task_id) REFERENCES learned_tasks(task_id))''')
        
        # Create indices for faster queries
        c.execute('CREATE INDEX IF NOT EXISTS idx_task_id ON learned_tasks(task_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_task_name ON learned_tasks(task_name)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON learned_tasks(created_at)')
        
        conn.commit()
        conn.close()


class LearnedTask:
    """Model for a learned automation task."""
    
    def __init__(self, task_id, task_name, playwright_code, description='', steps=None, 
                 tags=None, embedding_vector=None, version=1, parent_task_id=None):
        self.task_id = task_id
        self.task_name = task_name
        self.description = description
        self.steps = steps or []
        self.playwright_code = playwright_code
        self.tags = tags or []
        self.embedding_vector = embedding_vector
        self.version = version
        self.parent_task_id = parent_task_id
        self.success_count = 0
        self.failure_count = 0
        self.last_executed = None
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
    
    def to_dict(self):
        """Convert task to dictionary."""
        return {
            'task_id': self.task_id,
            'task_name': self.task_name,
            'description': self.description,
            'steps': self.steps,
            'playwright_code': self.playwright_code,
            'tags': self.tags,
            'version': self.version,
            'parent_task_id': self.parent_task_id,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'last_executed': self.last_executed.isoformat() if self.last_executed else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def save(self, db_path='automation.db'):
        """Save task to database."""
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Serialize complex fields
        steps_json = json.dumps(self.steps)
        tags_json = json.dumps(self.tags)
        
        # Serialize embedding vector if present
        embedding_blob = None
        if self.embedding_vector is not None:
            import numpy as np
            embedding_blob = self.embedding_vector.tobytes()
        
        c.execute('''INSERT OR REPLACE INTO learned_tasks 
                     (task_id, task_name, description, steps, playwright_code, tags, 
                      embedding_vector, version, parent_task_id, success_count, 
                      failure_count, last_executed, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (self.task_id, self.task_name, self.description, steps_json, 
                   self.playwright_code, tags_json, embedding_blob, self.version,
                   self.parent_task_id, self.success_count, self.failure_count,
                   self.last_executed, datetime.now()))
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def get_by_id(task_id, db_path='automation.db'):
        """Retrieve task by ID."""
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM learned_tasks WHERE task_id=?', (task_id,))
        row = c.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return LearnedTask._from_row(row)
    
    @staticmethod
    def get_all(db_path='automation.db', limit=100):
        """Retrieve all tasks."""
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM learned_tasks ORDER BY created_at DESC LIMIT ?', (limit,))
        rows = c.fetchall()
        conn.close()
        
        return [LearnedTask._from_row(row) for row in rows]
    
    @staticmethod
    def search_by_tags(tags, db_path='automation.db'):
        """Search tasks by tags."""
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Simple tag search - checks if any tag is present in the tags JSON
        tasks = []
        c.execute('SELECT * FROM learned_tasks')
        rows = c.fetchall()
        
        for row in rows:
            task_tags = json.loads(row[6]) if row[6] else []
            if any(tag in task_tags for tag in tags):
                tasks.append(LearnedTask._from_row(row))
        
        conn.close()
        return tasks
    
    @staticmethod
    def _from_row(row):
        """Create LearnedTask from database row."""
        import numpy as np
        
        task = LearnedTask(
            task_id=row[1],
            task_name=row[2],
            description=row[3],
            steps=json.loads(row[4]) if row[4] else [],
            playwright_code=row[5],
            tags=json.loads(row[6]) if row[6] else [],
            version=row[8],
            parent_task_id=row[9]
        )
        
        # Deserialize embedding vector
        if row[7]:
            task.embedding_vector = np.frombuffer(row[7], dtype=np.float32)
        
        task.success_count = row[10] or 0
        task.failure_count = row[11] or 0
        task.last_executed = datetime.fromisoformat(row[12]) if row[12] else None
        task.created_at = datetime.fromisoformat(row[13]) if row[13] else datetime.now()
        task.updated_at = datetime.fromisoformat(row[14]) if row[14] else datetime.now()
        
        return task


class TaskExecution:
    """Model for task execution record."""
    
    def __init__(self, task_id, execution_result, success, error_message=None, execution_time_ms=0):
        self.task_id = task_id
        self.execution_result = execution_result
        self.success = success
        self.error_message = error_message
        self.execution_time_ms = execution_time_ms
        self.created_at = datetime.now()
    
    def save(self, db_path='automation.db'):
        """Save execution record to database."""
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        c.execute('''INSERT INTO task_executions 
                     (task_id, execution_result, success, error_message, execution_time_ms)
                     VALUES (?, ?, ?, ?, ?)''',
                  (self.task_id, self.execution_result, self.success, 
                   self.error_message, self.execution_time_ms))
        
        conn.commit()
        conn.close()
