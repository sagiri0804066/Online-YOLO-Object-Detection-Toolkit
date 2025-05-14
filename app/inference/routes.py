# app/inference/routes.py
from flask import request, jsonify, current_app, send_from_directory
from . import inference_bp
# from .services import InferenceService # 不再需要从这里导入 InferenceService 类本身，除非你想做类型提示
from typing import TYPE_CHECKING  # 用于类型提示
from ..utils.decorators import login_required
import os
import json

if TYPE_CHECKING:
    from .services import InferenceService  # 仅用于类型提示，避免循环导入


def get_inference_service() -> 'InferenceService':  # 使用字符串或 TYPE_CHECKING 进行类型提示
    """获取在 app 初始化时创建的 InferenceService 单例实例。"""
    if not hasattr(current_app, 'inference_service'):
        # 这种情况理论上不应该发生，如果 app 初始化正确
        current_app.logger.error("CRITICAL: InferenceService 未在 Flask App 上初始化！")
        raise RuntimeError("InferenceService 未在 Flask App 上正确初始化。")

    # 直接返回在 create_app 中附加的实例
    return current_app.inference_service


# --- API Endpoint (统一处理所有命令) ---
@inference_bp.route('/Inference', methods=['POST'])
@login_required
def handle_inference_command(user_id):
    """
    统一处理来自前端的所有命令式请求 (JSON 或 Multipart)。
    """
    # 现在 service 是共享的单例
    service = get_inference_service()  # <--- 现在获取的是正确的单例
    current_app.logger.info(f"用户 {user_id} 发起命令式请求 /Inference")
    command = None
    payload = {}
    files = None
    content_type = request.content_type

    # --- 1. 解析请求 ---
    if content_type is None:
        current_app.logger.warning(f"用户 {user_id} 的请求缺少 Content-Type")
        return jsonify({"error": "请求头缺少 'Content-Type'"}), 400

    try:
        if content_type.startswith('application/json'):
            # 处理 JSON 请求 (LoadModel, EjectModel, Clear, Start, DeleteModel, UpdateConfig)
            data = request.get_json()
            if not data:
                current_app.logger.warning(f"用户 {user_id} 发送了空的 JSON 请求体")
                return jsonify({"error": "请求体不能为空且必须是 JSON 格式"}), 400
            command = data.get('command')
            payload = data.get('data', {}) # data 字段的内容
            files = None # JSON 请求不包含文件
            current_app.logger.debug(f"收到 JSON 命令: {command}, payload: {payload}")

        elif content_type.startswith('multipart/form-data'):
            # 处理 Multipart 请求 (UploadPicture/Atlas, UploadModel)
            command = request.form.get('command')
            payload_str = request.form.get('data') # 附加数据（可选，看前端是否发送）
            if payload_str:
                try:
                    payload = json.loads(payload_str)
                except json.JSONDecodeError:
                    current_app.logger.warning(f"用户 {user_id} 表单中的 'data' 字段不是有效的 JSON: {payload_str}")
                    return jsonify({"error": "表单中的 'data' 字段不是有效的 JSON 字符串"}), 400

            # 获取文件，字段名必须是 'file' (与前端 uploadInferenceFile 对应)
            files = request.files.getlist('file')
            current_app.logger.debug(f"收到 Multipart 命令: {command}, payload: {payload}, 文件数: {len(files)}")
        else:
            current_app.logger.error(f"用户 {user_id} 使用了不支持的 Content-Type: {content_type}")
            return jsonify({"error": f"不支持的 Content-Type: {content_type}"}), 415

    except Exception as e:
        current_app.logger.error(f"解析用户 {user_id} 的请求时出错: {e}", exc_info=True)
        return jsonify({"error": "解析请求时发生错误"}), 400

    # --- 2. 基本命令有效性检查 ---
    if not command:
        current_app.logger.warning(f"用户 {user_id} 的请求中缺少 'command' 字段")
        return jsonify({"error": "请求中缺少 'command' 字段"}), 400

    # --- 3. 特定命令的输入验证 ---
    # 注意：这里只做基本验证，详细逻辑应在 service 层
    if command in ["UploadPicture", "UploadModel"]:
        if not files or all(f.filename == '' for f in files):
            current_app.logger.warning(f"用户 {user_id} 执行命令 '{command}' 但未提供有效文件")
            return jsonify({"error": f"命令 '{command}' 需要至少一个有效的 'file' 字段"}), 400
        # 对于 UploadModel，如果需要显式名称，可以在这里检查 payload['ModelName']
        # 但根据前端代码，它不发送，所以我们假设服务层会处理（例如从文件名推断）
        current_app.logger.info(f"命令 '{command}' 收到 {len(files)} 个文件。")

    elif command in ["LoadModel", "DeleteModel"]:
        if "ModelName" not in payload or not payload["ModelName"]:
            current_app.logger.warning(f"用户 {user_id} 执行命令 '{command}' 但缺少 'ModelName' 数据")
            return jsonify({"error": f"命令 '{command}' 需要在 'data' 字段中提供 'ModelName'"}), 400

    elif command == "UpdateConfig":
        if "config" not in payload: # 假设 config 是必需的
            current_app.logger.warning(f"用户 {user_id} 执行命令 '{command}' 但缺少 'config' 数据")
            return jsonify({"error": f"命令 '{command}' 需要在 'data' 字段中提供 'config'"}), 400

    # --- 4. 调用服务处理命令 ---
    current_app.logger.info(f"用户 {user_id} 准备执行命令: {command}")
    try:
        # 将解析到的 command, payload, files 传递给服务层
        # 服务层 (InferenceService.handle_command) 需要实现所有命令的处理逻辑
        response_data, status_code = service.handle_command(user_id, command, payload, files)

        current_app.logger.info(f"命令 '{command}' 处理完成，用户 {user_id}，状态码: {status_code}")

        # --- 5. 返回响应 ---
        # (处理响应部分保持与之前版本类似，根据 service 返回类型决定如何 jsonify)
        if isinstance(response_data, tuple) and len(response_data) == 2 and isinstance(response_data[1], int):
             return jsonify(response_data[0]), response_data[1]
        elif hasattr(response_data, 'is_sequence') and not isinstance(response_data, (str, bytes)):
             return jsonify(response_data), status_code
        elif isinstance(response_data, dict):
             return jsonify(response_data), status_code
        else: # 假设是 Response 对象
             return response_data, status_code

    except Exception as e:
        # 捕获 service.handle_command 可能抛出的未预料异常
        current_app.logger.error(f"处理命令 '{command}' 时发生未捕获异常 (用户 {user_id}): {e}", exc_info=True)
        return jsonify({"error": "处理请求时发生内部错误"}), 500


@inference_bp.route('/DownloadOutcome', methods=['GET'])
@login_required
def download_outcome_route(user_id):
    """获取用户最新的推理结果 (保持不变)"""
    service = get_inference_service()
    current_app.logger.info(f"用户 {user_id} 请求下载推理结果 /DownloadOutcome")
    try:
        response_data, status_code = service.download_outcome(user_id)
        # (处理响应部分保持不变)
        if isinstance(response_data, tuple) and len(response_data) == 2 and isinstance(response_data[1], int):
             return jsonify(response_data[0]), response_data[1]
        elif hasattr(response_data, 'is_sequence') and not isinstance(response_data, (str, bytes)):
             return jsonify(response_data), status_code
        elif isinstance(response_data, dict):
             return jsonify(response_data), status_code
        else:
             return response_data, status_code
    except Exception as e:
        current_app.logger.error(f"用户 {user_id} 下载结果失败: {e}", exc_info=True)
        return jsonify({"error": "获取结果时发生错误"}), 500


@inference_bp.route('/GetModels', methods=['GET'])
@login_required
def get_models_route(user_id):
     """获取当前用户可用的模型列表 (保持不变, 依赖 service 实现)"""
     service = get_inference_service()
     current_app.logger.info(f"用户 {user_id} 请求模型列表 /GetModels")
     try:
         models_list, status_code = service.get_models(user_id=user_id)
         current_app.logger.debug(f"为用户 {user_id} 获取到 {len(models_list)} 个模型")
         return jsonify(models_list), status_code
     except Exception as e:
         current_app.logger.error(f"为用户 {user_id} 获取模型列表失败: {e}", exc_info=True)
         return jsonify({"error": "获取模型列表时发生错误"}), 500


# --- 下载模型文件路由 ---
@inference_bp.route('/download_model', methods=['GET'])
@login_required
def download_model_route(user_id):
    """
    处理用户下载指定模型文件的请求。
    需要 'model' 查询参数。
    将文件路径获取和验证委托给服务层。
    """
    service = get_inference_service()
    model_name = request.args.get('model')
    current_app.logger.info(f"用户 {user_id} 请求下载模型文件: {model_name}")

    if not model_name:
        current_app.logger.warning(f"用户 {user_id} 下载模型请求缺少 'model' 查询参数")
        return jsonify({"error": "请求缺少 'model' 查询参数"}), 400

    try:
        # --- 1. 调用服务层获取安全的文件路径 ---
        # **你需要** 在 InferenceService 中实现 get_model_filepath 方法。
        # 此方法必须:
        #   - 根据 user_id 和 model_name 查找文件。
        #   - 验证 user_id 对该文件的访问权限 (文件是否在 user_id 的目录下)。
        #   - 进行路径安全检查 (防止路径遍历等)。
        #   - 如果验证通过，返回文件的【绝对路径】。
        #   - 如果文件未找到或无权访问，抛出异常 (例如 FileNotFoundError, PermissionError)。
        model_filepath = service.get_model_filepath(user_id, model_name)
        current_app.logger.debug(f"服务层返回模型文件路径: {model_filepath} (用户 {user_id})")

        # --- 2. 检查服务层返回的路径是否有效 (基本检查) ---
        # 服务层应该保证返回的是有效路径，但这里可以加一层防御
        if not model_filepath or not isinstance(model_filepath, str) or not os.path.isabs(model_filepath):
             current_app.logger.error(f"服务层为用户 {user_id} 模型 {model_name} 返回了无效路径: {model_filepath}")
             raise ValueError("服务层未能提供有效的模型文件路径。") # 或者更具体的内部错误

        # --- 3. 使用 send_from_directory 发送文件 ---
        # 从绝对路径中安全地分离目录和文件名
        directory = os.path.dirname(model_filepath)
        filename = os.path.basename(model_filepath) # 使用 basename 确保只取文件名部分

        current_app.logger.info(f"准备发送文件: 目录='{directory}', 文件名='{filename}' (用户 {user_id})")

        # 发送文件作为附件下载
        return send_from_directory(directory, filename, as_attachment=True, download_name=model_name)

    except FileNotFoundError:
        # 假设服务层在找不到文件时抛出 FileNotFoundError
        current_app.logger.warning(f"下载模型失败 (用户 {user_id}, 模型 {model_name}): 文件未找到")
        return jsonify({"error": f"模型文件 '{model_name}' 未找到。"}), 404
    except PermissionError:
        # 假设服务层在用户无权访问时抛出 PermissionError (或自定义的 ModelPermissionError)
        current_app.logger.warning(f"下载模型失败 (用户 {user_id}, 模型 {model_name}): 权限不足")
        return jsonify({"error": "无权下载此模型。"}), 403
    except ValueError as e:
        # 捕获上面添加的路径验证错误或其他服务层可能抛出的值错误
        current_app.logger.error(f"下载模型时发生值错误 (用户 {user_id}, 模型 {model_name}): {e}", exc_info=True)
        return jsonify({"error": f"处理下载请求时出错: {e}"}), 400 # 或 500
    except Exception as e:
        # 捕获其他所有未预料的异常
        current_app.logger.error(f"下载模型时发生未知错误 (用户 {user_id}, 模型 {model_name}): {e}", exc_info=True)
        return jsonify({"error": "下载模型时发生内部错误。"}), 500