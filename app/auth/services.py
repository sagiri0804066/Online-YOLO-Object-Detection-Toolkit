from ..models import User
from ..database import db


class AuthService:
    """封装认证相关的业务逻辑"""

    @staticmethod
    def create_user(username, password):
        """创建新用户"""
        if not username or not password:
            return None, "用户名和密码不能为空"

        if User.query.filter_by(username=username).first():
            return None, "用户名已存在"

        try:
            new_user = User(username=username, password=password)
            db.session.add(new_user)
            db.session.commit()
            return new_user, "用户创建成功"
        except Exception as e:
            db.session.rollback() # 出错时回滚
            # 实际应用中应该记录日志 e
            print(f"数据库错误: {e}")
            return None, "创建用户时发生内部错误"

    @staticmethod
    def verify_user(username, password):
        """验证用户名和密码"""
        if not username or not password:
            return None

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            return user
        return None