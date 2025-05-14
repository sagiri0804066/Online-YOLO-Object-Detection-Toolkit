from flask import Blueprint

# 创建蓝图实例
# 'auth' 是蓝图名称，__name__ 用于定位模板和静态文件
# url_prefix 会加在所有该蓝图下的路由前面
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# 从 .routes 导入路由定义，确保蓝图创建后导入，避免循环依赖
from . import routes