"""
Configuration environment variables for Heroku.
"""
import os
from urllib.parse import urlparse

_REDIS_BASE_URL = os.getenv('REDIS_URL', '')
REDIS_CONFIG = urlparse(_REDIS_BASE_URL)
SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(24))
