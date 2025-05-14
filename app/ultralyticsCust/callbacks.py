# app/ultralyticsCust/callbacks.py
import os
import json
import logging
import time  # 新增 time 模块
from app.models import FinetuneTask
from app.database import db
from sqlalchemy.orm import Session  # 显式导入 Session 类型提示


class FinetuneProgressCallback:
    """
    自定义YOLOv8回调，用于向数据库报告轮次进度、处理取消信号，
    并通过Celery任务的update_state报告批次进度。
    大约每隔指定时间间隔更新一次数据库中的批次进度。
    """

    def __init__(self,
                 task_id: str,
                 user_id: int,
                 db_session_maker: callable,
                 user_task_base_dir: str,
                 logger: logging.Logger,  # 应使用 current_app.logger
                 total_epochs_from_task: int = 0,
                 celery_task_update_state_func: callable = None,
                 db_update_interval_seconds: int = 5):  # 新增参数：数据库更新时间间隔
        self.task_id = task_id
        self.user_id = user_id
        self.db_session_maker = db_session_maker
        self.user_task_base_dir = user_task_base_dir
        self.logger = logger  # 使用传入的 logger (应该是 current_app.logger)
        self.cancel_signal_file = os.path.join(self.user_task_base_dir, ".cancel_signal")
        self.initial_total_epochs = total_epochs_from_task
        self._trainer = None  # YOLO Trainer 实例
        self.celery_task_update_state_func = celery_task_update_state_func

        self.db_update_interval = db_update_interval_seconds
        self.last_db_update_time_batch = 0  # 上次批次相关信息更新到DB的时间戳
        self.last_metrics_for_db = {}  # 缓存上次写入DB的metrics_json内容，避免频繁读DB

        self.logger.info(
            f"[Callback:{self.task_id}] Initialized. DB update interval: {self.db_update_interval}s. Cancel signal file: {self.cancel_signal_file}")

    def _get_and_update_task(self, updates: dict, session: Session):
        task_record = session.query(FinetuneTask).filter_by(id=self.task_id, user_id=self.user_id).first()
        if task_record:
            for key, value in updates.items():
                setattr(task_record, key, value)
        else:
            self.logger.error(f"[Callback:{self.task_id}] Task not found in DB for update.")
        return task_record

    def _execute_db_update(self, updates: dict, force_update: bool = False):
        """
        执行数据库更新。
        :param updates: 要更新的字段字典。
        :param force_update: 是否强制更新，忽略时间间隔（例如轮次结束时）。
        """
        current_time = time.time()

        if not force_update and (current_time - self.last_db_update_time_batch < self.db_update_interval):
            # self.logger.debug(f"[Callback:{self.task_id}] Skipping DB update due to interval.")
            return  # 未到时间间隔，不更新数据库

        session: Session = None
        try:
            session = self.db_session_maker()
            self._get_and_update_task(updates, session)
            session.commit()
            self.logger.info(
                f"[Callback:{self.task_id}] DB successfully updated with keys: {list(updates.keys())}. Forced: {force_update}")
            if not force_update:  # 只为受时间间隔控制的更新（即批次更新）重置时间戳
                self.last_db_update_time_batch = current_time
                # 更新缓存的 metrics_json，如果它在 updates 中
                if "metrics_json" in updates:
                    self.last_metrics_for_db = json.loads(updates["metrics_json"]) if isinstance(
                        updates["metrics_json"], str) else updates["metrics_json"]

        except Exception as e:
            self.logger.error(f"[Callback:{self.task_id}] Error updating task in DB: {e}", exc_info=True)
            if session:
                session.rollback()
        finally:
            if session:
                session.close()

    def _check_cancel_signal(self) -> bool:
        if os.path.exists(self.cancel_signal_file):
            self.logger.info(f"[Callback:{self.task_id}] Cancel signal detected. Attempting to stop training.")
            if self._trainer:
                self._trainer.stop_training = True  # Ultralytics YOLOv8 停止训练的标志
                self.logger.info(f"[Callback:{self.task_id}] Requested trainer to stop training.")
            else:
                self.logger.warning(
                    f"[Callback:{self.task_id}] Cancel signal detected, but trainer instance is not yet available in callback.")

            updates = {
                "status": 'cancelled',
                "error_message": "任务被用户通过回调中的信号文件检测取消。",
                "completed_at": db.func.now()
            }
            self._execute_db_update(updates, force_update=True)  # 状态变更，强制更新

            try:
                os.remove(self.cancel_signal_file)
                self.logger.info(f"[Callback:{self.task_id}] Cancel signal file removed.")
            except OSError as e:
                self.logger.error(f"[Callback:{self.task_id}] Error removing cancel signal file: {e}")
            return True
        return False

    def on_pretrain_routine_start(self, trainer):
        self.logger.info(f"[Callback:{self.task_id}] on_pretrain_routine_start: Storing trainer instance.")
        self._trainer = trainer
        # 初始化/重置状态
        self.last_db_update_time_batch = 0
        # 从数据库加载一次 metrics_json 作为初始缓存，如果存在的话
        session: Session = None
        try:
            session = self.db_session_maker()
            task_record = session.query(FinetuneTask).filter_by(id=self.task_id, user_id=self.user_id).first()
            if task_record and task_record.metrics_json:
                self.last_metrics_for_db = json.loads(task_record.metrics_json)
            else:
                self.last_metrics_for_db = {}
        except Exception as e:
            self.logger.error(f"[Callback:{self.task_id}] Error loading initial metrics_json: {e}")
            self.last_metrics_for_db = {}
        finally:
            if session: session.close()

    def on_pretrain_routine_end(self, trainer):
        self.logger.info(f"[Callback:{self.task_id}] on_pretrain_routine_end called.")
        if self._check_cancel_signal():
            self.logger.info(f"[Callback:{self.task_id}] Training stopped by cancel signal before first epoch.")
            return

        session: Session = None
        try:
            session = self.db_session_maker()
            task_record = session.query(FinetuneTask).filter_by(id=self.task_id, user_id=self.user_id).first()
            if task_record:
                actual_total_epochs = getattr(trainer, 'epochs', 0)
                updates_for_db = {}

                if actual_total_epochs > 0:  # trainer.epochs 通常是准确的总轮次数
                    if task_record.total_epochs != actual_total_epochs:
                        updates_for_db["total_epochs"] = actual_total_epochs
                elif self.initial_total_epochs > 0 and (
                        task_record.total_epochs is None or task_record.total_epochs == 0):
                    # 如果 trainer.epochs 未提供，但我们从任务参数中得到了一个初始值
                    updates_for_db["total_epochs"] = self.initial_total_epochs

                # 确保 total_epochs 有值，用于Celery进度条等
                if not updates_for_db.get("total_epochs") and not task_record.total_epochs:
                    updates_for_db[
                        "total_epochs"] = self.initial_total_epochs if self.initial_total_epochs > 0 else 1  # 至少为1，防止除零

                if task_record.status == 'queued' or task_record.status == 'pending':  # 确保状态是 running
                    updates_for_db["status"] = 'running'
                if not task_record.started_at:
                    updates_for_db["started_at"] = db.func.now()

                if updates_for_db:
                    # 这里直接操作 session，因为 _execute_db_update 有自己的 session 管理
                    self._get_and_update_task(updates_for_db, session)
                    session.commit()
                    self.logger.info(
                        f"[Callback:{self.task_id}] Task pre-train info updated in DB: {list(updates_for_db.keys())}")
            else:
                self.logger.error(f"[Callback:{self.task_id}] Task not found in DB during on_pretrain_routine_end.")
        except Exception as e:
            self.logger.error(f"[Callback:{self.task_id}] Error in on_pretrain_routine_end: {e}", exc_info=True)
            if session: session.rollback()
        finally:
            if session: session.close()

    def on_fit_epoch_end(self, trainer):
        current_epoch_display = int(trainer.epoch) + 1 if hasattr(trainer, 'epoch') else 'N/A'
        self.logger.debug(f"[Callback:{self.task_id}] on_fit_epoch_end called for epoch {current_epoch_display}.")

        if self._check_cancel_signal():  # 检查取消
            self.logger.info(
                f"[Callback:{self.task_id}] Epoch {current_epoch_display}: Training stopped by cancel signal.")
            return

        current_epoch_db_val = int(trainer.epoch) + 1
        total_epochs_val = int(trainer.epochs) if hasattr(trainer, 'epochs') else self.initial_total_epochs

        # 从 trainer.metrics 获取轮次结束时的指标
        epoch_metrics = {}
        if hasattr(trainer, 'metrics') and trainer.metrics:
            epoch_metrics = {k: (round(float(v), 5) if isinstance(v, (float, int)) else str(v))
                             for k, v in trainer.metrics.items()}

        # 将这些轮次指标合并到我们维护的 metrics_json 中
        # self.last_metrics_for_db 此刻可能包含上一个批次的临时信息
        # 我们用 trainer.metrics (更权威的轮次结束指标) 来更新它
        # 同时保留一些可能由批次回调设置的非 trainer.metrics 的信息（如速度）

        # 创建一个新的字典，基于 self.last_metrics_for_db，但优先使用 trainer.metrics 的值
        merged_metrics = self.last_metrics_for_db.copy()  # 从缓存的指标开始
        merged_metrics.update(epoch_metrics)  # 用轮次结束的指标覆盖/添加

        # 确保 current_batch 和 total_batches_in_epoch 在轮次结束时是正确的
        if hasattr(trainer, 'train_loader') and trainer.train_loader:
            total_batches_in_this_epoch = len(trainer.train_loader)
            merged_metrics['current_batch'] = total_batches_in_this_epoch  # 轮次结束，当前批次等于总批次
            merged_metrics['total_batches_in_epoch'] = total_batches_in_this_epoch

        # 如果 iterations_per_second_batch 存在于 merged_metrics，可以保留它作为该轮次最后一个批次的速度参考
        # 或者计算一个轮次平均速度，如果 trainer 提供这种信息的话

        updates = {
            "current_epoch": current_epoch_db_val,
            "metrics_json": json.dumps(merged_metrics)
        }
        self._execute_db_update(updates, force_update=True)  # 轮次结束，强制更新数据库
        self.logger.info(
            f"[Callback:{self.task_id}] Epoch {current_epoch_display} progress saved to DB (forced). Metrics: {merged_metrics}")

        # 更新Celery任务状态 (用于前端显示轮次进度)
        if self.celery_task_update_state_func:
            celery_meta = {
                'type': 'epoch_progress',
                'current_epoch': current_epoch_db_val,
                'total_epochs': total_epochs_val,
                'status_message': f"Epoch {current_epoch_display}/{total_epochs_val} completed.",
                'metrics': merged_metrics  # 发送合并后的指标
            }
            try:
                self.celery_task_update_state_func(state='PROGRESS', meta=celery_meta)
            except Exception as e_celery:
                self.logger.error(f"[Callback:{self.task_id}] Error sending epoch progress to Celery: {e_celery}",
                                  exc_info=False)

    def on_train_batch_end(self, trainer):
        if not self._trainer: return  # trainer 未初始化
        if self._check_cancel_signal(): return  # 检查取消

        current_time = time.time()
        # 检查是否到达更新数据库的时间间隔
        if current_time - self.last_db_update_time_batch < self.db_update_interval and self.last_db_update_time_batch != 0:
            # 虽然不更新DB，但仍然可以发送Celery进度，如果需要非常实时的前端更新
            # 但为了与DB更新频率匹配，这里也先跳过Celery更新，或使其更频繁
            # 为简单起见，如果DB不更新，Celery的批次进度也不发（轮次进度会发）
            return

        try:
            current_epoch_display = int(trainer.epoch) + 1
            current_batch_idx_display = trainer.batch_idx + 1  # trainer.batch_idx 是0-indexed

            total_batches_in_epoch = 0
            if trainer.train_loader:
                total_batches_in_epoch = len(trainer.train_loader)
            elif hasattr(trainer, 'batches_per_epoch'):  # 有些版本可能是这个属性
                total_batches_in_epoch = trainer.batches_per_epoch

            # 估算速度 (it/s)
            # trainer.speed 是一个字典，例如: {'preprocess': 2.0, 'inference': 10.0, 'loss': 1.0, 'postprocess': 1.5} (单位: ms)
            # trainer.dt 是一个列表，包含各阶段耗时，例如 [preprocess_dt, inference_dt, loss_dt, postprocess_dt]
            iterations_per_second = None
            batch_time_sum_ms = 0
            if hasattr(trainer, 'speed') and isinstance(trainer.speed, dict) and trainer.speed:
                batch_time_sum_ms = sum(s for s in trainer.speed.values() if isinstance(s, (int, float)))
            elif hasattr(trainer, 'dt') and isinstance(trainer.dt, list) and len(trainer.dt) >= 3:  # 假设前3个是主要耗时
                batch_time_sum_ms = sum(trainer.dt[:3])

            if batch_time_sum_ms > 0:
                iterations_per_second = round(1000.0 / batch_time_sum_ms, 2)  # 转换为 it/s

            # 获取当前批次的损失等信息
            batch_specific_metrics = {}
            if hasattr(trainer, 'loss') and trainer.loss is not None:  # YOLOv8 的批次损失
                batch_specific_metrics['batch_loss'] = round(float(trainer.loss.item()), 5)

            # Ultralytics trainer.label_loss_items(trainer.tloss, prefix="train") 可以提供更详细的损失分类
            if hasattr(trainer, 'label_loss_items') and hasattr(trainer, 'tloss'):  # trainer.tloss 是 tensor 形式的损失
                # 这个方法可能需要 trainer.tloss 已经是 detached 和 on cpu 的
                try:
                    loss_items_dict = trainer.label_loss_items(trainer.tloss.detach().cpu(), prefix="train")
                    if loss_items_dict:
                        batch_specific_metrics.update({k: round(v, 5) for k, v in loss_items_dict.items()})
                except Exception as e_loss_items:
                    self.logger.debug(f"[Callback:{self.task_id}] Could not get detailed loss_items: {e_loss_items}")

            # 更新 metrics_json: 基于上次写入DB的 metrics (self.last_metrics_for_db)
            # 然后添加/更新当前批次的信息
            metrics_for_db_update = self.last_metrics_for_db.copy()  # 从缓存开始
            metrics_for_db_update['current_batch'] = current_batch_idx_display
            metrics_for_db_update['total_batches_in_epoch'] = total_batches_in_epoch
            if iterations_per_second is not None:
                metrics_for_db_update['iterations_per_second_batch'] = iterations_per_second
            metrics_for_db_update.update(batch_specific_metrics)  # 添加/更新批次特定的损失等

            # 更新数据库 (此方法内部会检查时间间隔并更新 self.last_db_update_time_batch)
            db_updates = {
                "current_epoch": current_epoch_display,  # 确保当前轮次也更新
                "metrics_json": json.dumps(metrics_for_db_update)
            }
            self._execute_db_update(db_updates, force_update=False)  # 非强制

            # 发送 Celery 任务进度 (这个可以每次都发，如果需要更频繁的前端更新)
            # 但如果上面DB没更新，这里的 metrics_for_db_update 可能不是最新的DB状态
            # 为了简单和一致性，如果DB没更新，Celery的这个详细批次进度也不发
            # （上面 return 的时候已经跳过了）
            if self.celery_task_update_state_func and (
                    time.time() - self.last_db_update_time_batch < 1.0):  # 检查是否刚更新了DB
                total_epochs_val = int(trainer.epochs) if hasattr(trainer, 'epochs') else self.initial_total_epochs
                celery_meta = {
                    'type': 'batch_progress',
                    'epoch': current_epoch_display,
                    'total_epochs': total_epochs_val,
                    'batch': current_batch_idx_display,
                    'total_batches_in_epoch': total_batches_in_epoch,
                    'iterations_per_second': iterations_per_second,
                    'batch_metrics': batch_specific_metrics,  # 只发送当前批次的指标
                    'status_message': f"Epoch {current_epoch_display}/{total_epochs_val}, Batch {current_batch_idx_display}/{total_batches_in_epoch}"
                }
                if iterations_per_second is not None:
                    celery_meta['status_message'] += f", Speed: {iterations_per_second} it/s"

                try:
                    self.celery_task_update_state_func(state='PROGRESS', meta=celery_meta)
                except Exception as e_celery:
                    self.logger.error(f"[Callback:{self.task_id}] Error sending batch progress to Celery: {e_celery}",
                                      exc_info=False)

        except Exception as e:
            self.logger.error(f"[Callback:{self.task_id}] Error in on_train_batch_end: {e}", exc_info=True)

    def on_train_end(self, trainer):
        self.logger.info(f"[Callback:{self.task_id}] on_train_end called.")

        # 检查是否因为取消信号而停止
        # trainer.stop_training 是 Ultralytics YOLOv8 的标志
        if self._trainer and getattr(self._trainer, 'stop_training', False) and os.path.exists(self.cancel_signal_file):
            self.logger.info(
                f"[Callback:{self.task_id}] Training ended due to cancel signal. Final status should be 'cancelled'.")
            # _check_cancel_signal 或 on_fit_epoch_end 中的检查应该已经处理了状态
            # 这里确保信号文件被移除
            if os.path.exists(self.cancel_signal_file):
                try:
                    os.remove(self.cancel_signal_file)
                except OSError:
                    pass
            return

            # 如果正常结束，确保最后的状态和指标被记录
        session: Session = None
        try:
            session = self.db_session_maker()
            task_record = session.query(FinetuneTask).filter_by(id=self.task_id, user_id=self.user_id).first()
            if not task_record: return

            # 只在任务仍在运行时更新最终指标
            if task_record.status == 'running':
                final_epoch_metrics = {}
                if hasattr(trainer, 'metrics') and trainer.metrics:  # trainer.metrics 是最后一个epoch的指标
                    final_epoch_metrics = {k: (round(float(v), 5) if isinstance(v, (float, int)) else str(v))
                                           for k, v in trainer.metrics.items()}

                # 合并到 self.last_metrics_for_db
                merged_final_metrics = self.last_metrics_for_db.copy()
                merged_final_metrics.update(final_epoch_metrics)

                # 获取最终模型路径 (绝对路径)
                best_model_path_abs = getattr(trainer, 'best', None)
                if best_model_path_abs and os.path.exists(str(best_model_path_abs)):
                    merged_final_metrics["callback_reported_best_model_path_abs"] = str(best_model_path_abs)

                # 新增：尝试获取最佳轮次（如果 trainer 有提供）
                best_epoch = getattr(trainer, 'best_epoch', None)
                if best_epoch is not None:
                    merged_final_metrics["best_epoch"] = int(best_epoch)

                updates = {}
                if merged_final_metrics:
                    updates["metrics_json"] = json.dumps(merged_final_metrics)

                # 确保 current_epoch 等于 total_epochs
                if hasattr(trainer, 'epochs') and task_record.current_epoch != trainer.epochs:
                    updates["current_epoch"] = int(trainer.epochs)

                if updates:
                    # 直接操作 session，因为这是最终更新
                    self._get_and_update_task(updates, session)
                    session.commit()
                    self.logger.info(f"[Callback:{self.task_id}] Final metrics/info updated in DB from on_train_end.")
            else:
                self.logger.info(
                    f"[Callback:{self.task_id}] Training ended, but task status was '{task_record.status}'. No final metric update from callback.")

        except Exception as e:
            self.logger.error(f"[Callback:{self.task_id}] Error in on_train_end: {e}", exc_info=True)
            if session: session.rollback()
        finally:
            if session: session.close()
            # 确保取消信号文件最终被清理
            if os.path.exists(self.cancel_signal_file):
                try:
                    os.remove(self.cancel_signal_file)
                    self.logger.info(f"[Callback:{self.task_id}] Cleaned up cancel signal file in on_train_end.")
                except OSError:
                    pass