"""
Configuration environment variables for Heroku.
"""
import os

REDIS_BASE_URL = os.getenv('REDIS_URL', 'redis://:p1c3e96aa869fc622f074840372045230dadc8b25a05353ca3261b88bdea851d2@ec2-34-237-207-90.compute-1.amazonaws.com:25249')
REDIS_PORT = REDIS_BASE_URL.split(':')[-1]
REDIS_HOST = REDIS_BASE_URL[0:-len(REDIS_PORT) - 1]
# Influenced by https://stackoverflow.com/a/62777378/6663851
_REDIS_CREDS, REDIS_HOST = REDIS_HOST.split('@')
REDIS_USERNAME = _REDIS_CREDS.split(':')[-1]
SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(24))
