import os
import secrets
from dotenv import load_dotenv

load_dotenv()


class Config:
    SCAN_TOKEN = os.environ.get('SCAN_TOKEN') or secrets.token_urlsafe(32)
    DASHBOARD_PASSWORD = os.environ.get('DASHBOARD_PASSWORD') or secrets.token_urlsafe(32)
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_urlsafe(32)
    NAMESPACE = os.environ.get('NAMESPACE', 'default')
    APP_URL = os.environ.get('APP_URL', 'http://localhost:5000')
    APP_PORT = os.environ.get('APP_PORT', '5000')
    POD_LABEL = 'qrpods'
    POD_IMAGE = 'nginx:1.30.5-alpine3.24'

    @staticmethod
    def init_app(app):
        pass


config = Config()
