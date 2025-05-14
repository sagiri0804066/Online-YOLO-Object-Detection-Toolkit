# app/utils/decorators.py
from functools import wraps
from flask import session, jsonify


def login_required(f):
    """
    检查用户是否已登录的装饰器。
    如果未登录，返回 403 Forbidden。
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "您还未登录，请登录账号后再试。"}), 403
        # 将 user_id 传递给被装饰的视图函数，方便使用
        kwargs['user_id'] = session['user_id']
        return f(*args, **kwargs)

    return decorated_function