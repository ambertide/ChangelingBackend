from src.server import socketio, app
from src.configs import SECRET_KEY
import os

app.config['SECRET_KEY'] = SECRET_KEY
