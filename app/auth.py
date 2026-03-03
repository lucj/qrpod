from functools import wraps
from flask import request, jsonify, session, redirect, url_for
from app.config import config


def require_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.args.get('token')
        if not token or token != config.SCAN_TOKEN:
            return jsonify({'error': 'Unauthorized', 'message': 'Invalid or missing token'}), 401
        return f(*args, **kwargs)
    return decorated_function


def require_session(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
