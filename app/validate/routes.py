# app/validate/routes.py
import os
import json
# from functools import wraps # No longer needed if using the shared decorator
from flask import request, jsonify, current_app, session, send_file # Keep session for username if needed for logging
from werkzeug.utils import secure_filename
from . import validate_bp
from ..utils.decorators import login_required

# ALLOWED_EXTENSIONS 保持不变
ALLOWED_EXTENSIONS_MODEL = {'pt'}
ALLOWED_EXTENSIONS_DATASET = {'zip'}
ALLOWED_EXTENSIONS_YAML = {'yaml', 'yml'}


def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions


@validate_bp.route('/tasks', methods=['POST'])
@login_required # 这个装饰器现在应该会注入 user_id
def create_validation_task_route(user_id): # <--- 接收 user_id 参数
    # username = session.get('username') # 仍然可以获取 username 用于日志等

    current_app.logger.info(f"用户ID '{user_id}' 正在尝试创建验证任务。")

    # --- 1. 获取任务基本信息 ---
    task_name = request.form.get('task_name', None)
    validation_params_str = request.form.get('validation_params', '{}')
    try:
        validation_params_input = json.loads(validation_params_str)
        if not isinstance(validation_params_input, dict):
            raise ValueError("validation_params must be a JSON object")
    except json.JSONDecodeError:
        current_app.logger.error(f"用户ID '{user_id}' 的 validation_params JSON无效: {validation_params_str}")
        return jsonify({"error": "Invalid JSON in validation_params"}), 400
    except ValueError as e:
        current_app.logger.error(f"用户ID '{user_id}' 的 validation_params 验证错误: {e}")
        return jsonify({"error": str(e)}), 400

    # --- 2. 处理模型来源 ---
    model_source_type = request.form.get('model_source_type')
    model_to_validate_fs = None
    model_identifier_for_service = None # 初始化

    if model_source_type == 'upload':
        if 'model_file_upload' not in request.files:
            return jsonify({"error": "Missing model_file_upload for 'upload' source type"}), 400
        model_to_validate_fs = request.files['model_file_upload']
        if not (model_to_validate_fs.filename and allowed_file(model_to_validate_fs.filename, ALLOWED_EXTENSIONS_MODEL)):
            return jsonify({"error": "Invalid model file type for validation model upload"}), 400
        # 为上传的模型设置一个标识符，例如使用安全的文件名
        model_identifier_for_service = f"upload:{secure_filename(model_to_validate_fs.filename)}"
    elif model_source_type == 'inference_model':
        inference_model_name = request.form.get('inference_model_name')
        if not inference_model_name:
            return jsonify({"error": "Missing inference_model_name for 'inference_model' source type"}), 400
        model_identifier_for_service = f"inference:{secure_filename(inference_model_name)}"
    elif model_source_type == 'finetune_output':
        finetune_task_id = request.form.get('finetune_task_id_for_model')
        model_type = request.form.get('finetune_model_type', 'best.pt')
        if not finetune_task_id:
            return jsonify({"error": "Missing finetune_task_id_for_model for 'finetune_output' source type"}), 400
        model_identifier_for_service = f"finetune:{secure_filename(finetune_task_id)}:{secure_filename(model_type)}"
    else:
        return jsonify({"error": "Invalid or missing model_source_type. Expected 'upload', 'inference_model', or 'finetune_output'."}), 400

    # --- 3. 处理数据集来源 ---
    dataset_source_type = request.form.get('dataset_source_type')
    dataset_zip_file_storage = None
    dataset_yaml_content = None
    dataset_identifier_for_service = None

    if dataset_source_type == 'upload':
        if 'dataset_zip_upload' not in request.files or 'dataset_yaml_upload' not in request.files:
            return jsonify({"error": "Missing dataset_zip_upload or dataset_yaml_upload for 'upload' dataset type"}), 400
        dataset_zip_file_storage = request.files['dataset_zip_upload']
        dataset_yaml_file = request.files['dataset_yaml_upload']
        if not (dataset_zip_file_storage.filename and allowed_file(dataset_zip_file_storage.filename, ALLOWED_EXTENSIONS_DATASET)):
            return jsonify({"error": "Invalid dataset zip file type for validation"}), 400
        if not (dataset_yaml_file.filename and allowed_file(dataset_yaml_file.filename, ALLOWED_EXTENSIONS_YAML)):
            return jsonify({"error": "Invalid dataset config file type for validation"}), 400
        try:
            dataset_yaml_content = dataset_yaml_file.read().decode('utf-8')
        except Exception as e:
            current_app.logger.error(f"读取 dataset_yaml_upload 文件失败，用户ID '{user_id}': {e}")
            return jsonify({"error": f"Could not read dataset_yaml for validation: {str(e)}"}), 400
        dataset_identifier_for_service = "upload"
    elif dataset_source_type == 'finetune_val_set':
        finetune_task_id_for_dataset = request.form.get('finetune_task_id_for_dataset')
        if not finetune_task_id_for_dataset:
            return jsonify({"error": "Missing finetune_task_id_for_dataset for 'finetune_val_set' dataset type"}), 400
        dataset_identifier_for_service = f"finetune_val:{secure_filename(finetune_task_id_for_dataset)}"
    elif dataset_source_type == 'preset_dataset':
        preset_dataset_name = request.form.get('preset_dataset_name')
        if not preset_dataset_name:
            return jsonify({"error": "Missing preset_dataset_name for 'preset_dataset' type"}), 400
        dataset_identifier_for_service = f"preset_ds:{secure_filename(preset_dataset_name)}"
    # else: # 如果数据集是可选的，这里可能不需要报错
    #    dataset_identifier_for_service = None # 或其他表示可选的标记

    if not dataset_identifier_for_service and model_source_type != 'some_type_with_builtin_data': # 明确要求数据集来源
        return jsonify({"error": "Invalid or missing dataset_source_type. Dataset is required."}), 400


    # --- 4. 合并验证参数 ---
    default_validation_params = {
        "imgsz": 640, "batch": 32, "conf": 0.001, "iou": 0.6,
        "save_json": True, "save_hybrid": False, "plots": True
    }
    final_validation_params = {**default_validation_params, **validation_params_input}

    # --- 5. 调用服务层 ---
    validate_service = current_app.validate_service
    try:
        task_id_result, message = validate_service.create_validate_task(
            user_id=user_id,  # <--- 使用注入的 user_id
            task_name=task_name,
            model_identifier=model_identifier_for_service, # 服务层会根据这个解析
            model_file_storage_if_upload=model_to_validate_fs, # 仅当 model_source_type=='upload' 时有值
            dataset_identifier=dataset_identifier_for_service, # 服务层会根据这个解析
            dataset_zip_file_storage_if_upload=dataset_zip_file_storage, # 仅当 dataset_source_type=='upload' 时有值
            dataset_yaml_content_if_upload=dataset_yaml_content, # 仅当 dataset_source_type=='upload' 时有值
            validation_params=final_validation_params
        )

        if task_id_result:
            current_app.logger.info(f"验证任务 '{task_id_result}' 已为用户ID '{user_id}' 成功创建。")
            return jsonify({"message": message, "task_id": task_id_result}), 201
        else:
            current_app.logger.error(f"为用户ID '{user_id}' 创建验证任务失败: {message}")
            status_code = 500
            if "未找到" in message.lower() or "无效" in message.lower() or "缺失" in message.lower():
                status_code = 400
            return jsonify({"error": message}), status_code
    except Exception as e:
        current_app.logger.error(f"用户ID '{user_id}' 创建验证任务期间发生异常: {str(e)}", exc_info=True)
        return jsonify({"error": "创建验证任务时发生意外错误。"}), 500


@validate_bp.route('/tasks', methods=['GET'])
@login_required
def get_validation_tasks_list_route(user_id): # <--- 接收 user_id 参数
    validate_service = current_app.validate_service
    tasks = validate_service.get_user_tasks(user_id) # <--- 传递 user_id
    return jsonify(tasks), 200


@validate_bp.route('/tasks/<task_id>', methods=['GET'])
@login_required
def get_validation_task_details_route(user_id, task_id): # <--- 接收 user_id 参数
    validate_service = current_app.validate_service
    task_details = validate_service.get_task_details(user_id, task_id) # <--- 传递 user_id
    if task_details:
        if task_details.get("error"): # 服务层通常不返回 error key，而是 None
             return jsonify(task_details), 404 # 假设 error 表示未找到
        return jsonify(task_details), 200
    else:
        return jsonify({"error": "验证任务未找到或访问被拒绝"}), 404


@validate_bp.route('/tasks/<task_id>/logs', methods=['GET'])
@login_required
def get_validation_task_logs_route(user_id, task_id): # <--- 接收 user_id 参数
    tail_str = request.args.get('tail', None)
    tail_lines = None
    if tail_str:
        try:
            tail_lines = int(tail_str)
            if tail_lines <= 0: tail_lines = None
        except ValueError:
            current_app.logger.warning(f"用户ID '{user_id}' 的验证任务 '{task_id}' 收到无效的 'tail' 参数: {tail_str}")
            tail_lines = None

    validate_service = current_app.validate_service
    log_content, error = validate_service.get_task_logs_content(user_id, task_id, tail_lines=tail_lines) # <--- 传递 user_id

    response_data = {"task_id": task_id, "logs": log_content if log_content else ""}
    if error:
        response_data["error"] = error
        if "未找到" in error or "尚未创建" in error:
             return jsonify(response_data), 404
        return jsonify(response_data), 500

    return jsonify(response_data), 200


@validate_bp.route('/tasks/<task_id>/output', methods=['GET'])
@login_required
def download_validation_task_output_route(user_id, task_id): # <--- 接收 user_id 参数
    validate_service = current_app.validate_service
    archive_path, error_msg = validate_service.get_task_output_archive_path(user_id, task_id) # <--- 传递 user_id

    if error_msg:
        status_code = 404 if "未找到" in error_msg or "尚不可用" in error_msg else 500
        return jsonify({"error": error_msg}), status_code

    if archive_path and os.path.exists(archive_path):
        try:
            return send_file(
                archive_path,
                as_attachment=True,
                download_name=os.path.basename(archive_path),
                mimetype='application/zip'
            )
        except Exception as e:
            current_app.logger.error(f"为用户ID '{user_id}' 的验证任务 '{task_id}' 发送输出归档 {archive_path} 时出错: {e}")
            return jsonify({"error": "无法发送验证归档文件。"}), 500
    else:
        return jsonify({"error": "验证输出归档未找到或无法创建。"}), 404


@validate_bp.route('/tasks/<task_id>/cancel', methods=['POST'])
@login_required
def cancel_validation_task_route(user_id, task_id):
    validate_service = current_app.validate_service
    current_app.logger.info(f"用户ID '{user_id}' 正在尝试取消验证任务 '{task_id}'。")
    try:
        success, message = validate_service.cancel_validate_task(user_id, task_id) # <--- 传递 user_id
        if success:
            current_app.logger.info(f"用户ID '{user_id}' 的验证任务 '{task_id}' 取消请求已处理。")
            return jsonify({"message": message, "task_id": task_id}), 200
        else:
            current_app.logger.warning(f"为用户ID '{user_id}' 取消验证任务 '{task_id}' 失败: {message}")
            status_code = 400 # Bad Request by default
            if "未找到" in message.lower() or "不存在" in message.lower():
                status_code = 404 # Not Found
            elif "无法取消" in message.lower() or "状态不正确" in message.lower():
                status_code = 409 # Conflict (e.g., already completed)
            return jsonify({"error": message, "task_id": task_id}), status_code
    except Exception as e:
        current_app.logger.error(f"为用户ID '{user_id}' 取消验证任务 '{task_id}' 期间发生异常: {str(e)}", exc_info=True)
        return jsonify({"error": "取消验证任务时发生意外错误。"}), 500


@validate_bp.route('/tasks/<task_id>/delete', methods=['DELETE'])
@login_required
def delete_validation_task_route(user_id, task_id): # <--- 接收 user_id 参数
    validate_service = current_app.validate_service
    current_app.logger.info(f"用户ID '{user_id}' 正在尝试删除验证任务 '{task_id}'。")
    try:
        success, message = validate_service.delete_validate_task(user_id, task_id) # <--- 传递 user_id
        if success:
            current_app.logger.info(f"用户ID '{user_id}' 的验证任务 '{task_id}' 已成功删除。")
            return jsonify({"message": message, "task_id": task_id}), 200
        else:
            current_app.logger.warning(f"为用户ID '{user_id}' 删除验证任务 '{task_id}' 失败: {message}")
            status_code = 400
            if "未找到" in message or "不存在" in message or "访问被拒绝" in message:
                status_code = 404
            elif "正在运行" in message:
                status_code = 409
            return jsonify({"error": message, "task_id": task_id}), status_code
    except Exception as e:
        current_app.logger.error(f"为用户ID '{user_id}' 删除验证任务 '{task_id}' 期间发生异常: {str(e)}", exc_info=True)
        return jsonify({"error": "删除验证任务时发生意外错误。"}), 500