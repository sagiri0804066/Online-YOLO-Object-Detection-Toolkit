# app/inference/services.py
import uuid
import shutil
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Lock, Thread, Event
import math
import os
import time
import base64
import cv2
from ultralytics import YOLO
from flask import current_app, Flask

CV2_AVAILABLE = True


# --- YOLO 模型推理器 ---
class YoloModel:
    def __init__(self, model_path):
        self.model_path = model_path
        self.log_func = current_app.logger.info if current_app else print

        self.log_func(f"开始加载 YOLO 模型: {model_path}")
        load_start_time = time.perf_counter()

        if not os.path.exists(model_path):
            self.log_func(f"错误: 模型文件未找到: {model_path}")
            raise FileNotFoundError(f"模型文件未找到: {model_path}")

        try:
            # 加载 YOLO 模型 (例如 YOLOv8)
            # device='cpu' 或 device='0' (for GPU 0) 可以通过 config 传入 predict
            self.model = YOLO(model_path)
            load_end_time = time.perf_counter()
            self.log_func(f"YOLO 模型加载完成: {model_path} (耗时: {load_end_time - load_start_time:.2f}s)")
        except Exception as e:
            self.log_func(f"加载YOLO 模型失败: {model_path}. 错误: {e}", exc_info=True)
            raise RuntimeError(f"加载模型失败: {e}") from e

    def predict(self, image_path, config):
        self.log_func = current_app.logger.info if current_app else print  # 确保在线程中也能正确获取logger
        self.log_func(f"使用模型 {os.path.basename(self.model_path)} 对 {image_path} 进行预测, 配置: {config}")

        start_time = time.perf_counter()

        if not os.path.exists(image_path):
            self.log_func(f"错误: 预测时图像文件未找到: {image_path}")
            # 返回与 InferenceExecutor 错误结构类似的信息
            return {
                "status": "error",
                "error": f"图像文件未找到: {image_path}",
                "image_path_when_error": image_path,
                "json_result": None,
                "annotated_image_base64": None,
                "metrics": None
            }

        # 从 config 中提取 YOLO predict 方法的可接受参数
        predict_kwargs = {}
        allowed_yolo_params = [
            'conf', 'iou', 'imgsz', 'half', 'device', 'max_det', 'vid_stride',
            'stream_buffer', 'visualize', 'augment', 'agnostic_nms', 'classes',
            'retina_masks', 'boxes', 'show', 'save', 'save_txt', 'save_conf',
            'save_crop', 'hide_labels', 'hide_conf', 'line_width', 'verbose',
            'tracker'  # 等等，具体参考 ultralytics 文档
        ]
        for key, value in config.items():
            if key in allowed_yolo_params:
                predict_kwargs[key] = value

        if 'source' in predict_kwargs:  # 'source' 是 predict 方法的第一个参数，不应在 kwargs 中
            del predict_kwargs['source']
        if 'model' in predict_kwargs:  # 'model' 是 YOLO 对象本身，不应在 kwargs 中
            del predict_kwargs['model']

        try:
            # 执行推理
            # results 是一个列表，通常对于单张图片，只包含一个 Result 对象
            results = self.model.predict(source=image_path, **predict_kwargs)
        except Exception as e:
            self.log_func(f" YOLO 模型预测时发生严重错误 (图像: {image_path}): {e}", exc_info=True)
            return {
                "status": "error",
                "error": f"YOLO 推理失败: {str(e)}",
                "image_path_when_error": image_path,
                "json_result": None,
                "annotated_image_base64": None,
                "metrics": None
            }

        json_detections_list = []
        total_confidence = 0
        object_count = 0
        annotated_image_base64 = None
        resolution_str = "N/A"

        if results and len(results) > 0:
            result = results[0]  # 获取第一个（通常是唯一的）结果对象

            # 1. 获取图像分辨率
            if result.orig_shape is not None:  # (height, width)
                resolution_str = f"{result.orig_shape[1]}x{result.orig_shape[0]}"

            # 2. 提取检测结果
            boxes = result.boxes  # Boxes object for bounding box outputs
            names = result.names  # Class names dictionary {id: name}

            for i in range(len(boxes.xyxy)):
                box_coords = boxes.xyxy[i].cpu().numpy().tolist()  # [x1, y1, x2, y2]
                confidence = float(boxes.conf[i].cpu().numpy())
                class_id = int(boxes.cls[i].cpu().numpy())
                class_name = names.get(class_id, f"class_{class_id}")

                json_detections_list.append({
                    "class": class_name,
                    "confidence": round(confidence, 4),
                    "box": [round(c, 2) for c in box_coords]  # x1, y1, x2, y2
                })
                total_confidence += confidence

            object_count = len(json_detections_list)

            # 3. 生成带标注的图像 (如果 OpenCV 可用)
            if CV2_AVAILABLE:
                try:
                    # 使用 result.plot() 获取带标注的图像 (NumPy array BGR)
                    annotated_frame = result.plot(conf=predict_kwargs.get('conf', 0.25), line_width=2)  # plot() 也有自己的参数

                    # 编码为Base64
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
                    _, buffer = cv2.imencode('.jpg', annotated_frame, encode_param)
                    base64_encoded = base64.b64encode(buffer).decode('utf-8')
                    annotated_image_base64 = f"data:image/jpeg;base64,{base64_encoded}"
                except Exception as e_img:
                    self.log_func(f"警告: 绘制或编码标注图像时出错 (图像: {image_path}): {e_img}", exc_info=True)
                    # 备用：如果标注失败，尝试编码原始图像
                    if os.path.exists(image_path):
                        try:
                            with open(image_path, 'rb') as f:
                                original_image_bytes = f.read()
                            base64_encoded = base64.b64encode(original_image_bytes).decode('utf-8')
                            # 尝试猜测图像类型，或默认为jpeg
                            img_ext = os.path.splitext(image_path)[1].lower()
                            mime_type = f"image/{img_ext[1:]}" if img_ext in ['.jpg', '.jpeg', '.png'] else "image/jpeg"
                            annotated_image_base64 = f"data:{mime_type};base64,{base64_encoded}"
                        except Exception as e_orig_img:
                            self.log_func(f"警告: 编码原始图像时也出错 (图像: {image_path}): {e_orig_img}",
                                          exc_info=True)
                            annotated_image_base64 = None  # 彻底失败
            else:  # CV2 不可用
                self.log_func(f"警告: CV2 不可用，跳过图像标注 for {image_path}")
                # 仍然可以尝试返回原始图像的 base64
                if os.path.exists(image_path):
                    try:
                        with open(image_path, 'rb') as f:
                            original_image_bytes = f.read()
                        base64_encoded = base64.b64encode(original_image_bytes).decode('utf-8')
                        img_ext = os.path.splitext(image_path)[1].lower()
                        mime_type = f"image/{img_ext[1:]}" if img_ext in ['.jpg', '.jpeg', '.png'] else "image/jpeg"
                        annotated_image_base64 = f"data:{mime_type};base64,{base64_encoded}"
                    except Exception as e_no_cv2_img:
                        self.log_func(f"警告: CV2 不可用时编码原始图像出错 (图像: {image_path}): {e_no_cv2_img}",
                                      exc_info=True)
                        annotated_image_base64 = None

        average_confidence = round(total_confidence / object_count, 4) if object_count > 0 else 0.0

        end_time = time.perf_counter()
        detection_time_ms = round((end_time - start_time) * 1000, 2)

        return {
            "json_result": {"detections": json_detections_list},
            "annotated_image_base64": annotated_image_base64,
            "metrics": {
                "resolution": resolution_str,
                "detection_time_ms": detection_time_ms,
                "object_count": object_count,
                "average_confidence": average_confidence,
                # 可以添加更多来自 result.speed 的详细计时
                "yolo_speed_metrics_ms": getattr(results[0], 'speed', None) if results and len(results) > 0 else None
            }
        }


# --- 用户会话数据管理 ---
class UserSessionManager:
    """管理用户特定的临时数据（上传文件、结果）"""
    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, upload_base_dir="user_uploads", max_age_seconds=600): # 10分钟
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self.upload_base_dir = upload_base_dir
            if not os.path.exists(self.upload_base_dir):
                os.makedirs(self.upload_base_dir)
            # user_id -> {'files': [{'path': abs_path, 'original_name': name}], 'result': result_json, 'timestamp': float, 'selected_model': str}
            self._user_data = {}
            self.max_age_seconds = max_age_seconds
            self._initialized = True
            print("UserSessionManager 初始化完成")
            # TODO: 启动一个后台线程定期清理过期数据

    def _update_timestamp(self, user_id):
        """更新用户数据的时间戳"""
        if user_id in self._user_data:
            self._user_data[user_id]['timestamp'] = time.time()

    def _ensure_user_entry(self, user_id):
        """确保用户条目存在"""
        if user_id not in self._user_data:
            self._user_data[user_id] = {
                'files': [],
                'result': None,
                'timestamp': time.time(),
                'selected_model': None,
                'config': {}
            }

    def store_config(self, user_id, config):
        """存储用户的推理配置"""
        with self._lock:
            self._ensure_user_entry(user_id)
            self._user_data[user_id]['config'] = config
            self._update_timestamp(user_id)

    def get_config(self, user_id):
        """获取用户的推理配置"""
        self._cleanup_check(user_id)
        with self._lock:
            return self._user_data.get(user_id, {}).get('config', {})

    def _get_user_dir(self, user_id):
        """获取用户的专属上传目录"""
        user_dir = os.path.join(self.upload_base_dir, str(user_id))
        if not os.path.exists(user_dir):
            os.makedirs(user_dir)
        return user_dir

    def store_uploaded_files(self, user_id, uploaded_files):
        """存储用户上传的文件，并清空旧文件"""
        self.clear_files(user_id) # 先清空旧的
        user_dir = self._get_user_dir(user_id)
        stored_file_info = []
        try:
            for file_storage in uploaded_files:
                # 安全地处理文件名，防止路径遍历
                original_filename = file_storage.filename
                safe_filename = str(uuid.uuid4()) + "_" + os.path.basename(original_filename) # 使用UUID保证唯一性
                filepath = os.path.join(user_dir, safe_filename)
                file_storage.save(filepath)
                stored_file_info.append({'path': filepath, 'original_name': original_filename})

            with self._lock:
                self._ensure_user_entry(user_id)
                self._user_data[user_id]['files'] = stored_file_info
                self._update_timestamp(user_id)
            return stored_file_info
        except Exception as e:
            print(f"存储用户 {user_id} 的文件时出错: {e}")
            # 清理本次尝试中可能已保存的文件
            for info in stored_file_info:
                if os.path.exists(info['path']):
                    os.remove(info['path'])
            raise # 重新抛出异常

    def get_uploaded_files(self, user_id):
        """获取用户已上传的文件列表"""
        self._cleanup_check(user_id) # 访问时检查是否过期
        with self._lock:
            return self._user_data.get(user_id, {}).get('files', [])

    def clear_files(self, user_id):
        """清空用户的上传文件和目录"""
        user_dir = os.path.join(self.upload_base_dir, str(user_id))
        if os.path.exists(user_dir):
            try:
                shutil.rmtree(user_dir) # 删除整个目录及其内容
                print(f"已清空用户 {user_id} 的上传目录: {user_dir}")
            except Exception as e:
                print(f"清空用户 {user_id} 目录 {user_dir} 时出错: {e}")
        with self._lock:
            if user_id in self._user_data:
                self._user_data[user_id]['files'] = []
                self._update_timestamp(user_id) # 清空也是一种操作，更新时间戳

    def store_result(self, user_id, result):
        """存储用户的最新推理结果"""
        with self._lock:
            self._ensure_user_entry(user_id)
            self._user_data[user_id]['result'] = result
            self._update_timestamp(user_id)

    def get_result(self, user_id):
        """获取用户的最新推理结果"""
        self._cleanup_check(user_id)
        with self._lock:
            return self._user_data.get(user_id, {}).get('result', None)

    def set_selected_model(self, user_id, model_name):
        """记录用户选择的模型"""
        with self._lock:
            self._ensure_user_entry(user_id)
            self._user_data[user_id]['selected_model'] = model_name
            self._update_timestamp(user_id)

    def get_selected_model(self, user_id):
        """获取用户选择的模型"""
        self._cleanup_check(user_id)
        with self._lock:
            return self._user_data.get(user_id, {}).get('selected_model', None)

    def clear_selected_model(self, user_id):
         """清除用户选择的模型记录"""
         with self._lock:
             if user_id in self._user_data:
                 self._user_data[user_id]['selected_model'] = None
                 self._update_timestamp(user_id)

    def _cleanup_check(self, user_id):
        """检查并清理指定用户的过期数据"""
        with self._lock:
            if user_id in self._user_data:
                last_access = self._user_data[user_id]['timestamp']
                if time.time() - last_access > self.max_age_seconds:
                    print(f"用户 {user_id} 的会话数据已过期，正在清理...")
                    self.clear_files(user_id) # 清理物理文件
                    del self._user_data[user_id] # 从内存中删除
                    print(f"用户 {user_id} 的会话数据已清理。")
                    return True # 已清理
            return False # 未过期或不存在

    def cleanup_expired_sessions(self):
        """清理所有过期的用户会话数据（用于后台任务）"""
        print("开始清理过期用户会话数据...")
        expired_users = []
        with self._lock:
            current_time = time.time()
            for user_id, data in self._user_data.items():
                if current_time - data['timestamp'] > self.max_age_seconds:
                    expired_users.append(user_id)

        for user_id in expired_users:
            print(f"清理过期用户 {user_id} 的数据...")
            self.clear_files(user_id) # 清理物理文件
            with self._lock:
                if user_id in self._user_data: # 再次检查，防止清理期间有活动
                     if current_time - self._user_data[user_id]['timestamp'] > self.max_age_seconds:
                         del self._user_data[user_id] # 从内存中删除
                         print(f"用户 {user_id} 的数据已从内存中删除。")
        print("过期用户会话数据清理完成。")


# --- 推理执行器 ---
class InferenceExecutor:
    """使用线程池异步执行推理任务"""
    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, max_workers=None): # 可以从配置读取 max_workers
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            # 如果不指定 max_workers，ThreadPoolExecutor 会根据 CPU 核数自动设置
            self.executor = ThreadPoolExecutor(max_workers=max_workers)
            self._initialized = True
            print(f"InferenceExecutor 初始化完成，最大工作线程数: {self.executor._max_workers}")

    def _run_inference_task(self, model_instance, image_path, config):
        logger = current_app.logger if current_app else print
        try:
            prediction_output = model_instance.predict(image_path, config)
            return prediction_output
        except Exception as e:
            logger.error(f"推理任务失败 (模型: {model_instance.model_path}, 图片: {image_path}): {e}", exc_info=True)
            return { # 保持与成功返回类似的结构，但标记错误
                "status": "error",
                "error": f"推理失败: {str(e)}",
                "image_path_when_error": image_path, # 用于调试
                "json_result": None,
                "annotated_image_base64": None,
                "metrics": None # 或者包含部分可获取的指标
            }

    def submit_inference(self, model_instance, image_path, config):
        """提交推理任务到线程池"""
        print(f"提交推理任务: 图片={image_path}, 模型={model_instance.model_path}")
        future = self.executor.submit(self._run_inference_task, model_instance, image_path, config)
        return future

    def shutdown(self, wait=True):
        """关闭线程池"""
        print("正在关闭 InferenceExecutor...")
        self.executor.shutdown(wait=wait)
        print("InferenceExecutor 已关闭。")


class InferenceService:
    def __init__(self, app: Flask, user_session_manager: UserSessionManager, inference_executor: InferenceExecutor):
        self.app = app
        self.user_session_manager = user_session_manager
        self.inference_executor = inference_executor

        self.user_model_base_dir = self.app.config.get('USER_MODEL_BASE_DIR', 'user_models')
        if not os.path.exists(self.user_model_base_dir):
            os.makedirs(self.user_model_base_dir)

        self.user_loaded_models = {}
        self.user_model_management_locks = {}
        self._main_model_management_lock = Lock()

        self._user_model_last_access = {}
        self.model_max_idle_time_seconds = self.app.config.get('MODEL_MAX_IDLE_SECONDS', 15*60)
        self._cleanup_interval_seconds = self.app.config.get('MODEL_CLEANUP_INTERVAL_SECONDS', 60)
        self._stop_cleanup_event = Event()
        self._cleanup_thread = Thread(target=self._model_cleanup_task, name="ModelCleanupThread", daemon=True)  # 给线程命名
        self._cleanup_thread.start()

    def _update_model_last_access(self, user_id):
        """
        更新指定用户模型的最后访问时间戳。
        """
        self._user_model_last_access[user_id] = time.time()
        self.app.logger.debug(f"更新用户 {user_id} 模型最后访问时间。")

    def _get_user_model_management_lock(self, user_id):
        """
        获取或创建用户特定的模型管理锁。
        """
        with self._main_model_management_lock:
            if user_id not in self.user_model_management_locks:
                self.user_model_management_locks[user_id] = Lock()
            return self.user_model_management_locks[user_id]

    def _model_cleanup_task(self):
        self.app.logger.info("模型闲置清理后台线程已启动。")
        while not self._stop_cleanup_event.is_set():
            try:
                self.app.logger.debug("模型清理线程：开始检查闲置模型...")
                now = time.time()
                users_to_eject = []

                with self._main_model_management_lock:
                    last_access_copy = dict(self._user_model_last_access)
                    loaded_models_copy_keys = list(self.user_loaded_models.keys())

                for user_id in loaded_models_copy_keys:
                    last_access_time = last_access_copy.get(user_id)
                    if last_access_time is None:
                        self.app.logger.warning(f"用户 {user_id} 的模型已加载但无最后访问时间戳，可能需要处理。")
                        continue
                    if now - last_access_time > self.model_max_idle_time_seconds:
                        users_to_eject.append(user_id)

                if users_to_eject:
                    self.app.logger.info(f"模型清理线程：发现以下闲置用户模型待弹出: {users_to_eject}")

                for user_id_to_eject in users_to_eject:
                    user_lock = self._get_user_model_management_lock(user_id_to_eject)
                    with user_lock:
                        if user_id_to_eject in self.user_loaded_models:
                            current_last_access = self._user_model_last_access.get(user_id_to_eject, 0)
                            if now - current_last_access > self.model_max_idle_time_seconds:

                                self.app.logger.info(f"模型清理线程：为用户 {user_id_to_eject} 弹出闲置模型。")
                                model_info = self.user_loaded_models.get(user_id_to_eject)
                                if model_info:
                                    self._eject_model_internal(user_id_to_eject, model_info)
                                    if user_id_to_eject in self._user_model_last_access:
                                        del self._user_model_last_access[user_id_to_eject]

                                    self.app.logger.info(f"模型清理线程：用户 {user_id_to_eject} 的闲置模型已弹出。")
                            else:

                                self.app.logger.info(
                                    f"模型清理线程：用户 {user_id_to_eject} 的模型在准备弹出时被再次访问，取消弹出。")
                        else:
                            self.app.logger.info(
                                f"模型清理线程：用户 {user_id_to_eject} 的模型在准备弹出时已被其他操作弹出。")
            except Exception as e:
                self.app.logger.error(f"模型清理后台线程发生错误: {e}", exc_info=True)

            self._stop_cleanup_event.wait(timeout=self._cleanup_interval_seconds)

        self.app.logger.info("模型闲置清理后台线程已停止。")

    def shutdown_service(self):
        self.app.logger.info("请求停止 InferenceService 清理线程...")
        self._stop_cleanup_event.set()
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=self._cleanup_interval_seconds + 5)
            if self._cleanup_thread.is_alive():
                self.app.logger.warning("InferenceService 清理线程未能及时停止。")
        self.app.logger.info("InferenceService 清理线程已处理停止请求。")

    def _load_model_task(self, user_id, model_name, model_path):
        # 在新线程中，必须使用 app_context
        with self.app.app_context(): # <--- 关键：创建应用上下文
            try:
                self.app.logger.info(f"用户 {user_id} 模型加载线程：开始加载模型 {model_name} 从 {model_path}")
                model_instance = YoloModel(model_path)

                user_lock = self._get_user_model_management_lock(user_id)
                with user_lock:
                    current_task_info = self.user_loaded_models.get(user_id)
                    if current_task_info and \
                            current_task_info['model_name'] == model_name and \
                            current_task_info['status'] == 'loading':
                        self.user_loaded_models[user_id].update({
                            'model_instance': model_instance,
                            'status': 'loaded',
                            'load_thread': None,
                            'error_message': None
                        })
                        self._update_model_last_access(user_id)
                        self.app.logger.info(f"用户 {user_id} 模型加载线程：成功加载并缓存模型 {model_name}")
                    else:
                        self.app.logger.info(
                            f"用户 {user_id} 模型加载线程：模型 {model_name} 加载完成，但用户状态已改变或任务被取消，丢弃此实例。")
                        if 'model_instance' in locals() and model_instance is not None:
                            del model_instance

            except Exception as e:
                self.app.logger.error(f"用户 {user_id} 模型加载线程：加载模型 {model_name} 失败: {e}", exc_info=True)
                user_lock = self._get_user_model_management_lock(user_id)
                with user_lock:
                    current_task_info = self.user_loaded_models.get(user_id)
                    if current_task_info and \
                            current_task_info['model_name'] == model_name and \
                            current_task_info['status'] == 'loading':
                        self.user_loaded_models[user_id].update({
                            'status': 'error',
                            'error_message': str(e),
                            'load_thread': None,
                            'model_instance': None
                        })

    def _get_user_inference_model_dir(self, user_id):
        """获取指定用户用于推理的模型的存储目录路径"""
        user_inference_dir = os.path.join(self.user_model_base_dir, str(user_id), "inference_models")
        os.makedirs(user_inference_dir, exist_ok=True)
        return user_inference_dir

    def _get_safe_model_path(self, user_id, model_name):
        """获取用户模型文件的安全绝对路径，并执行安全检查"""
        if not model_name or '..' in model_name or '/' in model_name or '\\' in model_name:
            # 基本的文件名安全检查
            raise ValueError(f"无效的模型名称: {model_name}")

        user_model_dir = self._get_user_inference_model_dir(user_id)
        model_path = os.path.join(user_model_dir, model_name)

        # --- 关键安全检查 ---
        abs_model_path = os.path.abspath(model_path)
        abs_user_dir = os.path.abspath(user_model_dir)
        if not abs_model_path.startswith(abs_user_dir):
            self.app.logger.warning(f"安全警告：用户 {user_id} 尝试访问模型目录外的路径: {model_name} -> {abs_model_path}")
            raise PermissionError("禁止访问模型目录之外的路径")

        return abs_model_path

    def handle_command(self, user_id, command, data, files=None):
        """根据命令分发处理 (已更新以支持用户隔离和新命令)"""
        self.app.logger.info(f"Service Handling command '{command}' for user {user_id}")
        try:
            if command == "LoadModel":
                model_name = data.get("ModelName")
                # (路由层已检查 ModelName 存在)
                return self.load_model(user_id, model_name)

            elif command == "EjectModel":
                # 弹出用户当前选择的模型 (仅清除选择记录)
                return self.eject_model(user_id)

            elif command == "UploadPicture":
                # (路由层已检查 files 存在)
                return self.upload_picture(user_id, files)

            elif command == "UploadAtlas":
                # (路由层已检查 files 存在)
                return self.upload_picture(user_id, files)

            elif command == "Clear":
                return self.clear(user_id)

            elif command == "Start":
                config = data.get("config", {})  # 获取推理配置
                # 可以在这里合并用户存储的配置（如果实现了 UpdateConfig）
                # stored_config = self.user_session_manager.get_config(user_id)
                # merged_config = {**stored_config, **config} # data 中的 config 优先
                return self.start_inference(user_id, config)

            elif command == "GetModels":
                # 获取用户自己的模型列表
                return self.get_models(user_id)

            elif command == "DownloadOutcome":
                return self.download_outcome(user_id)

            # --- 新命令处理 ---
            elif command == "UploadModel":
                return self.upload_model(user_id, files)

            elif command == "DeleteModel":
                model_name = data.get("ModelName")
                return self.delete_model(user_id, model_name)

            elif command == "UpdateConfig":
                config_data = data.get("config")
                return self.update_config(user_id, config_data)

            else:
                self.app.logger.warning(f"收到未知命令 '{command}' from user {user_id}")
                return {"error": f"未知命令: {command}"}, 400

        except FileNotFoundError as e:
            self.app.logger.warning(f"处理命令 '{command}' 时文件未找到 (用户 {user_id}): {e}")
            return {"error": str(e)}, 404
        except PermissionError as e:
            self.app.logger.error(f"处理命令 '{command}' 时权限错误 (用户 {user_id}): {e}")
            return {"error": str(e)}, 403
        except ValueError as e:
            self.app.logger.warning(f"处理命令 '{command}' 时值错误 (用户 {user_id}): {e}")
            return {"error": str(e)}, 400
        except RuntimeError as e:  # 例如推理冲突（如果保留了某些并发检查）
            self.app.logger.error(f"处理命令 '{command}' 时运行时错误 (用户 {user_id}): {e}")
            return {"error": str(e)}, 500  # 或 409 Conflict
        except Exception as e:
            self.app.logger.error(f"处理命令 '{command}' 时发生未捕获异常 (用户 {user_id}): {e}", exc_info=True)
            return {"error": "处理请求时发生内部错误"}, 500

    def get_models(self, user_id):
        def format_bytes(size_bytes):
            """将字节数转换为人类可读的格式 (KB, MB, GB 等)"""
            if size_bytes is None or size_bytes < 0:
                return "N/A"  # 或者返回空字符串或 0 Bytes
            if size_bytes == 0:
                return "0 Bytes"
            # 定义单位后缀 (使用 1024 为基数，对应 KiB, MiB, GiB，但通常显示为 KB, MB, GB)
            suffixes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
            base = 1024.0
            # 计算合适的单位索引            # 使用 log 来确定数量级，floor 向下取整得到索引
            #             # 加一个小的 epsilon 防止 log(1024) 稍小于 1 导致错误

            index = 0
            if size_bytes > 0:  # 避免 log(0)
                index = math.floor(math.log(size_bytes + 1e-9, base))
                # 确保索引不超过我们定义的后缀列表长度
                index = min(index, len(suffixes) - 1)

            # 计算转换后的值
            value = size_bytes / (base ** index)

            # 格式化输出，Bytes 不需要小数，其他保留一位小数
            if index == 0:
                return f"{int(value)} {suffixes[index]}"
            else:
                # 使用 .1f 格式化为一位小数
                return f"{value:.1f} {suffixes[index]}"

        """获取指定用户的模型列表 (字节大小已格式化)"""
        self.app.logger.debug(f"Service: 开始为用户 {user_id} 获取模型列表")
        models = []
        try:
            user_model_dir = self._get_user_inference_model_dir(user_id)
            if not os.path.exists(user_model_dir):
                self.app.logger.info(f"用户 {user_id} 的模型目录不存在或无法访问: {user_model_dir}")
                return [], 200  # 返回空列表和成功状态码

            for filename in os.listdir(user_model_dir):
                allowed_extensions = tuple(self.app.config.get('ALLOWED_MODEL_EXTENSIONS', ['.pt', '.onnx']))
                if filename.lower().endswith(allowed_extensions):
                    filepath = os.path.join(user_model_dir, filename)
                    try:
                        stat = os.stat(filepath)
                        formatted_size = format_bytes(stat.st_size)
                        models.append({
                            "modelname": filename,
                            "datemodified": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime)),
                            "bytesize": formatted_size
                        })
                    except OSError as e:
                        self.app.logger.error(f"无法获取用户 {user_id} 的模型文件信息 {filepath}: {e}")
                        # 跳过这个文件，继续处理下一个
            self.app.logger.info(f"为用户 {user_id} 获取到 {len(models)} 个模型 (大小已格式化)")
            return models, 200

        except Exception as e:
            self.app.logger.error(f"在 Service 中为用户 {user_id} 获取模型列表失败: {e}", exc_info=True)
            return [], 500

    def load_model(self, user_id, model_name):
        user_lock = self._get_user_model_management_lock(user_id)
        with user_lock:
            self.app.logger.info(f"用户 {user_id} 请求加载模型: {model_name}")
            try:
                model_path = self._get_safe_model_path(user_id, model_name)
                if not os.path.isfile(model_path): raise FileNotFoundError(f"模型 '{model_name}' 未找到。")
            except (FileNotFoundError, PermissionError, ValueError) as e:
                self.app.logger.warning(f"用户 {user_id} 加载模型 {model_name} 失败: {e}"); raise

            current_model_info = self.user_loaded_models.get(user_id)
            if current_model_info:
                if current_model_info['model_name'] == model_name:
                    if current_model_info['status'] == 'loaded':
                        self.user_session_manager.set_selected_model(user_id, model_name)
                        self._update_model_last_access(user_id)
                        return {"message": f"模型 '{model_name}' 已加载。", "loadedModel": model_name}, 200
                    elif current_model_info['status'] == 'loading':
                        return {"message": f"模型 '{model_name}' 正在加载中。", "loadedModel": model_name}, 200
                    elif current_model_info['status'] == 'error':
                        self.app.logger.info(f"模型 '{model_name}' 上次加载失败，尝试重载。")
                else:
                    self.app.logger.info(
                        f"用户 {user_id} 加载新模型 {model_name}，弹出旧模型 {current_model_info['model_name']}.")
                    self._eject_model_internal(user_id, current_model_info)  # 内部弹出也会清理时间戳

            self.app.logger.info(f"用户 {user_id} 开始异步加载模型: {model_name} @ {model_path}")
            load_thread = Thread(target=self._load_model_task, args=(user_id, model_name, model_path));
            load_thread.daemon = True
            self.user_loaded_models[user_id] = {'model_name': model_name, 'model_instance': None,
                                                'load_thread': load_thread, 'status': 'loading', 'error_message': None}
            # 注意：此时模型还未加载完成，不在 load_model 中直接更新时间戳，而是在 _load_model_task 成功后更新
            load_thread.start()
            self.user_session_manager.set_selected_model(user_id, model_name)
            return {"message": f"模型 '{model_name}' 开始加载。", "loadedModel": model_name}, 200

    def _eject_model_internal(self, user_id, model_info_to_eject):
        model_name_to_eject = model_info_to_eject['model_name']
        self.app.logger.info(f"内部弹出用户 {user_id} 的模型: {model_name_to_eject}")

        if model_info_to_eject['status'] == 'loading':
            self.app.logger.info(f"模型 {model_name_to_eject} (用户 {user_id}) 加载中，标记取消。")
        elif model_info_to_eject['status'] == 'loaded':
            instance = model_info_to_eject.get('model_instance')
            if instance: self.app.logger.info(f"释放用户 {user_id} 模型实例: {model_name_to_eject}"); del instance

        if user_id in self.user_loaded_models and self.user_loaded_models[user_id]['model_name'] == model_name_to_eject:
            del self.user_loaded_models[user_id]

        if user_id in self._user_model_last_access:
            del self._user_model_last_access[user_id]
            self.app.logger.debug(f"清除了用户 {user_id} 的模型最后访问时间戳。")
        self.app.logger.info(f"用户 {user_id} 模型 {model_name_to_eject} 已从活动加载中移除。")

    def eject_model(self, user_id):
        user_lock = self._get_user_model_management_lock(user_id)
        with user_lock:
            self.app.logger.info(f"用户 {user_id} 请求弹出模型。")
            current_model_info = self.user_loaded_models.get(user_id)
            if not current_model_info:
                self.user_session_manager.clear_selected_model(user_id)

                if user_id in self._user_model_last_access: del self._user_model_last_access[user_id]
                return {"message": "无活动模型可弹出，已清选择。"}, 200

            model_name_to_eject = current_model_info['model_name']
            self._eject_model_internal(user_id, current_model_info)
            self.user_session_manager.clear_selected_model(user_id)
            return {"message": f"模型 '{model_name_to_eject}' 已请求弹出。"}, 200

    def upload_model(self, user_id, files):
        """处理用户上传模型文件"""
        user_model_dir = self._get_user_inference_model_dir(user_id)
        uploaded_model_names = []
        errors = []

        allowed_extensions = self.app.config.get('ALLOWED_MODEL_EXTENSIONS', ['.pt', '.onnx'])

        for file_storage in files:
            original_filename = file_storage.filename
            if not original_filename:
                errors.append("收到一个没有文件名的文件。")
                continue

            # 安全地获取文件名并检查后缀
            safe_filename = os.path.basename(original_filename)  # 移除路径部分
            _, ext = os.path.splitext(safe_filename)
            if ext.lower() not in allowed_extensions:
                errors.append(
                    f"文件 '{original_filename}' 的后缀 '{ext}' 不被允许。允许的后缀: {', '.join(allowed_extensions)}")
                continue
            if '..' in safe_filename or '/' in safe_filename or '\\' in safe_filename:
                errors.append(f"文件名 '{original_filename}' 包含不允许的字符。")
                continue

            # 构建目标路径
            dest_path = os.path.join(user_model_dir, safe_filename)

            try:
                # 可以添加文件大小限制检查
                # if file_storage.content_length > self.app.config.get('MAX_MODEL_SIZE', 1024*1024*500): # 500MB limit
                #     raise ValueError(f"文件 '{original_filename}' 太大。")

                file_storage.save(dest_path)
                uploaded_model_names.append(safe_filename)
                self.app.logger.info(f"用户 {user_id} 成功上传模型: {dest_path}")
            except Exception as e:
                self.app.logger.error(f"用户 {user_id} 上传模型 '{original_filename}' 到 {dest_path} 失败: {e}",
                                         exc_info=True)
                errors.append(f"上传文件 '{original_filename}' 失败: {e}")
                # 如果保存失败，尝试清理可能已创建的文件
                if os.path.exists(dest_path):
                    try:
                        os.remove(dest_path)
                    except OSError:
                        pass  # 忽略清理错误

        if errors:
            # 如果有错误，即使部分成功也可能返回失败状态
            error_message = "模型上传过程中发生错误: " + "; ".join(errors)
            # 可以根据需求决定状态码，例如 400 或 207 (Multi-Status)
            return {"error": error_message, "uploaded": uploaded_model_names}, 400
        elif not uploaded_model_names:
            # 没有文件被上传（可能都因为后缀或名称问题被拒绝）
            return {"error": "没有有效的模型文件被上传。"}, 400
        else:
            return {"message": f"成功上传 {len(uploaded_model_names)} 个模型: {', '.join(uploaded_model_names)}"}, 200

    def delete_model(self, user_id, model_name):
        """
        删除用户指定的模型文件。如果删除的是当前加载的模型，也需要将其从内存中弹出。
        """
        user_lock = self._get_user_model_management_lock(user_id)  # 获取锁以安全操作 user_loaded_models
        with user_lock:
            try:
                model_path = self._get_safe_model_path(user_id, model_name)
                if not os.path.isfile(model_path):
                    raise FileNotFoundError(f"模型文件 '{model_name}' 未找到。")

                # 检查是否是当前加载/正在加载的模型
                current_model_info = self.user_loaded_models.get(user_id)
                was_active_model = False
                if current_model_info and current_model_info['model_name'] == model_name:
                    self.app.logger.info(f"用户 {user_id} 删除的模型 {model_name} 是当前活动模型，将执行弹出。")
                    self._eject_model_internal(user_id, current_model_info)  # 内部弹出
                    was_active_model = True

                os.remove(model_path)  # 物理删除文件
                self.app.logger.info(f"用户 {user_id} 成功删除模型文件: {model_path}")

                # 如果删除的是会话中选择的模型，也清除该选择
                if self.user_session_manager.get_selected_model(user_id) == model_name:
                    self.user_session_manager.clear_selected_model(user_id)

                message = f"模型 '{model_name}' 已成功删除。"
                if was_active_model:
                    message += " 该模型也已从当前活动状态中卸载。"
                return {"message": message}, 200

            except (FileNotFoundError, PermissionError, ValueError) as e:
                raise e
            except Exception as e:
                self.app.logger.error(f"删除模型时发生意外错误 (用户 {user_id}, 模型 {model_name}): {e}",
                                         exc_info=True)
                raise RuntimeError("删除模型时发生内部错误")

    def clear(self, user_id):
        """清空用户上传的内容"""
        try:
            self.user_session_manager.clear_files(user_id)
            # 同时清除上次的结果
            self.user_session_manager.store_result(user_id, None)
            return {"message": "已清空上传的内容和结果。"}, 200
        except Exception as e:
            self.app.logger.error(f"用户 {user_id} 清空内容失败: {e}", exc_info=True)
            return {"error": "清空内容时出错"}, 500

    def start_inference(self, user_id, inference_config):
        """
        开始检测。结果现在包含JSON检测详情、绘制后图像的Base64编码，以及本次推理使用的配置。
        """
        self.app.logger.info(f"Service: 用户 {user_id} 开始推理, config: {inference_config}")

        uploaded_files_info = self.user_session_manager.get_uploaded_files(user_id)
        if not uploaded_files_info:
            raise ValueError("请先上传图片或图集")

        model_instance = None
        selected_model_name = "未知"

        user_lock = self._get_user_model_management_lock(user_id)
        with user_lock:
            user_model_data = self.user_loaded_models.get(user_id)
            if not user_model_data:
                session_selected = self.user_session_manager.get_selected_model(user_id)
                msg = f"模型 '{session_selected}' 已选但未加载/已弹出。请重载。" if session_selected else "请先LoadModel选择并加载模型。"
                raise ValueError(msg)
            selected_model_name = user_model_data['model_name']
            if user_model_data['status'] == 'loading': raise RuntimeError(
                f"模型 '{selected_model_name}' 加载中，请稍候。")
            if user_model_data['status'] == 'error': raise RuntimeError(
                f"模型 '{selected_model_name}' 加载失败: {user_model_data.get('error_message', '未知错误')}")
            if user_model_data['status'] == 'loaded':
                model_instance = user_model_data.get('model_instance')
                if not model_instance: raise RuntimeError(f"模型 '{selected_model_name}' 状态异常，实例为空。")
                self._update_model_last_access(user_id)  # --- 更新时间戳 ---
                self.app.logger.info(f"用户 {user_id} 推理：使用已加载模型 {selected_model_name}")
            else:
                raise RuntimeError(f"模型 '{selected_model_name}' 状态未知 ({user_model_data['status']})。")

        futures = []
        for idx, info in enumerate(uploaded_files_info):
            image_path = info['path']
            future = self.inference_executor.submit_inference(model_instance, image_path, inference_config)
            futures.append(future)

        processed_results_for_session = []  # 用于存储到 session 的结果
        processed_results_for_response = []  # 用于即时响应的结果，可能包含更少信息或不同结构

        self.app.logger.info(f"用户 {user_id} 的推理任务 ({len(futures)}个) 已提交，等待结果...")
        batch_start_time = time.perf_counter()

        try:
            timeout_seconds = self.app.config.get('INFERENCE_TIMEOUT', 300)
            for i, future in enumerate(futures):
                single_image_output = future.result(timeout=timeout_seconds)
                # single_image_output 结构:
                # {
                #   "json_result": {"detections": [...]},
                #   "annotated_image_base64": "data:...",
                #   "metrics": {"resolution": ..., "detection_time_ms": ..., ...},
                #   "error": "...", (如果发生错误)
                #   "image_path_when_error": "..." (如果发生错误)
                # }

                # 准备存储到session和响应的数据
                result_item = {
                    'original_filename': uploaded_files_info[i]['original_name'],
                    'json_detections': single_image_output.get('json_result', {}).get('detections', []),
                    # 直接取detections列表
                    'annotated_image_base64': single_image_output.get('annotated_image_base64'),
                    'metrics': single_image_output.get('metrics'),
                }
                if 'error' in single_image_output and single_image_output['error']:
                    result_item['error'] = single_image_output['error']

                processed_results_for_session.append(result_item)
                # 为了减少Start响应体大小，可以选择不在此处返回base64图像，仅在DownloadOutcome返回
                # processed_results_for_response.append({k:v for k,v in result_item.items() if k != 'annotated_image_base64'})
                processed_results_for_response.append(result_item)  # 当前版本：Start响应也包含完整结果

            self.app.logger.info(f"用户 {user_id} 的所有 ({len(futures)}个) 推理任务完成。")
        except TimeoutError:  # ... (超时处理同前) ...
            self.app.logger.warning(f"用户 {user_id} 推理任务超时 ({timeout_seconds}s)!")
            for f in futures:
                if not f.done(): f.cancel()
            raise RuntimeError(f"推理任务超时 (>{timeout_seconds}s)")
        except Exception as e:  # ... (其他异常处理同前) ...
            self.app.logger.error(f"等待推理结果时出错 (用户 {user_id}): {e}", exc_info=True)
            raise RuntimeError(f"处理推理结果时发生错误: {str(e)}")

        batch_end_time = time.perf_counter()
        total_batch_processing_time_ms = round((batch_end_time - batch_start_time) * 1000, 2)

        # --- 计算总体指标 ---
        num_successful_images = 0
        total_individual_detection_time_ms = 0
        total_objects_detected_in_batch = 0
        sum_of_average_confidences = 0  # 用于计算批次平均置信度
        num_images_with_detections = 0

        for res_item in processed_results_for_session:
            if 'error' not in res_item or not res_item['error']:
                num_successful_images += 1
                if res_item.get('metrics'):
                    total_individual_detection_time_ms += res_item['metrics'].get('detection_time_ms', 0)
                    obj_count = res_item['metrics'].get('object_count', 0)
                    total_objects_detected_in_batch += obj_count
                    if obj_count > 0:
                        sum_of_average_confidences += res_item['metrics'].get('average_confidence', 0)
                        num_images_with_detections += 1

        batch_average_confidence = 0
        if num_images_with_detections > 0:  # 仅在有检测到目标的图片中计算平均
            # 这里是平均每个图片平均置信度的平均值，也可以是所有目标置信度的总平均
            batch_average_confidence = round(sum_of_average_confidences / num_images_with_detections, 4)

        overall_metrics = {
            "total_images_requested": len(uploaded_files_info),
            "total_images_processed_successfully": num_successful_images,
            "batch_processing_time_ms": total_batch_processing_time_ms,  # 包含等待和实际推理
            "sum_of_individual_detection_time_ms": round(total_individual_detection_time_ms, 2),  # 仅成功图片的推理时间总和
            "total_objects_detected": total_objects_detected_in_batch,
            "average_objects_per_successful_image": round(total_objects_detected_in_batch / num_successful_images,
                                                          2) if num_successful_images > 0 else 0,
            "batch_average_confidence": batch_average_confidence,  # 基于成功检测到目标的图片的平均置信度
        }

        # 存储结果到会话 (processed_results_for_session 包含完整信息)
        # 存储时也包含 overall_metrics 和 inference_config_used，这样 DownloadOutcome 也能获取
        session_data_to_store = {
            "overall_metrics": overall_metrics,
            "inference_config_used": inference_config,
            "results_per_image": processed_results_for_session
        }
        self.user_session_manager.store_result(user_id, session_data_to_store)

        # 准备返回给客户端的响应
        response_payload = {
            "status": "success",
            "message": f"检测完成。成功处理 {num_successful_images}/{len(uploaded_files_info)} 张图片。",
            "overall_metrics": overall_metrics,
            "inference_config_used": inference_config,
            "results_per_image": processed_results_for_response  # Start响应中也返回每个图片的详细结果
        }

        has_errors = any('error' in r for r in processed_results_for_session)
        if has_errors:
            response_payload["message"] += " 注意：部分图片处理失败，请检查各结果中的 'error' 字段。"

        return response_payload, 200

    def download_outcome(self, user_id):
        """返回上次的检测结果"""
        stored_session_data = self.user_session_manager.get_result(user_id)
        if stored_session_data is None:
            return {"error": "没有可用的检测结果。请先执行 Start 命令。"}, 404

        # 返回 YOLO 标准 JSON 格式的结果
        return stored_session_data, 200

    def get_model_filepath(self, user_id, model_name):
        """获取用户模型文件的安全绝对路径，用于下载"""
        self.app.logger.debug(f"Service: 用户 {user_id} 请求模型文件路径: {model_name}")
        try:
            # 使用已有的安全路径获取和验证函数
            model_path = self._get_safe_model_path(user_id, model_name)

            if not os.path.isfile(model_path):
                self.app.logger.warning(f"下载请求：用户 {user_id} 的模型文件不存在: {model_path}")
                raise FileNotFoundError(f"模型文件 '{model_name}' 未找到。")

            self.app.logger.info(f"Service: 为用户 {user_id} 提供模型下载路径: {model_path}")
            return model_path  # 返回绝对路径

        except (FileNotFoundError, PermissionError, ValueError) as e:
            # 这些异常会被路由层的 try-except 捕获
            self.app.logger.warning(f"获取模型下载路径失败 (用户 {user_id}, 模型 {model_name}): {e}")
            raise e  # 重新抛出，让路由处理
        except Exception as e:
            self.app.logger.error(f"获取模型下载路径时发生意外错误 (用户 {user_id}, 模型 {model_name}): {e}",
                                     exc_info=True)
            # 抛出一个通用错误给路由层
            raise RuntimeError("获取模型路径时发生内部错误")

    def update_config(self, user_id, config_data):
        """更新用户的推理配置 (存储在 UserSessionManager 中)"""
        try:
            if not isinstance(config_data, dict):
                raise ValueError("配置数据必须是一个 JSON 对象。")

            # --- 存储配置 ---
            self.user_session_manager.store_config(user_id, config_data)
            self.app.logger.info(f"用户 {user_id} 的推理配置已更新。")
            return {"message": "推理配置已更新。"}, 200

        except ValueError as e:
            raise e
        except Exception as e:
            self.app.logger.error(f"更新配置时发生意外错误 (用户 {user_id}): {e}", exc_info=True)
            raise RuntimeError("更新配置时发生内部错误")

    def upload_picture(self, user_id, files):
        """处理图片上传"""
        self.app.logger.debug(f"Service: Handling UploadPicture for user {user_id}")
        try:
            # 使用 UserSessionManager 来存储文件
            stored_files = self.user_session_manager.store_uploaded_files(user_id, files)
            filenames = [info['original_name'] for info in stored_files]
            self.app.logger.info(f"用户 {user_id} 成功上传 {len(filenames)} 个图片文件。")
            return {
                "message": f"成功上传 {len(filenames)} 个文件: {', '.join(filenames)}",
                "uploaded_files": stored_files
                }, 200
        except Exception as e:
            self.app.logger.error(f"用户 {user_id} 上传图片文件失败: {e}", exc_info=True)
            # 抛出异常
            raise RuntimeError(f"上传文件失败: {e}")