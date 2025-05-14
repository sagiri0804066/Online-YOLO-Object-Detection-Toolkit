# app/ultralyticsCust/training.py
import os
import logging
from ultralytics import YOLO
from typing import List, Dict, Any, Tuple, Callable


# 假设 FinetuneProgressCallback 已经定义在 app.ultralyticsCust.callbacks
# from .callbacks import FinetuneProgressCallback # 如果在同一个包内

def run_yolo_training(
        model_path: str,  # 基础模型路径 (e.g., 'yolov8n.pt' or path to a .pt file)
        data_yaml_path: str,  # 数据集配置文件路径 (data.yaml)
        project_path: str,  # YOLO训练输出的根目录 (YOLO会在下面创建 name)
        run_name: str,  # YOLO训练运行的名称 (e.g., "train_run")
        training_params: Dict[str, Any],  # 包含 epochs, batch, device, patience, etc.
        callbacks_list: List[Callable] = None,  # 回调列表
        # log_file_path: str, # YOLOv8 会在 project_path/run_name 下自动生成日志，回调会处理日志
        logger: logging.Logger = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    执行 YOLO 模型微调训练。

    :param model_path: 基础模型的路径。
    :param data_yaml_path: 数据集配置文件的路径。
    :param project_path: 训练输出的根目录。
    :param run_name: 本次训练的名称，YOLO会在此目录下创建子目录。
    :param training_params: 训练参数字典。
    :param callbacks_list: YOLO训练回调列表。
    :param logger: 日志记录器。
    :return: (success_flag, message_or_error, results_dict)
             results_dict 包含最终模型路径等信息。
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        if not logger.hasHandlers():
            logger.addHandler(logging.StreamHandler())

    logger.info(f"开始 YOLO 训练: model={model_path}, data={data_yaml_path}, project={project_path}, name={run_name}")
    logger.info(f"训练参数: {training_params}")

    try:
        model = YOLO(model_path)

        # Ultralytics YOLOv8 的 train 方法参数
        # 常见参数: data, epochs, batch, imgsz, device, project, name, patience, optimizer, lr0, lrf, etc.
        # callbacks 会自动处理，无需显式传递给 train 方法，而是通过 model.add_callback()
        if callbacks_list:
            for event, cb_func in callbacks_list:  # Ultralytics 回调注册方式
                model.add_callback(event, cb_func)

        # 确保训练参数中的 device, epochs, batch 等被正确传递
        yolo_train_args = {
            'data': data_yaml_path,
            'project': project_path,
            'name': run_name,
            **training_params  # 解包用户传入的参数
        }

        # 确保 epochs 等关键参数存在且有效
        if 'epochs' not in yolo_train_args or not isinstance(yolo_train_args['epochs'], int) or yolo_train_args[
            'epochs'] <= 0:
            yolo_train_args['epochs'] = 10  # 设置一个默认值以防万一
            logger.warning(f"训练参数中 epochs 无效或未提供，使用默认值: {yolo_train_args['epochs']}")

        logger.info(f"传递给 YOLO.train() 的参数: {yolo_train_args}")

        results = model.train(**yolo_train_args)

        # 训练完成后，results 对象包含很多信息
        # 例如，results.save_dir 是实际的输出目录 project_path/run_name
        # results.best 是最佳模型的路径
        output_dir = results.save_dir
        best_model_path = str(results.best) if hasattr(results, 'best') and results.best else None
        last_model_path = os.path.join(output_dir, 'weights', 'last.pt')  # 通常是这个路径

        if not best_model_path and os.path.exists(last_model_path) and not os.path.exists(best_model_path):
            best_model_path = last_model_path  # 如果 best.pt 不知何故未记录，但 last.pt 存在

        if best_model_path and os.path.exists(best_model_path):
            logger.info(f"训练成功完成。最佳模型保存在: {best_model_path}")
            final_results = {
                "message": "训练成功完成。",
                "output_directory": str(output_dir),
                "best_model_path": str(best_model_path),
                "last_model_path": str(last_model_path) if os.path.exists(last_model_path) else None,
                # 可以从 results.metrics 或其他属性获取最终指标
                "final_metrics": results.metrics if hasattr(results, 'metrics') else {}
            }
            return True, "训练成功完成。", final_results
        elif os.path.exists(last_model_path):
            logger.warning(f"训练可能已完成，但最佳模型路径未明确找到。最后模型: {last_model_path}")
            final_results = {
                "message": "训练已完成，但最佳模型路径未明确记录，请检查输出目录。",
                "output_directory": str(output_dir),
                "last_model_path": str(last_model_path),
                "final_metrics": results.metrics if hasattr(results, 'metrics') else {}
            }
            return True, "训练已完成，但最佳模型路径未明确记录。", final_results
        else:
            logger.error(f"训练过程可能已执行，但未找到输出模型。输出目录: {output_dir}")
            return False, "训练过程可能已执行，但未找到输出模型。", {"output_directory": str(output_dir)}

    except Exception as e:
        logger.error(f"YOLO 训练过程中发生严重错误: {str(e)}", exc_info=True)
        return False, f"YOLO 训练失败: {str(e)}", {}
