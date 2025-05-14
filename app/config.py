import yaml
import os


class Config:
    """加载并提供配置信息"""
    def __init__(self, config_path='config.yaml'):
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件未找到: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        # --- 基本验证和设置 ---
        self.SECRET_KEY = self.get('SECRET_KEY')
        if not self.SECRET_KEY or self.SECRET_KEY == 'change-this-to-a-very-secret-and-random-string':
            raise ValueError("请在 config.yaml 中设置一个安全的 SECRET_KEY!")

        self.SERVER_HOST = self.get('SERVER_HOST', '0.0.0.0')
        self.SERVER_PORT = int(self.get('SERVER_PORT', 8443))

        self.SQLALCHEMY_DATABASE_URI = self.get('DATABASE_URI', 'sqlite:///./database.db')
        self.SQLALCHEMY_TRACK_MODIFICATIONS = False # 建议关闭以节省资源

        self.CERT_FILE = self.get('CERT_FILE')
        self.KEY_FILE = self.get('KEY_FILE')
        self.SSL_PEM_FILE = self.get('SSL_PEM_FILE')
        if not self.CERT_FILE or not self.KEY_FILE:
            raise ValueError("请在 config.yaml 中配置 CERT_FILE 和 KEY_FILE")
        if not os.path.exists(self.CERT_FILE) or not os.path.exists(self.KEY_FILE):
             raise FileNotFoundError(f"证书或密钥文件未找到: {self.CERT_FILE}, {self.KEY_FILE}")

        if not self.SSL_PEM_FILE:
             raise ValueError("请在 config.yaml 中配置 SSL_PEM_FILE (合并的证书和密钥)")
        if not os.path.exists(self.SSL_PEM_FILE):
             if self.CERT_FILE and self.KEY_FILE and os.path.exists(self.CERT_FILE) and os.path.exists(self.KEY_FILE):
                 print(f"警告: 合并的 PEM 文件 {self.SSL_PEM_FILE} 未找到。尝试从 {self.CERT_FILE} 和 {self.KEY_FILE} 创建...")
                 try:
                     with open(self.SSL_PEM_FILE, 'wb') as outfile, \
                          open(self.CERT_FILE, 'rb') as certfile, \
                          open(self.KEY_FILE, 'rb') as keyfile:
                         outfile.write(certfile.read())
                         outfile.write(b'\n')
                         outfile.write(keyfile.read())
                     print(f"成功创建合并的 PEM 文件: {self.SSL_PEM_FILE}")
                 except Exception as e:
                     raise FileNotFoundError(f"无法创建合并的 PEM 文件 {self.SSL_PEM_FILE}: {e}")
             else:
                raise FileNotFoundError(f"合并的 PEM 文件未找到: {self.SSL_PEM_FILE}")

        # --- Session 配置 ---
        self.SESSION_TYPE = self.get('SESSION_TYPE', 'filesystem')
        self.SESSION_FILE_DIR = self.get('SESSION_FILE_DIR', './.flask_session')
        self.SESSION_PERMANENT = self.get('SESSION_PERMANENT', False)
        self.SESSION_USE_SIGNER = self.get('SESSION_USE_SIGNER', True)
        self.SESSION_KEY_PREFIX = self.get('SESSION_KEY_PREFIX', 'session:')

        # 确保 session 目录存在
        if self.SESSION_TYPE == 'filesystem' and not os.path.exists(self.SESSION_FILE_DIR):
            os.makedirs(self.SESSION_FILE_DIR)

    def get(self, key, default=None):
        """安全地获取配置项"""
        return self.config.get(key, default)

    def as_dict(self):
        """
        将配置转换为 Flask 可用的字典格式。
        返回一个包含所有从 config.yaml 加载的配置以及在 __init__ 中设置的实例属性的合并字典。
        实例属性会覆盖 self.config 中的同名键 (如果键名相同且大小写匹配)。
        Flask 通常关心大写的配置键。
        """
        # 优先使用 self.config (从yaml加载的原始配置) 作为基础
        # 因为它包含了所有在yaml中定义的键，包括我们新增的CELERY_BROKER_URL等
        flask_config = self.config.copy() # 创建一个副本以避免修改原始配置

        # 然后，将 __init__ 中设置的实例属性（通常是大写的Flask特定配置）合并进去
        # 这样可以确保 __init__ 中的验证和默认值设置被保留，并且如果实例属性与yaml中键名相同，实例属性优先
        for key, value in self.__dict__.items():
            if key.isupper(): # 通常Flask配置是大写的
                flask_config[key] = value
            elif key == 'config': # 跳过 self.config 本身
                continue
            # 你也可以选择将所有实例属性都合并，无论大小写
            # else:
            # flask_config[key] = value

        # 确保一些在 __init__ 中可能被修改或设置的属性被正确反映
        # 例如，如果 __init__ 中对 self.SQLALCHEMY_DATABASE_URI 做了处理
        if hasattr(self, 'SQLALCHEMY_DATABASE_URI'):
            flask_config['SQLALCHEMY_DATABASE_URI'] = self.SQLALCHEMY_DATABASE_URI
        if hasattr(self, 'SQLALCHEMY_TRACK_MODIFICATIONS'):
            flask_config['SQLALCHEMY_TRACK_MODIFICATIONS'] = self.SQLALCHEMY_TRACK_MODIFICATIONS
        # ... 其他在 __init__ 中作为实例属性设置的 Flask 配置 ...

        # 对于Celery配置，它们在yaml中是大写的，应该已经通过 self.config.copy() 包含进来了
        # 例如 CELERY_BROKER_URL, CELERY_RESULT_BACKEND

        return flask_config

# 全局配置实例 (可以在应用的不同部分导入使用)
# 在 app/__init__.py 中创建实例，避免循环导入问题
# config = Config() # 不在这里实例化