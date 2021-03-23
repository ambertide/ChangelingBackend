"""
Configuration environment variables for Heroku.
"""
import os


REDIS_BASE_URL = os.getenv('REDIS_URL', '')
REDIS_PORT = REDIS_BASE_URL.split(':')[-1]
REDIS_HOST = REDIS_BASE_URL[0:-len(REDIS_PORT) - 1]
# Influenced by https://stackoverflow.com/a/62777378/6663851
_REDIS_CREDS, REDIS_HOST = REDIS_HOST.split('@')
REDIS_USERNAME, REDIS_PASSWORD = _REDIS_CREDS.split(':')
SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(24))
