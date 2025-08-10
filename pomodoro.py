from flask import Flask, jsonify, request
from flask_cors import CORS
import time
import sqlite3
from datetime import datetime
import pytz  # For timezone handling

app = Flask(__name__)
CORS(app)

# Per-user timer states
user_states = {}

# Durations (added 'long_break')
DURATIONS = {'work': 25 * 60, 'break': 5 * 60, 'long_break': 15 * 60}

# Initialize DB
def init_db():
    conn = sqlite3.connect('pomodoro.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sessions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT,
                  type TEXT,
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
            'remaining_time': DURATIONS['work'],
            'current_session_id': None,
            'type': 'work',  # Start with work
            'work_count': 0,   # Track consecutive completed work sessions
            'sound_event': None  # Track sound event to trigger
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
            state['start_time'] = time.time() - (DURATIONS[state['type']] - state['remaining_time'])
            state['paused'] = 0
        else:
            conn = sqlite3.connect('pomodoro.db')
            c = conn.cursor()
            start_iso = datetime.now(pytz.UTC).isoformat()  # Store in UTC
            c.execute("INSERT INTO sessions (user_id, type, start_time, end_time, completed) VALUES (?, ?, ?, ?, ?)",
                      (user_id, state['type'], start_iso, None, 0))
            state['current_session_id'] = c.lastrowid
            conn.commit()
            conn.close()
            state['start_time'] = time.time()
            state['remaining_time'] = DURATIONS[state['type']]

        # Removed sound_event = 'start'

    response = jsonify(state)
    state['sound_event'] = None  # Clear after sending
    return response

@app.route('/api/pause_timer', methods=['POST'])
def pause_timer():
    data = request.json
    user_id = data.get('user_id', 'default_user')
    state = get_user_state(user_id)

    if state['is_running']:
        elapsed = time.time() - state['start_time']
        state['remaining_time'] = max(0, DURATIONS[state['type']] - elapsed)
        state['is_running'] = False
        state['start_time'] = None
        state['paused'] = 1

    return jsonify(state)

@app.route('/api/reset_timer', methods=['POST'])
def reset_timer():
    data = request.json
    user_id = data.get('user_id', 'default_user')
    state = get_user_state(user_id)

    if state['current_session_id'] and (state['is_running'] or state['paused']):
        conn = sqlite3.connect('pomodoro.db')
        c = conn.cursor()
        end_iso = datetime.now(pytz.UTC).isoformat()  # Store in UTC
        c.execute("UPDATE sessions SET end_time = ?, completed = 0 WHERE id = ?",
                  (end_iso, state['current_session_id']))
        conn.commit()
        conn.close()

    state['is_running'] = False
    state['start_time'] = None
    state['paused'] = 0
    state['remaining_time'] = DURATIONS['work']
    state['current_session_id'] = None
    state['type'] = 'work'  # Reset to work
    state['work_count'] = 0  # Reset work count on reset
    state['sound_event'] = None  # Clear sound event

    return jsonify(state)

@app.route('/api/timer_status', methods=['GET'])
def timer_status():
    user_id = request.args.get('user_id', 'default_user')
    state = get_user_state(user_id)

    sound_event = None  # Local variable for this request

    if state['is_running']:
        elapsed = time.time() - state['start_time']
        state['remaining_time'] = max(0, DURATIONS[state['type']] - elapsed)
        if state['remaining_time'] <= 0:
            state['remaining_time'] = 0
            # Complete current session
            if state['current_session_id']:
                conn = sqlite3.connect('pomodoro.db')
                c = conn.cursor()
                end_iso = datetime.now(pytz.UTC).isoformat()  # Store in UTC
                c.execute("UPDATE sessions SET end_time = ?, completed = 1 WHERE id = ?",
                          (end_iso, state['current_session_id']))
                conn.commit()
                conn.close()
                state['current_session_id'] = None

            # Determine sound event based on completed type
            if state['type'] == 'work':
                sound_event = 'work_end'
            elif state['type'] == 'break':
                sound_event = 'break_end'
            elif state['type'] == 'long_break':
                sound_event = 'long_break_end'

            # Auto-start next type with long break logic
            if state['type'] == 'work':
                state['work_count'] += 1
                next_type = 'long_break' if state['work_count'] >= 4 else 'break'
                if next_type == 'long_break':
                    state['work_count'] = 0  # Reset after long break
            else:
                next_type = 'work'
            state['type'] = next_type
            state['remaining_time'] = DURATIONS[next_type]
            state['start_time'] = time.time()
            state['is_running'] = True
            state['paused'] = 0

            # Insert new session for next type
            conn = sqlite3.connect('pomodoro.db')
            c = conn.cursor()
            start_iso = datetime.now(pytz.UTC).isoformat()  # Store in UTC
            c.execute("INSERT INTO sessions (user_id, type, start_time, end_time, completed) VALUES (?, ?, ?, ?, ?)",
                      (user_id, next_type, start_iso, None, 0))
            state['current_session_id'] = c.lastrowid
            conn.commit()
            conn.close()

    response_data = {
        'is_running': state['is_running'],
        'remaining_time': state['remaining_time'],
        'type': state['type'],
        'duration': DURATIONS[state['type']],
        'sound_event': state['sound_event'] or sound_event  # Include sound event if any
    }
    state['sound_event'] = None  # Clear after sending
    return jsonify(response_data)

@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    user_id = request.args.get('user_id', 'default_user')
    conn = sqlite3.connect('pomodoro.db')
    c = conn.cursor()
    c.execute("SELECT start_time, end_time, completed, type FROM sessions WHERE user_id = ? ORDER BY id DESC",
              (user_id,))
    sessions = [{'start_time': row[0], 'end_time': row[1], 'completed': row[2], 'type': row[3]} for row in c.fetchall()]
    conn.close()
    return jsonify(sessions)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)