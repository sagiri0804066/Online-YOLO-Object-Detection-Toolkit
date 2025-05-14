# app/inference/__init__.py
from flask import Blueprint

# 创建蓝图实例
inference_bp = Blueprint('inference', __name__, url_prefix='/api') # 注意前缀是 /api

# 导入路由定义
from . import routes