from flask import Flask, jsonify, request
from flask_cors import CORS
import time
import sqlite3
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# Per-user timer states (dict keyed by user_id)
user_states = {}

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect('pomodoro.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sessions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT,
                  start_time TEXT,
                  end_time TEXT,
                  completed INTEGER)''')
    conn.commit()
    conn.close()

init_db()

def get_user_state(user_id):
    if user_id not in user_states:
        user_states[user_id] = {
            'is_running': False,
            'start_time': None,
            'paused': 0,
            'remaining_time': 25 * 60,
            'current_session_id': None
        }
    return user_states[user_id]

@app.route('/api/start_timer', methods=['POST'])
def start_timer():
    data = request.json
    user_id = data.get('user_id', 'default_user')
    state = get_user_state(user_id)

    if not state['is_running']:
        state['is_running'] = True
        if state['paused'] == 1:
            # Resume: adjust start_time based on remaining
            state['start_time'] = time.time() - (25 * 60 - state['remaining_time'])
            state['paused'] = 0
        else:
            # New start: insert session and store ID
            conn = sqlite3.connect('pomodoro.db')
            c = conn.cursor()
            start_iso = datetime.now().isoformat()
            c.execute("INSERT INTO sessions (user_id, start_time, end_time, completed) VALUES (?, ?, ?, ?)",
                      (user_id, start_iso, None, 0))
            state['current_session_id'] = c.lastrowid
            conn.commit()
            conn.close()
            state['start_time'] = time.time()
            state['remaining_time'] = 25 * 60  # Reset for new session

    return jsonify(state)

@app.route('/api/pause_timer', methods=['POST'])
def pause_timer():
    data = request.json
    user_id = data.get('user_id', 'default_user')
    state = get_user_state(user_id)

    if state['is_running']:
        elapsed = time.time() - state['start_time']
        state['remaining_time'] = max(0, 25 * 60 - elapsed)
        state['is_running'] = False
        state['start_time'] = None
        state['paused'] = 1
        # Note: No end_time yet; session is paused, not ended

    return jsonify(state)

@app.route('/api/reset_timer', methods=['POST'])
def reset_timer():
    data = request.json
    user_id = data.get('user_id', 'default_user')
    state = get_user_state(user_id)

    if state['current_session_id'] and (state['is_running'] or state['paused']):
        # Mark current session as incomplete with end_time (aborted)
        conn = sqlite3.connect('pomodoro.db')
        c = conn.cursor()
        end_iso = datetime.now().isoformat()
        c.execute("UPDATE sessions SET end_time = ?, completed = 0 WHERE id = ?",
                  (end_iso, state['current_session_id']))
        conn.commit()
        conn.close()

    state['is_running'] = False
    state['start_time'] = None
    state['paused'] = 0
    state['remaining_time'] = 25 * 60
    state['current_session_id'] = None

    return jsonify(state)

@app.route('/api/timer_status', methods=['GET'])
def timer_status():
    user_id = request.args.get('user_id', 'default_user')
    state = get_user_state(user_id)

    if state['is_running']:
        elapsed = time.time() - state['start_time']
        state['remaining_time'] = max(0, 25 * 60 - elapsed)
        if state['remaining_time'] <= 0:
            state['remaining_time'] = 0
            state['is_running'] = False
            state['start_time'] = None
            state['paused'] = 0
            # Mark current session as completed with end_time
            if state['current_session_id']:
                conn = sqlite3.connect('pomodoro.db')
                c = conn.cursor()
                end_iso = datetime.now().isoformat()
                c.execute("UPDATE sessions SET end_time = ?, completed = 1 WHERE id = ?",
                          (end_iso, state['current_session_id']))
                conn.commit()
                conn.close()
                state['current_session_id'] = None

    return jsonify({
        'is_running': state['is_running'],
        'remaining_time': state['remaining_time']
    })  # Only send necessary fields

@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    user_id = request.args.get('user_id', 'default_user')
    conn = sqlite3.connect('pomodoro.db')
    c = conn.cursor()
    c.execute("SELECT start_time, end_time, completed FROM sessions WHERE user_id = ? ORDER BY id DESC",
              (user_id,))
    sessions = [{'start_time': row[0], 'end_time': row[1], 'completed': row[2]} for row in c.fetchall()]
    conn.close()
    return jsonify(sessions)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)