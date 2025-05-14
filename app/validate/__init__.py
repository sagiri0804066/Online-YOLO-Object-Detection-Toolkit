# app/validate/__init__.py
from flask import Blueprint

validate_bp = Blueprint('validate', __name__, url_prefix='/api/validate')

# 导入路由，确保在蓝图创建之后
from . import routes