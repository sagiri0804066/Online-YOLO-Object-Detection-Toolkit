# app/validate/services.py
import os
import uuid
import json
import shutil
import zipfile
import yaml  # PyYAML
from werkzeug.utils import secure_filename
from flask import current_app

from ..models import ValidateTask, User, FinetuneTask  # 如果需要引用，则导入 FinetuneTask
from ..database import db

# 假设这些全局变量已定义或在此处的辅助函数需要时导入
ALLOWED_EXTENSIONS_MODEL = {'pt', '.onnx'}  # .onnx 也可能对验证有效
ALLOWED_EXTENSIONS_DATASET = {'zip'}
ALLOWED_EXTENSIONS_YAML = {'yaml', 'yml'}


def allowed_file(filename, allowed_extensions):
    """
    检查文件扩展名是否在允许的扩展名集合中。

    :param filename: 文件名。
    :param allowed_extensions: 允许的扩展名集合。
    :return: 如果文件扩展名被允许，则返回 True，否则返回 False。
    """
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in allowed_extensions


class ValidateService:
    """处理验证任务相关操作的服务类。"""

    def __init__(self, app):
        """
        初始化 ValidateService。

        :param app: Flask 应用实例。
        """
        self.app = app
        self.user_model_base_dir = app.config.get('USER_MODEL_BASE_DIR', 'user_models')
        if not os.path.isabs(self.user_model_base_dir):
            # 假设 app.root_path 是 'app' 目录的父目录（项目根目录）
            self.user_model_base_dir = os.path.join(app.root_path, '..', self.user_model_base_dir)

        # 确保基础目录存在（FinetuneService 中已处理，但此处亦是良好实践）
        if not os.path.exists(self.user_model_base_dir):
            try:
                os.makedirs(self.user_model_base_dir, exist_ok=True)
                self.app.logger.info(f"ValidateService: 已创建基础用户模型目录 {self.user_model_base_dir}")
            except OSError as e:
                self.app.logger.error(
                    f"ValidateService: 创建基础用户模型目录 {self.user_model_base_dir} 失败: {e}")
                raise

    # --- 验证任务路径辅助方法 ---
    def _get_user_val_task_base_dir(self, user_id, task_id):
        """获取特定用户特定验证任务的基础存储目录。
        目录结构: USER_MODEL_BASE_DIR / str(user_id) / val / task_id /
        """
        safe_user_id_str = secure_filename(str(user_id))
        safe_task_id = secure_filename(str(task_id))
        return os.path.join(self.user_model_base_dir, safe_user_id_str, 'val', safe_task_id)

    def _get_val_task_input_dir(self, user_val_task_base_dir):
        """获取验证任务的输入目录路径。"""
        return os.path.join(user_val_task_base_dir, 'input')

    def _get_val_task_dataset_dir(self, user_val_task_base_dir):
        """获取验证任务的数据集目录路径（用于存放解压后的上传数据集）。"""
        return os.path.join(user_val_task_base_dir, 'dataset')

    def _get_val_task_output_dir(self, user_val_task_base_dir):
        """获取验证任务的输出目录路径。"""
        return os.path.join(user_val_task_base_dir, 'output')

    def _get_val_task_output_logs_dir(self, val_task_output_dir):
        """获取验证任务输出目录下的日志子目录路径。"""
        return os.path.join(val_task_output_dir, 'logs')

    def _cleanup_val_task_dirs_on_error(self, user_val_task_base_dir):
        """当验证任务发生错误时，清理相关的任务目录。"""
        if os.path.exists(user_val_task_base_dir):
            try:
                shutil.rmtree(user_val_task_base_dir)
                self.app.logger.info(f"验证任务错误发生，已清理任务目录: {user_val_task_base_dir}")
            except OSError as e:
                self.app.logger.error(f"清理验证任务目录 {user_val_task_base_dir} 时出错: {e}")

    def _prepare_uploaded_dataset_for_validation(self, task_id, user_id,
                                                 val_task_input_dir, val_task_dataset_dir,
                                                 original_dataset_zip_filename, original_dataset_yaml_filename):
        """
        解压上传的数据集并生成供验证使用的 data.yaml。
        此方法类似于 FinetuneService._prepare_dataset_and_config。

        :return: (生成的配置文件名, 错误信息)
        """
        self.app.logger.info(f"验证任务 {task_id} (用户 {user_id}): 开始准备上传的数据集和配置文件。")

        dataset_zip_path = os.path.join(val_task_input_dir, original_dataset_zip_filename)
        try:
            with zipfile.ZipFile(dataset_zip_path, 'r') as zip_ref:
                zip_ref.extractall(val_task_dataset_dir)
            self.app.logger.info(
                f"验证任务 {task_id}: 数据集 '{original_dataset_zip_filename}' 已成功解压到 '{val_task_dataset_dir}'。")
        except Exception as e:
            self.app.logger.error(f"验证任务 {task_id}: 解压数据集 '{dataset_zip_path}' 失败: {e}", exc_info=True)
            return None, f"解压验证数据集失败: {str(e)}"

        user_yaml_path = os.path.join(val_task_input_dir, original_dataset_yaml_filename)
        try:
            with open(user_yaml_path, 'r', encoding='utf-8') as f:
                user_config_data = yaml.safe_load(f)
            if not isinstance(user_config_data, dict):
                return None, "用户上传的验证数据集配置文件格式无效（不是字典）。"
        except Exception as e:
            self.app.logger.error(f"验证任务 {task_id}: 读取用户 YAML '{user_yaml_path}' 失败: {e}", exc_info=True)
            return None, f"读取用户上传的验证数据集配置文件失败: {str(e)}"

        val_config_data = user_config_data.copy()
        # 关键: 修改路径以指向解压后的 val_task_dataset_dir
        # 'path' 字段指向数据集根目录 (即 val_task_dataset_dir)
        val_config_data['path'] = os.path.abspath(val_task_dataset_dir)
        self.app.logger.info(f"验证任务 {task_id}: 更新验证配置中的 'path' 为 '{val_config_data['path']}'。")

        # 对于验证，主要关心 'val' 字段，但也可能用 'test'。'train' 通常不需要。
        if 'val' not in val_config_data and 'test' not in val_config_data:
            self.app.logger.error(f"验证任务 {task_id}: 用户配置中缺少 'val' 或 'test' 字段。")
            return None, "验证数据集配置文件缺少 'val' 或 'test' 字段。"
        if 'names' not in val_config_data:  # 'names' 字段依然重要
            self.app.logger.warning(f"验证任务 {task_id}: 用户配置中缺少 'names' 字段。")
            # 可以考虑使其可选: return None, "验证数据集配置文件缺少 'names' 字段。"

        generated_yaml_name = "data_for_validation.yaml"
        generated_yaml_path = os.path.join(val_task_input_dir, generated_yaml_name)
        try:
            with open(generated_yaml_path, 'w', encoding='utf-8') as f:
                yaml.dump(val_config_data, f, sort_keys=False, default_flow_style=False)
            self.app.logger.info(
                f"验证任务 {task_id}: 已生成验证配置文件 '{generated_yaml_name}' 到 '{generated_yaml_path}'。")
        except Exception as e:
            self.app.logger.error(
                f"验证任务 {task_id}: 保存生成的验证配置文件 '{generated_yaml_path}' 失败: {e}", exc_info=True)
            return None, f"保存生成的验证配置文件失败: {str(e)}"
        return generated_yaml_name, None

    def create_validate_task(self, user_id, task_name,
                             model_identifier, model_file_storage_if_upload,
                             dataset_identifier, dataset_zip_file_storage_if_upload,
                             dataset_yaml_content_if_upload,
                             validation_params):
        """
        创建新的验证任务，处理文件存储，并将任务提交到 Celery 队列。
        """
        self.app.logger.info(
            f"用户ID '{user_id}' 尝试创建验证任务。任务名: '{task_name}', 模型标识: '{model_identifier}', 数据集标识: '{dataset_identifier}'")

        user = User.query.get(user_id)
        if not user:
            self.app.logger.error(f"创建验证任务时未找到ID为 '{user_id}' 的用户。")
            return None, "用户未找到。"

        task_id = str(uuid.uuid4())
        self.app.logger.info(f"为用户ID '{user_id}' (用户名: {user.username}) 生成验证任务 task_id: {task_id}")

        user_val_task_base_dir = self._get_user_val_task_base_dir(user_id, task_id)
        val_task_input_dir = self._get_val_task_input_dir(user_val_task_base_dir)
        # val_task_dataset_dir 会在需要时由 Celery 任务或 _prepare_uploaded_dataset_for_validation 创建
        val_task_output_dir = self._get_val_task_output_dir(user_val_task_base_dir)
        val_task_output_logs_dir = self._get_val_task_output_logs_dir(val_task_output_dir)

        try:
            os.makedirs(val_task_input_dir, exist_ok=True)
            os.makedirs(val_task_output_dir, exist_ok=True)
            os.makedirs(val_task_output_logs_dir, exist_ok=True)
            self.app.logger.info(f"已为验证任务 {task_id} 在 {user_val_task_base_dir} 创建基础目录结构")
        except OSError as e:
            self.app.logger.error(f"为验证任务 {task_id} 创建目录结构失败: {e}")
            return None, f"服务器错误：无法创建验证任务目录。{str(e)}"

        # --- 初始化数据库字段变量 ---
        db_model_to_validate_identifier = model_identifier
        db_dataset_identifier = dataset_identifier
        db_dataset_zip_name_val = None
        db_dataset_yaml_name_val = None
        db_input_model_name_val = None
        db_input_dataset_zip_name_val = None
        db_input_dataset_yaml_name_val = None
        db_generated_config_yaml_name_val = None

        # --- 同步文件处理（仅限上传的情况） ---
        if model_file_storage_if_upload:  # 当模型来源类型为 'upload' 时
            if not allowed_file(model_file_storage_if_upload.filename, ALLOWED_EXTENSIONS_MODEL):
                self._cleanup_val_task_dirs_on_error(user_val_task_base_dir)
                return None, "待验证模型文件类型无效。"
            model_filename = secure_filename(model_file_storage_if_upload.filename)
            db_input_model_name_val = model_filename
            model_save_path = os.path.join(val_task_input_dir, db_input_model_name_val)
            try:
                model_file_storage_if_upload.save(model_save_path)
                self.app.logger.info(f"验证任务 {task_id}: 已保存上传的模型 '{db_input_model_name_val}'。")
            except Exception as e:  # pragma: no cover
                self.app.logger.error(f"验证任务 {task_id}: 保存上传模型失败: {e}")
                self._cleanup_val_task_dirs_on_error(user_val_task_base_dir)
                return None, "保存待验证模型文件失败。"

        if dataset_identifier == "upload":
            if not dataset_zip_file_storage_if_upload or not dataset_yaml_content_if_upload:
                self._cleanup_val_task_dirs_on_error(user_val_task_base_dir)
                return None, "选择上传数据集但缺少ZIP或YAML文件。"

            val_task_dataset_dir = self._get_val_task_dataset_dir(user_val_task_base_dir)  # 现在创建该目录
            os.makedirs(val_task_dataset_dir, exist_ok=True)

            db_dataset_zip_name_val = secure_filename(dataset_zip_file_storage_if_upload.filename)
            db_input_dataset_zip_name_val = db_dataset_zip_name_val
            dataset_zip_save_path = os.path.join(val_task_input_dir, db_input_dataset_zip_name_val)
            try:
                dataset_zip_file_storage_if_upload.save(dataset_zip_save_path)
            except Exception as e:  # pragma: no cover
                self._cleanup_val_task_dirs_on_error(user_val_task_base_dir)
                return None, f"保存验证数据集ZIP文件失败: {str(e)}"

            db_dataset_yaml_name_val = "user_config_val.yaml"
            db_input_dataset_yaml_name_val = db_dataset_yaml_name_val
            dataset_yaml_save_path = os.path.join(val_task_input_dir, db_input_dataset_yaml_name_val)
            try:
                with open(dataset_yaml_save_path, 'w', encoding='utf-8') as f:
                    f.write(dataset_yaml_content_if_upload)
            except Exception as e:  # pragma: no cover
                self._cleanup_val_task_dirs_on_error(user_val_task_base_dir)
                return None, f"保存验证数据集YAML文件失败: {str(e)}"

            generated_yaml, prep_error = self._prepare_uploaded_dataset_for_validation(
                task_id, user_id, val_task_input_dir, val_task_dataset_dir,
                db_input_dataset_zip_name_val, db_input_dataset_yaml_name_val
            )
            if prep_error:
                self._cleanup_val_task_dirs_on_error(user_val_task_base_dir)
                return None, prep_error
            db_generated_config_yaml_name_val = generated_yaml

        # --- 创建数据库记录 ---
        new_task = ValidateTask(
            id=task_id, user_id=user.id,
            task_name=task_name if task_name else f"验证任务 {task_id[:8]}",
            status='queued',
            model_to_validate_identifier=db_model_to_validate_identifier,
            dataset_identifier=db_dataset_identifier,
            dataset_zip_name_val=db_dataset_zip_name_val,
            dataset_yaml_name_val=db_dataset_yaml_name_val,
            validation_params_json=json.dumps(validation_params) if validation_params else '{}',
            task_dir_name_val=task_id,
            input_model_name_val=db_input_model_name_val,
            input_dataset_zip_name_val=db_input_dataset_zip_name_val,
            input_dataset_yaml_name_val=db_input_dataset_yaml_name_val,
            generated_config_yaml_name_val=db_generated_config_yaml_name_val
        )
        try:
            db.session.add(new_task)
            db.session.commit()
            self.app.logger.info(f"验证任务 {task_id} 已为用户ID '{user_id}' 成功在数据库中创建。")
        except Exception as e:  # pragma: no cover
            db.session.rollback()
            self.app.logger.error(f"为用户ID '{user_id}' 创建验证任务 {task_id} 时数据库出错: {e}", exc_info=True)
            self._cleanup_val_task_dirs_on_error(user_val_task_base_dir)
            return None, "服务器错误：无法将验证任务详情保存到数据库。"

        # --- 发送任务到 Celery 队列 ---
        try:
            if current_app.celery:
                celery_task_instance = current_app.celery.send_task(
                    'app.validate.run_validation',  # Celery 任务的名称
                    args=[task_id, user.id]
                )
                self.app.logger.info(f"验证任务 {task_id} 已发送到 Celery 队列。Celery Task ID: {celery_task_instance.id}")
            else:  # pragma: no cover
                self.app.logger.error(f"验证任务 {task_id} 创建成功，但 Celery 未初始化，无法发送到队列。")
                # 考虑将任务状态更新为错误
                new_task.status = 'failed'
                new_task.error_message = "Celery服务未初始化，无法处理任务。"
                db.session.commit()
                return None, "任务创建成功但无法提交到处理队列：Celery服务不可用。"
        except Exception as e:  # pragma: no cover
            self.app.logger.error(f"发送验证任务 {task_id} 到 Celery 队列失败: {e}", exc_info=True)
            new_task.status = 'failed'
            new_task.error_message = f"发送到处理队列失败: {str(e)}"
            db.session.commit()
            return None, f"任务创建成功但无法提交到处理队列: {str(e)}"

        message = f"验证任务 '{new_task.task_name}' (ID: {task_id}) 已创建并提交到处理队列。"
        return task_id, message

    # --- GET, DELETE 等方法（类似于 FinetuneService，但针对 ValidateTask） ---
    def get_user_tasks(self, user_id):
        """
        获取指定用户的所有验证任务列表。
        已重命名以避免直接导入时发生冲突。
        """
        user = User.query.get(user_id)
        if not user:
            return []
        tasks = ValidateTask.query.filter_by(user_id=user.id).order_by(ValidateTask.created_at.desc()).all()
        return [{
            "task_id": task.id, "task_name": task.task_name, "status": task.status,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "model_identifier": task.model_to_validate_identifier,
            "dataset_identifier": task.dataset_identifier
        } for task in tasks]

    def get_task_details(self, user_id, task_id):
        """获取特定验证任务的详细信息。"""
        task = ValidateTask.query.filter_by(id=task_id, user_id=user_id).first()
        if not task:
            self.app.logger.warning(f"未找到用户ID '{user_id}' 的验证任务 '{task_id}'。")
            return None

        # 从 results_json 中提取可能的进度或速度信息（如果验证过程中有更新的话）
        # 或者，如果为 ValidateTask 模型添加了专门的进度字段，则从那里读取
        results = json.loads(task.results_json) if task.results_json else {}

        details = {
            "task_id": task.id,
            "user_id": task.user_id,
            "task_name": task.task_name,
            "status": task.status,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "model_to_validate_identifier": task.model_to_validate_identifier,
            "dataset_identifier": task.dataset_identifier,
            "dataset_zip_name_val": task.dataset_zip_name_val,
            "dataset_yaml_name_val": task.dataset_yaml_name_val,
            "validation_params": json.loads(task.validation_params_json) if task.validation_params_json else {},
            "task_dir_name_val": task.task_dir_name_val,
            "input_model_name_val": task.input_model_name_val,
            "input_dataset_zip_name_val": task.input_dataset_zip_name_val,
            "input_dataset_yaml_name_val": task.input_dataset_yaml_name_val,
            "generated_config_yaml_name_val": task.generated_config_yaml_name_val,
            "output_dir_name_val": task.output_dir_name_val,
            "log_file_name_val": task.log_file_name_val,
            "results_json": results,  # 返回解析后的 results
            "error_message": task.error_message,
            "error_code": task.error_code if hasattr(task, 'error_code') else None,  # 如果添加了 error_code 字段
            "queue_position": None,  # 初始化
            "progress": None  # 初始化
        }

        if task.status == 'running':
            # 假设 ValidateTask 模型中添加了以下字段用于进度跟踪：
            # current_progress_value (e.g., images processed)
            # total_progress_value (e.g., total images in val set)
            # current_speed_val (e.g., "150 img/s")
            # progress_text_val (e.g., "Processing 500/1000 images")

            current_prog = getattr(task, 'current_progress_value', None)
            total_prog = getattr(task, 'total_progress_value', None)
            speed = getattr(task, 'current_speed_val', results.get('speed', None))  # 优先从独立字段获取，其次从results
            progress_text = getattr(task, 'progress_text_val', None)

            if progress_text is None and current_prog is not None and total_prog is not None and total_prog > 0:
                progress_text = f"{current_prog}/{total_prog}"
            elif progress_text is None and current_prog is not None:
                progress_text = f"已处理 {current_prog}"

            progress_info = {
                "current_progress": current_prog,
                "total_progress": total_prog,
                "progress_text": progress_text if progress_text else "进行中...",
                "speed": speed
            }
            details["progress"] = progress_info

        elif task.status == 'queued':
            all_queued_tasks_of_type = ValidateTask.query.filter(
                ValidateTask.status == 'queued'
            ).order_by(ValidateTask.created_at.asc()).all()

            total_queued_globally = len(all_queued_tasks_of_type)
            current_task_global_position = 0
            found_in_global_queue = False

            for i, queued_task_global in enumerate(all_queued_tasks_of_type):
                if queued_task_global.id == task_id:
                    current_task_global_position = i + 1
                    found_in_global_queue = True
                    break

            if found_in_global_queue:
                details["queue_position"] = {
                    "position": current_task_global_position,
                    "total": total_queued_globally
                }

        # 对于 'completed', 'failed', 'cancelled' 状态，
        # 前端主要依赖 status 和 error_message/error_code 或固定的完成/取消信息。
        # results_json 字段在 'completed' 状态下包含了所有详细的验证指标。

        return details

    def get_task_log_path(self, user_id, task_id, ensure_exists=False):
        """
        获取验证任务日志文件的完整路径。

        :param user_id: 用户ID。
        :param task_id: 任务ID。
        :param ensure_exists: 如果为 True，则确保日志目录存在。
        :return: (日志文件路径, 错误信息)
        """
        task = ValidateTask.query.filter_by(id=task_id, user_id=user_id).first()
        if not task:
            return None, "验证任务未找到或访问被拒绝。"
        # 使用带有 _val 后缀的数据库字段
        if not task.log_file_name_val:
            return None, f"验证任务 {task_id} 的日志配置不完整。"

        user_val_task_base_dir = self._get_user_val_task_base_dir(user_id, task_id)
        val_task_output_dir = self._get_val_task_output_dir(user_val_task_base_dir)
        val_task_output_logs_dir = self._get_val_task_output_logs_dir(val_task_output_dir)
        # 使用带有 _val 后缀的数据库字段
        log_file_path = os.path.join(val_task_output_logs_dir, task.log_file_name_val)

        if ensure_exists:
            if not os.path.exists(val_task_output_logs_dir):
                try:
                    os.makedirs(val_task_output_logs_dir, exist_ok=True)
                except OSError as e:  # pragma: no cover
                    self.app.logger.error(
                        f"为验证任务 {task_id} 创建日志目录 {val_task_output_logs_dir} 失败: {e}")
                    return None, f"服务器错误：无法确保日志目录存在。{str(e)}"
        return log_file_path, None

    def get_task_logs_content(self, user_id, task_id, tail_lines=None):
        """
        获取验证任务日志文件的内容。
        已重命名。
        """
        log_file_path, error = self.get_task_log_path(user_id, task_id)  # 使用已重命名的辅助函数
        if error:
            return "", error
        if not log_file_path or not os.path.exists(log_file_path) or not os.path.isfile(log_file_path):
            return "", f"验证任务 {task_id} 的日志文件未找到或尚未创建。"
        try:
            with open(log_file_path, 'r', encoding='utf-8') as f:
                if tail_lines and isinstance(tail_lines, int) and tail_lines > 0:
                    return "".join(f.readlines()[-tail_lines:]), None
                return f.read(), None
        except Exception as e:
            return "", f"读取验证日志文件错误：{str(e)}"

    def get_task_output_archive_path(self, user_id, task_id):
        """
        获取验证任务输出结果的归档文件路径。如果归档不存在，则创建它。
        已重命名。
        """
        task = ValidateTask.query.filter_by(id=task_id, user_id=user_id).first()
        if not task:
            return None, "验证任务未找到或访问被拒绝。"
        if task.status != 'completed':
            return None, "验证任务输出尚不可用（任务未完成）。"

        user_val_task_base_dir = self._get_user_val_task_base_dir(user_id, task_id)
        val_task_output_dir = self._get_val_task_output_dir(user_val_task_base_dir)

        # 对于验证，输出可能更简单：一个 results.json、图表和可能的日志文件。
        # Ultralytics 验证模式会将图表和 results.json 保存在 'runs/val/exp*' 目录中。
        # 我们需要找到这个目录。

        # 在输出中搜索最新的 'exp*'、'val*' 或 'run*' 目录
        run_dirs = [d for d in os.listdir(val_task_output_dir) if
                    os.path.isdir(os.path.join(val_task_output_dir, d)) and
                    (d.startswith('exp') or d.startswith('val') or d.startswith('run'))]
        # YOLO 验证模式可能使用 'val' 或 'exp' 作为目录名

        if not run_dirs:
            return None, "未找到验证任务的输出运行目录。"

        run_dirs.sort(key=lambda x: os.path.getmtime(os.path.join(val_task_output_dir, x)), reverse=True)
        latest_run_dir_path = os.path.join(val_task_output_dir, run_dirs[0])

        # 需要归档的项目是此最新运行目录的内容
        # 例如：results.json, confusion_matrix.png, PR_curve.png 等。
        archive_name = f"{task_id}_validation_output.zip"
        archive_path = os.path.join(val_task_output_dir, archive_name)  # 将归档文件存储在父输出目录中

        if os.path.exists(archive_path):
            self.app.logger.info(f"返回已存在的验证归档: {archive_path}")
            return archive_path, None

        try:
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(latest_run_dir_path):
                    for file_item in files:
                        file_path = os.path.join(root, file_item)
                        # 将文件添加到 zip 包，并保持其在 run_dir 中的相对结构
                        arcname = os.path.relpath(file_path, latest_run_dir_path)
                        zf.write(file_path, arcname)
            self.app.logger.info(f"已为验证任务 {task_id} 创建输出归档 {archive_path} 从目录 {latest_run_dir_path}")
            return archive_path, None
        except Exception as e:
            self.app.logger.error(f"为验证任务 {task_id} 创建归档失败: {e}")
            return None, f"创建验证输出归档失败：{str(e)}"

    def cancel_validate_task(self, user_id, task_id):
        """取消指定的验证任务。"""
        task = ValidateTask.query.filter_by(id=task_id, user_id=user_id).first()
        if not task:
            self.app.logger.warning(f"尝试取消验证任务：未找到用户ID '{user_id}' 的任务 '{task_id}'。")
            return False, "验证任务未找到或访问被拒绝。"

        if task.status not in ['queued', 'running']:
            self.app.logger.info(
                f"验证任务 '{task_id}' (用户ID '{user_id}') 无法取消，当前状态: {task.status}。")
            return False, f"验证任务无法取消。当前状态：{task.status}。"

        original_status = task.status
        task.status = 'cancelled'
        try:
            db.session.commit()
            self.app.logger.info(
                f"用户ID '{user_id}' 的验证任务 '{task_id}' 在数据库中标记为 '已取消' (原状态: {original_status})。")

            if original_status == 'running':
                # 为正在运行的任务创建取消信号文件
                user_val_task_base_dir = self._get_user_val_task_base_dir(user_id, task_id)
                cancel_signal_path = os.path.join(user_val_task_base_dir, ".cancel_signal_val") # 使用不同名称以区分
                try:
                    with open(cancel_signal_path, 'w') as f:
                        f.write("cancel")
                    self.app.logger.info(f"已为验证任务 {task_id} 在 {cancel_signal_path} 创建取消信号文件。")
                except IOError as e: # pragma: no cover
                    self.app.logger.error(f"为验证任务 {task_id} 创建取消信号文件 {cancel_signal_path} 失败: {e}")
                    # 即使信号文件创建失败，任务状态已更新，但Celery任务可能不会立即停止

            return True, f"验证任务 {task_id} 取消请求已处理。状态已设置为 '已取消'。"
        except Exception as e: # pragma: no cover
            db.session.rollback()
            self.app.logger.error(f"为用户ID '{user_id}' 取消验证任务 {task_id} 时数据库出错: {e}", exc_info=True)
            return False, "服务器错误：无法更新验证任务状态以进行取消。"

    def delete_validate_task(self, user_id, task_id):
        """删除指定的验证任务及其关联的文件。"""
        task = ValidateTask.query.filter_by(id=task_id, user_id=user_id).first()
        if not task:
            return False, "验证任务未找到或访问被拒绝。"
        if task.status == 'running':
            return False, "验证任务正在运行时无法删除。"

        user_val_task_base_dir = self._get_user_val_task_base_dir(user_id, task_id)
        try:
            db.session.delete(task)
            if os.path.exists(user_val_task_base_dir):
                try:
                    shutil.rmtree(user_val_task_base_dir)
                except OSError as e:
                    # 即使目录删除失败，也提交数据库记录的删除
                    db.session.commit()
                    self.app.logger.error(f"删除验证任务目录 {user_val_task_base_dir} 失败: {e}")
                    return True, f"验证任务 {task_id} 记录已删除，但删除其文件时发生错误。"
            db.session.commit()
            return True, f"验证任务 {task_id} 及其关联文件已被删除。"
        except Exception as e:
            db.session.rollback()
            self.app.logger.error(f"删除验证任务 {task_id} 时数据库或意外错误: {e}", exc_info=True)
            return False, "服务器错误：无法从数据库或文件系统删除验证任务。"