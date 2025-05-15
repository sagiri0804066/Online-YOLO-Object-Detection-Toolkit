# app/ultralyticsCust/callbacks.py
import os
import json
import logging
import time
from app.models import FinetuneTask
from app.database import db
from sqlalchemy.orm import Session
from math import ceil  # 导入ceil用于向上取整


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
                 logger: logging.Logger,
                 total_epochs_from_task: int = 0,
                 celery_task_update_state_func: callable = None,
                 db_update_interval_seconds: int = 5):
        self.task_id = task_id
        self.user_id = user_id
        self.db_session_maker = db_session_maker
        self.user_task_base_dir = user_task_base_dir
        self.logger = logger
        self.cancel_signal_file = os.path.join(self.user_task_base_dir, ".cancel_signal")
        self.initial_total_epochs = total_epochs_from_task
        self._trainer = None
        self.celery_task_update_state_func = celery_task_update_state_func

        self.db_update_interval = db_update_interval_seconds
        self.last_db_update_time_batch = 0
        self.last_metrics_for_db = {}

        self.batch_start_time_manual = 0
        self.ema_batch_time_manual = None
        self.ema_alpha_manual = 0.1

        # 计数器
        self.manual_batch_counter_for_epoch = 0  # 1-indexed counter for batches within an epoch
        self.last_epoch_for_manual_counter = -1  # Tracks the epoch for resetting the counter

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
        current_time = time.time()
        if not force_update and (current_time - self.last_db_update_time_batch < self.db_update_interval):
            # self.logger.debug(f"[Callback:{self.task_id}] Skipping DB update due to interval.") # Can be noisy
            return

        session: Session = None
        try:
            session = self.db_session_maker()
            self._get_and_update_task(updates, session)
            session.commit()
            self.logger.info(
                f"[Callback:{self.task_id}] DB successfully updated with keys: {list(updates.keys())}. Forced: {force_update}")

            if not force_update:
                self.last_db_update_time_batch = current_time

            if "metrics_json" in updates:
                try:
                    if isinstance(updates["metrics_json"], str):
                        self.last_metrics_for_db = json.loads(updates["metrics_json"])
                    elif isinstance(updates["metrics_json"], dict):
                        self.last_metrics_for_db = updates["metrics_json"]
                    else:
                        self.logger.warning(
                            f"[Callback:{self.task_id}] metrics_json in updates was neither string nor dict. Type: {type(updates['metrics_json'])}")
                except json.JSONDecodeError as e:
                    self.logger.error(
                        f"[Callback:{self.task_id}] Failed to decode metrics_json for caching: {e}. Metrics string: {updates['metrics_json']}")
                except TypeError as e:
                    self.logger.error(
                        f"[Callback:{self.task_id}] metrics_json for caching was not a string or dict: {e}. Value: {updates['metrics_json']}")
        except Exception as e:
            self.logger.error(f"[Callback:{self.task_id}] Error updating task in DB: {e}", exc_info=True)
            if session:
                session.rollback()
        finally:
            if session:
                session.close()

    def _check_cancel_signal(self) -> bool:
        trainer_to_stop = self._trainer  # Use the stored trainer instance
        if os.path.exists(self.cancel_signal_file):
            self.logger.info(f"[Callback:{self.task_id}] Cancel signal detected. Attempting to stop training.")
            if trainer_to_stop:
                trainer_to_stop.stop_training = True
                self.logger.info(f"[Callback:{self.task_id}] Requested trainer (self._trainer) to stop training.")
            else:
                self.logger.warning(
                    f"[Callback:{self.task_id}] Cancel signal detected, but self._trainer instance is not yet available in callback.")
            updates = {
                "status": 'cancelled',
                "error_message": "任务被用户通过回调中的信号文件检测取消。",
                "completed_at": db.func.now()
            }
            self._execute_db_update(updates, force_update=True)
            try:
                os.remove(self.cancel_signal_file)
                self.logger.info(f"[Callback:{self.task_id}] Cancel signal file removed.")
            except OSError as e:
                self.logger.error(f"[Callback:{self.task_id}] Error removing cancel signal file: {e}")
            return True
        return False

    def on_pretrain_routine_start(self, trainer):
        self.logger.info(
            f"[Callback:{self.task_id}] on_pretrain_routine_start: Storing trainer instance as self._trainer.")
        self._trainer = trainer  # Store the trainer instance
        self.last_db_update_time_batch = 0
        self.last_metrics_for_db = {}
        self.manual_batch_counter_for_epoch = 0
        self.last_epoch_for_manual_counter = -1

        session: Session = None
        try:
            session = self.db_session_maker()
            task_record = session.query(FinetuneTask).filter_by(id=self.task_id, user_id=self.user_id).first()
            if task_record and task_record.metrics_json:
                try:
                    self.last_metrics_for_db = json.loads(task_record.metrics_json)
                    self.logger.info(
                        f"[Callback:{self.task_id}] Loaded initial metrics from DB: {self.last_metrics_for_db if len(str(self.last_metrics_for_db)) < 200 else str(self.last_metrics_for_db)[:200] + '...'}")
                except json.JSONDecodeError:
                    self.logger.warning(
                        f"[Callback:{self.task_id}] Failed to decode existing metrics_json from DB, starting fresh.")
                    self.last_metrics_for_db = {}
            else:
                self.last_metrics_for_db = {}
        except Exception as e:
            self.logger.error(
                f"[Callback:{self.task_id}] Error loading initial metrics_json in on_pretrain_routine_start: {e}")
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
                if actual_total_epochs > 0:
                    if task_record.total_epochs != actual_total_epochs:
                        updates_for_db["total_epochs"] = actual_total_epochs
                elif self.initial_total_epochs > 0 and (
                        task_record.total_epochs is None or task_record.total_epochs == 0):
                    updates_for_db["total_epochs"] = self.initial_total_epochs
                if not updates_for_db.get("total_epochs") and not task_record.total_epochs:
                    updates_for_db["total_epochs"] = 1
                if task_record.status == 'queued' or task_record.status == 'pending':
                    updates_for_db["status"] = 'running'
                if not task_record.started_at:
                    updates_for_db["started_at"] = db.func.now()
                if updates_for_db:
                    self._execute_db_update(updates_for_db, force_update=True)
                    self.logger.info(
                        f"[Callback:{self.task_id}] Task pre-train info updated in DB: {list(updates_for_db.keys())}")
            else:
                self.logger.error(f"[Callback:{self.task_id}] Task not found in DB during on_pretrain_routine_end.")
        except Exception as e:
            self.logger.error(f"[Callback:{self.task_id}] Error in on_pretrain_routine_end: {e}", exc_info=True)
        finally:
            if session: session.close()

    def on_train_batch_start(self, trainer):
        # self.logger.critical(f"!!!!!!!!!! [Callback:{self.task_id}] on_train_batch_start CALLED !!!!!!!!!!") # Keep for debugging if needed
        # self.logger.critical(f"[Callback:{self.task_id}] Trainer type (on_train_batch_start): {type(trainer)}")

        # Update manual batch counter
        current_trainer_epoch = -1
        if hasattr(trainer, 'epoch'):
            current_trainer_epoch = int(trainer.epoch)  # 0-indexed

        if current_trainer_epoch != self.last_epoch_for_manual_counter:
            self.manual_batch_counter_for_epoch = 0  # Reset for new epoch
            self.last_epoch_for_manual_counter = current_trainer_epoch
            self.logger.info(
                f"[Callback:{self.task_id}] New epoch {current_trainer_epoch + 1} started, batch counter reset.")

        self.manual_batch_counter_for_epoch += 1  # Increment for current batch (becomes 1-indexed)
        # self.logger.critical(f"[Callback:{self.task_id}] Manual batch counter for epoch {current_trainer_epoch + 1}: {self.manual_batch_counter_for_epoch}")

        self.batch_start_time_manual = time.time()

    def on_fit_epoch_end(self, trainer):
        current_epoch_0_indexed = int(trainer.epoch) if hasattr(trainer, 'epoch') else -1
        current_epoch_display = current_epoch_0_indexed + 1
        self.logger.info(f"[Callback:{self.task_id}] on_fit_epoch_end called for epoch {current_epoch_display}.")
        self.logger.info(
            f"[Callback:{self.task_id}] trainer.metrics at epoch end: {trainer.metrics if hasattr(trainer, 'metrics') else 'N/A'}")

        if self._check_cancel_signal():
            self.logger.info(
                f"[Callback:{self.task_id}] Epoch {current_epoch_display}: Training stopped by cancel signal.")
            return

        total_epochs_val = int(trainer.epochs) if hasattr(trainer, 'epochs') else self.initial_total_epochs

        metrics_for_db = {}
        if hasattr(trainer, 'metrics') and trainer.metrics:
            metrics_for_db = {k: (round(float(v), 5) if isinstance(v, (float, int)) else str(v))
                              for k, v in trainer.metrics.items()}

        total_batches_in_this_epoch = 0
        if hasattr(trainer, 'train_loader') and trainer.train_loader:
            total_batches_in_this_epoch = len(trainer.train_loader)
        elif hasattr(trainer, 'batches_per_epoch'):
            total_batches_in_this_epoch = trainer.batches_per_epoch

        if total_batches_in_this_epoch > 0:
            metrics_for_db['current_batch'] = total_batches_in_this_epoch
            metrics_for_db['total_batches_in_epoch'] = total_batches_in_this_epoch
        else:
            metrics_for_db.pop('current_batch', None)
            metrics_for_db.pop('total_batches_in_epoch', None)

        if isinstance(self.last_metrics_for_db, dict):
            for key_to_preserve in ["best_epoch", "best_fitness_val", "iterations_per_second_batch", "batch_loss"]:
                if key_to_preserve in self.last_metrics_for_db and key_to_preserve not in metrics_for_db:
                    metrics_for_db[key_to_preserve] = self.last_metrics_for_db[key_to_preserve]

        common_train_loss_keys = ['train/box_loss', 'train/cls_loss', 'train/dfl_loss']
        missing_train_losses = [k for k in common_train_loss_keys if k not in metrics_for_db]
        if missing_train_losses:
            self.logger.warning(
                f"[Callback:{self.task_id}] Epoch {current_epoch_display}: trainer.metrics is missing common train loss keys: {missing_train_losses}. Content keys: {list(metrics_for_db.keys())}")

        updates = {
            "current_epoch": current_epoch_display,
            "metrics_json": json.dumps(metrics_for_db)
        }
        self._execute_db_update(updates, force_update=True)
        self.logger.info(
            f"[Callback:{self.task_id}] Epoch {current_epoch_display} progress saved to DB (forced). Metrics: {metrics_for_db if len(str(metrics_for_db)) < 200 else str(metrics_for_db)[:200] + '...'}")

        if self.celery_task_update_state_func:
            progress_percent = (current_epoch_display / total_epochs_val * 100) if total_epochs_val > 0 else 0
            celery_meta = {
                'type': 'epoch_progress',
                'current_epoch': current_epoch_display,
                'total_epochs': total_epochs_val,
                'progress_percent': round(progress_percent, 2),
                'status_message': f"Epoch {current_epoch_display}/{total_epochs_val} completed.",
                'metrics': metrics_for_db
            }
            try:
                self.celery_task_update_state_func(state='PROGRESS', meta=celery_meta)
            except Exception as e_celery:
                self.logger.error(f"[Callback:{self.task_id}] Error sending epoch progress to Celery: {e_celery}",
                                  exc_info=False)

    def on_train_batch_end(self, trainer):
        # self.logger.critical(f"!!!!!!!!!! [Callback:{self.task_id}] on_train_batch_end CALLED !!!!!!!!!!") # Keep for debugging if needed

        if self._check_cancel_signal():
            self.logger.info(f"[Callback:{self.task_id}] on_train_batch_end: Cancel signal detected, stopping.")
            return

        if not trainer:  # Should use self._trainer if trainer param is None, but callbacks usually provide it.
            self.logger.error(
                f"[Callback:{self.task_id}] Critical: trainer parameter in on_train_batch_end is None. Using self._trainer if available.")
            trainer = self._trainer  # Fallback to stored trainer
            if not trainer:
                self.logger.error(
                    f"[Callback:{self.task_id}] Critical: self._trainer is also None. Skipping batch update.")
                return

        current_time = time.time()
        # Check if it's time to update DB based on interval (only if not forced)
        if self.last_db_update_time_batch != 0 and (
                current_time - self.last_db_update_time_batch < self.db_update_interval):
            return  # Not time yet

        try:
            current_epoch_0_indexed = -1
            if hasattr(trainer, 'epoch'):
                current_epoch_0_indexed = int(trainer.epoch)
            else:
                self.logger.warning(
                    f"[Callback:{self.task_id}] trainer.epoch not found in on_train_batch_end. Using last known: {self.last_epoch_for_manual_counter}")
                current_epoch_0_indexed = self.last_epoch_for_manual_counter  # Use the one updated by on_train_batch_start

            current_epoch_display = current_epoch_0_indexed + 1 if current_epoch_0_indexed != -1 else 1  # 1-indexed for display

            total_batches_in_epoch = 0
            if hasattr(trainer, 'train_loader') and trainer.train_loader:
                total_batches_in_epoch = len(trainer.train_loader)
            elif hasattr(trainer, 'batches_per_epoch'):  # Fallback, might not be set early
                total_batches_in_epoch = trainer.batches_per_epoch

            if total_batches_in_epoch == 0 and hasattr(trainer, 'args') and hasattr(trainer.args,
                                                                                    'nbs'):  # nbs: nominal batch size (total batches in an epoch)
                total_batches_in_epoch = getattr(trainer.args, 'nbs', 0)
                if total_batches_in_epoch > 0:
                    self.logger.info(
                        f"[Callback:{self.task_id}] Used trainer.args.nbs for total_batches_in_epoch: {total_batches_in_epoch}")

            if total_batches_in_epoch == 0:  # If still zero, log warning
                self.logger.warning(
                    f"[Callback:{self.task_id}] total_batches_in_epoch is 0 in on_train_batch_end. Progress calculation might be inaccurate.")

            # --- 获取当前批次索引 ---
            # Use the 1-indexed manual counter directly for display
            current_batch_idx_display = self.manual_batch_counter_for_epoch
            # For calculations, we might need 0-indexed
            current_batch_idx_0_indexed = self.manual_batch_counter_for_epoch - 1

            # self.logger.info(f"[Callback:{self.task_id}] Using manual batch counter. Display: {current_batch_idx_display}, 0-indexed: {current_batch_idx_0_indexed}")

            # Cap display value if total_batches_in_epoch is known
            if total_batches_in_epoch > 0:
                current_batch_idx_display = max(1, min(current_batch_idx_display, total_batches_in_epoch))
            # --- 结束获取批次索引 ---

            iterations_per_second = None
            # Try trainer.speed (usually in ms per component)
            if hasattr(trainer, 'speed') and isinstance(trainer.speed, dict) and trainer.speed:
                relevant_speed_keys = ['preprocess', 'inference', 'loss', 'postprocess', 'forward', 'backward']
                batch_time_sum_ms = sum(trainer.speed.get(k, 0.0) for k in relevant_speed_keys if
                                        isinstance(trainer.speed.get(k), (int, float)))
                if batch_time_sum_ms > 0:
                    iterations_per_second = round(1000.0 / batch_time_sum_ms, 2)

            # Try trainer.stats (may contain 'time/batch' in seconds)
            if iterations_per_second is None and hasattr(trainer, 'stats') and isinstance(trainer.stats, dict):
                if 'time/batch' in trainer.stats:
                    batch_time_s = trainer.stats['time/batch']
                    if isinstance(batch_time_s, (int, float)) and batch_time_s > 0:
                        iterations_per_second = round(1.0 / batch_time_s, 2)

            # Try trainer.dt (list/tuple of [preprocess, inference, postprocess] times in seconds)
            if iterations_per_second is None and hasattr(trainer, 'dt') and isinstance(trainer.dt, (list, tuple)):
                if len(trainer.dt) > 0:
                    total_dt_seconds = sum(t for t in trainer.dt if isinstance(t, (int, float)))
                    if total_dt_seconds > 0:
                        iterations_per_second = round(1.0 / total_dt_seconds, 2)

            # Fallback to manual EMA calculation
            if iterations_per_second is None and self.batch_start_time_manual > 0:
                current_batch_duration_manual = time.time() - self.batch_start_time_manual
                if current_batch_duration_manual > 1e-3:
                    if self.ema_batch_time_manual is None:
                        self.ema_batch_time_manual = current_batch_duration_manual
                    else:
                        self.ema_batch_time_manual = self.ema_alpha_manual * current_batch_duration_manual + \
                                                     (1 - self.ema_alpha_manual) * self.ema_batch_time_manual
                    if self.ema_batch_time_manual > 1e-3:
                        iterations_per_second = round(1.0 / self.ema_batch_time_manual, 2)
                        # self.logger.info(f"[Callback:{self.task_id}] Speed calculated manually (EMA): {iterations_per_second} it/s")

            if iterations_per_second is None:
                self.logger.warning(
                    f"[Callback:{self.task_id}] Could not determine iterations_per_second for batch {current_batch_idx_display}.")

            batch_specific_metrics = {}
            if hasattr(trainer, 'loss') and trainer.loss is not None:  # This is total loss for the batch
                try:
                    batch_specific_metrics['batch_loss'] = round(float(trainer.loss.item()), 5)
                except Exception as e_loss:
                    self.logger.warning(f"[Callback:{self.task_id}] Could not get trainer.loss.item(): {e_loss}")

            # Detailed losses (e.g., box_loss, cls_loss, dfl_loss)
            if hasattr(trainer, 'label_loss_items') and hasattr(trainer, 'tloss') and trainer.tloss is not None:
                try:
                    loss_items_dict = trainer.label_loss_items(trainer.tloss.detach().cpu(),
                                                               prefix="train")  # Adds "train/" prefix
                    if loss_items_dict:
                        batch_specific_metrics.update(
                            {k: round(float(v), 5) for k, v in loss_items_dict.items() if isinstance(v, (int, float))})
                except Exception as e_loss_items:
                    self.logger.debug(
                        f"[Callback:{self.task_id}] Could not get detailed loss_items via label_loss_items: {e_loss_items}")
            elif hasattr(trainer,
                         'loss_items') and trainer.loss_items is not None:  # Fallback for some trainer versions
                try:
                    # loss_names are usually ('box_loss', 'cls_loss', 'dfl_loss')
                    loss_names = getattr(trainer, 'loss_names',
                                         ['box_loss', 'cls_loss', 'dfl_loss'])  # Default if not found
                    if hasattr(trainer.loss_items, 'detach'):  # Ensure it's a tensor
                        detached_loss_items = trainer.loss_items.detach().cpu().tolist()
                        if len(detached_loss_items) == len(loss_names):
                            for i, name in enumerate(loss_names):
                                # Add "train/" prefix if not already there
                                key_name = f"train/{name}" if not name.startswith("train/") else name
                                batch_specific_metrics[key_name] = round(float(detached_loss_items[i]), 5)
                except Exception as e_loss_items_alt:
                    self.logger.debug(
                        f"[Callback:{self.task_id}] Could not get detailed loss_items from trainer.loss_items: {e_loss_items_alt}")

            metrics_for_db_update = {}
            if isinstance(self.last_metrics_for_db, dict):  # Start with last known good epoch metrics
                metrics_for_db_update = self.last_metrics_for_db.copy()

            metrics_for_db_update['current_batch'] = current_batch_idx_display
            metrics_for_db_update[
                'total_batches_in_epoch'] = total_batches_in_epoch if total_batches_in_epoch > 0 else current_batch_idx_display  # Best guess if total_batches is 0

            if iterations_per_second is not None:
                metrics_for_db_update['iterations_per_second_batch'] = iterations_per_second
            else:  # If speed couldn't be determined, remove it if it was there from a previous successful read
                metrics_for_db_update.pop('iterations_per_second_batch', None)

            metrics_for_db_update.update(batch_specific_metrics)  # Add/overwrite with current batch specifics

            db_updates = {
                "current_epoch": current_epoch_display,
                "metrics_json": json.dumps(metrics_for_db_update)
            }
            self._execute_db_update(db_updates, force_update=False)  # This will update self.last_db_update_time_batch

            if self.celery_task_update_state_func:
                total_epochs_val = int(trainer.epochs) if hasattr(trainer, 'epochs') else self.initial_total_epochs
                progress_percent = 0
                if total_epochs_val > 0 and total_batches_in_epoch > 0 and current_epoch_0_indexed != -1:
                    # current_batch_idx_0_indexed is already 0-indexed
                    current_global_iteration_0_indexed = (
                                                                     current_epoch_0_indexed * total_batches_in_epoch) + current_batch_idx_0_indexed
                    total_iterations = total_epochs_val * total_batches_in_epoch
                    if total_iterations > 0:
                        progress_percent = ((
                                                        current_global_iteration_0_indexed + 1) / total_iterations) * 100  # +1 because we're reporting end of this batch
                        progress_percent = min(progress_percent, 100.0)

                celery_meta = {
                    'type': 'batch_progress',
                    'epoch': current_epoch_display,
                    'total_epochs': total_epochs_val,
                    'batch': current_batch_idx_display,
                    'total_batches_in_epoch': total_batches_in_epoch,
                    'progress_percent': round(progress_percent, 2),
                    'iterations_per_second': iterations_per_second,
                    'batch_metrics': batch_specific_metrics,
                    # Only send current batch metrics to Celery for this update
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
        finally:
            # Reset manual batch start time for the next batch, regardless of success/failure here
            self.batch_start_time_manual = 0

    def on_model_save(self, trainer):
        try:
            if hasattr(trainer, 'ckpt') and trainer.ckpt and isinstance(trainer.ckpt, dict):
                saved_epoch_0_indexed = trainer.ckpt.get('epoch', -1)  # epoch is 0-indexed
                fitness_of_saved_ckpt = trainer.ckpt.get('best_fitness')

                if fitness_of_saved_ckpt is not None and hasattr(trainer, 'best_fitness') and \
                        abs(fitness_of_saved_ckpt - trainer.best_fitness) < 1e-6:

                    new_best_epoch_1_indexed = saved_epoch_0_indexed + 1

                    metrics_update_for_best = {}
                    if isinstance(self.last_metrics_for_db, dict):
                        metrics_update_for_best = self.last_metrics_for_db.copy()

                    update_needed = False
                    if metrics_update_for_best.get("best_epoch") != new_best_epoch_1_indexed:
                        metrics_update_for_best["best_epoch"] = new_best_epoch_1_indexed
                        update_needed = True

                    current_best_fitness_in_metrics = metrics_update_for_best.get("best_fitness_val")
                    if current_best_fitness_in_metrics is None or \
                            abs(fitness_of_saved_ckpt - current_best_fitness_in_metrics) > 1e-6:
                        metrics_update_for_best["best_fitness_val"] = round(float(fitness_of_saved_ckpt), 5)
                        update_needed = True

                    if update_needed:
                        db_updates = {"metrics_json": json.dumps(metrics_update_for_best)}
                        self._execute_db_update(db_updates, force_update=True)
                        self.logger.info(
                            f"[Callback:{self.task_id}] Updated best_epoch to {new_best_epoch_1_indexed} and/or best_fitness_val to {fitness_of_saved_ckpt} in DB via on_model_save.")
                else:
                    self.logger.debug(
                        f"[Callback:{self.task_id}] on_model_save: ckpt fitness {fitness_of_saved_ckpt} does not match trainer.best_fitness {getattr(trainer, 'best_fitness', 'N/A')}. Not updating best_epoch from this save.")
            else:
                self.logger.debug(f"[Callback:{self.task_id}] on_model_save: trainer.ckpt not available or not a dict.")
        except Exception as e:
            self.logger.error(f"[Callback:{self.task_id}] Error in on_model_save: {e}", exc_info=True)

    def on_train_end(self, trainer):
        self.logger.info(f"[Callback:{self.task_id}] on_train_end called.")
        is_cancelled_by_signal = self._trainer and getattr(self._trainer, 'stop_training', False) and os.path.exists(
            self.cancel_signal_file)

        if is_cancelled_by_signal:
            self.logger.info(
                f"[Callback:{self.task_id}] Training ended due to cancel signal. Final status should be 'cancelled'.")
            if os.path.exists(self.cancel_signal_file):
                try:
                    os.remove(self.cancel_signal_file)
                    self.logger.info(
                        f"[Callback:{self.task_id}] Cleaned up cancel signal file in on_train_end (cancelled case).")
                except OSError as e:
                    self.logger.error(
                        f"[Callback:{self.task_id}] Error removing cancel signal file in on_train_end (cancelled case): {e}")
            return

        session: Session = None
        try:
            session = self.db_session_maker()
            task_record = session.query(FinetuneTask).filter_by(id=self.task_id, user_id=self.user_id).first()
            if not task_record:
                self.logger.error(f"[Callback:{self.task_id}] Task not found in DB during on_train_end.")
                return

            if task_record.status == 'running':
                final_trainer_metrics = {}
                if hasattr(trainer, 'metrics') and trainer.metrics:
                    final_trainer_metrics = {k: (round(float(v), 5) if isinstance(v, (float, int)) else str(v))
                                             for k, v in trainer.metrics.items()}

                merged_final_metrics = {}
                if isinstance(self.last_metrics_for_db, dict):
                    merged_final_metrics = self.last_metrics_for_db.copy()

                merged_final_metrics.update(final_trainer_metrics)

                best_model_abs_path = getattr(trainer, 'best', None)
                if best_model_abs_path and os.path.exists(str(best_model_abs_path)):
                    try:
                        best_model_rel_path = os.path.relpath(str(best_model_abs_path), start=self.user_task_base_dir)
                        merged_final_metrics["best_model_path"] = best_model_rel_path
                    except ValueError:
                        merged_final_metrics["best_model_path_abs"] = str(best_model_abs_path)
                    self.logger.info(f"[Callback:{self.task_id}] Best model path recorded: {best_model_abs_path}")

                updates = {}
                if merged_final_metrics:
                    updates["metrics_json"] = json.dumps(merged_final_metrics)

                final_total_epochs = int(trainer.epochs) if hasattr(trainer, 'epochs') else self.initial_total_epochs
                updates["current_epoch"] = final_total_epochs
                updates["total_epochs"] = final_total_epochs
                updates["status"] = 'completed'
                updates["completed_at"] = db.func.now()
                updates["error_message"] = None

                if updates:
                    self._execute_db_update(updates, force_update=True)
                    self.logger.info(
                        f"[Callback:{self.task_id}] Final metrics/info and status updated to 'completed' in DB from on_train_end. Final metrics: {merged_final_metrics if len(str(merged_final_metrics)) < 200 else str(merged_final_metrics)[:200] + '...'}")

                if self.celery_task_update_state_func:
                    celery_meta = {
                        'type': 'training_completed',
                        'status': 'completed',
                        'message': '训练完成',
                        'metrics': merged_final_metrics,
                        'current_epoch': final_total_epochs,
                        'total_epochs': final_total_epochs,
                        'progress_percent': 100.0
                    }
                    try:
                        self.celery_task_update_state_func(state='PROGRESS', meta=celery_meta)
                        self.logger.info(f"[Callback:{self.task_id}] Sent training completed signal to Celery.")
                    except Exception as e_celery:
                        self.logger.error(
                            f"[Callback:{self.task_id}] Error sending completed status to Celery: {e_celery}",
                            exc_info=False)
            else:
                self.logger.info(
                    f"[Callback:{self.task_id}] Training ended, but task status was '{task_record.status}'. No final metric/status update from callback.")
        except Exception as e:
            self.logger.error(f"[Callback:{self.task_id}] Error in on_train_end: {e}", exc_info=True)
        finally:
            if session: session.close()
            if os.path.exists(self.cancel_signal_file):
                try:
                    os.remove(self.cancel_signal_file)
                    self.logger.info(
                        f"[Callback:{self.task_id}] Cleaned up cancel signal file in on_train_end (final cleanup).")
                except OSError as e:
                    self.logger.error(
                        f"[Callback:{self.task_id}] Error removing cancel signal file during final cleanup: {e}")