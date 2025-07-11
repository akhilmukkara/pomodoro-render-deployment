from flask import Flask, jsonify, request
from flask_cors import CORS
import time
import sqlite3
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests from Bubble

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect('pomodoro.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sessions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT,
                  start_time TEXT,
                  completed INTEGER)''')
    conn.commit()
    conn.close()

init_db()

# Timer state
timer_state = {
    'is_running': False,
    'start_time': None,
    'duration': 25 * 60,  # 25 minutes in seconds
    'remaining_time': 25 * 60
}

@app.route('/api/start_timer', methods=['POST'])
def start_timer():
    if not timer_state['is_running']:
        timer_state['is_running'] = True
        timer_state['start_time'] = time.time()
        user_id = request.json.get('user_id', 'default_user')
        conn = sqlite3.connect('pomodoro.db')
        c = conn.cursor()
        c.execute("INSERT INTO sessions (user_id, start_time, completed) VALUES (?, ?, ?)",
                  (user_id, datetime.now().isoformat(), 0))
        conn.commit()
        conn.close()
    return jsonify(timer_state)

@app.route('/api/pause_timer', methods=['POST'])
def pause_timer():
    if timer_state['is_running']:
        elapsed = time.time() - timer_state['start_time']
        timer_state['remaining_time'] -= elapsed
        timer_state['is_running'] = False
        timer_state['start_time'] = None
    return jsonify(timer_state)

@app.route('/api/reset_timer', methods=['POST'])
def reset_timer():
    timer_state['is_running'] = False
    timer_state['start_time'] = None
    timer_state['remaining_time'] = 25 * 60
    return jsonify(timer_state)

@app.route('/api/timer_status', methods=['GET'])
def timer_status():
    if timer_state['is_running']:
        elapsed = time.time() - timer_state['start_time']
        timer_state['remaining_time'] = max(0, 25 * 60 - elapsed)
        if timer_state['remaining_time'] == 0:
            timer_state['is_running'] = False
            timer_state['start_time'] = None
            # Mark session as completed
            conn = sqlite3.connect('pomodoro.db')
            c = conn.cursor()
            c.execute("UPDATE sessions SET completed = 1 WHERE completed = 0")
            conn.commit()
            conn.close()
    return jsonify(timer_state)

@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    user_id = request.args.get('user_id', 'default_user')
    conn = sqlite3.connect('pomodoro.db')
    c = conn.cursor()
    c.execute("SELECT start_time, completed FROM sessions WHERE user_id = ?", (user_id,))
    sessions = [{'start_time': row[0], 'completed': row[1]} for row in c.fetchall()]
    conn.close()
    return jsonify(sessions)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)