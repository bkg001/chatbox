from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from flask_socketio import SocketIO, join_room, leave_room, emit
from werkzeug.utils import secure_filename
import os
import uuid
import json
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.secret_key = 'super_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
socketio = SocketIO(app)

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

DATA_FILE = 'chat_data.json'
ADMIN_FILE = 'admin.json'
all_users = {}
online_users = {}
user_sessions = {}

def load_messages():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_messages(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_admin_credentials():
    with open(ADMIN_FILE, 'r') as f:
        return json.load(f)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/join', methods=['POST'])
def join():
    name = request.form['name']
    room = request.form['room']
    return redirect(url_for('chat', room_id=room, name=name))

@app.route('/chat/<room_id>')
def chat(room_id):
    name = request.args.get('name')
    if not name:
        return redirect('/')
    return render_template('chat.html', room_id=room_id, name=name)

@app.route('/admin')
def admin():
    if not session.get('admin_logged_in'):
        return redirect('/admin_login')
    return render_template('admin.html')

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        data = load_admin_credentials()
        username = request.form['username']  # ✅ Correct field
        password = request.form['password']
        if username == data['username'] and password == data['password']:
            session['admin_logged_in'] = True
            return redirect('/admin')
        else:
            return "Invalid credentials", 401
    return render_template('admin_login.html')

@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect('/admin_login')

@app.route('/reset_admin', methods=['GET', 'POST'])
def reset_admin():
    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm = request.form['confirm_password']
        if new_password != confirm:
            return "Passwords do not match", 400
        data = load_admin_credentials()
        data['password'] = new_password
        with open(ADMIN_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return redirect('/admin_login')
    return render_template('reset_admin.html')

@app.route('/room_activity/<room>')
def room_activity(room):
    if not session.get('admin_logged_in'):
        return redirect('/admin_login')
    messages = load_messages().get(room, [])
    return render_template('room_activity.html', room=room, messages=messages)

@app.route('/upload_image', methods=['POST'])
def upload_image():
    file = request.files['image']
    if file:
        filename = secure_filename(str(uuid.uuid4()) + "_" + file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        url = f'/static/uploads/{filename}'
        return jsonify({'url': url})
    return jsonify({'error': 'No file uploaded'}), 400

@app.route('/delete_message', methods=['POST'])
def delete_message():
    data = request.json
    room = data['room']
    timestamp = data['timestamp']
    messages = load_messages()
    if room in messages:
        messages[room] = [m for m in messages[room] if m.get('timestamp') != timestamp]
    save_messages(messages)
    return '', 204

@app.route('/delete_message_admin', methods=['POST'])
def delete_message_admin():
    data = request.json
    timestamp = data['timestamp']
    messages = load_messages()
    for room in messages:
        messages[room] = [m for m in messages[room] if m.get('timestamp') != timestamp]
    save_messages(messages)
    return '', 204

@app.route('/clear_all_chats', methods=['POST'])
def clear_all_chats():
    save_messages({})
    return '', 204

@app.route('/get_rooms')
def get_rooms():
    messages = load_messages()
    return jsonify({'rooms': list(messages.keys())})

@app.route('/clear_room_chat', methods=['POST'])
def clear_room_chat():
    data = request.json
    room = data.get('room')
    messages = load_messages()
    if room in messages:
        del messages[room]
        save_messages(messages)
    return '', 204

@app.route('/get_members/<room>')
def get_members(room):
    online = list(online_users.get(room, set()))
    all_in_room = list(all_users.get(room, set()))
    members = [{'name': user, 'online': user in online} for user in all_in_room]
    return jsonify({'members': members})

@socketio.on('join')
def handle_join(data):
    room = data['room']
    name = data['name']
    join_room(room)

    all_users.setdefault(room, set()).add(name)
    online_users.setdefault(room, set()).add(name)
    user_sessions[request.sid] = (name, room)

    emit('message', {
        'user': 'System',
        'text': f'{name} joined the room.',
        'type': 'text',
        'timestamp': datetime.utcnow().isoformat()
    }, room=room)

    messages = load_messages().get(room, [])
    for msg in messages:
        emit('message', msg)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in user_sessions:
        name, room = user_sessions[sid]
        online_users.get(room, set()).discard(name)
        user_sessions.pop(sid, None)

@socketio.on('send_message')
def handle_send_message(data):
    room = data['room']
    name = data['name']
    msg_type = data.get('type', 'text')
    timestamp = datetime.utcnow().isoformat()

    message = {
        'user': name,
        'type': msg_type,
        'timestamp': timestamp
    }

    if msg_type == 'text':
        message['text'] = data['message']
    elif msg_type in ['image', 'sticker', 'document']:
        message['image_url'] = data['image_url']
    else:
        return

    all_msgs = load_messages()
    all_msgs.setdefault(room, []).append(message)
    save_messages(all_msgs)

    emit('message', message, room=room)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=5050, allow_unsafe_werkzeug=True)
