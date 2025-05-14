import os
import uuid
import json
import shutil
from werkzeug.utils import secure_filename
from flask import current_app
import zipfile
import yaml

from ..models import FinetuneTask, User
from ..database import db

ALLOWED_EXTENSIONS_MODEL = {'pt'}
ALLOWED_EXTENSIONS_DATASET = {'zip'}
ALLOWED_EXTENSIONS_YAML = {'yaml', 'yml'}


def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in allowed_extensions


class FinetuneService:
    def __init__(self, app):
        self.app = app
        self.user_model_base_dir = app.config.get('USER_MODEL_BASE_DIR', 'user_models')
        if not os.path.isabs(self.user_model_base_dir):
            self.user_model_base_dir = os.path.join(app.root_path, '..', self.user_model_base_dir)

        if not os.path.exists(self.user_model_base_dir):
            try:
                os.makedirs(self.user_model_base_dir, exist_ok=True)
                self.app.logger.info(f"FinetuneService: 已创建基础目录 {self.user_model_base_dir}")
            except OSError as e:
                self.app.logger.error(
                    f"FinetuneService: 创建基础目录 {self.user_model_base_dir} 失败: {e}")
                raise

    def _get_user_task_base_dir(self, user_id, task_id):
        """获取特定用户特定任务的基础存储目录，基于 user_id。"""
        # 路径结构： USER_MODEL_BASE_DIR / str(user_id) / train / task_id /
        safe_user_id_str = secure_filename(str(user_id))  # 确保 user_id 是安全的目录名组件
        safe_task_id = secure_filename(str(task_id))
        return os.path.join(self.user_model_base_dir, safe_user_id_str, 'train', safe_task_id)

    def _get_task_input_dir(self, user_task_base_dir):
        return os.path.join(user_task_base_dir, 'input')

    def _get_task_dataset_dir(self, user_task_base_dir):
        return os.path.join(user_task_base_dir, 'dataset')

    def _get_task_output_dir(self, user_task_base_dir):
        return os.path.join(user_task_base_dir, 'output')

    def _get_task_output_logs_dir(self, user_task_base_dir):
        return os.path.join(user_task_base_dir, 'log')

    def create_finetune_task(self, user_id, task_name,
                             base_model_file_storage, preset_model_name,
                             dataset_zip_file_storage, dataset_yaml_content,
                             training_params):
        self.app.logger.info(f"用户ID '{user_id}' 尝试创建微调任务。任务名: '{task_name}'")

        user = User.query.get(user_id)
        if not user:
            self.app.logger.error(f"创建任务时未找到ID为 '{user_id}' 的用户。")
            return None, "用户未找到。"
        username_for_logging = user.username

        task_id = str(uuid.uuid4())
        self.app.logger.info(f"为用户ID '{user_id}' (用户名: {username_for_logging}) 生成 task_id: {task_id}")

        user_task_base_dir = self._get_user_task_base_dir(user_id, task_id)
        task_input_dir = self._get_task_input_dir(user_task_base_dir)
        task_dataset_dir = self._get_task_dataset_dir(user_task_base_dir)
        task_output_dir = self._get_task_output_dir(user_task_base_dir)
        task_output_logs_dir = self._get_task_output_logs_dir(task_output_dir)

        try:
            os.makedirs(task_input_dir, exist_ok=True)
            os.makedirs(task_dataset_dir, exist_ok=True)
            os.makedirs(task_output_dir, exist_ok=True)
            os.makedirs(task_output_logs_dir, exist_ok=True)
            self.app.logger.info(f"已为任务 {task_id} 在 {user_task_base_dir} 创建目录结构")
        except OSError as e:
            self.app.logger.error(f"为任务 {task_id} 创建目录结构失败: {e}")
            return None, f"服务器错误：无法创建任务目录。{str(e)}"

        saved_base_model_name = None
        base_model_identifier_for_db = None
        if base_model_file_storage:
            if not allowed_file(base_model_file_storage.filename, ALLOWED_EXTENSIONS_MODEL):
                self._cleanup_task_dirs_on_error(user_task_base_dir)
                return None, "基础模型文件类型无效。允许的类型: .pt"
            base_model_filename = secure_filename(base_model_file_storage.filename)
            saved_base_model_name = base_model_filename # 使用原始文件名或标准化
            base_model_save_path = os.path.join(task_input_dir, saved_base_model_name)
            try:
                base_model_file_storage.save(base_model_save_path)
                base_model_identifier_for_db = saved_base_model_name
                self.app.logger.info(f"已为任务 {task_id} 保存基础模型 '{saved_base_model_name}' 到 {task_input_dir}")
            except Exception as e:
                self.app.logger.error(f"为任务 {task_id} 保存基础模型失败: {e}")
                self._cleanup_task_dirs_on_error(user_task_base_dir)
                return None, "保存基础模型文件失败。"
        elif preset_model_name:
            if not self._is_valid_preset_model(preset_model_name):
                self._cleanup_task_dirs_on_error(user_task_base_dir)
                return None, f"预设模型 '{preset_model_name}' 无效或未找到。"
            base_model_identifier_for_db = f"preset:{preset_model_name}"
            copied_model_name = f"{secure_filename(preset_model_name)}.pt" # 预设模型在任务目录中的标准名称
            if self._prepare_preset_model(preset_model_name, task_input_dir, copied_model_name):
                saved_base_model_name = copied_model_name
            else:
                self._cleanup_task_dirs_on_error(user_task_base_dir)
                return None, f"准备预设模型 '{preset_model_name}' 失败。"
            self.app.logger.info(f"任务 {task_id} 使用预设模型 '{preset_model_name}' (保存为 {saved_base_model_name})")
        else:
            self._cleanup_task_dirs_on_error(user_task_base_dir)
            return None, "未提供基础模型（既没有文件也没有预设名称）。"

        if not dataset_zip_file_storage or not dataset_zip_file_storage.filename:
            self._cleanup_task_dirs_on_error(user_task_base_dir)
            return None, "数据集 ZIP 文件缺失。"
        if not allowed_file(dataset_zip_file_storage.filename, ALLOWED_EXTENSIONS_DATASET):
            self._cleanup_task_dirs_on_error(user_task_base_dir)
            return None, "数据集文件类型无效。必须是 .zip 文件。"

        original_dataset_zip_filename = secure_filename(dataset_zip_file_storage.filename)
        dataset_zip_save_path = os.path.join(task_input_dir, original_dataset_zip_filename)
        try:
            dataset_zip_file_storage.save(dataset_zip_save_path)
            self.app.logger.info(f"已为任务 {task_id} 保存数据集zip '{original_dataset_zip_filename}' 到 {task_input_dir}")
        except Exception as e:
            self.app.logger.error(f"为任务 {task_id} 保存数据集zip失败: {e}")
            self._cleanup_task_dirs_on_error(user_task_base_dir)
            return None, "保存数据集 zip 文件失败。"

        original_dataset_yaml_filename = "user_config.yaml"
        dataset_yaml_save_path = os.path.join(task_input_dir, original_dataset_yaml_filename)
        try:
            with open(dataset_yaml_save_path, 'w', encoding='utf-8') as f:
                f.write(dataset_yaml_content)
            self.app.logger.info(f"已为任务 {task_id} 保存数据集yaml '{original_dataset_yaml_filename}' 到 {task_input_dir}")
        except Exception as e:
            self.app.logger.error(f"为任务 {task_id} 保存数据集yaml失败: {e}")
            self._cleanup_task_dirs_on_error(user_task_base_dir)
            return None, "保存数据集 yaml 文件失败。"

        # --- 调用数据集准备和配置生成 ---
        generated_config_yaml_name, error_msg = self._prepare_dataset_and_config(
            task_id, user_id, username_for_logging,
            task_input_dir, task_dataset_dir,
            original_dataset_zip_filename, original_dataset_yaml_filename
        )
        if error_msg:
            self._cleanup_task_dirs_on_error(user_task_base_dir)

        new_task = FinetuneTask(
            id=task_id,
            user_id=user.id,
            task_name=task_name if task_name else f"微调任务 {task_id[:8]}",
            status='queued', # 初始状态
            base_model_identifier=base_model_identifier_for_db,
            dataset_zip_name=original_dataset_zip_filename,
            dataset_yaml_name=original_dataset_yaml_filename, # 用户上传的yaml名
            training_params_json=json.dumps(training_params) if training_params else '{}',
            task_dir_name=task_id,
            input_base_model_name=saved_base_model_name,
            input_dataset_zip_name=original_dataset_zip_filename, # zip文件名
            input_dataset_yaml_name=original_dataset_yaml_filename, # 用户yaml文件名
            generated_config_yaml_name=generated_config_yaml_name # <-- 新增字段赋值
            # log_file_name 默认在模型中设置，或在任务开始时设置
        )

        try:
            db.session.add(new_task)
            db.session.commit()
            self.app.logger.info(f"微调任务 {task_id} 已为用户ID '{user_id}' 成功在数据库中创建。")
        except Exception as e:
            db.session.rollback()
            self.app.logger.error(f"为用户ID '{user_id}' 创建微调任务 {task_id} 时数据库出错: {e}", exc_info=True)
            self._cleanup_task_dirs_on_error(user_task_base_dir)
            return None, "服务器错误：无法将任务详情保存到数据库。"

        # --- 发送任务到 Celery 队列 ---
        try:
            if current_app.celery:
                # 注意任务名称 'app.finetune.run_training' 必须与 celery_worker.py 中定义的一致
                celery_task_instance = current_app.celery.send_task(
                    'app.finetune.run_training', # Celery 任务的名称
                    args=[task_id, user.id],      # 传递给任务的参数
                    # task_id=task_id # 可以选择让Celery使用我们生成的task_id作为其内部ID，但这可能与Celery的自动ID冲突
                                    # 通常让Celery自己生成内部task ID，我们的task_id作为业务ID传递
                )
                # 更新数据库记录中的 celery_task_id (如果需要追踪Celery的内部ID)
                # new_task.celery_internal_id = celery_task_instance.id
                # db.session.commit()
                self.app.logger.info(f"任务 {task_id} 已发送到 Celery 队列。Celery Task ID: {celery_task_instance.id}")
            else:
                self.app.logger.error(f"任务 {task_id} 创建成功，但 Celery 未初始化，无法发送到队列。")
                # 可以在这里决定如何处理，例如将任务状态标记为错误，或者只是记录警告
                # 为了演示，我们继续，但实际应用中可能需要更健壮的处理
        except Exception as e:
            self.app.logger.error(f"发送任务 {task_id} 到 Celery 队列失败: {e}", exc_info=True)
            # 考虑回滚数据库中的任务创建，或将其标记为错误
            new_task.status = 'failed'
            new_task.error_message = f"发送到处理队列失败: {str(e)}"
            db.session.commit()
            # 不需要清理目录，因为文件已准备好，只是队列发送失败
            return None, f"任务创建成功但无法提交到处理队列: {str(e)}"

        message = f"微调任务 '{new_task.task_name}' (ID: {task_id}) 已创建并提交到处理队列。"
        return task_id, message

    def _is_valid_preset_model(self, preset_model_name):
        preset_models_dir = self.app.config.get('PRESET_MODELS_DIR')
        if not preset_models_dir:
            self.app.logger.warning("PRESET_MODELS_DIR 未配置。无法验证预设模型。")
            return False
        if not os.path.isabs(preset_models_dir):
            preset_models_dir = os.path.join(self.app.root_path, '..', preset_models_dir)

        safe_name = secure_filename(preset_model_name)
        if safe_name != preset_model_name:  # 检查是否包含非法字符
            self.app.logger.warning(f"预设模型名称包含无效字符: {preset_model_name}")
            return False

        expected_model_path = os.path.join(preset_models_dir, f"{preset_model_name}.pt")
        if os.path.exists(expected_model_path) and os.path.isfile(expected_model_path):
            self.app.logger.info(f"预设模型 '{preset_model_name}' 存在于 '{expected_model_path}'。")
            return True
        else:
            self.app.logger.warning(
                f"预设模型 '{preset_model_name}' (期望路径 '{expected_model_path}') 未找到。")
            return False

    def _prepare_preset_model(self, preset_model_name, task_input_dir, target_model_name="base_model.pt"):
        preset_models_dir = self.app.config.get('PRESET_MODELS_DIR')
        if not preset_models_dir: return None
        if not os.path.isabs(preset_models_dir):
            preset_models_dir = os.path.join(self.app.root_path, '..', preset_models_dir)

        source_model_path = os.path.join(preset_models_dir, f"{secure_filename(preset_model_name)}.pt")
        destination_model_path = os.path.join(task_input_dir, secure_filename(target_model_name))
        try:
            shutil.copy2(source_model_path, destination_model_path)
            self.app.logger.info(f"已复制预设模型 '{preset_model_name}' 到 '{destination_model_path}'。")
            return destination_model_path
        except Exception as e:
            self.app.logger.error(
                f"从 '{source_model_path}' 复制预设模型 '{preset_model_name}' 到 '{destination_model_path}' 失败: {e}")
            return None

    def _cleanup_task_dirs_on_error(self, user_task_base_dir):
        if os.path.exists(user_task_base_dir):
            try:
                shutil.rmtree(user_task_base_dir)
                self.app.logger.info(f"错误发生，已清理任务目录: {user_task_base_dir}")
            except OSError as e:
                self.app.logger.error(f"清理任务目录 {user_task_base_dir} 时出错: {e}")

    def get_user_tasks(self, user_id):
        user = User.query.get(user_id)
        if not user:
            self.app.logger.warning(f"尝试获取不存在的用户ID '{user_id}' 的任务列表。")
            return []

        tasks = FinetuneTask.query.filter_by(user_id=user.id).order_by(FinetuneTask.created_at.desc()).all()
        tasks_list = []
        for task in tasks:
            tasks_list.append({
                "task_id": task.id,
                "task_name": task.task_name,
                "status": task.status,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "base_model": task.base_model_identifier,
            })
        return tasks_list

    def get_task_details(self, user_id, task_id):
        task = FinetuneTask.query.filter_by(id=task_id, user_id=user_id).first()
        if not task:
            self.app.logger.warning(f"未找到用户ID '{user_id}' 的任务 '{task_id}'。")
            return None

        metrics = json.loads(task.metrics_json) if task.metrics_json else {}

        details = {
            "task_id": task.id,
            "user_id": task.user_id,
            "task_name": task.task_name,
            "status": task.status,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "base_model_identifier": task.base_model_identifier,
            "dataset_zip_name": task.dataset_zip_name,
            "dataset_yaml_name": task.dataset_yaml_name,
            "training_params": json.loads(task.training_params_json) if task.training_params_json else {},
            "task_dir_name": task.task_dir_name,
            "input_base_model_name": task.input_base_model_name,
            "input_dataset_zip_name": task.input_dataset_zip_name,
            "input_dataset_yaml_name": task.input_dataset_yaml_name,
            "generated_config_yaml_name": task.generated_config_yaml_name,
            "output_dir_name": task.output_dir_name,
            "log_file_name": task.log_file_name,
            # "current_epoch": task.current_epoch, # 将移入 progress 对象
            # "total_epochs": task.total_epochs,   # 将移入 progress 对象
            # "metrics": metrics, # 可以选择是否将整个原始metrics对象也返回
            "error_message": task.error_message,
            "error_code": task.error_code if hasattr(task, 'error_code') else None,  # 如果添加了 error_code 字段
            "queue_position": None,
            "progress": None,
            "best_epoch": None
        }

        if task.status == 'running':
            progress_info = {
                "current_epoch": task.current_epoch,
                "total_epochs": task.total_epochs,
                "speed": metrics.get("speed", None)  # 假设 speed 存在 metrics 中
            }
            details["progress"] = progress_info

        elif task.status == 'queued':
            all_queued_tasks_of_type = FinetuneTask.query.filter(
                FinetuneTask.status == 'queued'
            ).order_by(FinetuneTask.created_at.asc()).all()

            total_queued_globally = len(all_queued_tasks_of_type)
            current_task_global_position = 0
            found_in_global_queue = False

            for i, queued_task_global in enumerate(all_queued_tasks_of_type):
                if queued_task_global.id == task_id:  # 比较的是当前查看的任务ID
                    current_task_global_position = i + 1  # 位置从1开始
                    found_in_global_queue = True
                    break

            if found_in_global_queue:
                details["queue_position"] = {
                    "position": current_task_global_position,
                    "total": total_queued_globally  # 这是全局队列的总数
                }
            else:  # pragma: no cover
                # 如果一个任务状态是 queued，它理论上应该在全局队列查询中被找到
                # 但如果它刚被worker拿起，状态还没来得及更新，可能会有短暂的不一致
                self.app.logger.warning(
                    f"任务 {task_id} 状态为 queued 但在全局队列查询中未找到，无法计算全局排队位置。"
                )
                # 此时 queue_position 保持 None，前端可以显示 "正在获取..." 或类似

        elif task.status == 'completed':
            details["best_epoch"] = metrics.get("best_epoch", None)  # 假设 best_epoch 存在 metrics 中
            # 或者 task.best_epoch_number if hasattr(task, 'best_epoch_number') else None

        return details

    def get_task_log_path(self, user_id, task_id, ensure_exists=False):
        task = FinetuneTask.query.filter_by(id=task_id, user_id=user_id).first()
        if not task:
            return None, "任务未找到或访问被拒绝。"

        if not task.log_file_name:  # 如果任务从未开始或初始化，可能没有日志文件名
            self.app.logger.warning(f"任务 '{task_id}' (用户ID '{user_id}') 的 log_file_name 未设置。")
            return None, f"任务 {task_id} 的日志配置信息不完整。"

        user_task_base_dir = self._get_user_task_base_dir(user_id, task_id)
        task_output_dir = self._get_task_output_dir(user_task_base_dir)
        task_output_logs_dir = self._get_task_output_logs_dir(task_output_dir)
        log_file_path = os.path.join(task_output_logs_dir, task.log_file_name)

        if ensure_exists:  # 通常由训练脚本自身创建日志文件和目录
            if not os.path.exists(task_output_logs_dir):
                try:
                    os.makedirs(task_output_logs_dir, exist_ok=True)
                except OSError as e:
                    self.app.logger.error(
                        f"为任务 {task_id} 创建日志目录 {task_output_logs_dir} 失败: {e}")
                    return None, f"服务器错误：无法确保日志目录存在。{str(e)}"
        return log_file_path, None

    def get_task_logs_content(self, user_id, task_id, tail_lines=None):
        log_file_path, error = self.get_task_log_path(user_id, task_id, ensure_exists=False)
        if error:
            return "", error  # 返回中文错误信息

        if not log_file_path or not os.path.exists(log_file_path) or not os.path.isfile(log_file_path):
            # 即使log_file_path有效，但文件可能尚未创建
            return "", f"任务 {task_id} 的日志文件未找到或尚未创建。"

        try:
            with open(log_file_path, 'r', encoding='utf-8') as f:
                if tail_lines and isinstance(tail_lines, int) and tail_lines > 0:
                    lines = f.readlines()
                    return "".join(lines[-tail_lines:]), None
                else:
                    return f.read(), None
        except Exception as e:
            self.app.logger.error(f"为任务 {task_id} 读取日志文件 {log_file_path} 时出错: {e}")
            return "", f"读取日志文件错误：{str(e)}"

    def get_task_output_archive_path(self, user_id, task_id):
        task = FinetuneTask.query.filter_by(id=task_id, user_id=user_id).first()
        if not task:
            return None, "任务未找到或访问被拒绝。"

        if task.status != 'completed':
            return None, "任务输出尚不可用（任务未完成）。"

        user_task_base_dir = self._get_user_task_base_dir(user_id, task_id)
        task_output_dir = self._get_task_output_dir(user_task_base_dir)  # output 目录本身

        # 寻找模型文件，通常在 output/runs/exp*/weights/best.pt 或 last.pt
        potential_model_path = None
        # 检查 task.output_dir_name 是否被设置，它可能指向具体的 run 目录
        actual_output_search_dir = task_output_dir
        if task.output_dir_name and os.path.isdir(os.path.join(task_output_dir, task.output_dir_name)):
            actual_output_search_dir = os.path.join(task_output_dir, task.output_dir_name)

        # 优先在 actual_output_search_dir (可能是某个run) 中查找
        weights_dir_in_actual = os.path.join(actual_output_search_dir, 'weights')
        if os.path.isdir(weights_dir_in_actual):
            best_model_in_actual = os.path.join(weights_dir_in_actual, 'best.pt')
            if os.path.exists(best_model_in_actual):
                potential_model_path = best_model_in_actual
            else:
                last_model_in_actual = os.path.join(weights_dir_in_actual, 'last.pt')
                if os.path.exists(last_model_in_actual):
                    potential_model_path = last_model_in_actual

        # 如果在特定 output_dir_name 中未找到，则在 task_output_dir 下的 run/exp 目录中查找
        if not potential_model_path:
            run_dirs = [d for d in os.listdir(task_output_dir) if
                        os.path.isdir(os.path.join(task_output_dir, d)) and (
                                    d.startswith('run') or d.startswith('exp'))]
            if run_dirs:
                run_dirs.sort(key=lambda x: os.path.getmtime(os.path.join(task_output_dir, x)), reverse=True)
                latest_run_dir = os.path.join(task_output_dir, run_dirs[0])  # 最新的 run 目录
                weights_dir_in_latest_run = os.path.join(latest_run_dir, 'weights')
                if os.path.isdir(weights_dir_in_latest_run):
                    best_model_in_run = os.path.join(weights_dir_in_latest_run, 'best.pt')
                    if os.path.exists(best_model_in_run):
                        potential_model_path = best_model_in_run
                    else:
                        last_model_in_run = os.path.join(weights_dir_in_latest_run, 'last.pt')
                        if os.path.exists(last_model_in_run):
                            potential_model_path = last_model_in_run

        if potential_model_path:
            # 将模型文件打包成zip
            archive_name = f"{task_id}_output_model.zip"  # 归档文件名
            # 归档文件存储在任务的基础输出目录中，而不是run/weights里
            archive_path = os.path.join(task_output_dir, archive_name)

            if os.path.exists(archive_path):  # 如果归档已存在，直接返回
                self.app.logger.info(f"返回已存在的归档: {archive_path}")
                return archive_path, None

            try:
                import zipfile
                self.app.logger.info(f"为模型 {potential_model_path} 创建归档 {archive_path}")
                with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    # 将模型文件添加到zip的根目录，而不是包含完整路径
                    zf.write(potential_model_path, arcname=os.path.basename(potential_model_path))
                return archive_path, None
            except Exception as e:
                self.app.logger.error(f"为任务 {task_id} 创建归档失败: {e}")
                return None, f"创建输出归档失败：{str(e)}"
        else:
            return None, "未找到此任务的输出模型 (best.pt 或 last.pt)。"

    def cancel_finetune_task(self, user_id, task_id):
        task = FinetuneTask.query.filter_by(id=task_id, user_id=user_id).first()
        if not task:
            return False, "任务未找到或访问被拒绝。"

        if task.status not in ['queued', 'running']:
            return False, f"任务无法取消。当前状态：{task.status}。"

        original_status = task.status
        task.status = 'cancelled'
        try:
            db.session.commit()
            self.app.logger.info(
                f"用户ID '{user_id}' 的任务 {task_id} 在数据库中标记为 '已取消' (原状态: {original_status})。")
            if original_status == 'running':
                # 为正在运行的任务创建取消信号文件，训练脚本应检查此文件
                cancel_signal_path = os.path.join(self._get_user_task_base_dir(user_id, task_id),
                                                  ".cancel_signal")
                with open(cancel_signal_path, 'w') as f:
                    f.write("cancel")
                self.app.logger.info(f"已为任务 {task_id} 在 {cancel_signal_path} 创建取消信号文件")
            return True, f"任务 {task_id} 取消请求已处理。状态已设置为 '已取消'。"
        except Exception as e:
            db.session.rollback()
            self.app.logger.error(f"为用户ID '{user_id}' 取消任务 {task_id} 时数据库出错: {e}")
            return False, "服务器错误：无法更新任务状态以进行取消。"

    def delete_finetune_task(self, user_id, task_id):
        task = FinetuneTask.query.filter_by(id=task_id, user_id=user_id).first()
        if not task:
            return False, "任务未找到或访问被拒绝。"

        if task.status == 'running':
            return False, "任务正在运行时无法删除。请先取消任务。"

        user_task_base_dir = self._get_user_task_base_dir(user_id, task_id)

        try:
            # 先删除数据库记录，然后尝试删除文件系统中的目录
            # 如果文件删除失败，数据库记录仍然会被删除，但会记录错误
            db.session.delete(task)

            dir_deleted_successfully = True
            if os.path.exists(user_task_base_dir):
                try:
                    shutil.rmtree(user_task_base_dir)
                    self.app.logger.info(f"任务目录 {user_task_base_dir} 已成功删除。")
                except OSError as e:
                    dir_deleted_successfully = False
                    self.app.logger.error(
                        f"为任务 {task_id} (用户ID {user_id}) 删除任务目录 {user_task_base_dir} 时出错: {e}")
                    # 即使目录删除失败，也提交数据库更改，但返回带警告的消息
                    db.session.commit()
                    return True, f"任务 {task_id} 记录已删除，但在删除其文件时发生错误：{str(e)}。请检查服务器日志。"

            db.session.commit()  # 如果目录不存在或删除成功，提交数据库更改
            self.app.logger.info(f"用户ID '{user_id}' 的任务 {task_id} 记录和目录已成功删除。")
            return True, f"任务 {task_id} 及其关联文件已被删除。"
        except Exception as e:
            db.session.rollback()
            self.app.logger.error(
                f"为用户ID '{user_id}' 删除任务 {task_id} 时数据库或意外错误: {e}",
                exc_info=True)
            return False, "服务器错误：无法从数据库或文件系统删除任务。"

    def _prepare_dataset_and_config(self, task_id, user_id, username_for_logging,
                                    task_input_dir, task_dataset_dir,
                                    original_dataset_zip_filename, original_dataset_yaml_filename):
        """
        解压数据集并生成供训练使用的 data.yaml。
        返回 (generated_config_yaml_name, error_message)
        """
        self.app.logger.info(f"任务 {task_id} (用户 {username_for_logging}): 开始准备数据集和配置文件。")

        # 1. 解压数据集 ZIP
        dataset_zip_path = os.path.join(task_input_dir, original_dataset_zip_filename)
        try:
            with zipfile.ZipFile(dataset_zip_path, 'r') as zip_ref:
                # 安全解压，防止路径遍历 (通常 zipfile 默认行为是安全的，但明确更好)
                for member in zip_ref.namelist():
                    # 检查解压路径是否在目标目录内 (可选，增加一层防护)
                    # target_path = os.path.join(task_dataset_dir, member)
                    # if not os.path.abspath(target_path).startswith(os.path.abspath(task_dataset_dir)):
                    #     raise zipfile.BadZipFile(f"非法成员路径: {member}")
                    zip_ref.extract(member, task_dataset_dir)
            self.app.logger.info(
                f"任务 {task_id}: 数据集 '{original_dataset_zip_filename}' 已成功解压到 '{task_dataset_dir}'。")
        except zipfile.BadZipFile as e:
            self.app.logger.error(f"任务 {task_id}: 解压数据集 '{dataset_zip_path}' 失败 - 无效的ZIP文件: {e}")
            return None, f"解压数据集失败：无效的ZIP文件。 {str(e)}"
        except Exception as e:
            self.app.logger.error(f"任务 {task_id}: 解压数据集 '{dataset_zip_path}' 时发生未知错误: {e}", exc_info=True)
            return None, f"解压数据集时发生服务器错误。 {str(e)}"

        # 2. 读取用户上传的 YAML 文件内容
        user_yaml_path = os.path.join(task_input_dir, original_dataset_yaml_filename)
        try:
            with open(user_yaml_path, 'r', encoding='utf-8') as f:
                user_config_data = yaml.safe_load(f)
            if not isinstance(user_config_data, dict):
                self.app.logger.error(f"任务 {task_id}: 用户上传的 YAML '{user_yaml_path}' 内容不是一个有效的字典。")
                return None, "用户上传的 dataset config 文件格式无效（不是字典）。"
            self.app.logger.info(f"任务 {task_id}: 已成功读取用户 YAML '{user_yaml_path}'。")
        except yaml.YAMLError as e:
            self.app.logger.error(f"任务 {task_id}: 解析用户 YAML '{user_yaml_path}' 失败: {e}")
            return None, f"解析用户上传的 dataset config 文件失败: {str(e)}"
        except Exception as e:
            self.app.logger.error(f"任务 {task_id}: 读取用户 YAML '{user_yaml_path}' 时发生错误: {e}", exc_info=True)
            return None, f"读取用户上传的 dataset config 文件时发生服务器错误。 {str(e)}"

        # 3. 生成训练专用的 data_for_training.yaml
        #    YOLO data.yaml 期望的结构示例:
        #    path: ../datasets/coco128  # dataset root dir (相对于 data.yaml 或项目根目录)
        #    train: images/train2017    # train images (relative to 'path')
        #    val: images/val2017        # val images (relative to 'path')
        #    test:                      # test images (optional)
        #
        #    names:
        #      0: person
        #      1: bicycle
        #    或者 names: ['person', 'bicycle']

        training_config_data = user_config_data.copy() # 从用户配置开始

        # 关键: 修改路径以指向解压后的 task_dataset_dir
        # 假设 data_for_training.yaml 将保存在 task_input_dir
        # task_dataset_dir 相对于 task_input_dir 是 '../dataset'
        # 或者，我们可以使用相对于项目根目录的绝对路径或相对于训练脚本工作目录的路径。
        # Ultralytics YOLO 倾向于 data.yaml 中的 'path' 指向数据集的根目录，
        # 而 'train'/'val' 是相对于这个 'path' 的。

        # 选项1: 让 'path' 指向 task_dataset_dir (绝对路径或相对于项目根目录的路径)
        # training_config_data['path'] = os.path.abspath(task_dataset_dir)

        # 选项2: 如果 data_for_training.yaml 存放在 task_input_dir，
        # 并且训练脚本的工作目录是 user_task_base_dir (即 task_id 目录)
        # 那么 path 可以是 './dataset'
        # training_config_data['path'] = './dataset' # 相对于 user_task_base_dir

        # 选项3 (推荐给Ultralytics): 将 data_for_training.yaml 也放入 task_dataset_dir，
        # 这样内部路径可以更简单。或者，如果 data_for_training.yaml 在 input 目录，
        # 那么 'path' 字段需要正确指向 dataset 目录。
        # 我们假设 data_for_training.yaml 存放在 task_input_dir。
        # Ultralytics的train脚本通常会将 data.yaml 中的 'path' 解析为数据集根目录。
        # 如果用户上传的yaml中没有 'path' 字段，我们添加一个。
        # 如果有，我们覆盖它，使其指向解压后的数据集目录。
        # 我们将 'path' 设置为相对于 task_input_dir 中 data_for_training.yaml 的路径。
        # task_dataset_dir = os.path.join(user_task_base_dir, 'dataset')
        # task_input_dir = os.path.join(user_task_base_dir, 'input')
        # data_for_training.yaml 将在 task_input_dir
        # 所以，从 task_input_dir 到 task_dataset_dir 的相对路径是 '../dataset'
        # 注意: Ultralytics 的 `check_dataset` 函数会尝试解析这个 `path`。
        # 它会先尝试相对于 data.yaml 文件的路径，然后尝试相对于当前工作目录。
        # 如果我们将 data_for_training.yaml 放在 task_input_dir，
        # 那么 path: ../dataset 应该是可行的，前提是训练时的工作目录是 task_input_dir
        # 或者训练脚本能正确处理。
        # 更稳妥的是，如果训练脚本的工作目录是 user_task_base_dir (即 task_id 目录)，
        # 那么 data_for_training.yaml 在 input/data_for_training.yaml,
        # 数据集在 dataset/。则 data_for_training.yaml 中 path 应为 '../dataset'
        # 或者，如果训练脚本的工作目录是 task_input_dir，则 path 应为 '../dataset'

        # 为了简单和通用性，我们假设训练脚本能够处理相对于项目根目录的绝对路径，
        # 或者 data.yaml 中的 'path' 字段被解析为数据集的根目录。
        # 我们将 'path' 设置为 task_dataset_dir 的绝对路径。
        # 这样 'train' 和 'val' 字段就可以是用户原始yaml中相对于其数据集根的路径。
        training_config_data['path'] = os.path.abspath(task_dataset_dir)
        self.app.logger.info(f"任务 {task_id}: 更新训练配置中的 'path' 为 '{training_config_data['path']}'。")

        # 确保 train 和 val 字段存在 (如果用户yaml中没有，训练会失败)
        if 'train' not in training_config_data:
            self.app.logger.error(f"任务 {task_id}: 用户配置中缺少 'train' 字段。")
            return None, "用户上传的 dataset config 文件缺少 'train' 字段。"
        if 'val' not in training_config_data:
            self.app.logger.error(f"任务 {task_id}: 用户配置中缺少 'val' 字段。")
            return None, "用户上传的 dataset config 文件缺少 'val' 字段。"

        # 检查 names 字段 (类别名称)
        if 'names' not in training_config_data or not training_config_data['names']:
            self.app.logger.warning(f"任务 {task_id}: 用户配置中缺少 'names' 字段或为空。训练可能失败或使用默认类别。")
            # 可以考虑是否强制要求 names，或者让训练脚本处理
        elif isinstance(training_config_data['names'], str):
            # 如果 names 是一个文件名，例如 'custom.names'，需要确保它在解压后的数据集中存在
            # 并将其路径也调整为相对于 training_config_data['path']
            names_file_relative_path = training_config_data['names']
            names_file_abs_path = os.path.join(os.path.abspath(task_dataset_dir), names_file_relative_path)
            if not os.path.exists(names_file_abs_path):
                self.app.logger.error(f"任务 {task_id}: 'names' 字段指向的文件 '{names_file_relative_path}' 在数据集中未找到 (期望路径: {names_file_abs_path})。")
                return None, f"'names' 字段指向的文件 '{names_file_relative_path}' 在数据集中未找到。"
            # training_config_data['names'] = names_file_relative_path # 保持相对路径，因为 path 已经是绝对的

        generated_yaml_name = "data_for_training.yaml"
        generated_yaml_path = os.path.join(task_input_dir, generated_yaml_name)

        try:
            with open(generated_yaml_path, 'w', encoding='utf-8') as f:
                yaml.dump(training_config_data, f, sort_keys=False, default_flow_style=False)
            self.app.logger.info(
                f"任务 {task_id}: 已生成训练配置文件 '{generated_yaml_name}' 到 '{generated_yaml_path}'。")
        except Exception as e:
            self.app.logger.error(
                f"任务 {task_id}: 保存生成的训练配置文件 '{generated_yaml_path}' 失败: {e}", exc_info=True)
            return None, f"保存生成的训练配置文件失败。 {str(e)}"

        return generated_yaml_name, None