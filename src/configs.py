import os

REDIS_URL = os.getenv('REDIS_URL', '')
SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(24))
