from flask import Flask, jsonify, request
from flask_cors import CORS
import time
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests from Bubble

print("Starting Flask app...")

# Initialize SQLite database
def init_db():
    try:
        conn = sqlite3.connect('pomodoro.db')
        c = conn.cursor()
        
        # Create table first if it doesn't exist
        c.execute('''CREATE TABLE IF NOT EXISTS sessions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT,
                      start_time TEXT,
                      completed INTEGER)''')
        
        # Then check if end_time column exists and add it
        c.execute("PRAGMA table_info(sessions)")
        columns = [column[1] for column in c.fetchall()]
        
        if 'end_time' not in columns:
            c.execute('ALTER TABLE sessions ADD COLUMN end_time TEXT')
        
        conn.commit()
        conn.close()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Database initialization error: {e}")
        raise

try:
    init_db()
    print("Database initialization completed")
except Exception as e:
    print(f"Failed to initialize database: {e}")
    exit(1)

# Per-user timer states - each user gets their own timer
user_timers = {}

def get_user_timer(user_id):
    """Get or create timer state for a specific user"""
    if user_id not in user_timers:
        user_timers[user_id] = {
            'is_running': False,
            'start_time': None,
            'paused': 0,  
            'remaining_time': 25 * 60
        }
    return user_timers[user_id]

@app.route('/api/start_timer', methods=['POST'])
def start_timer():
    user_id = request.json.get('user_id', 'default_user')
    timer_state = get_user_timer(user_id)
    
    if not timer_state['is_running']:
        timer_state['is_running'] = True
        if timer_state['paused'] == 1:
            timer_state['start_time'] = time.time() - (25 * 60 - timer_state['remaining_time'])
            timer_state['paused'] = 0
        else:
            timer_state['start_time'] = time.time()
        
        conn = sqlite3.connect('pomodoro.db')
        c = conn.cursor()
        c.execute("INSERT INTO sessions (user_id, start_time, completed) VALUES (?, ?, ?)",
                (user_id, datetime.now().isoformat(), 0))
        conn.commit()
        conn.close()
    
    return jsonify(timer_state)

@app.route('/api/pause_timer', methods=['POST'])
def pause_timer():
    user_id = request.json.get('user_id', 'default_user')
    timer_state = get_user_timer(user_id)
    
    if timer_state['is_running']:
        elapsed = time.time() - timer_state['start_time']
        timer_state['remaining_time'] = max(0, (25 * 60 - elapsed + 1))
        timer_state['is_running'] = False
        timer_state['start_time'] = None
        timer_state['paused'] = 1
    
    return jsonify(timer_state)

@app.route('/api/reset_timer', methods=['POST'])
def reset_timer():
    user_id = request.json.get('user_id', 'default_user')
    timer_state = get_user_timer(user_id)
    
    # Mark any running session as incomplete before resetting
    if timer_state['is_running'] or timer_state['paused'] == 1:
        conn = sqlite3.connect('pomodoro.db')
        c = conn.cursor()
        c.execute("UPDATE sessions SET end_time = ? WHERE user_id = ? AND completed = 0 AND end_time IS NULL", 
                 (datetime.now().isoformat(), user_id))
        conn.commit()
        conn.close()
    
    timer_state['is_running'] = False
    timer_state['start_time'] = None
    timer_state['paused'] = 0
    timer_state['remaining_time'] = 25 * 60
    
    return jsonify(timer_state)

@app.route('/api/timer_status', methods=['GET'])
def timer_status():
    user_id = request.args.get('user_id', 'default_user')
    timer_state = get_user_timer(user_id)
    
    if timer_state['is_running']:
        elapsed = time.time() - timer_state['start_time']
        timer_state['remaining_time'] = max(0, 25 * 60 - elapsed)
        if timer_state['remaining_time'] == 0:
            timer_state['is_running'] = False
            timer_state['start_time'] = None
            # Mark session as completed AND store end time
            conn = sqlite3.connect('pomodoro.db')
            c = conn.cursor()
            c.execute("UPDATE sessions SET completed = 1, end_time = ? WHERE user_id = ? AND completed = 0", 
                     (datetime.now().isoformat(), user_id))
            conn.commit()
            conn.close()
    
    return jsonify(timer_state)

@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    user_id = request.args.get('user_id', 'default_user')
    conn = sqlite3.connect('pomodoro.db')
    c = conn.cursor()
    c.execute("SELECT start_time, end_time, completed FROM sessions WHERE user_id = ? ORDER BY start_time DESC", (user_id,))
    sessions = [{'start_time': row[0], 'end_time': row[1], 'completed': row[2]} for row in c.fetchall()]
    conn.close()
    return jsonify(sessions)

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=False, host='0.0.0.0', port=port)