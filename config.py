import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'samah-secret-key-change-in-production-2024')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        f'sqlite:///{os.path.join(BASE_DIR, "samah.db")}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    WTF_CSRF_ENABLED = True
    # SSO simulation - in production replace with real SSO
    SSO_ENABLED = os.environ.get('SSO_ENABLED', 'false').lower() == 'true'
    SSO_URL = os.environ.get('SSO_URL', 'https://sso.my.gov.ir/login')
