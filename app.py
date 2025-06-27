from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_socketio import SocketIO, join_room, leave_room, emit
from werkzeug.utils import secure_filename
import os
import uuid
import json
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
socketio = SocketIO(app)

# Ensure upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

DATA_FILE = 'chat_data.json'
all_users = {}         # { room_id: set of all users who ever joined }
online_users = {}      # { room_id: set of currently online users }
user_sessions = {}     # { sid: (username, room_id) }

# Load chat history
def load_messages():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

# Save chat history
def save_messages(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# Routes
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
    return render_template('admin.html')

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

# User deletes own message
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

# Admin deletes specific message
@app.route('/delete_message_admin', methods=['POST'])
def delete_message_admin():
    data = request.json
    timestamp = data['timestamp']
    messages = load_messages()
    for room in messages:
        messages[room] = [m for m in messages[room] if m.get('timestamp') != timestamp]
    save_messages(messages)
    return '', 204

# Admin clears all messages
@app.route('/clear_all_chats', methods=['POST'])
def clear_all_chats():
    save_messages({})
    return '', 204

# Admin selects room to clear
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

# Get members of a room
@app.route('/get_members/<room>')
def get_members(room):
    online = list(online_users.get(room, set()))
    all_in_room = list(all_users.get(room, set()))
    members = []
    for user in all_in_room:
        members.append({
            'name': user,
            'online': user in online
        })
    return jsonify({'members': members})

# Socket.IO events
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

    # Send past messages
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
    elif msg_type in ['image', 'sticker']:
        message['image_url'] = data['image_url']
    else:
        return

    all_msgs = load_messages()
    all_msgs.setdefault(room, []).append(message)
    save_messages(all_msgs)

    emit('message', message, room=room)

# Run App
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
