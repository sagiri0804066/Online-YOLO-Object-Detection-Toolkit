import os
import json
from flask import request, jsonify, current_app, send_file
from . import finetune_bp
from ..utils.decorators import login_required

ALLOWED_EXTENSIONS_MODEL = {'pt'}
ALLOWED_EXTENSIONS_DATASET = {'zip'}
ALLOWED_EXTENSIONS_YAML = {'yaml', 'yml'}


def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in allowed_extensions


@finetune_bp.route('/tasks', methods=['POST'])
@login_required
def create_task_route(user_id):  # user_id 由 @login_required 注入
    # 1. 获取模型输入
    base_model_file = request.files.get('base_model_pt')
    preset_model_name = request.form.get('preset_model_name')

    if not base_model_file and not preset_model_name:
        return jsonify({
                           "error": "缺少基础模型输入。请提供 'base_model_pt' 文件或 'preset_model_name' 表单字段。"}), 400

    if base_model_file and (
            not base_model_file.filename or not allowed_file(base_model_file.filename, ALLOWED_EXTENSIONS_MODEL)):
        return jsonify({"error": "基础模型文件类型无效或缺少文件名。允许的类型: .pt"}), 400

    # 2. 校验数据集文件和yaml文件
    dataset_zip_file = request.files.get('dataset_zip')
    dataset_yaml_file = request.files.get('dataset_yaml')

    if not dataset_zip_file:
        return jsonify({"error": "缺少数据集文件。期望 'dataset_zip'。"}), 400
    if not dataset_yaml_file:
        return jsonify({"error": "缺少数据集配置文件。期望 'dataset_yaml'。"}), 400

    if not (dataset_zip_file.filename and allowed_file(dataset_zip_file.filename, ALLOWED_EXTENSIONS_DATASET)):
        return jsonify({"error": "数据集文件类型无效或缺少文件名，必须是 .zip 文件"}), 400
    if not (dataset_yaml_file.filename and allowed_file(dataset_yaml_file.filename, ALLOWED_EXTENSIONS_YAML)):
        return jsonify({"error": "数据集配置文件类型无效或缺少文件名，必须是 .yaml 或 .yml 文件"}), 400

    try:
        dataset_yaml_content = dataset_yaml_file.read().decode('utf-8')
    except Exception as e:
        current_app.logger.error(f"读取 dataset_yaml 文件失败，用户ID '{user_id}': {e}")
        return jsonify({"error": f"无法读取 dataset_yaml 文件: {str(e)}"}), 400

    # 3. 获取训练参数
    task_name = request.form.get('task_name')
    training_params_str = request.form.get('training_params', '{}')
    try:
        training_params = json.loads(training_params_str)
        if not isinstance(training_params, dict):
            raise ValueError("'training_params' 必须是一个 JSON 对象。")
    except json.JSONDecodeError:
        current_app.logger.error(f"用户ID '{user_id}' 的 training_params JSON无效: {training_params_str}")
        return jsonify({"error": "'training_params' 的 JSON 格式无效。"}), 400
    except ValueError as e:
        current_app.logger.error(f"用户ID '{user_id}' 的 training_params 验证错误: {e}")
        return jsonify({"error": str(e)}), 400

    # 4. 调用服务层创建任务
    finetune_service = current_app.finetune_service
    try:
        task_id_result, message = finetune_service.create_finetune_task(
            user_id=user_id,
            task_name=task_name,
            base_model_file_storage=base_model_file,
            preset_model_name=preset_model_name,
            dataset_zip_file_storage=dataset_zip_file,
            dataset_yaml_content=dataset_yaml_content,
            training_params=training_params
        )

        if task_id_result:
            current_app.logger.info(f"微调任务 '{task_id_result}' 已为用户ID '{user_id}' 成功创建。")
            return jsonify({"message": message, "task_id": task_id_result}), 201
        else:
            current_app.logger.error(f"为用户ID '{user_id}' 创建微调任务失败: {message}")
            # 根据服务层返回的中文消息调整判断逻辑
            if "预设模型" in message and ("未找到" in message or "无效" in message):
                return jsonify({"error": message}), 400
            elif "无效" in message or "缺失" in message or "未提供" in message: # 对应 "Invalid" 或 "Missing"
                return jsonify({"error": message}), 400
            return jsonify({"error": message}), 500

    except Exception as e:
        current_app.logger.error(f"用户ID '{user_id}' 创建微调任务期间发生异常: {str(e)}",
                                 exc_info=True)
        return jsonify({"error": "创建任务时发生意外错误。"}), 500


@finetune_bp.route('/tasks', methods=['GET'])
@login_required
def get_tasks_list_route(user_id):
    finetune_service = current_app.finetune_service
    tasks = finetune_service.get_user_tasks(user_id)
    return jsonify(tasks), 200


@finetune_bp.route('/tasks/<task_id>', methods=['GET'])
@login_required
def get_task_details_route(user_id, task_id):
    finetune_service = current_app.finetune_service
    task_details = finetune_service.get_task_details(user_id, task_id)
    if task_details:
        if task_details.get("error"): # 例如用户找不到，服务层返回错误对象 (服务层目前不直接返回error key，而是None)
            return jsonify(task_details), 404
        return jsonify(task_details), 200
    else:
        # 服务层返回 None 时，表示任务未找到或无权访问
        return jsonify({"error": "任务未找到或访问被拒绝"}), 404


@finetune_bp.route('/tasks/<task_id>/logs', methods=['GET'])
@login_required
def get_task_logs_route(user_id, task_id):
    tail_str = request.args.get('tail', None)
    tail_lines = None
    if tail_str:
        try:
            tail_lines = int(tail_str)
            if tail_lines <= 0: tail_lines = None
        except ValueError:
            current_app.logger.warning(
                f"用户ID '{user_id}' 的任务 '{task_id}' 收到无效的 'tail' 参数: {tail_str}")
            tail_lines = None

    finetune_service = current_app.finetune_service
    log_content, error = finetune_service.get_task_logs_content(user_id, task_id,
                                                                tail_lines=tail_lines)

    response_data = {"task_id": task_id, "logs": log_content if log_content else ""}
    if error:
        response_data["error"] = error
        # 根据前端JS的逻辑，它期望即使有错误 (如404)，logs字段也存在
        # 前端JS: const errorMessage = responseData.error || `HTTP 错误! 状态: ${response.status}`;
        # 后端日志接口即使404也可能返回JSON {"error": "...", "logs": ""}
        if "未找到" in error or "尚未创建" in error: # 检查中文错误信息
            return jsonify(response_data), 404  # 日志文件未找到
        return jsonify(response_data), 500  # 其他服务器错误

    return jsonify(response_data), 200


@finetune_bp.route('/tasks/<task_id>/output', methods=['GET'])
@login_required
def download_task_output_route(user_id, task_id):
    finetune_service = current_app.finetune_service
    archive_path, error_msg = finetune_service.get_task_output_archive_path(user_id, task_id)

    if error_msg:
        # 前端JS: throw new Error(errorMessage);
        # 所以后端返回的JSON中需要有error字段
        status_code = 404 if "未找到" in error_msg or "尚不可用" in error_msg else 500 # 检查中文错误信息
        return jsonify({"error": error_msg}), status_code

    if archive_path and os.path.exists(archive_path):
        try:
            return send_file(
                archive_path,
                as_attachment=True,
                download_name=os.path.basename(archive_path), # 注意: send_file 使用 download_name 参数指定下载文件名
                mimetype='application/zip'
            )
        except Exception as e:
            current_app.logger.error(
                f"为用户ID '{user_id}' 的任务 '{task_id}' 发送输出归档 {archive_path} 时出错: {e}")
            return jsonify({"error": "无法发送归档文件。"}), 500
    else:
        # 此处情况理论上应该被 error_msg 覆盖，但作为双重保险
        return jsonify({"error": "输出归档未找到或无法创建。"}), 404


@finetune_bp.route('/tasks/<task_id>/cancel', methods=['POST'])
@login_required
def cancel_task_route(user_id, task_id):
    finetune_service = current_app.finetune_service
    success, message = finetune_service.cancel_finetune_task(user_id, task_id)
    if success:
        return jsonify({"message": message, "task_id": task_id}), 200
    else:
        # 前端JS: const errorMessage = responseData.error || `HTTP 错误! 状态: ${response.status}`;
        status_code = 404 if "未找到" in message else 400 # 检查中文错误信息
        return jsonify({"error": message, "task_id": task_id}), status_code


@finetune_bp.route('/tasks/<task_id>/delete', methods=['DELETE'])
@login_required
def delete_task_route(user_id, task_id):
    finetune_service = current_app.finetune_service
    current_app.logger.info(f"用户ID '{user_id}' 正在尝试删除微调任务 '{task_id}'。")
    try:
        success, message = finetune_service.delete_finetune_task(user_id, task_id)
        if success:
            current_app.logger.info(f"用户ID '{user_id}' 的微调任务 '{task_id}' 已成功删除。")
            # 前端JS期望: return responseData; // 应包含 { message: "...", task_id: "..." }
            # 或: return { message: `任务 ${taskId} 已成功删除...`, task_id: taskId };
            return jsonify({"message": message, "task_id": task_id}), 200  # 200 OK 带响应体
        else:
            current_app.logger.warning(f"为用户ID '{user_id}' 删除微调任务 '{task_id}' 失败: {message}")
            status_code = 400 # 默认为错误请求
            # 检查中文错误信息
            if "未找到" in message or "不存在" in message or "访问被拒绝" in message:
                status_code = 404
            elif "正在运行" in message: # 对应 "cannot be deleted while running"
                status_code = 409  # Conflict
            return jsonify({"error": message, "task_id": task_id}), status_code
    except Exception as e:
        current_app.logger.error(f"为用户ID '{user_id}' 删除任务 '{task_id}' 期间发生异常: {str(e)}",
                                 exc_info=True)
        return jsonify({"error": "删除任务时发生意外错误。"}), 500