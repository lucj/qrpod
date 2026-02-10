import os
import secrets
from dotenv import load_dotenv

load_dotenv()


class Config:
    AUTH_TOKEN = os.environ.get('AUTH_TOKEN') or secrets.token_urlsafe(32)
    NAMESPACE = os.environ.get('NAMESPACE', 'default')
    APP_URL = os.environ.get('APP_URL', 'http://localhost:5000')
    POD_LABEL = 'qrpods'
    POD_IMAGE = 'nginx:alpine'

    @staticmethod
    def init_app(app):
        pass


config = Config()
