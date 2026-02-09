from functools import wraps
from flask import request, jsonify
from app.config import config


def require_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.args.get('token')
        expected_token = config.AUTH_TOKEN

        if not token or token != expected_token:
            return jsonify({'error': 'Unauthorized', 'message': 'Invalid or missing token'}), 401

        return f(*args, **kwargs)
    return decorated_function
