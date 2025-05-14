# app/finetune/__init__.py
from flask import Blueprint

# 将 url_prefix 修改为 '/api/finetune'
finetune_bp = Blueprint('finetune_api', __name__, url_prefix='/api/finetune')

# 导入路由，确保在蓝图创建之后
from . import routes