from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO, join_room, emit
import eventlet
import uuid

eventlet.monkey_patch()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode='eventlet')

# Homepage: create or join a room
@app.route('/')
def index():
    return render_template('index.html')

# Redirect to room with name
@app.route('/join', methods=['POST'])
def join():
    name = request.form['name']
    room = request.form['room']
    return redirect(url_for('chat', room_id=room, name=name))

# Chat room
@app.route('/chat/<room_id>')
def chat(room_id):
    name = request.args.get('name')
    if not name:
        return redirect('/')
    return render_template('chat.html', room_id=room_id, name=name)

# SocketIO: handle messages
@socketio.on('join')
def handle_join(data):
    join_room(data['room'])
    emit('message', {'user': 'System', 'text': f"{data['name']} joined the room."}, room=data['room'])

@socketio.on('send_message')
def handle_send_message(data):
    emit('message', {'user': data['name'], 'text': data['message']}, room=data['room'])

# Main start point for Render
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
