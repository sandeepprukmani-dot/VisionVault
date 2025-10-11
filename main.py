from app import app, socketio

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 7890))
    socketio.run(app, port=port, debug=True, allow_unsafe_werkzeug=True)
