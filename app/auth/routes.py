from flask import request, jsonify, session
from . import auth_bp # 从同级 __init__ 文件导入蓝图
from .services import AuthService


@auth_bp.route('/signup', methods=['POST'])
def signup():
    """用户注册接口"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "请求体不能为空且必须是 JSON 格式"}), 400

    username = data.get('username')
    password = data.get('password')

    user, message = AuthService.create_user(username, password)

    if user:
        return jsonify({"message": message, "user_id": user.id}), 201 # 201 Created
    else:
        # 根据错误消息判断状态码
        status_code = 409 if "已存在" in message else 400 if "不能为空" in message else 500
        return jsonify({"error": message}), status_code


@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录接口"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "请求体不能为空且必须是 JSON 格式"}), 400

    username = data.get('username')
    password = data.get('password')

    user = AuthService.verify_user(username, password)

    if user:
        # 登录成功，在 Session 中记录用户信息
        # 只存储必要且不敏感的信息
        session['user_id'] = user.id
        session['username'] = user.username
        # session.permanent = True # 如果希望 session 持久化（根据 config 决定）

        return jsonify({"message": "登录成功", "user": {"id": user.id, "username": user.username}}), 200
    else:
        return jsonify({"error": "用户名或密码错误"}), 401 # 401 Unauthorized


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """用户登出接口"""
    # 从 Session 中移除用户信息
    session.pop('user_id', None)
    session.pop('username', None)
    # 或者直接清空 session
    # session.clear()
    return jsonify({"message": "登出成功"}), 200


@auth_bp.route('/status', methods=['GET'])
def status():
    """检查当前登录状态"""
    if 'user_id' in session:
        return jsonify({
            "logged_in": True,
            "user": {
                "id": session['user_id'],
                "username": session.get('username', '未知') # 做个保护
            }
        }), 200
    else:
        return jsonify({"logged_in": False}), 200


# 可以添加一个需要登录才能访问的示例路由
@auth_bp.route('/protected', methods=['GET'])
def protected():
    if 'user_id' not in session:
        return jsonify({"error": "需要登录"}), 401
    # 这里可以执行需要登录才能进行的操作
    return jsonify({"message": f"欢迎回来, {session.get('username')}! 这是受保护的资源。"}), 200