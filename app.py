from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_socketio import SocketIO, join_room, emit
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

chat_history = {}

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

@socketio.on('join')
def handle_join(data):
    room = data['room']
    name = data['name']
    join_room(room)
    emit('message', {'user': 'System', 'text': f"{name} joined the room."}, room=room)

    now = datetime.now()
    if room in chat_history:
        for msg in chat_history[room]:
            if now - msg['time'] < timedelta(hours=24):
                emit('message', {
                    'user': msg['user'],
                    'text': msg['text'],
                    'image_url': msg.get('image_url')
                })

@socketio.on('send_message')
def handle_send_message(data):
    room = data['room']
    msg = {
        'user': data['name'],
        'text': data.get('message', ''),
        'time': datetime.now()
    }
    if 'image_url' in data:
        msg['image_url'] = data['image_url']

    if room not in chat_history:
        chat_history[room] = []
    chat_history[room].append(msg)

    emit('message', {
        'user': msg['user'],
        'text': msg['text'],
        'image_url': msg.get('image_url')
    }, room=room)

@app.route('/upload_image', methods=['POST'])
def upload_image():
    file = request.files['image']
    filename = f"{datetime.now().timestamp()}_{file.filename}"
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)
    return jsonify({"url": f"/static/uploads/{filename}"})

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/clear_chats', methods=['POST'])
def clear_chats():
    global chat_history
    chat_history = {}
    socketio.emit('message', {'user': 'System', 'text': '⚠️ Chat history was cleared by Admin.'})
    return redirect(url_for('admin'))

if __name__ == '__main__':
    socketio.run(app, debug=True)
