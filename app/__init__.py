# app/__init__.py
import os
import atexit
import logging
from flask import Flask, render_template, session
from flask_session import Session  # type: ignore

# --- 导入配置类 ---
try:
    from .config import Config
except ImportError:
    class Config:
        def __init__(self, path=None): self.config = {}
        def as_dict(self): return self.config
        def get(self, key, default=None): return self.config.get(key, default)


# --- 导入数据库实例 ---
try:
    from .database import db
except ImportError:
    class MockDB:
        def init_app(self, app): pass
        def create_all(self): pass
    db = MockDB()

# --- 导入 Celery 工具函数 ---
try:
    from .celery_utils import make_celery
except ImportError:
    print("Warning: app/celery_utils.py or make_celery function not found. Celery features will be unavailable.")

    def make_celery(app): # Fallback
        print("ERROR: make_celery is not available!")
        return None


# --- 导入服务类 ---
try:
    from .inference.services import UserSessionManager, InferenceExecutor, InferenceService
except ImportError as e:
    print(f"错误：无法导入推理服务类，请确保 app/inference/services.py 文件存在且无误: {e}")
try:
    from .finetune.services import FinetuneService
except ImportError as e:
    print(f"错误：无法导入微调服务类，请确保 app/finetune/services.py 文件存在且无误: {e}")
try:
    from .validate.services import ValidateService
except ImportError as e:
    print(f"错误：无法导入验证服务类，请确保 app/validate/services.py 文件存在且无误: {e}")


# --- 导入蓝图 ---
from .auth import auth_bp
try:
    from .inference import inference_bp
except ImportError as e:
    print(f"错误：无法导入 inference_bp，请确保 app/inference/__init__.py 和 app/inference/routes.py 文件存在且无误: {e}")
try:
    from .finetune import finetune_bp
except ImportError as e:
    print(f"错误：无法导入 finetune_bp，请确保 app/finetune/__init__.py 和 app/finetune/routes.py 文件存在且无误: {e}")
try:
    from .validate import validate_bp
except ImportError as e:
    print(f"错误：无法导入 validate_bp，请确保 app/validate/__init__.py 和 app/validate/routes.py 文件存在且无误: {e}")


server_session = Session()
celery = None # 在 create_app 中初始化

def create_app(config_object=None):
    """应用工厂函数"""
    global celery

    app = Flask(__name__)

    if not app.debug:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s'
        ))
        app.logger.addHandler(stream_handler)
        app.logger.setLevel(logging.INFO)
    else:
        app.logger.setLevel(logging.DEBUG)
    logging.basicConfig(level=logging.INFO if not app.debug else logging.DEBUG,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    app.logger.info("应用开始创建...")

    if config_object is None:
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
        app.logger.info(f"尝试从 {config_path} 加载配置...")
        try:
            app_config = Config(config_path)
        except FileNotFoundError:
            app.logger.error(f"配置文件 {config_path} 未找到！将使用默认配置。")
            app_config = Config(None) # 使用空的Config实例
            # 为Celery提供必要的默认值，如果配置文件未找到
            app_config.config.setdefault('CELERY_BROKER_URL', 'redis://localhost:6379/0')
            app_config.config.setdefault('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
    else:
        app_config = config_object
        app.logger.info("使用传入的配置对象。")

    try:
        config_dict = app_config.as_dict()
        app.config.from_mapping(config_dict)
        app.logger.info("配置已加载到 app.config。")
        # 确保关键配置存在
        app.config.setdefault('USER_MODEL_BASE_DIR', 'user_models')
        app.config.setdefault('UPLOAD_DIR', 'user_uploads')
        app.config.setdefault('USER_SESSION_TTL', 600)
        app.config.setdefault('SESSION_TYPE', 'filesystem')
        app.config.setdefault('SECRET_KEY', os.urandom(24))
        # 为Celery确保配置存在
        app.config.setdefault('CELERY_BROKER_URL', 'redis://localhost:6379/0')
        app.config.setdefault('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
        app.config.setdefault('CELERY_TASK_TRACK_STARTED', True)
        app.config.setdefault('CELERY_TASK_SERIALIZER', 'json')
        app.config.setdefault('CELERY_RESULT_SERIALIZER', 'json')
        app.config.setdefault('CELERY_ACCEPT_CONTENT', ['json'])
        app.config.setdefault('CELERY_TIMEZONE', 'UTC')
        app.config.setdefault('CELERY_ENABLE_UTC', True)

        app.logger.info(f"  - USER_MODEL_BASE_DIR: {app.config.get('USER_MODEL_BASE_DIR')}")
        app.logger.info(f"  - UPLOAD_DIR: {app.config.get('UPLOAD_DIR')}")
        app.logger.info(f"  - CELERY_BROKER_URL: {app.config.get('CELERY_BROKER_URL')}")

    except Exception as e:
        app.logger.error(f"加载配置到 app.config 时出错: {e}", exc_info=True)
        raise e

    db.init_app(app)
    app.logger.info("数据库已初始化。")
    server_session.init_app(app)
    app.logger.info("服务器会话已初始化。")

    # --- 初始化 Celery ---
    if make_celery: # 检查 make_celery 是否成功导入
        celery = make_celery(app)
        app.celery = celery # 将Celery实例附加到app对象
        app.logger.info("Celery 已初始化并附加到 app。")
    else:
        app.celery = None
        app.logger.error("Celery 初始化失败，make_celery 函数不可用。")

    app.logger.info("正在初始化共享服务...")
    try:
        user_model_base_dir = app.config.get('USER_MODEL_BASE_DIR')
        upload_dir = app.config.get('UPLOAD_DIR')
        session_ttl = app.config.get('USER_SESSION_TTL')
        inference_workers = app.config.get('INFERENCE_WORKERS', None)

        for directory in [user_model_base_dir, upload_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)
                app.logger.info(f"目录 {directory} 不存在，已创建。")

        if 'UserSessionManager' in globals() and 'InferenceExecutor' in globals() and 'InferenceService' in globals():
            app.user_session_manager = UserSessionManager(upload_base_dir=upload_dir, max_age_seconds=session_ttl)
            app.inference_executor = InferenceExecutor(max_workers=inference_workers)
            app.inference_service = InferenceService(app, app.user_session_manager, app.inference_executor)
            app.logger.info("Inference 相关服务初始化完成。")
        else:
            app.logger.warning("一个或多个 Inference 服务类未导入，跳过其初始化。")

        if 'FinetuneService' in globals():
            # FinetuneService现在可能需要Celery实例，如果它直接发送任务
            # 但更推荐的做法是在FinetuneService中通过 current_app.celery 访问
            app.finetune_service = FinetuneService(app)
            app.logger.info("FinetuneService 初始化完成并附加到 app。")
        else:
            app.logger.warning("FinetuneService 类未导入，跳过其初始化。")

        if 'ValidateService' in globals():
            app.validate_service = ValidateService(app)
            app.logger.info("ValidateService 初始化完成并附加到 app。")
        else:
            app.logger.warning("ValidateService 类未导入，跳过其初始化。")
    except Exception as e:
        app.logger.error(f"初始化共享服务时出错: {e}", exc_info=True)
        raise e


    if 'auth_bp' in globals(): app.register_blueprint(auth_bp)
    if 'inference_bp' in globals(): app.register_blueprint(inference_bp)
    if 'finetune_bp' in globals(): app.register_blueprint(finetune_bp)
    if 'validate_bp' in globals(): app.register_blueprint(validate_bp)


    @app.route('/')
    def index():
        user_logged_in = 'user_id' in session
        username = session.get('username')
        return render_template('main.html', logged_in=user_logged_in, current_user=username)

    app.logger.info("根路由 '/' 已添加。")

    with app.app_context():
        try:
            db.create_all()
            app.logger.info("数据库表已检查/创建。")
        except Exception as e:
            app.logger.error(f"创建数据库表时出错: {e}", exc_info=True)

    # ... (你的 shutdown_services 和 atexit.register，保持不变) ...
    def shutdown_services():
        app.logger.info("应用关闭，开始清理服务...")
        if hasattr(app, 'inference_executor') and app.inference_executor is not None:
            app.logger.info("正在关闭 InferenceExecutor...")
            app.inference_executor.shutdown(wait=True)
            app.logger.info("InferenceExecutor 已关闭。")
        app.logger.info("服务清理完成。")
    atexit.register(shutdown_services)


    app.logger.info("应用创建完成。")
    return app, app_config