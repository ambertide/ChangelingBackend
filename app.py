from src.server import socketio, app
import os

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24))