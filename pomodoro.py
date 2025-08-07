from flask import Flask, jsonify, request
from flask_cors import CORS
import time
import sqlite3
from datetime import datetime
import pytz
import os
import logging

app = Flask(__name__)
CORS(app)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Per-user timer states
user_states = {}

# Durations
DURATIONS = {'work': 25 * 60, 'break': 5 * 60, 'long_break': 15 * 60}

# Initialize DB
def init_db():
    try:
        db_path = '/data/pomodoro.db'  # Persistent disk path
        os.makedirs('/data', exist_ok=True)  # Ensure /data exists
        conn = sqlite3.connect(db_path)
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
        logger.info("Database initialized successfully at %s", db_path)
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
        raise

try:
    init_db()
except Exception as e:
    logger.error("Initialization failed: %s", e)
    raise

def get_user_state(user_id):
    if user_id not in user_states:
        user_states[user_id] = {
            'is_running': False,
            'start_time': None,
            'paused': 0,
            'remaining_time': DURATIONS['work'],
            'current_session_id': None,
            'type': 'work',
            'work_count': 0
        }
    return user_states[user_id]

@app.route('/api/start_timer', methods=['POST'])
def start_timer():
    try:
        data = request.json
        user_id = data.get('user_id', 'default_user')
        state = get_user_state(user_id)

        if not state['is_running']:
            state['is_running'] = True
            if state['paused'] == 1:
                state['start_time'] = time.time() - (DURATIONS[state['type']] - state['remaining_time'])
                state['paused'] = 0
            else:
                conn = sqlite3.connect('/data/pomodoro.db')
                c = conn.cursor()
                start_iso = datetime.now(pytz.UTC).isoformat()
                c.execute("INSERT INTO sessions (user_id, type, start_time, end_time, completed) VALUES (?, ?, ?, ?, ?)",
                          (user_id, state['type'], start_iso, None, 0))
                state['current_session_id'] = c.lastrowid
                conn.commit()
                conn.close()
                state['start_time'] = time.time()
                state['remaining_time'] = DURATIONS[state['type']]
            logger.info("Timer started for user %s: %s", user_id, state)
        return jsonify(state)
    except Exception as e:
        logger.error("Error in start_timer: %s", e)
        return jsonify({'error': str(e)}), 500

@app.route('/api/pause_timer', methods=['POST'])
def pause_timer():
    try:
        data = request.json
        user_id = data.get('user_id', 'default_user')
        state = get_user_state(user_id)

        if state['is_running']:
            elapsed = time.time() - state['start_time']
            state['remaining_time'] = max(0, DURATIONS[state['type']] - elapsed)
            state['is_running'] = False
            state['start_time'] = None
            state['paused'] = 1
            logger.info("Timer paused for user %s: %s", user_id, state)
        return jsonify(state)
    except Exception as e:
        logger.error("Error in pause_timer: %s", e)
        return jsonify({'error': str(e)}), 500

@app.route('/api/reset_timer', methods=['POST'])
def reset_timer():
    try:
        data = request.json
        user_id = data.get('user_id', 'default_user')
        state = get_user_state(user_id)

        if state['current_session_id'] and (state['is_running'] or state['paused']):
            conn = sqlite3.connect('/data/pomodoro.db')
            c = conn.cursor()
            end_iso = datetime.now(pytz.UTC).isoformat()
            c.execute("UPDATE sessions SET end_time = ?, completed = 0 WHERE id = ?",
                      (end_iso, state['current_session_id']))
            conn.commit()
            conn.close()

        state['is_running'] = False
        state['start_time'] = None
        state['paused'] = 0
        state['remaining_time'] = DURATIONS['work']
        state['current_session_id'] = None
        state['type'] = 'work'
        state['work_count'] = 0
        logger.info("Timer reset for user %s: %s", user_id, state)
        return jsonify(state)
    except Exception as e:
        logger.error("Error in reset_timer: %s", e)
        return jsonify({'error': str(e)}), 500

@app.route('/api/timer_status', methods=['GET'])
def timer_status():
    try:
        user_id = request.args.get('user_id', 'default_user')
        state = get_user_state(user_id)

        if state['is_running']:
            elapsed = time.time() - state['start_time']
            state['remaining_time'] = max(0, DURATIONS[state['type']] - elapsed)
            if state['remaining_time'] <= 0:
                state['remaining_time'] = 0
                if state['current_session_id']:
                    conn = sqlite3.connect('/data/pomodoro.db')
                    c = conn.cursor()
                    end_iso = datetime.now(pytz.UTC).isoformat()
                    c.execute("UPDATE sessions SET end_time = ?, completed = 1 WHERE id = ?",
                              (end_iso, state['current_session_id']))
                    conn.commit()
                    conn.close()
                    state['current_session_id'] = None

                if state['type'] == 'work':
                    state['work_count'] += 1
                    next_type = 'long_break' if state['work_count'] >= 4 else 'break'
                    if next_type == 'long_break':
                        state['work_count'] = 0
                else:
                    next_type = 'work'
                state['type'] = next_type
                state['remaining_time'] = DURATIONS[next_type]
                state['start_time'] = time.time()
                state['is_running'] = True
                state['paused'] = 0

                conn = sqlite3.connect('/data/pomodoro.db')
                c = conn.cursor()
                start_iso = datetime.now(pytz.UTC).isoformat()
                c.execute("INSERT INTO sessions (user_id, type, start_time, end_time, completed) VALUES (?, ?, ?, ?, ?)",
                          (user_id, next_type, start_iso, None, 0))
                state['current_session_id'] = c.lastrowid
                conn.commit()
                conn.close()
                logger.info("Session completed for user %s, started %s", user_id, next_type)

        return jsonify({
            'is_running': state['is_running'],
            'remaining_time': state['remaining_time'],
            'type': state['type'],
            'duration': DURATIONS[state['type']]
        })
    except Exception as e:
        logger.error("Error in timer_status: %s", e)
        return jsonify({'error': str(e)}), 500

@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    try:
        user_id = request.args.get('user_id', 'default_user')
        conn = sqlite3.connect('/data/pomodoro.db')
        c = conn.cursor()
        c.execute("SELECT start_time, end_time, completed, type FROM sessions WHERE user_id = ? ORDER BY id DESC",
                  (user_id,))
        sessions = [{'start_time': row[0], 'end_time': row[1], 'completed': row[2], 'type': row[3]} for row in c.fetchall()]
        conn.close()
        logger.info("Fetched sessions for user %s: %d sessions", user_id, len(sessions))
        return jsonify(sessions)
    except Exception as e:
        logger.error("Error in get_sessions: %s", e)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)