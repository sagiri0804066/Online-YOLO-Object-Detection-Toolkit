# celery_worker.py
import os
import logging
import json
import time  # 仍然需要 time.sleep 用于某些场景，但主要训练/验证不再依赖它
import shutil  # 用于文件操作

from app import create_app
from app.celery_utils import make_celery
from app.config import Config
from flask import current_app
from app.models import FinetuneTask, ValidateTask  # 确保 ValidateTask 也导入
from app.database import db
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession  # 用于回调的独立会话

# --- 从 app.ultralyticsCust 导入相关函数和回调 ---
# 假设这些文件在 app/ultralyticsCust/ 目录下
from app.ultralyticsCust.callbacks import FinetuneProgressCallback
from app.ultralyticsCust.training import run_yolo_training
from app.ultralyticsCust.validation import run_yolo_validation

# --- 配置加载 ---
base_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_dir, 'config.yaml')

try:
    cfg = Config(config_path)
    print(f"Celery Worker: 从 {config_path} 加载配置...")
except FileNotFoundError:
    print(f"Celery Worker 错误: 配置文件 {config_path} 未找到！")
    exit(1)
except Exception as e:
    print(f"Celery Worker 加载配置时出错: {e}")
    exit(1)

# --- 创建临时的 Flask 应用实例 ---
flask_app, _ = create_app(cfg)
flask_app.app_context().push()

# --- 创建 Celery 实例 ---
celery_app = make_celery(flask_app)
print(f"Celery Worker: Celery 应用已创建，Broker: {celery_app.conf.broker_url}")


# --- 辅助函数：为回调创建新的数据库会话 ---
def get_new_db_session_for_callback() -> SQLAlchemySession:
    """
    为回调创建一个新的、独立的 SQLAlchemy 会话。
    """
    engine = db.engine  # current_app.extensions['sqlalchemy'].engine
    if not engine:
        current_app.logger.error("DB engine not available for creating new session in callback.")
        raise RuntimeError("DB engine not available for creating new session for callback.")

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    return session


# --- 定义 Celery 任务 ---

@celery_app.task(bind=True, name='app.finetune.run_training')
def run_finetune_training_task(self, task_id: str, user_id: int):
    """
    Celery 任务，用于执行实际的微调训练。
    """
    current_app.logger.info(f"[CeleryTask:{self.request.id}] 开始执行微调任务 {task_id} (用户ID: {user_id})")

    task_db_record = None
    user_task_base_dir = None  # 定义在try外部，确保finally中可用
    try:
        # 1. 获取任务记录并初步检查
        task_db_record = FinetuneTask.query.filter_by(id=task_id, user_id=user_id).first()
        if not task_db_record:
            current_app.logger.error(f"[CeleryTask:{self.request.id}] 任务 {task_id} 在数据库中未找到。")
            raise ValueError(f"任务 {task_id} 未找到。")

        user_task_base_dir = current_app.finetune_service._get_user_task_base_dir(user_id, task_id)

        # 检查任务是否在排队时已被取消
        if task_db_record.status == 'cancelled':
            current_app.logger.info(f"[CeleryTask:{self.request.id}] 任务 {task_id} 在开始执行前已被标记为取消。")
            # 清理可能的取消信号文件
            cancel_signal_file = os.path.join(user_task_base_dir, ".cancel_signal")
            if os.path.exists(cancel_signal_file):
                try:
                    os.remove(cancel_signal_file)
                except OSError:
                    pass
            return {"status": "cancelled", "message": "任务在开始执行前已被取消。"}

        # 更新数据库中任务状态为 'running'
        task_db_record.status = 'running'
        task_db_record.started_at = db.func.now()
        db.session.commit()
        current_app.logger.info(f"[CeleryTask:{self.request.id}] 任务 {task_id} 状态更新为 'running'。")

        # 2. 准备训练所需路径和参数
        task_input_dir = current_app.finetune_service._get_task_input_dir(user_task_base_dir)
        base_model_path = os.path.join(task_input_dir, task_db_record.input_base_model_name)
        generated_yaml_path = os.path.join(task_input_dir, task_db_record.generated_config_yaml_name)
        output_dir_project = current_app.finetune_service._get_task_output_dir(user_task_base_dir)  # 这是YOLO的project目录
        yolo_run_name = "train_run"  # 或者从参数配置

        log_file_path, log_dir = current_app.finetune_service.get_task_log_path(user_id, task_id, ensure_exists=True)
        # 注意: run_yolo_training 会在 output_dir_project/yolo_run_name 下创建自己的日志。
        # FinetuneService.get_task_log_path 返回的路径可能需要与YOLO的日志输出机制协调。
        # 一个简单的方法是让 get_task_log_path 返回 project/name/logs/log.txt 这样的路径。
        # 或者，回调可以将日志写入此 log_file_path。
        # 为简单起见，我们假设回调和YOLO本身会记录到其标准位置，而此 log_file_path 用于Celery任务的额外日志或摘要。

        current_app.logger.info(f"[CeleryTask:{self.request.id}] 任务 {task_id} - 基础模型: {base_model_path}")
        current_app.logger.info(f"[CeleryTask:{self.request.id}] 任务 {task_id} - 数据配置: {generated_yaml_path}")
        current_app.logger.info(f"[CeleryTask:{self.request.id}] 任务 {task_id} - 输出项目目录: {output_dir_project}")
        current_app.logger.info(f"[CeleryTask:{self.request.id}] 任务 {task_id} - YOLO运行名称: {yolo_run_name}")
        current_app.logger.info(f"[CeleryTask:{self.request.id}] 任务 {task_id} - Celery日志文件: {log_file_path}")

        training_params_dict = {}
        if task_db_record.training_params_json:
            try:
                training_params_dict = json.loads(task_db_record.training_params_json)
            except json.JSONDecodeError as e:
                current_app.logger.error(
                    f"[CeleryTask:{self.request.id}] 任务 {task_id}: 解析 training_params_json 失败: {e}. 内容: '{task_db_record.training_params_json}'")
                # 可以选择使用默认参数或抛出错误
                raise ValueError(f"解析训练参数失败: {e}")

        # 确保 epochs 参数存在并传递给回调用于初始化
        initial_total_epochs = training_params_dict.get('epochs', 0)  # 默认0，回调会尝试从trainer获取
        if task_db_record.total_epochs and task_db_record.total_epochs > 0:  # 如果数据库已有值
            initial_total_epochs = task_db_record.total_epochs
        elif initial_total_epochs > 0:
            task_db_record.total_epochs = initial_total_epochs  # 更新到数据库
            db.session.commit()

        # 3. 实例化并准备回调
        # 回调日志可以与Celery任务日志分开，或使用同一个logger但加前缀
        callback_logger = logging.getLogger(f"FinetuneCallback.{task_id}")
        # 你可能需要为 callback_logger 配置 handler 和 formatter，如果它还没有
        if not callback_logger.handlers:
            # 简单配置，实际项目中你可能会有更复杂的日志配置
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            callback_logger.addHandler(handler)
            callback_logger.setLevel(logging.INFO)  # 或 current_app.logger.level

        finetune_callback_instance = FinetuneProgressCallback(
            task_id=task_id,
            user_id=user_id,
            db_session_maker=get_new_db_session_for_callback,  # 传递会话工厂
            user_task_base_dir=user_task_base_dir,
            logger=callback_logger,  # 使用专门的或共享的logger
            total_epochs_from_task=initial_total_epochs,
            celery_task_update_state_func=self.update_state  # 传递Celery任务的update_state方法
        )

        # Ultralytics YOLOv8 通过 model.add_callback(event_name, callback_function) 注册回调
        # 所以 run_yolo_training 需要接收一个回调实例列表或一个配置好的YOLO模型实例
        # 这里我们假设 run_yolo_training 内部会处理回调的注册
        # Ultralytics 的回调是基于事件的，所以我们需要将回调的方法映射到事件名称
        # 例如: [('on_fit_epoch_end', finetune_callback_instance.on_fit_epoch_end), ...]
        # 或者，如果 FinetuneProgressCallback 遵循 Ultralytics 的回调基类，可以直接传递实例。
        # 假设 FinetuneProgressCallback 实例可以直接传递，并且 run_yolo_training 知道如何使用它。
        # 或者更简单，run_yolo_training 接收一个回调对象列表，它自己去调用 add_callback。
        # 为了符合 FinetuneProgressCallback 的设计，它本身就是一个完整的对象，
        # run_yolo_training 应该能够直接使用它。
        # Ultralytics 的 model.train() 方法有一个 callbacks 参数。
        # 我们的 run_yolo_training 应该将 finetune_callback_instance 放入一个列表中传递给 model.train()

        # Ultralytics 回调注册方式是 model.add_callback(hook_name, callback_method)
        # 所以，run_yolo_training 应该接收一个回调对象，并在内部调用 add_callback
        # 或者，我们在这里准备好回调列表给 run_yolo_training
        yolo_callbacks_for_train_func = [
            ('on_pretrain_routine_start', finetune_callback_instance.on_pretrain_routine_start),
            ('on_pretrain_routine_end', finetune_callback_instance.on_pretrain_routine_end),
            ('on_fit_epoch_end', finetune_callback_instance.on_fit_epoch_end),
            ('on_train_batch_end', finetune_callback_instance.on_train_batch_end),
            ('on_train_end', finetune_callback_instance.on_train_end),
            # 你可以添加更多YOLOv8支持的回调事件
        ]

        # 4. 执行实际的YOLO微调训练
        current_app.logger.info(f"[CeleryTask:{self.request.id}] 任务 {task_id}: 调用 run_yolo_training...")

        success, message, results_data = run_yolo_training(
            model_path=base_model_path,
            data_yaml_path=generated_yaml_path,
            project_path=output_dir_project,
            run_name=yolo_run_name,
            training_params=training_params_dict,
            callbacks_list=yolo_callbacks_for_train_func,  # 传递回调方法列表
            logger=current_app.logger  # 将Celery任务的logger传递给训练函数
        )

        # 5. 处理训练结果
        # 重新从数据库获取记录，因为回调可能已经更新了它
        task_db_record = FinetuneTask.query.filter_by(id=task_id, user_id=user_id).first()
        if not task_db_record:  # 理论上不应发生
            current_app.logger.error(f"[CeleryTask:{self.request.id}] 任务 {task_id} 在训练后无法从数据库重新获取。")
            raise ValueError(f"任务 {task_id} 训练后丢失。")

        if task_db_record.status == 'cancelled':  # 如果回调检测到取消并已更新状态
            current_app.logger.info(f"[CeleryTask:{self.request.id}] 任务 {task_id} 在训练期间被取消 (由回调处理)。")
            # 清理取消信号文件（如果回调没有清理）
            cancel_signal_file = os.path.join(user_task_base_dir, ".cancel_signal")
            if os.path.exists(cancel_signal_file):
                try:
                    os.remove(cancel_signal_file)
                except OSError:
                    pass  # pragma: no cover
            return {"status": "cancelled", "task_id": task_id,
                    "message": task_db_record.error_message or "训练被用户取消。"}

        if success:
            task_db_record.status = 'completed'
            task_db_record.completed_at = db.func.now()
            task_db_record.error_message = None  # 清空错误信息

            # 更新 metrics_json 和其他输出信息
            final_metrics = {}
            if task_db_record.metrics_json:
                try:
                    final_metrics = json.loads(task_db_record.metrics_json)
                except json.JSONDecodeError:
                    pass

            if results_data:
                final_metrics.update(results_data.get("final_metrics", {}))
                if "best_model_path" in results_data and results_data["best_model_path"]:
                    # 将绝对路径转换为相对于 user_task_base_dir/output/<run_name>/weights 的相对路径或项目根目录的相对路径
                    # 假设 FinetuneService 有方法处理这个
                    # task_db_record.output_model_relative_path = ...
                    # 这里简单记录绝对路径到metrics，Service层获取任务详情时再处理
                    final_metrics["task_reported_best_model_path"] = results_data["best_model_path"]
                    # 你可能需要一个字段来存储最终模型的相对路径，例如 task_db_record.output_model_path
                    # 例如，如果 output_dir_project = user_models/user1/train/task123/output
                    # yolo_run_name = train_run
                    # best_model_path = user_models/user1/train/task123/output/train_run/weights/best.pt
                    # 相对路径可以是 'train_run/weights/best.pt' (相对于 output_dir_project)
                    try:
                        actual_output_run_dir = results_data.get("output_directory",
                                                                 os.path.join(output_dir_project, yolo_run_name))
                        if os.path.commonpath(
                                [results_data["best_model_path"], actual_output_run_dir]) == actual_output_run_dir:
                            task_db_record.output_model_path = os.path.relpath(results_data["best_model_path"],
                                                                               actual_output_run_dir)
                    except Exception as e_relpath:
                        current_app.logger.warning(f"无法计算模型相对路径: {e_relpath}")

            task_db_record.metrics_json = json.dumps(final_metrics)

            db.session.commit()
            current_app.logger.info(f"[CeleryTask:{self.request.id}] 微调任务 {task_id} 成功完成。")
            return {"status": "completed", "task_id": task_id, "message": message, "results": final_metrics}
        else:
            # 训练失败
            task_db_record.status = 'failed'
            task_db_record.error_message = message or "YOLO训练执行失败，未提供具体错误信息。"
            task_db_record.completed_at = db.func.now()
            db.session.commit()
            current_app.logger.error(f"[CeleryTask:{self.request.id}] 微调任务 {task_id} 失败: {message}")
            # 抛出异常让Celery标记为FAILURE，或者返回错误信息
            # 如果 run_yolo_training 抛出异常，这里可能不会执行，而是直接进入 except Exception
            # 如果它返回 success=False，则我们在这里处理
            raise Exception(f"微调任务失败: {message}")

    except Exception as e:
        current_app.logger.error(f"[CeleryTask:{self.request.id}] 执行微调任务 {task_id} 时发生严重错误: {str(e)}",
                                 exc_info=True)
        if task_db_record and task_db_record.status not in ['completed', 'cancelled']:  # 避免覆盖已取消的状态
            task_db_record.status = 'failed'
            task_db_record.error_message = str(e)
            task_db_record.completed_at = db.func.now()
            db.session.commit()
        raise  # 重新抛出异常，Celery会处理
    finally:
        # 清理取消信号文件（如果因任何原因仍然存在）
        if user_task_base_dir:
            cancel_signal_file = os.path.join(user_task_base_dir, ".cancel_signal")
            if os.path.exists(cancel_signal_file):
                try:
                    os.remove(cancel_signal_file)
                    current_app.logger.info(f"[CeleryTask:{self.request.id}] 清理取消信号文件: {cancel_signal_file}")
                except OSError:  # pragma: no cover
                    pass


@celery_app.task(bind=True, name='app.validate.run_validation')
def run_validation_task(self, task_id: str, user_id: int):
    """
    Celery 任务，用于执行实际的模型验证。
    """
    current_app.logger.info(f"[CeleryTask:{self.request.id}] 开始执行验证任务 {task_id} (用户ID: {user_id})")

    task_db_record = None
    user_val_task_base_dir = None
    try:
        task_db_record = ValidateTask.query.filter_by(id=task_id, user_id=user_id).first()
        if not task_db_record:
            current_app.logger.error(f"[CeleryTask:{self.request.id}] 验证任务 {task_id} 在数据库中未找到。")
            raise ValueError(f"验证任务 {task_id} 未找到。")

        user_val_task_base_dir = current_app.validate_service._get_user_val_task_base_dir(user_id, task_id)
        cancel_signal_file = os.path.join(user_val_task_base_dir, ".cancel_signal_val")

        if task_db_record.status == 'cancelled':
            current_app.logger.info(f"[CeleryTask:{self.request.id}] 验证任务 {task_id} 在开始执行前已被标记为取消。")
            if os.path.exists(cancel_signal_file):
                try:
                    os.remove(cancel_signal_file)
                except OSError:
                    pass
            return {"status": "cancelled", "message": "任务在开始执行前已被取消."}

        task_db_record.status = 'running'
        task_db_record.started_at = db.func.now()
        db.session.commit()
        current_app.logger.info(f"[CeleryTask:{self.request.id}] 验证任务 {task_id} 状态更新为 'running'。")
        self.update_state(state='PROGRESS', meta={'status': '准备验证环境...'})

        # --- 检查取消信号 (在耗时操作之前) ---
        if os.path.exists(cancel_signal_file):
            current_app.logger.info(f"[CeleryTask:{self.request.id}] 验证任务 {task_id}: 检测到取消信号。")
            task_db_record.status = 'cancelled'
            task_db_record.error_message = "任务在实际开始前被用户取消。"
            task_db_record.completed_at = db.func.now()
            db.session.commit()
            os.remove(cancel_signal_file)
            return {"status": "cancelled", "task_id": task_id, "message": "验证在开始前被用户取消。"}

        # --- 准备验证所需的模型和数据 ---
        val_task_input_dir = current_app.validate_service._get_val_task_input_dir(user_val_task_base_dir)

        # --- 1. 模型准备 ---
        model_identifier = task_db_record.model_to_validate_identifier
        model_for_validation_path = None

        if not model_identifier:
            raise ValueError("model_to_validate_identifier 未在任务中设置。")

        id_parts = model_identifier.split(":", 1)
        model_type = id_parts[0]
        model_specifier = id_parts[1] if len(id_parts) > 1 else None

        current_app.logger.info(
            f"[CeleryTask:{self.request.id}] 准备模型: 类型='{model_type}', 标识符='{model_specifier}'")

        if model_type == "upload":
            # 假设上传的模型已由服务层处理并命名为 input_model_name_val 存储在 val_task_input_dir
            if not task_db_record.input_model_name_val:
                raise ValueError("上传模型类型，但 input_model_name_val 未设置。")
            model_for_validation_path = os.path.join(val_task_input_dir, task_db_record.input_model_name_val)
            if not os.path.exists(model_for_validation_path):
                raise FileNotFoundError(f"上传的模型文件 {model_for_validation_path} 未找到。")

        elif model_type == "inference":
            # 从预设推理模型库复制
            # PRESET_MODELS_DIR 来自 config.yaml -> cfg.PRESET_MODELS_DIR
            preset_models_dir = current_app.config.get('PRESET_MODELS_DIR',
                                                       os.path.join(current_app.root_path, '..', 'models'))
            src_model_path = os.path.join(preset_models_dir, model_specifier)  # model_specifier 是模型文件名，如 yolov8n.pt
            if not os.path.exists(src_model_path):
                raise FileNotFoundError(f"预设推理模型 {src_model_path} 未找到。")

            # 确保 val_task_input_dir 存在
            os.makedirs(val_task_input_dir, exist_ok=True)
            model_for_validation_path = os.path.join(val_task_input_dir, os.path.basename(src_model_path))
            shutil.copy2(src_model_path, model_for_validation_path)
            task_db_record.input_model_name_val = os.path.basename(model_for_validation_path)  # 记录复制后的名称
            db.session.commit()

        elif model_type == "finetune":
            # 从微调任务输出复制，格式 "finetune:source_task_id:model_filename.pt"
            # model_specifier 应该是 "source_task_id:model_filename.pt"
            ft_task_id_parts = model_specifier.split(":", 1)
            source_finetune_task_id = ft_task_id_parts[0]
            source_model_filename = ft_task_id_parts[1] if len(ft_task_id_parts) > 1 else "best.pt"  # 默认 best.pt

            source_ft_task_record = FinetuneTask.query.filter_by(id=source_finetune_task_id, user_id=user_id).first()
            if not source_ft_task_record:
                raise ValueError(f"源微调任务 {source_finetune_task_id} 未找到。")
            if source_ft_task_record.status != 'completed' or not source_ft_task_record.output_model_path:
                raise ValueError(f"源微调任务 {source_finetune_task_id} 未成功完成或无输出模型路径。")

            # output_model_path 是相对于其任务的 output/<run_name>/ 的路径
            # 例如 'train_run/weights/best.pt'
            source_ft_task_base_dir = current_app.finetune_service._get_user_task_base_dir(user_id,
                                                                                           source_finetune_task_id)
            source_ft_output_dir = current_app.finetune_service._get_task_output_dir(source_ft_task_base_dir)

            # 如果 source_ft_task_record.output_model_path 是相对于 source_ft_output_dir/<run_name> 的，
            # 那么需要确定 <run_name>。或者 output_model_path 已经是相对于 source_ft_output_dir 的。
            # 假设 output_model_path 是相对于 yolo run name 目录的，例如 'weights/best.pt'
            # 而 yolo_run_name 可能存储在 metrics_json 或需要一个固定约定。
            # 简化：假设 output_model_path 是相对于 source_ft_output_dir 的路径，如 'train_run/weights/best.pt'
            # 或者，更直接地，如果 FinetuneTask 有一个字段 `full_output_model_path`
            # 之前在微调任务中，我们设置了 task_db_record.output_model_path 为相对路径
            # 如 'train_run/weights/best.pt'
            src_model_path = os.path.join(source_ft_output_dir, source_ft_task_record.output_model_path)

            if not os.path.exists(src_model_path):
                raise FileNotFoundError(f"源微调模型文件 {src_model_path} 未找到。")

            os.makedirs(val_task_input_dir, exist_ok=True)
            model_for_validation_path = os.path.join(val_task_input_dir,
                                                     f"ft_{source_finetune_task_id}_{os.path.basename(src_model_path)}")
            shutil.copy2(src_model_path, model_for_validation_path)
            task_db_record.input_model_name_val = os.path.basename(model_for_validation_path)
            db.session.commit()
        else:
            raise NotImplementedError(f"不支持的模型类型: {model_type}")

        current_app.logger.info(f"[CeleryTask:{self.request.id}] 待验证模型准备完成: {model_for_validation_path}")

        # --- 2. 数据集配置文件准备 ---
        dataset_identifier = task_db_record.dataset_identifier
        data_yaml_for_validation_path = None

        if not dataset_identifier:
            raise ValueError("dataset_identifier 未在任务中设置。")

        ds_id_parts = dataset_identifier.split(":", 1)
        ds_type = ds_id_parts[0]
        ds_specifier = ds_id_parts[1] if len(ds_id_parts) > 1 else None

        current_app.logger.info(f"[CeleryTask:{self.request.id}] 准备数据集: 类型='{ds_type}', 标识符='{ds_specifier}'")

        if ds_type == "upload":
            # 假设上传的数据集配置文件已由服务层处理并命名为 generated_config_yaml_name_val
            if not task_db_record.generated_config_yaml_name_val:
                raise ValueError("上传数据集类型，但 generated_config_yaml_name_val 未设置。")
            data_yaml_for_validation_path = os.path.join(val_task_input_dir,
                                                         task_db_record.generated_config_yaml_name_val)
            if not os.path.exists(data_yaml_for_validation_path):
                raise FileNotFoundError(f"上传的数据集配置文件 {data_yaml_for_validation_path} 未找到。")

        elif ds_type == "finetune_val":
            # 使用指定微调任务的验证集，ds_specifier 是源微调任务ID
            source_finetune_task_id_for_ds = ds_specifier
            source_ft_task_ds_record = FinetuneTask.query.filter_by(id=source_finetune_task_id_for_ds,
                                                                    user_id=user_id).first()
            if not source_ft_task_ds_record:
                raise ValueError(f"用于数据集的源微调任务 {source_finetune_task_id_for_ds} 未找到。")
            if not source_ft_task_ds_record.generated_config_yaml_name:
                raise ValueError(f"源微调任务 {source_finetune_task_id_for_ds} 没有数据集配置文件。")

            source_ft_task_base_dir_ds = current_app.finetune_service._get_user_task_base_dir(user_id,
                                                                                              source_finetune_task_id_for_ds)
            source_ft_input_dir_ds = current_app.finetune_service._get_task_input_dir(source_ft_task_base_dir_ds)
            src_data_yaml_path = os.path.join(source_ft_input_dir_ds,
                                              source_ft_task_ds_record.generated_config_yaml_name)

            if not os.path.exists(src_data_yaml_path):
                raise FileNotFoundError(f"源微调任务的数据集配置文件 {src_data_yaml_path} 未找到。")

            os.makedirs(val_task_input_dir, exist_ok=True)
            # 需要注意：原始的 data.yaml 路径是相对于其原始位置的。复制后可能需要调整路径。
            # 简单复制，假设 ValidateService 在创建此任务时已确保yaml内容适用或会调整它。
            # 或者，ValidateService 应该生成一个新的yaml文件，其路径指向原始数据位置。
            # 这里我们先简单复制，并假设 ValidateService 已经处理了路径问题，或者数据本身就在共享位置。
            data_yaml_for_validation_path = os.path.join(val_task_input_dir,
                                                         f"data_from_ft_{source_finetune_task_id_for_ds}.yaml")
            shutil.copy2(src_data_yaml_path, data_yaml_for_validation_path)
            # TODO: 可能需要解析复制的yaml，并将其中的相对路径（如 train, val, test 图片目录）调整为绝对路径，
            # 或者相对于验证任务的工作目录。这取决于原始yaml的结构和数据的实际存储位置。
            # 为避免复杂性，此处假设 ValidateService 已经提供了可以直接使用的yaml，或者原始yaml中的路径是全局可访问的。
            task_db_record.generated_config_yaml_name_val = os.path.basename(data_yaml_for_validation_path)
            db.session.commit()
            current_app.logger.warning(
                f"[CeleryTask:{self.request.id}] 数据集配置文件 {src_data_yaml_path} 已复制到 {data_yaml_for_validation_path}. "
                "请确保其内部路径对于验证任务是有效的。")


        elif ds_type == "preset_ds":
            # 使用预设数据集，ds_specifier 是预设数据集的名称
            # PRESET_DATASETS_DIR 来自 config.yaml，其下应有 <ds_specifier>/data.yaml
            preset_datasets_dir = current_app.config.get('PRESET_DATASETS_DIR')  # e.g., /path/to/preset_datasets
            if not preset_datasets_dir:
                raise ValueError("PRESET_DATASETS_DIR 未在配置中设置。")

            src_data_yaml_path = os.path.join(preset_datasets_dir, ds_specifier, "data.yaml")
            if not os.path.exists(src_data_yaml_path):
                raise FileNotFoundError(f"预设数据集配置文件 {src_data_yaml_path} 未找到。")

            os.makedirs(val_task_input_dir, exist_ok=True)
            data_yaml_for_validation_path = os.path.join(val_task_input_dir, f"preset_{ds_specifier}.yaml")
            shutil.copy2(src_data_yaml_path, data_yaml_for_validation_path)
            # 同样，需要确保此yaml中的路径是有效的。
            task_db_record.generated_config_yaml_name_val = os.path.basename(data_yaml_for_validation_path)
            db.session.commit()
            current_app.logger.warning(
                f"[CeleryTask:{self.request.id}] 预设数据集配置文件 {src_data_yaml_path} 已复制到 {data_yaml_for_validation_path}. "
                "请确保其内部路径对于验证任务是有效的。")
        else:
            raise NotImplementedError(f"不支持的数据集类型: {ds_type}")

        current_app.logger.info(f"[CeleryTask:{self.request.id}] 数据集配置准备完成: {data_yaml_for_validation_path}")

        # --- 其他路径和参数 ---
        val_output_dir_project = current_app.validate_service._get_val_task_output_dir(user_val_task_base_dir)
        yolo_val_run_name = "val_run"  # 或从参数配置
        val_log_file_path, _ = current_app.validate_service.get_task_log_path(user_id, task_id, ensure_exists=True)

        current_app.logger.info(
            f"[CeleryTask:{self.request.id}] 验证任务 {task_id} - 输出项目目录: {val_output_dir_project}")
        current_app.logger.info(
            f"[CeleryTask:{self.request.id}] 验证任务 {task_id} - YOLO运行名称: {yolo_val_run_name}")
        current_app.logger.info(
            f"[CeleryTask:{self.request.id}] 验证任务 {task_id} - Celery日志文件: {val_log_file_path}")

        validation_params_dict = {}
        if task_db_record.validation_params_json:
            try:
                validation_params_dict = json.loads(task_db_record.validation_params_json)
            except json.JSONDecodeError as e:
                current_app.logger.error(
                    f"[CeleryTask:{self.request.id}] 验证任务 {task_id}: 解析 validation_params_json 失败: {e}.")
                # 可以选择使用默认参数或抛出错误

        # --- 执行实际的YOLO验证 ---
        current_app.logger.info(f"[CeleryTask:{self.request.id}] 任务 {task_id}: 调用 run_yolo_validation...")
        self.update_state(state='PROGRESS', meta={'status': '模型验证进行中...'})

        # 在调用验证前再次检查取消信号
        if os.path.exists(cancel_signal_file):
            current_app.logger.info(f"[CeleryTask:{self.request.id}] 验证任务 {task_id}: 在执行前检测到取消信号。")
            task_db_record.status = 'cancelled'
            task_db_record.error_message = "任务在验证执行前被用户取消。"
            task_db_record.completed_at = db.func.now()
            db.session.commit()
            os.remove(cancel_signal_file)
            return {"status": "cancelled", "task_id": task_id, "message": "验证在执行前被用户取消。"}

        success, message, results_metrics = run_yolo_validation(
            model_path=model_for_validation_path,
            data_yaml_path=data_yaml_for_validation_path,
            project_path=val_output_dir_project,
            run_name=yolo_val_run_name,
            validation_params=validation_params_dict,
            logger=current_app.logger  # 将Celery任务的logger传递给验证函数
        )

        # --- 处理验证结果 ---
        if success:
            task_db_record.status = 'completed'
            task_db_record.completed_at = db.func.now()
            task_db_record.results_json = json.dumps(results_metrics)
            task_db_record.error_message = None
            db.session.commit()
            current_app.logger.info(
                f"[CeleryTask:{self.request.id}] 验证任务 {task_id} 成功完成。结果: {results_metrics}")
            return {"status": "completed", "task_id": task_id, "results": results_metrics, "message": message}
        else:
            task_db_record.status = 'failed'
            task_db_record.error_message = message or "YOLO验证执行失败，未提供具体错误信息。"
            task_db_record.completed_at = db.func.now()
            db.session.commit()
            current_app.logger.error(f"[CeleryTask:{self.request.id}] 验证任务 {task_id} 失败: {message}")
            raise Exception(f"验证任务失败: {message}")

    except NotImplementedError as nie:
        current_app.logger.error(
            f"[CeleryTask:{self.request.id}] 执行验证任务 {task_id} 因功能未实现而失败: {str(nie)}", exc_info=True)
        if task_db_record:
            task_db_record.status = 'failed'
            task_db_record.error_message = f"任务配置不完整或功能未实现: {str(nie)}"
            task_db_record.completed_at = db.func.now()
            db.session.commit()
        raise
    except FileNotFoundError as fnfe:
        current_app.logger.error(
            f"[CeleryTask:{self.request.id}] 执行验证任务 {task_id} 因文件未找到而失败: {str(fnfe)}", exc_info=True)
        if task_db_record:
            task_db_record.status = 'failed'
            task_db_record.error_message = f"必要文件未找到: {str(fnfe)}"
            task_db_record.completed_at = db.func.now()
            db.session.commit()
        raise
    except Exception as e:
        current_app.logger.error(f"[CeleryTask:{self.request.id}] 执行验证任务 {task_id} 时发生严重错误: {str(e)}",
                                 exc_info=True)
        if task_db_record and task_db_record.status not in ['completed', 'cancelled']:
            task_db_record.status = 'failed'
            task_db_record.error_message = str(e)
            task_db_record.completed_at = db.func.now()
            db.session.commit()
        raise
    finally:
        if user_val_task_base_dir:
            cancel_signal_file = os.path.join(user_val_task_base_dir, ".cancel_signal_val")
            if os.path.exists(cancel_signal_file):
                try:
                    os.remove(cancel_signal_file)
                    current_app.logger.info(
                        f"[CeleryTask:{self.request.id}] 清理验证取消信号文件: {cancel_signal_file}")
                except OSError:  # pragma: no cover
                    pass