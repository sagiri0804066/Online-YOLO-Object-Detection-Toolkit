from flask_sqlalchemy import SQLAlchemy

# 创建 SQLAlchemy 实例，但不绑定具体 app
# 会在 app 工厂函数中初始化
db = SQLAlchemy()