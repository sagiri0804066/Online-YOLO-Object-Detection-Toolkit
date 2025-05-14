# app/models.py
from .database import db
from werkzeug.security import generate_password_hash, check_password_hash
import datetime


class User(db.Model):
    """用户模型"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    # 反向关系
    finetune_tasks = db.relationship('FinetuneTask', backref='user', lazy='dynamic') # lazy='dynamic' 更适合大量关联对象
    validate_tasks = db.relationship('ValidateTask', backref='user', lazy='dynamic') # 新增

    def __init__(self, username, password):
        self.username = username
        self.set_password(password)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


# app/models.py
# ... (User model) ...

class FinetuneTask(db.Model):
    """微调任务模型"""
    __tablename__ = 'finetune_tasks'

    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    task_name = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    base_model_identifier = db.Column(db.String(255), nullable=True)
    dataset_zip_name = db.Column(db.String(255), nullable=True)
    dataset_yaml_name = db.Column(db.String(255), nullable=True)
    training_params_json = db.Column(db.Text, nullable=True)

    task_dir_name = db.Column(db.String(255), nullable=True)
    input_base_model_name = db.Column(db.String(255), nullable=True)
    input_dataset_zip_name = db.Column(db.String(255), nullable=True)
    input_dataset_yaml_name = db.Column(db.String(255), nullable=True)
    generated_config_yaml_name = db.Column(db.String(255), nullable=True)

    output_dir_name = db.Column(db.String(50), default='output')  # 通常是 'runs' 或 'train'，YOLO会在此下创建exp
    log_file_name = db.Column(db.String(255), default='train_log.txt')

    # --- 进度相关字段 ---
    current_epoch = db.Column(db.Integer, default=0)
    total_epochs = db.Column(db.Integer, nullable=True)
    # 新增: 批次进度 (可以直接存百分比，或者当前批次和总批次数)
    current_batch_in_epoch = db.Column(db.Integer, nullable=True)
    total_batches_in_epoch = db.Column(db.Integer, nullable=True)
    # batch_progress_percent = db.Column(db.Integer, nullable=True) # 备选方案：直接存百分比

    # 新增: 训练速度 (例如 "10.5 iter/s" 或 "200 img/s")
    current_speed = db.Column(db.String(50), nullable=True)

    # metrics_json 已经存在，可以用来存储每个epoch的详细指标，包括最终的 best_epoch
    metrics_json = db.Column(db.Text, nullable=True)
    # (可选) 如果想把 best_epoch 单独提出来，而不是仅在 metrics_json 中
    # best_epoch_number = db.Column(db.Integer, nullable=True)

    # --- 错误相关字段 ---
    error_message = db.Column(db.Text, nullable=True)
    # 新增: 错误代码
    error_code = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f'<FinetuneTask {self.id} (User: {self.user_id}, Status: {self.status})>'


# app/models.py
# ... (User model and FinetuneTask model) ...

class ValidateTask(db.Model):
    """验证任务模型"""
    __tablename__ = 'validate_tasks'

    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    task_name = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    model_to_validate_identifier = db.Column(db.String(255), nullable=False)
    dataset_identifier = db.Column(db.String(255), nullable=True)
    dataset_zip_name_val = db.Column(db.String(255), nullable=True)
    dataset_yaml_name_val = db.Column(db.String(255), nullable=True)
    validation_params_json = db.Column(db.Text, nullable=True)

    task_dir_name_val = db.Column(db.String(255), nullable=True)
    input_model_name_val = db.Column(db.String(255), nullable=True)
    input_dataset_zip_name_val = db.Column(db.String(255), nullable=True)
    input_dataset_yaml_name_val = db.Column(db.String(255), nullable=True)
    generated_config_yaml_name_val = db.Column(db.String(255), nullable=True)

    output_dir_name_val = db.Column(db.String(50), default='output')  # YOLO val 模式通常在 project/name 下创建目录
    log_file_name_val = db.Column(db.String(255), default='val_log.txt')

    # --- 进度相关字段 (验证任务的进度可能与训练不同) ---
    # 例如：已处理的图片数/总图片数，或已处理的批次数/总批次数
    current_progress_value = db.Column(db.Integer, nullable=True)  # 例如，当前处理的图片/批次数
    total_progress_value = db.Column(db.Integer, nullable=True)  # 例如，总图片/批次数
    # progress_text_val = db.Column(db.String(100), nullable=True) # 可以由后端动态生成，不一定存库

    # 新增: 验证速度
    current_speed_val = db.Column(db.String(50), nullable=True)  # 例如 "300 img/s"

    # results_json 已经存在，用于存储最终的验证指标
    results_json = db.Column(db.Text, nullable=True)

    # --- 错误相关字段 ---
    error_message = db.Column(db.Text, nullable=True)
    # 新增: 错误代码
    error_code = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f'<ValidateTask {self.id} (User: {self.user_id}, Status: {self.status})>'